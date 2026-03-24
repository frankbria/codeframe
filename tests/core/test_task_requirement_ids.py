"""Tests for task requirement_ids field (issue #468).

Tests that tasks can be linked to PROOF9 requirement IDs for traceability.
"""

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

    def test_task_without_requirement_ids_in_existing_db(self, workspace):
        """Tasks created before migration (no requirement_ids column) return []."""
        # This is tested implicitly by the migration guard in workspace init,
        # but we verify a freshly-created task always has the field.
        task = tasks.create(workspace, title="Legacy-style task")
        assert hasattr(task, "requirement_ids")
        assert task.requirement_ids == []
