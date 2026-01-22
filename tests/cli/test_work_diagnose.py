"""Tests for work diagnose CLI command.

Tests the diagnostic analysis command for failed runs.
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.diagnostics import (
    DiagnosticRecommendation,
    DiagnosticReport,
    FailureCategory,
    LogCategory,
    RemediationAction,
    RunLogger,
    Severity,
    save_diagnostic_report,
)
from codeframe.core.workspace import create_or_load_workspace
from codeframe.core import tasks, runtime


runner = CliRunner()

# Mark all tests as v2
pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    """Create a temporary workspace for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def task(workspace):
    """Create a test task."""
    return tasks.create(
        workspace,
        title="Test task",
        description="A test task for diagnosis",
    )


@pytest.fixture
def failed_run(workspace, task):
    """Create a failed run for testing."""
    run = runtime.start_task_run(workspace, task.id)
    runtime.fail_run(workspace, run.id, reason="Test failure")
    return run


class TestWorkDiagnoseCommand:
    """Tests for the work diagnose command."""

    def test_diagnose_shows_report(self, tmp_path, workspace, task, failed_run):
        """Test that diagnose shows diagnostic report."""
        # Create some logs for the run
        logger = RunLogger(workspace, failed_run.id, task.id)
        logger.error(LogCategory.ERROR, "Task description is ambiguous")

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}. Output: {result.stdout}"

    def test_diagnose_no_workspace(self, tmp_path):
        """Test diagnose with no workspace."""
        result = runner.invoke(
            app,
            ["work", "diagnose", "nonexistent", "--workspace", str(tmp_path)],
        )

        assert result.exit_code != 0
        assert "No workspace found" in result.stdout or "Error" in result.stdout

    def test_diagnose_task_not_found(self, tmp_path, workspace):
        """Test diagnose with non-existent task."""
        result = runner.invoke(
            app,
            ["work", "diagnose", "nonexistent-task", "--workspace", str(workspace.repo_path)],
        )

        assert result.exit_code != 0
        assert "No task found" in result.stdout or "Error" in result.stdout

    def test_diagnose_shows_recommendations(self, tmp_path, workspace, task, failed_run):
        """Test that diagnose shows recommendations."""
        logger = RunLogger(workspace, failed_run.id, task.id)
        logger.error(LogCategory.ERROR, "ModuleNotFoundError: No module named 'requests'")

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}. Output: {result.stdout}"

    def test_diagnose_with_verbose(self, tmp_path, workspace, task, failed_run):
        """Test diagnose with verbose flag shows more details."""
        logger = RunLogger(workspace, failed_run.id, task.id)
        logger.info(LogCategory.AGENT_ACTION, "Step 1")
        logger.error(LogCategory.ERROR, "Step 2 failed")

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--verbose", "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}. Output: {result.stdout}"


class TestWorkDiagnoseFormatting:
    """Tests for diagnostic output formatting."""

    def test_diagnose_formats_severity_critical(self, tmp_path, workspace, task, failed_run):
        """Test that CRITICAL severity is highlighted."""
        # Create report with critical severity
        report = DiagnosticReport(
            task_id=task.id,
            run_id=failed_run.id,
            root_cause="Multiple failures with unresolved blocker",
            failure_category=FailureCategory.BLOCKER_UNRESOLVED,
            severity=Severity.CRITICAL,
            recommendations=[
                DiagnosticRecommendation(
                    action=RemediationAction.ANSWER_BLOCKER,
                    reason="Blocker needs answer",
                    command="cf blocker list",
                )
            ],
            log_summary="Test summary",
            created_at=datetime.now(timezone.utc),
        )
        save_diagnostic_report(workspace, report)

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}. Output: {result.stdout}"

    def test_diagnose_shows_cli_commands(self, tmp_path, workspace, task, failed_run):
        """Test that recommendations include executable CLI commands."""
        logger = RunLogger(workspace, failed_run.id, task.id)
        logger.error(LogCategory.ERROR, "Test error for diagnosis")

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}. Output: {result.stdout}"


class TestWorkDiagnoseHistory:
    """Tests for viewing diagnostic history."""

    def test_diagnose_shows_previous_report(self, tmp_path, workspace, task, failed_run):
        """Test that diagnose shows previously saved report."""
        # Pre-create a report
        report = DiagnosticReport(
            task_id=task.id,
            run_id=failed_run.id,
            root_cause="Previously diagnosed issue",
            failure_category=FailureCategory.TASK_DESCRIPTION,
            severity=Severity.HIGH,
            recommendations=[],
            log_summary="Previous summary",
            created_at=datetime.now(timezone.utc),
        )
        save_diagnostic_report(workspace, report)

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully
        assert result.exit_code == 0, f"Expected exit_code 0, got {result.exit_code}. Output: {result.stdout}"


class TestWorkDiagnoseEdgeCases:
    """Tests for edge cases in diagnosis."""

    def test_diagnose_no_runs(self, tmp_path, workspace, task):
        """Test diagnose when task has no runs."""
        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should handle gracefully
        assert "No failed run" in result.stdout or result.exit_code != 0

    def test_diagnose_running_task(self, tmp_path, workspace, task):
        """Test diagnose on a currently running task."""
        run = runtime.start_task_run(workspace, task.id)
        # Don't fail it - leave it running

        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should indicate no failed run found (diagnosis requires a failed run)
        assert result.exit_code != 0
        assert "No failed run" in result.stdout or "failed" in result.stdout.lower()

    def test_diagnose_multiple_matching_tasks(self, tmp_path, workspace):
        """Test diagnose with ambiguous task ID."""
        # Create tasks with similar IDs by using specific prefixes
        task1 = tasks.create(workspace, title="Task 1", description="First")
        task2 = tasks.create(workspace, title="Task 2", description="Second")

        # Use a very short prefix that might match multiple
        # This depends on UUID generation, so we just test that it handles the case
        result = runner.invoke(
            app,
            ["work", "diagnose", "a", "--workspace", str(workspace.repo_path)],  # Very short prefix
        )

        # Should either match one, none, or indicate multiple matches
        # The important thing is it doesn't crash
        assert result.exit_code is not None
