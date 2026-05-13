"""Tests for cost analytics endpoints (issue #557).

Covers:
- GET /api/v2/costs/summary returns zero-state when no data
- GET /api/v2/costs/summary aggregates token_usage into daily buckets
- days query param is bounded to [7, 90]
- Default days is 30
"""

import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2


def _ensure_token_usage_table(db_path: Path) -> None:
    """Create token_usage on the workspace DB without invoking SchemaManager.

    The router opens the workspace DB directly and tolerates the table
    being absent. Tests that exercise real data need to create the table
    inline to mirror what an agent run would produce.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                actual_cost_usd REAL,
                call_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT DEFAULT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)

    yield workspace

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import costs_v2

    app = FastAPI()
    app.include_router(costs_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace
    client = TestClient(app)
    client.workspace = test_workspace
    return client


def _record_usage(workspace, *, task_id=1, cost=0.10, when=None):
    _ensure_token_usage_table(workspace.db_path)
    timestamp = (when or datetime.now(timezone.utc)).isoformat()
    conn = sqlite3.connect(str(workspace.db_path))
    try:
        conn.execute(
            """
            INSERT INTO token_usage (
                task_id, agent_id, project_id, model_name,
                input_tokens, output_tokens, estimated_cost_usd,
                call_type, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, "agent-001", 1, "claude-sonnet-4-5",
             100, 50, cost, "task_execution", timestamp),
        )
        conn.commit()
    finally:
        conn.close()


class TestCostsSummaryEmpty:
    def test_returns_zero_state(self, test_client):
        response = test_client.get("/api/v2/costs/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["total_spend_usd"] == 0.0
        assert body["total_tasks"] == 0
        assert body["avg_cost_per_task"] == 0.0
        assert isinstance(body["daily"], list)
        assert len(body["daily"]) == 30


class TestCostsSummaryWithData:
    def test_aggregates_token_usage(self, test_client):
        _record_usage(test_client.workspace, task_id=1, cost=0.50)
        _record_usage(test_client.workspace, task_id=1, cost=0.25)

        response = test_client.get("/api/v2/costs/summary?days=30")
        assert response.status_code == 200
        body = response.json()
        assert body["total_spend_usd"] == pytest.approx(0.75)
        assert body["total_tasks"] == 1
        assert body["avg_cost_per_task"] == pytest.approx(0.75)

    def test_daily_series_length_matches_days(self, test_client):
        _record_usage(test_client.workspace, task_id=1, cost=0.10)
        response = test_client.get("/api/v2/costs/summary?days=7")
        assert response.status_code == 200
        body = response.json()
        assert len(body["daily"]) == 7
        for entry in body["daily"]:
            assert "date" in entry
            assert "cost_usd" in entry


class TestDaysValidation:
    def test_below_minimum_rejected(self, test_client):
        response = test_client.get("/api/v2/costs/summary?days=3")
        assert response.status_code == 422

    def test_above_maximum_rejected(self, test_client):
        response = test_client.get("/api/v2/costs/summary?days=365")
        assert response.status_code == 422

    def test_default_is_30(self, test_client):
        response = test_client.get("/api/v2/costs/summary")
        assert response.status_code == 200
        assert len(response.json()["daily"]) == 30

    @pytest.mark.parametrize("days", [7, 30, 90])
    def test_valid_ranges_accepted(self, test_client, days):
        response = test_client.get(f"/api/v2/costs/summary?days={days}")
        assert response.status_code == 200
        assert len(response.json()["daily"]) == days
