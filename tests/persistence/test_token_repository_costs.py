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


class TestGetCostsSummaryRangeValidation:
    @pytest.mark.parametrize("days", [7, 30, 90])
    def test_valid_ranges(self, db, days):
        summary = db.token_usage.get_costs_summary(days=days)
        assert len(summary["daily"]) == days
