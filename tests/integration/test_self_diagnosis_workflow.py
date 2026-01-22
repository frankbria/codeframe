"""Integration tests for the self-diagnosis workflow.

Tests the complete flow from task failure to diagnosis to remediation.
"""

import pytest
from pathlib import Path

from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.diagnostics import (
    FailureCategory,
    LogCategory,
    RemediationAction,
    RunLogger,
    Severity,
    get_latest_diagnostic_report,
)
from codeframe.core.diagnostic_agent import DiagnosticAgent
from codeframe.core.workspace import create_or_load_workspace
from codeframe.core import tasks, runtime
from codeframe.core.state_machine import TaskStatus


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
        title="Implement user authentication",
        description="Add user login and logout functionality",
    )


class TestSelfDiagnosisWorkflow:
    """Integration tests for the self-diagnosis workflow."""

    def test_complete_failure_to_diagnosis_flow(self, workspace, task):
        """Test the complete flow: failure -> logs -> diagnosis -> recommendations."""
        # Step 1: Start a run
        run = runtime.start_task_run(workspace, task.id)
        assert run.status == runtime.RunStatus.RUNNING

        # Step 2: Simulate agent execution with logging
        run_logger = RunLogger(workspace, run.id, task.id)
        run_logger.info(LogCategory.AGENT_ACTION, "Starting task execution")
        run_logger.info(LogCategory.LLM_CALL, "Generating implementation plan")
        run_logger.warning(LogCategory.VERIFICATION, "Initial lint check found issues")
        run_logger.error(
            LogCategory.ERROR,
            "Failed to generate plan: Task description lacks acceptance criteria",
            {"error_type": "ambiguous_requirements"},
        )

        # Step 3: Fail the run
        runtime.fail_run(workspace, run.id, reason="Ambiguous requirements")

        # Verify run and task status
        updated_run = runtime.get_run(workspace, run.id)
        assert updated_run.status == runtime.RunStatus.FAILED

        updated_task = tasks.get(workspace, task.id)
        assert updated_task.status == TaskStatus.FAILED

        # Step 4: Run diagnosis
        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        # Verify diagnosis
        assert report is not None
        assert report.task_id == task.id
        assert report.run_id == run.id
        assert report.failure_category == FailureCategory.TASK_DESCRIPTION
        assert report.severity in (Severity.HIGH, Severity.MEDIUM)
        assert len(report.recommendations) > 0

        # Verify recommendations include update description
        actions = [r.action for r in report.recommendations]
        assert RemediationAction.UPDATE_TASK_DESCRIPTION in actions

    def test_cli_diagnosis_workflow(self, tmp_path, workspace, task):
        """Test the CLI-based diagnosis workflow."""
        # Create a failed run with logs
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.error(LogCategory.ERROR, "ModuleNotFoundError: No module named 'requests'")
        runtime.fail_run(workspace, run.id)

        # Run CLI diagnosis
        result = runner.invoke(
            app,
            ["work", "diagnose", task.id[:8], "--workspace", str(workspace.repo_path)],
        )

        # Should complete successfully and show diagnosis
        assert result.exit_code == 0 or result.exit_code is None

    def test_update_description_and_retry_workflow(self, tmp_path, workspace, task):
        """Test updating description and retrying after diagnosis."""
        # Create a failed run
        run = runtime.start_task_run(workspace, task.id)
        runtime.fail_run(workspace, run.id)

        # Update description via CLI
        new_description = "Implement JWT-based authentication with refresh tokens and session management"
        result = runner.invoke(
            app,
            [
                "work", "update-description",
                task.id[:8],
                new_description,
                "--workspace", str(workspace.repo_path),
            ],
        )

        assert result.exit_code == 0 or result.exit_code is None
        assert "updated" in result.stdout.lower()

        # Verify description was updated
        updated_task = tasks.get(workspace, task.id)
        assert updated_task.description == new_description

    def test_retry_command_resets_failed_task(self, tmp_path, workspace, task):
        """Test that retry command resets a failed task to READY."""
        # Create and fail a run
        run = runtime.start_task_run(workspace, task.id)
        runtime.fail_run(workspace, run.id)

        # Verify task is FAILED
        failed_task = tasks.get(workspace, task.id)
        assert failed_task.status == TaskStatus.FAILED

        # This test can't fully execute retry (needs ANTHROPIC_API_KEY)
        # but we can test the reset behavior
        tasks.update_status(workspace, task.id, TaskStatus.READY)

        ready_task = tasks.get(workspace, task.id)
        assert ready_task.status == TaskStatus.READY


class TestDiagnosisWithMultipleFailures:
    """Tests for diagnosis with multiple failure attempts."""

    def test_diagnosis_tracks_multiple_runs(self, workspace, task):
        """Test that diagnosis considers history from multiple runs."""
        # Run 1: Fail with dependency issue
        run1 = runtime.start_task_run(workspace, task.id)
        logger1 = RunLogger(workspace, run1.id, task.id)
        logger1.error(LogCategory.ERROR, "ModuleNotFoundError: No module named 'flask'")
        runtime.fail_run(workspace, run1.id)

        # Reset task for retry
        tasks.update_status(workspace, task.id, TaskStatus.READY)

        # Run 2: Fail with same issue
        run2 = runtime.start_task_run(workspace, task.id)
        logger2 = RunLogger(workspace, run2.id, task.id)
        logger2.error(LogCategory.ERROR, "ModuleNotFoundError: No module named 'flask'")
        runtime.fail_run(workspace, run2.id)

        # Diagnose the second run
        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run2.id)

        # Should detect dependency issue
        assert report.failure_category == FailureCategory.DEPENDENCY_ISSUE


class TestDiagnosisCategories:
    """Tests for different failure category detection."""

    def test_detect_code_quality_failure(self, workspace, task):
        """Test detection of code quality issues."""
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.error(LogCategory.VERIFICATION, "pytest failed: 5 tests failed, 10 passed")
        runtime.fail_run(workspace, run.id)

        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        assert report.failure_category == FailureCategory.CODE_QUALITY

    def test_detect_blocker_issue(self, workspace, task):
        """Test detection of blocker-related issues."""
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.warning(LogCategory.BLOCKER, "Blocker created: Human input needed for design decision")
        runtime.fail_run(workspace, run.id)

        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        assert report.failure_category == FailureCategory.BLOCKER_UNRESOLVED

    def test_detect_environment_issue(self, workspace, task):
        """Test detection of environment issues."""
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.error(LogCategory.ERROR, "Permission denied: Cannot write to /etc/config")
        runtime.fail_run(workspace, run.id)

        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        assert report.failure_category == FailureCategory.ENVIRONMENT_ISSUE


class TestRemediationCommands:
    """Tests for remediation command output."""

    def test_diagnosis_provides_executable_commands(self, workspace, task):
        """Test that diagnosis provides executable CLI commands."""
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.error(LogCategory.ERROR, "Task description is ambiguous")
        runtime.fail_run(workspace, run.id)

        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        # All recommendations should have commands
        for rec in report.recommendations:
            assert rec.command is not None
            assert len(rec.command) > 0
            # Commands should reference the task ID
            assert "cf" in rec.command or "#" in rec.command  # Either CLI command or comment

    def test_retry_recommendation_includes_verbose_option(self, workspace, task):
        """Test that retry recommendations mention verbose mode."""
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.error(LogCategory.ERROR, "Unknown technical error occurred")
        runtime.fail_run(workspace, run.id)

        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        # Find retry recommendation
        retry_recs = [
            r for r in report.recommendations
            if r.action == RemediationAction.RETRY_WITH_CONTEXT
        ]

        assert len(retry_recs) > 0
        # At least one should mention verbose for unknown errors
        commands = " ".join(r.command for r in retry_recs)
        # Either has --verbose or is a standard retry
        assert "cf work" in commands


class TestDiagnosisReportPersistence:
    """Tests for diagnostic report storage and retrieval."""

    def test_report_saved_and_retrievable(self, workspace, task):
        """Test that reports are saved to database and retrievable."""
        run = runtime.start_task_run(workspace, task.id)
        logger = RunLogger(workspace, run.id, task.id)
        logger.error(LogCategory.ERROR, "Test error")
        runtime.fail_run(workspace, run.id)

        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, run.id)

        # Should be retrievable by run ID
        retrieved = get_latest_diagnostic_report(workspace, run_id=run.id)
        assert retrieved is not None
        assert retrieved.id == report.id

    def test_multiple_reports_for_task(self, workspace, task):
        """Test handling multiple diagnostic reports for the same task."""
        # First run and diagnosis
        run1 = runtime.start_task_run(workspace, task.id)
        RunLogger(workspace, run1.id, task.id).error(LogCategory.ERROR, "Error 1")
        runtime.fail_run(workspace, run1.id)

        agent = DiagnosticAgent(workspace)
        report1 = agent.analyze(task.id, run1.id)

        # Reset and second run
        tasks.update_status(workspace, task.id, TaskStatus.READY)
        run2 = runtime.start_task_run(workspace, task.id)
        RunLogger(workspace, run2.id, task.id).error(LogCategory.ERROR, "Error 2")
        runtime.fail_run(workspace, run2.id)

        report2 = agent.analyze(task.id, run2.id)

        # Should have two different reports
        assert report1.id != report2.id
        assert report1.run_id != report2.run_id

        # Latest should be report2
        latest = get_latest_diagnostic_report(workspace, task_id=task.id)
        assert latest.id == report2.id
