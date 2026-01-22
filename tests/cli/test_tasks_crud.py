"""Tests for task CRUD operations (delete, generate --overwrite)."""

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import workspace, tasks, prd

# Mark all tests in this module as v2
pytestmark = pytest.mark.v2


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def workspace_with_tasks(tmp_path):
    """Create a workspace with tasks."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    ws = workspace.create_or_load_workspace(repo)

    prd_content = """# Test PRD
## Tasks
- Task 1: First task
- Task 2: Second task
- Task 3: Third task
"""
    prd_file = tmp_path / "test.md"
    prd_file.write_text(prd_content)
    prd_record = prd.store(ws, prd_content, source_path=prd_file)

    created = tasks.generate_from_prd(ws, prd_record, use_llm=False)

    return ws, repo, created, prd_file


class TestTasksDeleteSingle:
    """Test deleting single tasks."""

    def test_delete_single_task(self, runner, workspace_with_tasks):
        """Should delete a single task by ID."""
        ws, repo, created, _ = workspace_with_tasks
        task = created[0]

        result = runner.invoke(
            app,
            ["tasks", "delete", task.id[:8], "--force", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Deleted task" in result.output

        # Verify task is gone
        remaining = tasks.list_tasks(ws)
        assert len(remaining) == 2
        assert task.id not in [t.id for t in remaining]

    def test_delete_partial_id(self, runner, workspace_with_tasks):
        """Should match task by partial ID."""
        ws, repo, created, _ = workspace_with_tasks
        task = created[1]

        result = runner.invoke(
            app,
            ["tasks", "delete", task.id[:6], "--force", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Deleted task" in result.output

    def test_delete_nonexistent_task(self, runner, workspace_with_tasks):
        """Should error for non-matching task ID."""
        ws, repo, created, _ = workspace_with_tasks

        result = runner.invoke(
            app,
            ["tasks", "delete", "nonexistent", "--force", "-w", str(repo)],
        )

        assert result.exit_code == 1
        assert "No task found" in result.output

    def test_delete_warns_about_dependents(self, runner, workspace_with_tasks):
        """Should warn when deleting a task that others depend on."""
        ws, repo, created, _ = workspace_with_tasks
        task1 = created[0]
        task2 = created[1]

        # Make task2 depend on task1
        tasks.update_depends_on(ws, task2.id, [task1.id])

        result = runner.invoke(
            app,
            ["tasks", "delete", task1.id[:8], "--force", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Warning" in result.output
        assert "depend on this task" in result.output


class TestTasksDeleteAll:
    """Test deleting all tasks."""

    def test_delete_all_with_force(self, runner, workspace_with_tasks):
        """--all --force should delete all tasks without prompt."""
        ws, repo, created, _ = workspace_with_tasks

        result = runner.invoke(
            app,
            ["tasks", "delete", "--all", "--force", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Deleted 3 tasks" in result.output

        # Verify all tasks gone
        remaining = tasks.list_tasks(ws)
        assert len(remaining) == 0

    def test_delete_all_empty_workspace(self, runner, tmp_path):
        """--all on empty workspace should handle gracefully."""
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        workspace.create_or_load_workspace(repo)

        result = runner.invoke(
            app,
            ["tasks", "delete", "--all", "--force", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "No tasks to delete" in result.output

    def test_delete_all_requires_confirmation(self, runner, workspace_with_tasks):
        """--all without --force should prompt for confirmation."""
        ws, repo, created, _ = workspace_with_tasks

        # Simulate 'n' response
        result = runner.invoke(
            app,
            ["tasks", "delete", "--all", "-w", str(repo)],
            input="n\n",
        )

        assert result.exit_code == 0
        assert "Cancelled" in result.output

        # Tasks should still exist
        remaining = tasks.list_tasks(ws)
        assert len(remaining) == 3


class TestTasksDeleteErrors:
    """Test error handling for delete command."""

    def test_delete_no_args(self, runner, workspace_with_tasks):
        """Should error when no task ID or --all provided."""
        ws, repo, _, _ = workspace_with_tasks

        result = runner.invoke(
            app,
            ["tasks", "delete", "-w", str(repo)],
        )

        assert result.exit_code == 1
        assert "Specify a task ID or use --all" in result.output


class TestTasksGenerateOverwrite:
    """Test tasks generate --overwrite flag."""

    def test_generate_overwrite_clears_existing(self, runner, workspace_with_tasks):
        """--overwrite should delete existing tasks before generating."""
        ws, repo, created, prd_file = workspace_with_tasks

        # Verify we have 3 tasks
        assert len(tasks.list_tasks(ws)) == 3

        result = runner.invoke(
            app,
            ["tasks", "generate", "--overwrite", "--no-llm", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Cleared 3 existing tasks" in result.output
        assert "Generated" in result.output

        # Should still have 3 tasks (regenerated)
        final_tasks = tasks.list_tasks(ws)
        assert len(final_tasks) == 3

    def test_generate_without_overwrite_appends(self, runner, workspace_with_tasks):
        """Without --overwrite, tasks should be appended."""
        ws, repo, created, prd_file = workspace_with_tasks

        # Verify we have 3 tasks
        assert len(tasks.list_tasks(ws)) == 3

        result = runner.invoke(
            app,
            ["tasks", "generate", "--no-llm", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Cleared" not in result.output

        # Should have 6 tasks (3 original + 3 new)
        final_tasks = tasks.list_tasks(ws)
        assert len(final_tasks) == 6

    def test_generate_overwrite_empty_workspace(self, runner, tmp_path):
        """--overwrite on empty workspace should not error."""
        repo = tmp_path / "test_repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        ws = workspace.create_or_load_workspace(repo)

        # Add a PRD
        prd_content = """# Test PRD
## Tasks
- Task 1: Only task
"""
        prd_file = tmp_path / "test.md"
        prd_file.write_text(prd_content)
        prd.store(ws, prd_content, source_path=prd_file)

        result = runner.invoke(
            app,
            ["tasks", "generate", "--overwrite", "--no-llm", "-w", str(repo)],
        )

        assert result.exit_code == 0
        assert "Cleared" not in result.output  # No tasks to clear
        assert "Generated 1 tasks" in result.output


class TestCoreTasksDelete:
    """Test core tasks.delete and tasks.delete_all functions."""

    def test_delete_returns_true_on_success(self, workspace_with_tasks):
        """delete() should return True when task is deleted."""
        ws, repo, created, _ = workspace_with_tasks
        task = created[0]

        result = tasks.delete(ws, task.id)
        assert result is True

    def test_delete_returns_false_on_not_found(self, workspace_with_tasks):
        """delete() should return False when task doesn't exist."""
        ws, repo, created, _ = workspace_with_tasks

        result = tasks.delete(ws, "nonexistent-id")
        assert result is False

    def test_delete_all_returns_count(self, workspace_with_tasks):
        """delete_all() should return count of deleted tasks."""
        ws, repo, created, _ = workspace_with_tasks

        count = tasks.delete_all(ws)
        assert count == 3

    def test_delete_all_on_empty_returns_zero(self, tmp_path):
        """delete_all() on empty workspace should return 0."""
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        ws = workspace.create_or_load_workspace(repo)

        count = tasks.delete_all(ws)
        assert count == 0
