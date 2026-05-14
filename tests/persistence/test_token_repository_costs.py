"""Tests for TokenRepository.get_costs_summary (Issue #557).

The method aggregates token_usage rows into daily buckets for the
cost analytics page. Returns total spend, total tasks, average cost
per task, and a daily series filled with zeros where no data exists.
"""

import pytest
from datetime import datetime, timedelta, timezone

from codeframe.core.models import CallType, TokenUsage
from codeframe.persistence.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def db():
    database = Database(":memory:")
    database.initialize()
    cursor = database.conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, description, workspace_path, status) VALUES (?, ?, ?, ?)",
        ("test-project", "Test project", "/tmp/test", "active"),
    )
    database.conn.commit()
    return database


def _create_task(db, project_id=1, title="Task"):
    cursor = db.conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (project_id, title, description, status) VALUES (?, ?, ?, ?)",
        (project_id, title, "Test", "in_progress"),
    )
    db.conn.commit()
    return cursor.lastrowid


def _save(db, task_id=None, cost=0.01, timestamp=None, project_id=1):
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    usage = TokenUsage(
        task_id=task_id,
        agent_id="agent-001",
        project_id=project_id,
        model_name="claude-sonnet-4-5",
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=cost,
        actual_cost_usd=None,
        call_type=CallType.TASK_EXECUTION,
        timestamp=timestamp,
    )
    return db.save_token_usage(usage)


class TestGetCostsSummaryEmpty:
    def test_empty_table_returns_zeros(self, db):
        summary = db.token_usage.get_costs_summary(days=30)

        assert summary["total_spend_usd"] == 0.0
        assert summary["total_tasks"] == 0
        assert summary["avg_cost_per_task"] == 0.0
        # daily should have one entry per day in the range
        assert len(summary["daily"]) == 30
        assert all(d["cost_usd"] == 0.0 for d in summary["daily"])

    def test_default_days_is_30(self, db):
        summary = db.token_usage.get_costs_summary(days=30)
        assert len(summary["daily"]) == 30


class TestGetCostsSummaryWithData:
    def test_aggregates_total_spend(self, db):
        t1 = _create_task(db)
        t2 = _create_task(db)
        now = datetime.now(timezone.utc)
        _save(db, task_id=t1, cost=0.50, timestamp=now)
        _save(db, task_id=t1, cost=0.25, timestamp=now)
        _save(db, task_id=t2, cost=0.30, timestamp=now)

        summary = db.token_usage.get_costs_summary(days=30)

        assert summary["total_spend_usd"] == pytest.approx(1.05)
        assert summary["total_tasks"] == 2  # distinct task_ids
        assert summary["avg_cost_per_task"] == pytest.approx(1.05 / 2)

    def test_excludes_null_task_ids_from_count(self, db):
        t1 = _create_task(db)
        now = datetime.now(timezone.utc)
        _save(db, task_id=t1, cost=0.10, timestamp=now)
        _save(db, task_id=None, cost=0.10, timestamp=now)  # standalone call

        summary = db.token_usage.get_costs_summary(days=30)

        assert summary["total_spend_usd"] == pytest.approx(0.20)
        assert summary["total_tasks"] == 1

    def test_daily_buckets_filled_with_zeros(self, db):
        t1 = _create_task(db)
        # Two records on different days within the range
        now = datetime.now(timezone.utc)
        _save(db, task_id=t1, cost=0.10, timestamp=now)
        _save(db, task_id=t1, cost=0.20, timestamp=now - timedelta(days=3))

        summary = db.token_usage.get_costs_summary(days=7)

        assert len(summary["daily"]) == 7
        # All entries have date keys and cost_usd keys
        for entry in summary["daily"]:
            assert "date" in entry
            assert "cost_usd" in entry
        # Sum of daily matches total
        assert sum(d["cost_usd"] for d in summary["daily"]) == pytest.approx(0.30)

    def test_excludes_data_outside_window(self, db):
        t1 = _create_task(db)
        now = datetime.now(timezone.utc)
        _save(db, task_id=t1, cost=0.10, timestamp=now)
        # 100 days ago — outside 30-day window
        _save(db, task_id=t1, cost=99.0, timestamp=now - timedelta(days=100))

        summary = db.token_usage.get_costs_summary(days=30)

        assert summary["total_spend_usd"] == pytest.approx(0.10)

    def test_excludes_future_dated_rows(self, db):
        """A row with a timestamp past today must not inflate the KPI cards.

        Without an upper bound the daily chart (which is built from a fixed
        list of dates within the window) would exclude future rows while the
        SUM() KPIs would include them, making the two views disagree.
        """
        t1 = _create_task(db)
        now = datetime.now(timezone.utc)
        _save(db, task_id=t1, cost=0.10, timestamp=now)
        _save(db, task_id=t1, cost=42.0, timestamp=now + timedelta(days=2))

        summary = db.token_usage.get_costs_summary(days=7)

        assert summary["total_spend_usd"] == pytest.approx(0.10)
        # And the daily series sum agrees with the KPI total
        assert sum(d["cost_usd"] for d in summary["daily"]) == pytest.approx(0.10)

    def test_daily_dates_are_ordered_oldest_to_newest(self, db):
        summary = db.token_usage.get_costs_summary(days=7)
        dates = [d["date"] for d in summary["daily"]]
        assert dates == sorted(dates)

    def test_avg_cost_per_task_zero_when_no_tasks(self, db):
        # Record exists but has NULL task_id
        now = datetime.now(timezone.utc)
        _save(db, task_id=None, cost=0.50, timestamp=now)

        summary = db.token_usage.get_costs_summary(days=30)

        assert summary["total_spend_usd"] == pytest.approx(0.50)
        assert summary["total_tasks"] == 0
        assert summary["avg_cost_per_task"] == 0.0


class TestGetCostsSummaryTimestampFormats:
    """Records inserted via different timestamp formats must all be picked up.

    SQLite's `CURRENT_TIMESTAMP` produces space-separated values
    ("YYYY-MM-DD HH:MM:SS"), Python `.isoformat()` produces T-separated
    values with an offset suffix ("YYYY-MM-DDTHH:MM:SS+00:00"). The query
    must include both.
    """

    def test_includes_records_with_space_separated_timestamps(self, db):
        """A record inserted with SQLite's default timestamp format must be counted."""
        tid = _create_task(db)
        # Insert raw with a space-separated timestamp (the schema default format).
        # This simulates DEFAULT CURRENT_TIMESTAMP behavior.
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage (task_id, agent_id, project_id, model_name,
                input_tokens, output_tokens, estimated_cost_usd, call_type, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (tid, "agent-001", 1, "claude-sonnet-4-5",
             100, 50, 0.42, "task_execution", now_str),
        )
        db.conn.commit()

        summary = db.token_usage.get_costs_summary(days=7)

        assert summary["total_spend_usd"] == pytest.approx(0.42)
        assert summary["total_tasks"] == 1


class TestGetCostsSummaryRangeValidation:
    @pytest.mark.parametrize("days", [7, 30, 90])
    def test_valid_ranges(self, db, days):
        summary = db.token_usage.get_costs_summary(days=days)
        assert len(summary["daily"]) == days


# ---------------------------------------------------------------------------
# get_top_tasks_by_cost (Issue #558) — per-task cost breakdown
# ---------------------------------------------------------------------------


def _save_with_agent(
    db, task_id, cost, agent_id="agent-001", project_id=1, timestamp=None,
    input_tokens=100, output_tokens=50,
):
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    usage = TokenUsage(
        task_id=task_id,
        agent_id=agent_id,
        project_id=project_id,
        model_name="claude-sonnet-4-5",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        actual_cost_usd=None,
        call_type=CallType.TASK_EXECUTION,
        timestamp=timestamp,
    )
    return db.save_token_usage(usage)


class TestGetTopTasksByCost:
    def test_empty_returns_empty_list(self, db):
        result = db.token_usage.get_top_tasks_by_cost(days=30)
        assert result == []

    def test_aggregates_cost_per_task(self, db):
        t1 = _create_task(db)
        t2 = _create_task(db)
        _save_with_agent(db, task_id=t1, cost=0.25)
        _save_with_agent(db, task_id=t1, cost=0.50)
        _save_with_agent(db, task_id=t2, cost=0.10)

        result = db.token_usage.get_top_tasks_by_cost(days=30)

        # Sorted by cost desc
        assert len(result) == 2
        assert result[0]["task_id"] == t1
        assert result[0]["total_cost_usd"] == pytest.approx(0.75)
        assert result[0]["input_tokens"] == 200
        assert result[0]["output_tokens"] == 100
        assert result[1]["task_id"] == t2
        assert result[1]["total_cost_usd"] == pytest.approx(0.10)

    def test_includes_most_used_agent_per_task(self, db):
        """Task aggregates should report the agent with the most calls."""
        t1 = _create_task(db)
        _save_with_agent(db, task_id=t1, cost=0.10, agent_id="react-agent")
        _save_with_agent(db, task_id=t1, cost=0.10, agent_id="react-agent")
        _save_with_agent(db, task_id=t1, cost=0.10, agent_id="other-agent")

        result = db.token_usage.get_top_tasks_by_cost(days=30)

        assert result[0]["agent_id"] == "react-agent"

    def test_excludes_null_task_ids(self, db):
        t1 = _create_task(db)
        _save_with_agent(db, task_id=t1, cost=0.10)
        _save_with_agent(db, task_id=None, cost=99.0)

        result = db.token_usage.get_top_tasks_by_cost(days=30)

        assert len(result) == 1
        assert result[0]["task_id"] == t1

    def test_respects_limit(self, db):
        for _ in range(15):
            tid = _create_task(db)
            _save_with_agent(db, task_id=tid, cost=0.01)

        result = db.token_usage.get_top_tasks_by_cost(days=30, limit=10)
        assert len(result) == 10

    def test_excludes_data_outside_window(self, db):
        t1 = _create_task(db)
        now = datetime.now(timezone.utc)
        _save_with_agent(db, task_id=t1, cost=0.10, timestamp=now)
        _save_with_agent(db, task_id=t1, cost=99.0, timestamp=now - timedelta(days=100))

        result = db.token_usage.get_top_tasks_by_cost(days=30)

        assert result[0]["total_cost_usd"] == pytest.approx(0.10)

    def test_supports_text_task_ids(self, db):
        """SQLite is type-flexible: TEXT (UUID) task_ids must be aggregated correctly.

        v2 workspaces store task UUIDs in the same INTEGER-declared column; the
        aggregation has to group by the raw value without type coercion. The v1
        Database fixture enforces FK(token_usage.task_id → tasks.id), so we
        relax it for this test to model the v2 schema where token_usage has no
        such constraint.
        """
        uuid_a = "task-uuid-aaaa"
        uuid_b = "task-uuid-bbbb"
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF")
        try:
            for tid, cost in [(uuid_a, 0.50), (uuid_a, 0.25), (uuid_b, 0.10)]:
                cursor.execute(
                    """
                    INSERT INTO token_usage (task_id, agent_id, project_id, model_name,
                        input_tokens, output_tokens, estimated_cost_usd, call_type, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tid, "react-agent", 1, "claude-sonnet-4-5",
                     100, 50, cost, "task_execution",
                     datetime.now(timezone.utc).isoformat()),
                )
            db.conn.commit()
        finally:
            cursor.execute("PRAGMA foreign_keys = ON")

        result = db.token_usage.get_top_tasks_by_cost(days=30)

        assert len(result) == 2
        assert result[0]["task_id"] == uuid_a
        assert result[0]["total_cost_usd"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# get_costs_by_agent (Issue #558) — per-agent cost breakdown
# ---------------------------------------------------------------------------


class TestGetCostsByAgent:
    def test_empty_returns_zero_state(self, db):
        result = db.token_usage.get_costs_by_agent(days=30)
        assert result["by_agent"] == []
        assert result["total_input_tokens"] == 0
        assert result["total_output_tokens"] == 0

    def test_aggregates_cost_per_agent(self, db):
        t1 = _create_task(db)
        _save_with_agent(db, task_id=t1, cost=0.30, agent_id="claude-code")
        _save_with_agent(db, task_id=t1, cost=0.20, agent_id="claude-code")
        _save_with_agent(db, task_id=t1, cost=0.40, agent_id="codex")

        result = db.token_usage.get_costs_by_agent(days=30)

        # Sorted by cost desc
        agents = result["by_agent"]
        assert len(agents) == 2
        assert agents[0]["agent_id"] == "claude-code"
        assert agents[0]["total_cost_usd"] == pytest.approx(0.50)
        assert agents[0]["call_count"] == 2
        assert agents[0]["input_tokens"] == 200
        assert agents[0]["output_tokens"] == 100
        assert agents[1]["agent_id"] == "codex"
        assert agents[1]["total_cost_usd"] == pytest.approx(0.40)

    def test_includes_null_task_records(self, db):
        """Per-agent totals should include calls not linked to a task."""
        _save_with_agent(db, task_id=None, cost=0.10, agent_id="solo-agent")

        result = db.token_usage.get_costs_by_agent(days=30)

        assert len(result["by_agent"]) == 1
        assert result["by_agent"][0]["agent_id"] == "solo-agent"

    def test_totals_match_sum_of_agents(self, db):
        t1 = _create_task(db)
        _save_with_agent(db, task_id=t1, cost=0.10,
                         agent_id="a", input_tokens=100, output_tokens=50)
        _save_with_agent(db, task_id=t1, cost=0.10,
                         agent_id="b", input_tokens=200, output_tokens=75)

        result = db.token_usage.get_costs_by_agent(days=30)

        assert result["total_input_tokens"] == 300
        assert result["total_output_tokens"] == 125

    def test_excludes_data_outside_window(self, db):
        t1 = _create_task(db)
        now = datetime.now(timezone.utc)
        _save_with_agent(db, task_id=t1, cost=0.10, agent_id="a", timestamp=now)
        _save_with_agent(db, task_id=t1, cost=99.0, agent_id="a",
                         timestamp=now - timedelta(days=100))

        result = db.token_usage.get_costs_by_agent(days=30)

        assert result["by_agent"][0]["total_cost_usd"] == pytest.approx(0.10)
