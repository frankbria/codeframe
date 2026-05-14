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
from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# /api/v2/costs/tasks (Issue #558)
# ---------------------------------------------------------------------------


def _record_usage_text_task(
    workspace, *, task_id, cost=0.10, agent_id="react-agent",
    input_tokens=100, output_tokens=50, when=None,
):
    """Insert a token_usage record with a TEXT (v2 UUID) task_id."""
    _ensure_token_usage_table(workspace.db_path)
    timestamp = (when or datetime.now(timezone.utc)).isoformat()
    conn = sqlite3.connect(str(workspace.db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            """
            INSERT INTO token_usage (
                task_id, agent_id, project_id, model_name,
                input_tokens, output_tokens, estimated_cost_usd,
                call_type, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, agent_id, 1, "claude-sonnet-4-5",
             input_tokens, output_tokens, cost, "task_execution", timestamp),
        )
        conn.commit()
    finally:
        conn.close()


class TestCostsTasksEmpty:
    def test_returns_empty_list(self, test_client):
        response = test_client.get("/api/v2/costs/tasks")
        assert response.status_code == 200
        body = response.json()
        assert body == {"tasks": []}


class TestCostsTasksWithData:
    def test_returns_top_tasks_with_titles(self, test_client):
        """Tasks present in the workspace are joined to their titles."""
        from codeframe.core import tasks as tasks_module

        workspace = test_client.workspace
        task = tasks_module.create(
            workspace, title="Implement search", description="..."
        )
        _record_usage_text_task(workspace, task_id=task.id, cost=0.50)
        _record_usage_text_task(workspace, task_id=task.id, cost=0.25)

        response = test_client.get("/api/v2/costs/tasks")
        assert response.status_code == 200
        tasks_list = response.json()["tasks"]
        assert len(tasks_list) == 1
        entry = tasks_list[0]
        assert entry["task_id"] == task.id
        assert entry["task_title"] == "Implement search"
        assert entry["agent_id"] == "react-agent"
        assert entry["input_tokens"] == 200
        assert entry["output_tokens"] == 100
        assert entry["total_cost_usd"] == pytest.approx(0.75)

    def test_missing_task_falls_back_to_placeholder_title(self, test_client):
        """When token_usage references a task that no longer exists,
        the response still includes the row with a synthesized title."""
        workspace = test_client.workspace
        _record_usage_text_task(workspace, task_id="orphan-uuid", cost=0.10)

        response = test_client.get("/api/v2/costs/tasks")
        body = response.json()
        assert len(body["tasks"]) == 1
        assert body["tasks"][0]["task_id"] == "orphan-uuid"
        assert "orphan-uu" in body["tasks"][0]["task_title"].lower() or \
               "unknown" in body["tasks"][0]["task_title"].lower()

    def test_caps_at_10_tasks(self, test_client):
        from codeframe.core import tasks as tasks_module
        workspace = test_client.workspace
        for i in range(15):
            t = tasks_module.create(workspace, title=f"T{i}", description="")
            _record_usage_text_task(workspace, task_id=t.id, cost=0.01 * (i + 1))

        response = test_client.get("/api/v2/costs/tasks")
        assert len(response.json()["tasks"]) == 10

    def test_days_param_filters_window(self, test_client):
        from codeframe.core import tasks as tasks_module
        workspace = test_client.workspace
        t = tasks_module.create(workspace, title="Recent", description="")
        now = datetime.now(timezone.utc)
        _record_usage_text_task(workspace, task_id=t.id, cost=0.10, when=now)
        _record_usage_text_task(
            workspace, task_id=t.id, cost=99.0,
            when=now - timedelta(days=60),
        )

        response = test_client.get("/api/v2/costs/tasks?days=30")
        assert response.json()["tasks"][0]["total_cost_usd"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# /api/v2/costs/by-agent (Issue #558)
# ---------------------------------------------------------------------------


class TestCostsByAgentEmpty:
    def test_returns_zero_state(self, test_client):
        response = test_client.get("/api/v2/costs/by-agent")
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "by_agent": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }


class TestCostsByAgentWithData:
    def test_aggregates_by_agent(self, test_client):
        workspace = test_client.workspace
        _record_usage_text_task(
            workspace, task_id="t1", agent_id="claude-code",
            cost=0.30, input_tokens=100, output_tokens=50,
        )
        _record_usage_text_task(
            workspace, task_id="t1", agent_id="claude-code",
            cost=0.20, input_tokens=200, output_tokens=100,
        )
        _record_usage_text_task(
            workspace, task_id="t2", agent_id="codex",
            cost=0.10, input_tokens=50, output_tokens=25,
        )

        response = test_client.get("/api/v2/costs/by-agent")
        body = response.json()

        assert body["total_input_tokens"] == 350
        assert body["total_output_tokens"] == 175

        agents = body["by_agent"]
        assert len(agents) == 2
        assert agents[0]["agent_id"] == "claude-code"
        assert agents[0]["total_cost_usd"] == pytest.approx(0.50)
        assert agents[0]["call_count"] == 2
        assert agents[1]["agent_id"] == "codex"


class TestCostsTasksDaysValidation:
    def test_below_minimum_rejected(self, test_client):
        response = test_client.get("/api/v2/costs/tasks?days=0")
        assert response.status_code == 422

    def test_above_maximum_rejected(self, test_client):
        response = test_client.get("/api/v2/costs/tasks?days=400")
        assert response.status_code == 422

    def test_by_agent_below_minimum_rejected(self, test_client):
        response = test_client.get("/api/v2/costs/by-agent?days=0")
        assert response.status_code == 422
