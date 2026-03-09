"""Edge case tests for task management in CodeFRAME.

Covers boundary conditions and failure scenarios for create, get, update,
delete, list, and status transition operations in codeframe.core.tasks.
"""

import pytest

from codeframe.core import tasks
from codeframe.core.state_machine import InvalidTransitionError, TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.edge_case


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


class TestTaskEdgeCases:
    """Edge case tests for task management."""

    def test_create_task_with_empty_title(self, workspace):
        """Creating a task with an empty string title should succeed because
        tasks.create performs no input validation on the title field."""
        task = tasks.create(workspace, title="")
        assert task.title == ""

        retrieved = tasks.get(workspace, task.id)
        assert retrieved is not None
        assert retrieved.title == ""

    def test_update_status_invalid_transition_done_to_backlog(self, workspace):
        """Transitioning a DONE task directly to BACKLOG should raise
        InvalidTransitionError because DONE only allows READY or MERGED."""
        task = tasks.create(workspace, title="transition test")
        tasks.update_status(workspace, task.id, TaskStatus.READY)
        tasks.update_status(workspace, task.id, TaskStatus.IN_PROGRESS)
        tasks.update_status(workspace, task.id, TaskStatus.DONE)

        with pytest.raises(InvalidTransitionError) as exc_info:
            tasks.update_status(workspace, task.id, TaskStatus.BACKLOG)

        assert exc_info.value.current == TaskStatus.DONE
        assert exc_info.value.target == TaskStatus.BACKLOG

    def test_get_nonexistent_task(self, workspace):
        """Fetching a task ID that does not exist should return None."""
        result = tasks.get(workspace, "nonexistent-uuid-value")
        assert result is None

    def test_update_status_nonexistent_task(self, workspace):
        """Updating the status of a task that does not exist should raise
        ValueError with a message identifying the missing task ID."""
        with pytest.raises(ValueError, match="Task not found"):
            tasks.update_status(workspace, "nonexistent-uuid-value", TaskStatus.READY)

    def test_list_tasks_empty_workspace(self, workspace):
        """Listing tasks on a workspace with no tasks returns an empty list."""
        result = tasks.list_tasks(workspace)
        assert result == []

    def test_list_by_status_empty_workspace(self, workspace):
        """list_by_status on an empty workspace returns a dict with every
        TaskStatus as a key, each mapping to an empty list."""
        result = tasks.list_by_status(workspace)

        for status in TaskStatus:
            assert status in result, f"Missing key for {status.value}"
            assert result[status] == [], f"Expected empty list for {status.value}"
