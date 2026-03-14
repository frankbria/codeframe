"""Tests for engine_stats module.

Tests engine performance tracking: recording runs, computing aggregate stats,
and retrieving run logs.
"""

import uuid

import pytest

from codeframe.core.workspace import create_or_load_workspace, get_db_connection


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def run_id():
    return str(uuid.uuid4())


@pytest.fixture
def task_id():
    return str(uuid.uuid4())


def _record(workspace, engine, status, duration_ms=None, tokens_used=0,
            gates_passed=None, self_corrections=0):
    """Helper to record a run with a fresh run_id."""
    from codeframe.core.engine_stats import record_run

    rid = str(uuid.uuid4())
    tid = str(uuid.uuid4())
    record_run(
        workspace=workspace,
        run_id=rid,
        engine=engine,
        task_id=tid,
        status=status,
        duration_ms=duration_ms,
        tokens_used=tokens_used,
        gates_passed=gates_passed,
        self_corrections=self_corrections,
    )
    return rid


class TestRecordRun:
    """Tests for record_run function."""

    def test_record_run_inserts_row(self, workspace, run_id, task_id):
        """Verify a row exists in run_engine_log after recording."""
        from codeframe.core.engine_stats import record_run

        record_run(
            workspace=workspace,
            run_id=run_id,
            engine="react",
            task_id=task_id,
            status="COMPLETED",
            duration_ms=5000,
            tokens_used=1200,
            gates_passed=1,
            self_corrections=0,
        )

        conn = get_db_connection(workspace)
        row = conn.execute(
            "SELECT run_id, engine, task_id, status, duration_ms, tokens_used, "
            "gates_passed, self_corrections FROM run_engine_log WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == run_id
        assert row[1] == "react"
        assert row[2] == task_id
        assert row[3] == "COMPLETED"
        assert row[4] == 5000
        assert row[5] == 1200
        assert row[6] == 1
        assert row[7] == 0

    def test_record_run_updates_aggregates(self, workspace, run_id, task_id):
        """Verify engine_stats table is updated after recording a run."""
        from codeframe.core.engine_stats import record_run

        record_run(
            workspace=workspace,
            run_id=run_id,
            engine="react",
            task_id=task_id,
            status="COMPLETED",
            duration_ms=5000,
            tokens_used=1200,
            gates_passed=1,
            self_corrections=0,
        )

        conn = get_db_connection(workspace)
        rows = conn.execute(
            "SELECT metric, value FROM engine_stats "
            "WHERE workspace_id = ? AND engine = ?",
            (workspace.id, "react"),
        ).fetchall()
        conn.close()

        metrics = {r[0]: r[1] for r in rows}
        assert metrics["tasks_attempted"] == 1.0
        assert metrics["tasks_completed"] == 1.0
        assert metrics["tasks_failed"] == 0.0


class TestGetEngineStats:
    """Tests for get_engine_stats function."""

    def test_get_engine_stats_single_engine(self, workspace):
        """Verify stats structure for a single engine."""
        from codeframe.core.engine_stats import get_engine_stats

        _record(workspace, "react", "COMPLETED", duration_ms=3000, tokens_used=500)

        stats = get_engine_stats(workspace)

        assert "react" in stats
        assert "tasks_attempted" in stats["react"]
        assert "tasks_completed" in stats["react"]
        assert stats["react"]["tasks_attempted"] == 1.0
        assert stats["react"]["tasks_completed"] == 1.0

    def test_get_engine_stats_multiple_engines(self, workspace):
        """Verify stats returned for multiple engines."""
        from codeframe.core.engine_stats import get_engine_stats

        _record(workspace, "react", "COMPLETED", duration_ms=3000, tokens_used=500)
        _record(workspace, "plan", "COMPLETED", duration_ms=4000, tokens_used=800)

        stats = get_engine_stats(workspace)

        assert "react" in stats
        assert "plan" in stats

    def test_get_engine_stats_filter_by_engine(self, workspace):
        """Verify filtering to a specific engine."""
        from codeframe.core.engine_stats import get_engine_stats

        _record(workspace, "react", "COMPLETED", duration_ms=3000, tokens_used=500)
        _record(workspace, "plan", "COMPLETED", duration_ms=4000, tokens_used=800)

        stats = get_engine_stats(workspace, engine="react")

        assert "react" in stats
        assert "plan" not in stats

    def test_get_engine_stats_empty(self, workspace):
        """Returns empty dict when no data exists."""
        from codeframe.core.engine_stats import get_engine_stats

        stats = get_engine_stats(workspace)

        assert stats == {}


class TestGetRunLog:
    """Tests for get_run_log function."""

    def test_get_run_log(self, workspace):
        """Verify run log returns correct records."""
        from codeframe.core.engine_stats import get_run_log

        rid1 = _record(workspace, "react", "COMPLETED", duration_ms=3000)
        rid2 = _record(workspace, "react", "FAILED", duration_ms=1000)

        logs = get_run_log(workspace)

        assert len(logs) == 2
        run_ids = {log["run_id"] for log in logs}
        assert rid1 in run_ids
        assert rid2 in run_ids

    def test_get_run_log_with_limit(self, workspace):
        """Verify limit works."""
        from codeframe.core.engine_stats import get_run_log

        for _ in range(5):
            _record(workspace, "react", "COMPLETED", duration_ms=1000)

        logs = get_run_log(workspace, limit=3)

        assert len(logs) == 3


class TestAggregateCalculations:
    """Tests for aggregate metric calculations."""

    def test_aggregate_gate_pass_rate(self, workspace):
        """Verify correct gate pass rate calculation."""
        from codeframe.core.engine_stats import get_engine_stats

        # 2 passed, 1 failed out of 3 with gate data
        _record(workspace, "react", "COMPLETED", gates_passed=1)
        _record(workspace, "react", "COMPLETED", gates_passed=1)
        _record(workspace, "react", "FAILED", gates_passed=0)

        stats = get_engine_stats(workspace)

        # 2/3 * 100 = ~66.67
        assert abs(stats["react"]["gate_pass_rate"] - 66.67) < 0.1

    def test_aggregate_self_correction_rate(self, workspace):
        """Verify correct self-correction rate calculation."""
        from codeframe.core.engine_stats import get_engine_stats

        _record(workspace, "react", "COMPLETED", self_corrections=2)
        _record(workspace, "react", "COMPLETED", self_corrections=0)
        _record(workspace, "react", "COMPLETED", self_corrections=1)

        stats = get_engine_stats(workspace)

        # 2 out of 3 had self_corrections > 0 = 66.67%
        assert abs(stats["react"]["self_correction_rate"] - 66.67) < 0.1

    def test_aggregate_handles_zero_completed(self, workspace):
        """No division by zero when no tasks completed."""
        from codeframe.core.engine_stats import get_engine_stats

        _record(workspace, "react", "FAILED", tokens_used=500)

        stats = get_engine_stats(workspace)

        assert stats["react"]["tasks_completed"] == 0.0
        assert stats["react"]["avg_tokens_per_task"] == 0.0
