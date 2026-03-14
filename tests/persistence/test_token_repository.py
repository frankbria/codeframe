"""Tests for TokenRepository query methods (Issue #314 Step 3).

Tests for:
- get_task_token_summary: SQL aggregate for a single task
- get_batch_token_usage: Filter by list of task_ids
- get_workspace_token_usage: All records, no project filter
"""

import pytest
from datetime import datetime, timedelta, timezone

from codeframe.core.models import CallType, TokenUsage
from codeframe.persistence.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def db():
    """Create in-memory database for testing."""
    database = Database(":memory:")
    database.initialize()

    # Create test project
    cursor = database.conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, description, workspace_path, status) VALUES (?, ?, ?, ?)",
        ("test-project", "Test project", "/tmp/test", "active"),
    )
    database.conn.commit()

    return database


def _create_task(db, project_id=1, task_id_hint=None):
    """Helper to create a task and return its ID."""
    cursor = db.conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (project_id, title, description, status) VALUES (?, ?, ?, ?)",
        (project_id, f"Task {task_id_hint or 'x'}", "Test task", "in_progress"),
    )
    db.conn.commit()
    return cursor.lastrowid


def _save_usage(db, task_id=None, agent_id="agent-001", project_id=1,
                model_name="claude-sonnet-4-5", input_tokens=1000,
                output_tokens=500, cost=0.0105, call_type=CallType.TASK_EXECUTION,
                timestamp=None):
    """Helper to save a token usage record."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    usage = TokenUsage(
        task_id=task_id,
        agent_id=agent_id,
        project_id=project_id,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        actual_cost_usd=None,
        call_type=call_type,
        timestamp=timestamp,
    )
    return db.save_token_usage(usage)


# ============================================================================
# get_task_token_summary
# ============================================================================


def test_get_task_token_summary_single_call(db):
    """Test task summary with a single LLM call."""
    tid = _create_task(db)
    _save_usage(db, task_id=tid, input_tokens=1000, output_tokens=500, cost=0.0105)

    summary = db.get_task_token_summary(task_id=tid)

    assert summary["task_id"] == tid
    assert summary["total_input_tokens"] == 1000
    assert summary["total_output_tokens"] == 500
    assert summary["total_tokens"] == 1500
    assert summary["total_cost_usd"] == pytest.approx(0.0105, abs=1e-6)
    assert summary["call_count"] == 1


def test_get_task_token_summary_multiple_calls(db):
    """Test task summary aggregates multiple LLM calls."""
    tid = _create_task(db)
    _save_usage(db, task_id=tid, input_tokens=1000, output_tokens=500, cost=0.01)
    _save_usage(db, task_id=tid, input_tokens=2000, output_tokens=1000, cost=0.02)

    summary = db.get_task_token_summary(task_id=tid)

    assert summary["total_input_tokens"] == 3000
    assert summary["total_output_tokens"] == 1500
    assert summary["total_tokens"] == 4500
    assert summary["total_cost_usd"] == pytest.approx(0.03, abs=1e-6)
    assert summary["call_count"] == 2


def test_get_task_token_summary_no_records(db):
    """Test task summary returns zeros when no records exist."""
    summary = db.get_task_token_summary(task_id=999)

    assert summary["task_id"] == 999
    assert summary["total_input_tokens"] == 0
    assert summary["total_output_tokens"] == 0
    assert summary["total_tokens"] == 0
    assert summary["total_cost_usd"] == 0.0
    assert summary["call_count"] == 0


def test_get_task_token_summary_excludes_other_tasks(db):
    """Test task summary only includes records for the specified task."""
    tid1 = _create_task(db)
    tid2 = _create_task(db)
    _save_usage(db, task_id=tid1, input_tokens=1000, output_tokens=500, cost=0.01)
    _save_usage(db, task_id=tid2, input_tokens=2000, output_tokens=1000, cost=0.02)

    summary = db.get_task_token_summary(task_id=tid1)

    assert summary["total_input_tokens"] == 1000
    assert summary["call_count"] == 1


# ============================================================================
# get_batch_token_usage
# ============================================================================


def test_get_batch_token_usage(db):
    """Test getting token usage for a batch of task IDs."""
    tid1 = _create_task(db)
    tid2 = _create_task(db)
    tid3 = _create_task(db)
    _save_usage(db, task_id=tid1, input_tokens=100, output_tokens=50, cost=0.001)
    _save_usage(db, task_id=tid2, input_tokens=200, output_tokens=100, cost=0.002)
    _save_usage(db, task_id=tid3, input_tokens=300, output_tokens=150, cost=0.003)

    records = db.get_batch_token_usage(task_ids=[tid1, tid2])

    assert len(records) == 2
    task_ids = {r["task_id"] for r in records}
    assert task_ids == {tid1, tid2}


def test_get_batch_token_usage_with_date_filter(db):
    """Test batch token usage with date filtering."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=10)

    tid1 = _create_task(db)
    tid2 = _create_task(db)
    _save_usage(db, task_id=tid1, input_tokens=100, output_tokens=50, cost=0.001, timestamp=now)
    _save_usage(db, task_id=tid2, input_tokens=200, output_tokens=100, cost=0.002, timestamp=old)

    start = now - timedelta(days=1)
    records = db.get_batch_token_usage(task_ids=[tid1, tid2], start_date=start)

    assert len(records) == 1
    assert records[0]["task_id"] == tid1


def test_get_batch_token_usage_empty_list(db):
    """Test batch token usage with empty task ID list."""
    tid = _create_task(db)
    _save_usage(db, task_id=tid, input_tokens=100, output_tokens=50, cost=0.001)

    records = db.get_batch_token_usage(task_ids=[])

    assert len(records) == 0


# ============================================================================
# get_workspace_token_usage
# ============================================================================


def test_get_workspace_token_usage(db):
    """Test getting all token usage across the workspace."""
    tid = _create_task(db)
    _save_usage(db, task_id=tid, project_id=1, input_tokens=100, output_tokens=50, cost=0.001)
    _save_usage(db, task_id=None, project_id=1, input_tokens=200, output_tokens=100, cost=0.002)

    records = db.get_workspace_token_usage()

    assert len(records) == 2


def test_get_workspace_token_usage_with_date_filter(db):
    """Test workspace token usage with date filtering."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=10)

    tid1 = _create_task(db)
    tid2 = _create_task(db)
    _save_usage(db, task_id=tid1, input_tokens=100, output_tokens=50, cost=0.001, timestamp=now)
    _save_usage(db, task_id=tid2, input_tokens=200, output_tokens=100, cost=0.002, timestamp=old)

    start = now - timedelta(days=1)
    end = now + timedelta(days=1)
    records = db.get_workspace_token_usage(start_date=start, end_date=end)

    assert len(records) == 1
    assert records[0]["task_id"] == tid1


def test_get_workspace_token_usage_empty(db):
    """Test workspace token usage when no records exist."""
    records = db.get_workspace_token_usage()

    assert len(records) == 0
