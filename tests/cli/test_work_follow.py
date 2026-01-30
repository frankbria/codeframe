"""Tests for the `cf work follow` CLI command.

Tests for real-time execution streaming of individual task runs.
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch
import threading
import time

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace, Workspace
from codeframe.core import tasks


# Mark all tests in this module as v2 tests (CLI-first, headless functionality)
pytestmark = pytest.mark.v2


runner = CliRunner()


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    """Create a temporary workspace with a task."""
    workspace = create_or_load_workspace(tmp_path)
    return workspace


@pytest.fixture
def task_with_run(temp_workspace: Workspace):
    """Create a task with an active run."""
    from codeframe.core import runtime

    task = tasks.create(temp_workspace, title="Test task for follow")
    run = runtime.start_task_run(temp_workspace, task.id)
    return task, run, temp_workspace


class TestWorkFollowCommand:
    """Tests for cf work follow command."""

    def test_follow_requires_task_id(self, tmp_path: Path):
        """Follow command should require a task ID argument."""
        result = runner.invoke(app, ["work", "follow"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage" in result.output

    def test_follow_shows_error_for_nonexistent_task(self, temp_workspace: Workspace):
        """Should show error when task doesn't exist."""
        result = runner.invoke(
            app,
            ["work", "follow", "nonexistent", "--workspace", str(temp_workspace.repo_path)],
        )
        assert result.exit_code != 0
        assert "No task found" in result.output or "Error" in result.output

    def test_follow_shows_error_for_no_active_run(self, temp_workspace: Workspace):
        """Should show message when task has no active run."""
        task = tasks.create(temp_workspace, title="Task without run")

        result = runner.invoke(
            app,
            ["work", "follow", task.id[:8], "--workspace", str(temp_workspace.repo_path)],
        )

        # Should indicate no active run
        assert "No active run" in result.output or "not running" in result.output.lower()

    def test_follow_shows_completed_run_output(self, temp_workspace: Workspace):
        """Should show final output for completed runs."""
        from codeframe.core import runtime
        from codeframe.core.streaming import RunOutputLogger

        # Create task and run
        task = tasks.create(temp_workspace, title="Completed task")
        run = runtime.start_task_run(temp_workspace, task.id)

        # Write some output
        with RunOutputLogger(temp_workspace, run.id) as logger:
            logger.write("Step 1 completed\n")
            logger.write("Step 2 completed\n")
            logger.write("Task finished successfully\n")

        # Complete the run
        runtime.complete_run(temp_workspace, run.id)

        result = runner.invoke(
            app,
            ["work", "follow", task.id[:8], "--workspace", str(temp_workspace.repo_path)],
        )

        # Should show completion message
        assert result.exit_code == 0
        assert "completed" in result.output.lower() or "finished" in result.output.lower()

    def test_follow_with_tail_shows_buffered_output(self, task_with_run):
        """Should show last N lines when --tail is specified."""
        task, run, workspace = task_with_run
        from codeframe.core.streaming import RunOutputLogger
        from codeframe.core import runtime

        # Write output
        with RunOutputLogger(workspace, run.id) as logger:
            for i in range(10):
                logger.write(f"Line {i}\n")

        # Complete the run so follow doesn't wait
        runtime.complete_run(workspace, run.id)

        result = runner.invoke(
            app,
            [
                "work", "follow", task.id[:8],
                "--tail", "3",
                "--workspace", str(workspace.repo_path)
            ],
        )

        assert result.exit_code == 0
        # Should show last 3 lines
        assert "Line 7" in result.output or "Line 8" in result.output or "Line 9" in result.output

    def test_follow_streams_output_for_active_run(self, task_with_run):
        """Should stream output while run is active."""
        task, run, workspace = task_with_run
        from codeframe.core.streaming import RunOutputLogger
        from codeframe.core import runtime

        # This test simulates real-time streaming
        # Write output in a separate thread while follow is running

        output_collected = []

        def writer_thread():
            time.sleep(0.2)
            with RunOutputLogger(workspace, run.id) as logger:
                logger.write("First line\n")
                time.sleep(0.2)
                logger.write("Second line\n")
                time.sleep(0.2)
                runtime.complete_run(workspace, run.id)

        thread = threading.Thread(target=writer_thread)
        thread.start()

        result = runner.invoke(
            app,
            [
                "work", "follow", task.id[:8],
                "--workspace", str(workspace.repo_path),
                "--timeout", "3",  # Short timeout for test
            ],
        )

        thread.join(timeout=5)

        # Should have captured some output
        assert "First line" in result.output or "Second line" in result.output

    def test_follow_handles_ctrl_c_gracefully(self, task_with_run):
        """Should handle keyboard interrupt gracefully."""
        task, run, workspace = task_with_run

        # Mock KeyboardInterrupt during streaming
        with patch('codeframe.core.streaming.tail_run_output') as mock_tail:
            def raise_interrupt():
                yield "Test line\n"
                raise KeyboardInterrupt()

            mock_tail.return_value = raise_interrupt()

            result = runner.invoke(
                app,
                [
                    "work", "follow", task.id[:8],
                    "--workspace", str(workspace.repo_path),
                ],
                catch_exceptions=False,
            )

            # Should exit cleanly with interrupt message
            assert "interrupt" in result.output.lower() or "cancelled" in result.output.lower() or result.exit_code == 0


class TestWorkFollowOutput:
    """Tests for follow output formatting."""

    def test_output_includes_timestamps(self, task_with_run):
        """Output should include timestamps when available."""
        task, run, workspace = task_with_run
        from codeframe.core.streaming import RunOutputLogger
        from codeframe.core import runtime

        with RunOutputLogger(workspace, run.id) as logger:
            logger.write_timestamped("Step started")

        runtime.complete_run(workspace, run.id)

        result = runner.invoke(
            app,
            ["work", "follow", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should show timestamp format [HH:MM:SS]
        assert "[" in result.output and "]" in result.output

    def test_shows_task_info_on_attach(self, task_with_run):
        """Should show task info when attaching to a run."""
        task, run, workspace = task_with_run
        from codeframe.core import runtime

        runtime.complete_run(workspace, run.id)

        result = runner.invoke(
            app,
            ["work", "follow", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should show task title or ID
        assert task.title in result.output or task.id[:8] in result.output


class TestWorkFollowWithEvents:
    """Tests for follow command with run completion."""

    def test_follow_shows_run_completion(self, task_with_run):
        """Should show completion message when run finishes."""
        task, run, workspace = task_with_run
        from codeframe.core import runtime
        from codeframe.core.streaming import RunOutputLogger

        # Write some output
        with RunOutputLogger(workspace, run.id) as logger:
            logger.write("Processing task...\n")

        runtime.complete_run(workspace, run.id)

        result = runner.invoke(
            app,
            [
                "work", "follow", task.id[:8],
                "--workspace", str(workspace.repo_path),
            ],
        )

        # Should show completion information
        assert "completed" in result.output.lower()
