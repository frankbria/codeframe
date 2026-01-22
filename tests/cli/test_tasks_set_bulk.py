"""Tests for tasks set bulk operations (--all, --from flags)."""

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import workspace, tasks, prd
from codeframe.core.tasks import TaskStatus

# Mark all tests in this module as v2
pytestmark = pytest.mark.v2


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def workspace_with_tasks(tmp_path):
    """Create a workspace with tasks in various states."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    # Create workspace
    ws = workspace.create_or_load_workspace(repo)

    # Create a minimal PRD
    prd_content = """# Test PRD
## Tasks
- Task 1: First task
- Task 2: Second task
- Task 3: Third task
- Task 4: Fourth task
"""
    prd_file = tmp_path / "test.md"
    prd_file.write_text(prd_content)
    prd_record = prd.store(ws, prd_content, source_path=prd_file)

    # Generate tasks (all start as BACKLOG)
    created = tasks.generate_from_prd(ws, prd_record, use_llm=False)

    # Set some to READY for variety
    tasks.update_status(ws, created[0].id, TaskStatus.READY)
    tasks.update_status(ws, created[1].id, TaskStatus.READY)

    return ws, repo, created


class TestTasksSetAll:
    """Test --all flag for bulk status updates."""

    def test_set_all_to_ready(self, runner, workspace_with_tasks):
        """--all should update all tasks to target status."""
        ws, repo, created = workspace_with_tasks

        result = runner.invoke(
            app, ["tasks", "set", "status", "READY", "--all", "-w", str(repo)]
        )

        assert result.exit_code == 0
        assert "Updated" in result.output

        # Verify all tasks are READY
        all_tasks = tasks.list_tasks(ws)
        for task in all_tasks:
            assert task.status == TaskStatus.READY

    def test_set_all_skips_already_at_status(self, runner, workspace_with_tasks):
        """--all should skip tasks already at target status."""
        ws, repo, created = workspace_with_tasks

        # Two tasks are already READY
        result = runner.invoke(
            app, ["tasks", "set", "status", "READY", "--all", "-w", str(repo)]
        )

        assert result.exit_code == 0
        assert "Skipped" in result.output
        assert "2" in result.output  # 2 were already READY

    def test_set_all_reports_count(self, runner, workspace_with_tasks):
        """--all should report how many tasks were updated."""
        ws, repo, created = workspace_with_tasks

        # The fixture sets 2 tasks to READY, so 2 are still BACKLOG
        # Setting all to READY should update 2 (BACKLOG->READY) and skip 2 (already READY)
        result = runner.invoke(
            app, ["tasks", "set", "status", "READY", "--all", "-w", str(repo)]
        )

        assert result.exit_code == 0
        assert "Updated 2 tasks" in result.output
        assert "Skipped 2" in result.output


class TestTasksSetFrom:
    """Test --from flag for filtered bulk updates."""

    def test_set_from_backlog_to_ready(self, runner, workspace_with_tasks):
        """--from BACKLOG should only update BACKLOG tasks."""
        ws, repo, created = workspace_with_tasks

        # Initially: 2 READY, 2 BACKLOG
        result = runner.invoke(
            app,
            ["tasks", "set", "status", "READY", "--all", "--from", "BACKLOG", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Updated 2 tasks" in result.output

        # Verify all are now READY
        all_tasks = tasks.list_tasks(ws)
        for task in all_tasks:
            assert task.status == TaskStatus.READY

    def test_set_from_ready_to_backlog(self, runner, workspace_with_tasks):
        """--from READY should only update READY tasks."""
        ws, repo, created = workspace_with_tasks

        # Reset READY tasks back to BACKLOG
        result = runner.invoke(
            app,
            ["tasks", "set", "status", "BACKLOG", "--all", "--from", "READY", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Updated 2 tasks" in result.output

        # Verify counts
        all_tasks = tasks.list_tasks(ws)
        backlog_count = sum(1 for t in all_tasks if t.status == TaskStatus.BACKLOG)
        assert backlog_count == 4  # All should be BACKLOG now

    def test_set_from_nonexistent_status_exits_clean(self, runner, workspace_with_tasks):
        """--from with no matching tasks should exit cleanly."""
        ws, repo, created = workspace_with_tasks

        # No tasks are DONE
        result = runner.invoke(
            app,
            ["tasks", "set", "status", "READY", "--all", "--from", "DONE", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "No tasks with status DONE" in result.output


class TestTasksSetSingleTask:
    """Test single task updates (backward compatibility)."""

    def test_set_single_task_by_id(self, runner, workspace_with_tasks):
        """Single task ID should still work."""
        ws, repo, created = workspace_with_tasks
        task = created[2]  # A BACKLOG task

        result = runner.invoke(
            app, ["tasks", "set", "status", task.id[:8], "READY", "-w", str(repo)]
        )

        assert result.exit_code == 0
        assert "Task updated" in result.output

        # Verify update by listing tasks and finding the updated one
        all_tasks = tasks.list_tasks(ws)
        updated = next(t for t in all_tasks if t.id == task.id)
        assert updated.status == TaskStatus.READY

    def test_set_single_task_partial_id(self, runner, workspace_with_tasks):
        """Partial task ID should work with unique prefix."""
        ws, repo, created = workspace_with_tasks
        task = created[2]

        result = runner.invoke(
            app, ["tasks", "set", "status", task.id[:6], "READY", "-w", str(repo)]
        )

        assert result.exit_code == 0

    def test_set_single_task_already_at_status(self, runner, workspace_with_tasks):
        """Setting task to current status should show message."""
        ws, repo, created = workspace_with_tasks
        task = created[0]  # Already READY

        result = runner.invoke(
            app, ["tasks", "set", "status", task.id[:8], "READY", "-w", str(repo)]
        )

        assert result.exit_code == 0
        assert "already READY" in result.output


class TestTasksSetErrors:
    """Test error handling."""

    def test_no_task_id_or_all_flag(self, runner, workspace_with_tasks):
        """Missing task ID without --all should error."""
        ws, repo, created = workspace_with_tasks

        result = runner.invoke(
            app, ["tasks", "set", "status", "-w", str(repo)]
        )

        assert result.exit_code == 1
        assert "Missing task ID" in result.output

    def test_invalid_status_value(self, runner, workspace_with_tasks):
        """Invalid status should error."""
        ws, repo, created = workspace_with_tasks

        result = runner.invoke(
            app, ["tasks", "set", "status", "INVALID", "--all", "-w", str(repo)]
        )

        assert result.exit_code == 1

    def test_nonexistent_task_id(self, runner, workspace_with_tasks):
        """Non-matching task ID should error."""
        ws, repo, created = workspace_with_tasks

        result = runner.invoke(
            app, ["tasks", "set", "status", "nonexistent123", "READY", "-w", str(repo)]
        )

        assert result.exit_code == 1
        assert "No task found" in result.output

    def test_empty_workspace(self, runner, tmp_path):
        """Empty workspace should handle gracefully."""
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        workspace.create_or_load_workspace(repo)

        result = runner.invoke(
            app, ["tasks", "set", "status", "READY", "--all", "-w", str(repo)]
        )

        assert result.exit_code == 0
        assert "No tasks in workspace" in result.output
