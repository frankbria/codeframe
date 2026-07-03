"""Regression tests for the per-workspace `token_usage` table (issue #712 / P0.1).

Before the fix, no production code created `token_usage` — the only CREATE TABLE
lived in test fixtures — so every `save_token_usage()` raised
`OperationalError: no such table` (silently swallowed in react_agent) and all
cost/token data was dropped. These tests lock in that:

1. `create_or_load_workspace()` creates `token_usage` with the columns the
   repository INSERT expects and indexes on timestamp/task_id/agent_id.
2. A fresh workspace can save a record and read it back through the same
   `Database` path react_agent uses in production.
3. `_ensure_schema_upgrades()` adds the table to a pre-existing DB that lacks it.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core.models import CallType, TokenUsage
from codeframe.core.workspace import (
    _ensure_schema_upgrades,
    create_or_load_workspace,
)
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "test-repo"
    repo.mkdir()
    return repo


def _table_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _index_names(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}
    finally:
        conn.close()


class TestTokenUsageSchema:
    def test_fresh_workspace_creates_token_usage_table(self, temp_repo: Path):
        ws = create_or_load_workspace(temp_repo)
        cols = _table_columns(ws.db_path, "token_usage")
        # Every column the repository INSERT writes must exist.
        assert {
            "id",
            "task_id",
            "agent_id",
            "project_id",
            "model_name",
            "input_tokens",
            "output_tokens",
            "estimated_cost_usd",
            "actual_cost_usd",
            "call_type",
            "timestamp",
        } <= cols

    def test_token_usage_has_expected_indexes(self, temp_repo: Path):
        ws = create_or_load_workspace(temp_repo)
        idx = _index_names(ws.db_path, "token_usage")
        assert "idx_token_usage_timestamp" in idx
        assert "idx_token_usage_task_id" in idx
        assert "idx_token_usage_agent_id" in idx

    def test_save_and_read_roundtrip(self, temp_repo: Path):
        """Mirrors react_agent's production path: create_or_load_workspace then
        a Database over the same db_path saves and reads a record with no error."""
        ws = create_or_load_workspace(temp_repo)
        db = Database(str(ws.db_path))
        db.initialize()
        try:
            usage = TokenUsage(
                task_id="a1b2c3d4-uuid-task",  # v2 UUID string, not int
                agent_id="react-agent",
                project_id=0,
                model_name="claude-sonnet-4-5",
                input_tokens=1000,
                output_tokens=500,
                estimated_cost_usd=0.0105,
                call_type=CallType.TASK_EXECUTION,
                timestamp=datetime.now(timezone.utc),
            )
            db.save_token_usage(usage)
            rows = db.get_workspace_token_usage()
        finally:
            db.close()

        assert len(rows) == 1
        assert rows[0]["task_id"] == "a1b2c3d4-uuid-task"
        assert rows[0]["input_tokens"] == 1000
        assert rows[0]["output_tokens"] == 500

    def test_ensure_schema_upgrades_adds_table_to_old_db(self, tmp_path: Path):
        """An existing DB created before token_usage existed gets the table on upgrade."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE workspace (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        # Precondition: table absent.
        conn = sqlite3.connect(str(db_path))
        present = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'"
        ).fetchone()
        conn.close()
        assert present is None

        _ensure_schema_upgrades(db_path)

        assert "input_tokens" in _table_columns(db_path, "token_usage")
