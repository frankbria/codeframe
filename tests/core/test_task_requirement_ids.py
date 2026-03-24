"""Tests for task requirement_ids field (issue #468).

Tests that tasks can be linked to PROOF9 requirement IDs for traceability.
"""

import sqlite3

import pytest

from codeframe.core import tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


class TestTaskRequirementIdsField:
    """Test the requirement_ids field on Task model."""

    def test_task_has_empty_requirement_ids_by_default(self, workspace):
        """New tasks should have empty requirement_ids list."""
        task = tasks.create(workspace, title="Test task")
        assert task.requirement_ids == []

    def test_task_created_with_requirement_ids(self, workspace):
        """Tasks can be created with requirement_ids."""
        req_ids = ["REQ-001", "REQ-002"]
        task = tasks.create(workspace, title="Task with reqs", requirement_ids=req_ids)
        assert task.requirement_ids == req_ids

    def test_task_get_includes_requirement_ids(self, workspace):
        """Getting a task should include its requirement_ids."""
        req_ids = ["REQ-042"]
        task = tasks.create(workspace, title="Task", requirement_ids=req_ids)
        retrieved = tasks.get(workspace, task.id)
        assert retrieved.requirement_ids == req_ids

    def test_task_list_includes_requirement_ids(self, workspace):
        """Listing tasks should include requirement_ids."""
        t1 = tasks.create(workspace, title="No reqs")
        t2 = tasks.create(workspace, title="With reqs", requirement_ids=["REQ-007"])

        all_tasks = tasks.list_tasks(workspace)
        task_map = {t.id: t for t in all_tasks}

        assert task_map[t1.id].requirement_ids == []
        assert task_map[t2.id].requirement_ids == ["REQ-007"]

    def test_task_requirement_ids_persisted_across_get(self, workspace):
        """requirement_ids should survive a round-trip to the database."""
        req_ids = ["REQ-001", "REQ-002", "REQ-003"]
        task = tasks.create(workspace, title="Multi-req task", requirement_ids=req_ids)
        fetched = tasks.get(workspace, task.id)
        assert fetched.requirement_ids == req_ids

    def test_update_requirement_ids(self, workspace):
        """requirement_ids can be updated on an existing task."""
        task = tasks.create(workspace, title="Task")
        assert task.requirement_ids == []

        updated = tasks.update_requirement_ids(workspace, task.id, ["REQ-099"])
        assert updated.requirement_ids == ["REQ-099"]

        fetched = tasks.get(workspace, task.id)
        assert fetched.requirement_ids == ["REQ-099"]

    def test_update_requirement_ids_to_empty(self, workspace):
        """requirement_ids can be cleared."""
        task = tasks.create(workspace, title="Task", requirement_ids=["REQ-001"])
        updated = tasks.update_requirement_ids(workspace, task.id, [])
        assert updated.requirement_ids == []

    def test_task_without_requirement_ids_in_existing_db(self, tmp_path):
        """Migration guard adds requirement_ids column to pre-migration databases.

        Simulates a workspace that was created before the requirement_ids column
        was added, then verifies that opening it triggers the migration guard
        and tasks can be read back with requirement_ids == [].
        """
        # Step 1: Create a workspace and inject a "pre-migration" tasks table
        # by directly dropping the requirement_ids column from the DB.
        ws = create_or_load_workspace(tmp_path)
        db_path = ws.db_path

        conn = sqlite3.connect(db_path)
        # Insert a task using the old schema (without requirement_ids)
        import uuid
        from datetime import datetime, timezone
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO tasks (id, workspace_id, prd_id, title, description, status,
                               priority, depends_on, created_at, updated_at)
            VALUES (?, ?, NULL, ?, '', 'BACKLOG', 0, '[]', ?, ?)
            """,
            (task_id, ws.id, "Legacy task", now, now),
        )
        # Simulate the column not existing by removing it (SQLite workaround)
        conn.execute("ALTER TABLE tasks RENAME TO tasks_old")
        conn.execute("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                prd_id TEXT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'BACKLOG',
                priority INTEGER DEFAULT 0,
                depends_on TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO tasks (id, workspace_id, prd_id, title, description, status,
                               priority, depends_on, created_at, updated_at)
            SELECT id, workspace_id, prd_id, title, description, status,
                   priority, depends_on, created_at, updated_at
            FROM tasks_old
        """)
        conn.execute("DROP TABLE tasks_old")
        conn.commit()
        conn.close()

        # Step 2: Re-open workspace — this triggers _ensure_schema_upgrades()
        # which should add the requirement_ids column.
        ws2 = create_or_load_workspace(tmp_path)

        # Step 3: Verify the legacy task reads back with requirement_ids == []
        fetched = tasks.get(ws2, task_id)
        assert fetched is not None
        assert hasattr(fetched, "requirement_ids")
        assert fetched.requirement_ids == []
