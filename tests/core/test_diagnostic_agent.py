"""Tests for DiagnosticAgent.

Tests the LLM-powered diagnostic analysis of run failures.
"""

import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.diagnostics import (
    DiagnosticReport,
    FailureCategory,
    LogCategory,
    LogLevel,
    RemediationAction,
    RunLogger,
    Severity,
    get_run_logs,
    save_diagnostic_report,
)
from codeframe.core.workspace import create_or_load_workspace


@pytest.fixture
def workspace(tmp_path: Path):
    """Create a temporary workspace for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    return create_or_load_workspace(repo_path)


@pytest.fixture
def run_id():
    """Create a unique run ID."""
    return str(uuid.uuid4())


@pytest.fixture
def task_id():
    """Create a unique task ID."""
    return str(uuid.uuid4())


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    mock = MagicMock()
    mock.complete.return_value = MagicMock(
        content="""Based on the logs, the root cause is:

Root Cause: Task description lacks clear acceptance criteria
Failure Category: task_description
Severity: high

Recommendations:
1. UPDATE_TASK_DESCRIPTION: The task description should include specific acceptance criteria
   Command: cf tasks update {task_id} --description "Updated description with criteria"

2. RETRY_WITH_CONTEXT: After updating the description, retry the task
   Command: cf work start {task_id} --execute

Log Summary: Agent failed during planning phase due to ambiguous requirements."""
    )
    return mock


class TestDiagnosticAgentAnalyze:
    """Tests for DiagnosticAgent.analyze method."""

    def test_analyze_generates_report(self, workspace, run_id, task_id, mock_llm_provider):
        """Test that analyze generates a diagnostic report."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent

        # Create some test logs
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Starting planning phase")
        logger.error(
            LogCategory.ERROR,
            "Failed to generate plan",
            {"error": "Task description is ambiguous"},
        )

        agent = DiagnosticAgent(workspace, mock_llm_provider)
        report = agent.analyze(task_id, run_id)

        assert report is not None
        assert report.task_id == task_id
        assert report.run_id == run_id
        assert report.root_cause is not None
        assert len(report.root_cause) > 0

    def test_analyze_categorizes_failure(self, workspace, run_id, task_id, mock_llm_provider):
        """Test that analyze categorizes the failure correctly."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(LogCategory.ERROR, "Task description lacks acceptance criteria")

        agent = DiagnosticAgent(workspace, mock_llm_provider)
        report = agent.analyze(task_id, run_id)

        # The mock returns task_description category
        assert report.failure_category == FailureCategory.TASK_DESCRIPTION

    def test_analyze_includes_recommendations(self, workspace, run_id, task_id, mock_llm_provider):
        """Test that analyze includes actionable recommendations."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(LogCategory.ERROR, "Planning failed")

        agent = DiagnosticAgent(workspace, mock_llm_provider)
        report = agent.analyze(task_id, run_id)

        assert len(report.recommendations) > 0
        # Check that recommendations have required fields
        for rec in report.recommendations:
            assert rec.action is not None
            assert rec.reason is not None
            assert rec.command is not None

    def test_analyze_saves_report(self, workspace, run_id, task_id, mock_llm_provider):
        """Test that analyze saves the report to database."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent
        from codeframe.core.diagnostics import get_diagnostic_report

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(LogCategory.ERROR, "Test error")

        agent = DiagnosticAgent(workspace, mock_llm_provider)
        report = agent.analyze(task_id, run_id)

        # Verify saved to database
        saved = get_diagnostic_report(workspace, report.id)
        assert saved is not None
        assert saved.id == report.id

    def test_analyze_with_no_logs(self, workspace, run_id, task_id, mock_llm_provider):
        """Test analyze handles case with no logs gracefully."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent

        agent = DiagnosticAgent(workspace, mock_llm_provider)
        report = agent.analyze(task_id, run_id)

        # Should still generate a report
        assert report is not None
        assert report.log_summary is not None


class TestDiagnosticAgentPatternMatching:
    """Tests for pattern-based failure detection without LLM."""

    def test_detect_ambiguous_task_pattern(self, workspace, run_id, task_id):
        """Test detection of ambiguous task description pattern."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent, detect_failure_patterns

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(
            LogCategory.ERROR,
            "Cannot determine implementation approach - task description is unclear",
        )

        logs = get_run_logs(workspace, run_id)
        patterns = detect_failure_patterns(logs)

        assert FailureCategory.TASK_DESCRIPTION in patterns

    def test_detect_model_limitation_pattern(self, workspace, run_id, task_id):
        """Test detection of model/token limit pattern."""
        from codeframe.core.diagnostic_agent import detect_failure_patterns

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(
            LogCategory.ERROR,
            "Error: Maximum context length exceeded",
            {"tokens": 200000},
        )

        logs = get_run_logs(workspace, run_id)
        patterns = detect_failure_patterns(logs)

        assert FailureCategory.MODEL_LIMITATION in patterns

    def test_detect_dependency_pattern(self, workspace, run_id, task_id):
        """Test detection of dependency issue pattern."""
        from codeframe.core.diagnostic_agent import detect_failure_patterns

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(
            LogCategory.ERROR,
            "ModuleNotFoundError: No module named 'some_package'",
        )

        logs = get_run_logs(workspace, run_id)
        patterns = detect_failure_patterns(logs)

        assert FailureCategory.DEPENDENCY_ISSUE in patterns

    def test_detect_code_quality_pattern(self, workspace, run_id, task_id):
        """Test detection of code quality issue pattern."""
        from codeframe.core.diagnostic_agent import detect_failure_patterns

        logger = RunLogger(workspace, run_id, task_id)
        logger.error(
            LogCategory.VERIFICATION,
            "pytest failed: 3 tests failed",
            {"failed": 3, "passed": 10},
        )

        logs = get_run_logs(workspace, run_id)
        patterns = detect_failure_patterns(logs)

        assert FailureCategory.CODE_QUALITY in patterns


class TestDiagnosticAgentRecommendationGeneration:
    """Tests for recommendation generation logic."""

    def test_generate_update_description_recommendation(self, workspace, run_id, task_id):
        """Test generating UPDATE_TASK_DESCRIPTION recommendation."""
        from codeframe.core.diagnostic_agent import generate_recommendations

        recs = generate_recommendations(
            task_id=task_id,
            run_id=run_id,
            failure_category=FailureCategory.TASK_DESCRIPTION,
            error_messages=["Task description is ambiguous"],
        )

        update_rec = next(
            (r for r in recs if r.action == RemediationAction.UPDATE_TASK_DESCRIPTION),
            None,
        )
        assert update_rec is not None
        assert task_id in update_rec.command

    def test_generate_retry_recommendation(self, workspace, run_id, task_id):
        """Test generating RETRY_WITH_CONTEXT recommendation."""
        from codeframe.core.diagnostic_agent import generate_recommendations

        recs = generate_recommendations(
            task_id=task_id,
            run_id=run_id,
            failure_category=FailureCategory.TECHNICAL_ERROR,
            error_messages=["Transient network error"],
        )

        retry_rec = next(
            (r for r in recs if r.action == RemediationAction.RETRY_WITH_CONTEXT),
            None,
        )
        assert retry_rec is not None
        assert "cf work start" in retry_rec.command

    def test_generate_dependency_fix_recommendation(self, workspace, run_id, task_id):
        """Test generating RESOLVE_DEPENDENCY recommendation."""
        from codeframe.core.diagnostic_agent import generate_recommendations

        recs = generate_recommendations(
            task_id=task_id,
            run_id=run_id,
            failure_category=FailureCategory.DEPENDENCY_ISSUE,
            error_messages=["ModuleNotFoundError: No module named 'requests'"],
        )

        dep_rec = next(
            (r for r in recs if r.action == RemediationAction.RESOLVE_DEPENDENCY),
            None,
        )
        assert dep_rec is not None


class TestDiagnosticAgentSeverityAssessment:
    """Tests for severity assessment logic."""

    def test_critical_severity_for_repeated_failures(self, workspace, run_id, task_id):
        """Test that repeated failures get CRITICAL severity."""
        from codeframe.core.diagnostic_agent import assess_severity

        severity = assess_severity(
            failure_category=FailureCategory.TECHNICAL_ERROR,
            error_count=10,
            has_blocker=True,
        )

        assert severity == Severity.CRITICAL

    def test_high_severity_for_task_description_issues(self, workspace, run_id, task_id):
        """Test that task description issues get HIGH severity."""
        from codeframe.core.diagnostic_agent import assess_severity

        severity = assess_severity(
            failure_category=FailureCategory.TASK_DESCRIPTION,
            error_count=1,
            has_blocker=False,
        )

        assert severity == Severity.HIGH

    def test_medium_severity_for_code_quality(self, workspace, run_id, task_id):
        """Test that code quality issues get MEDIUM severity."""
        from codeframe.core.diagnostic_agent import assess_severity

        severity = assess_severity(
            failure_category=FailureCategory.CODE_QUALITY,
            error_count=2,
            has_blocker=False,
        )

        assert severity == Severity.MEDIUM

    def test_low_severity_for_transient_errors(self, workspace, run_id, task_id):
        """Test that single transient errors get LOW severity."""
        from codeframe.core.diagnostic_agent import assess_severity

        severity = assess_severity(
            failure_category=FailureCategory.TECHNICAL_ERROR,
            error_count=1,
            has_blocker=False,
        )

        assert severity == Severity.LOW


class TestDiagnosticAgentLogSummarization:
    """Tests for log summarization."""

    def test_summarize_logs(self, workspace, run_id, task_id):
        """Test summarizing logs into a human-readable format."""
        from codeframe.core.diagnostic_agent import summarize_logs

        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Step 1: Planning")
        logger.info(LogCategory.LLM_CALL, "Called Claude")
        logger.error(LogCategory.ERROR, "Step 2 failed: File not found")
        logger.info(LogCategory.AGENT_ACTION, "Step 3: Rollback")

        logs = get_run_logs(workspace, run_id)
        summary = summarize_logs(logs)

        assert "Step 1" in summary or "Planning" in summary
        assert "failed" in summary.lower() or "error" in summary.lower()

    def test_summarize_truncates_long_logs(self, workspace, run_id, task_id):
        """Test that summarization truncates very long logs."""
        from codeframe.core.diagnostic_agent import summarize_logs

        logger = RunLogger(workspace, run_id, task_id)
        for i in range(100):
            logger.info(LogCategory.AGENT_ACTION, f"Step {i}: " + "x" * 100)

        logs = get_run_logs(workspace, run_id)
        summary = summarize_logs(logs, max_length=500)

        assert len(summary) <= 500


class TestDiagnosticAgentIntegration:
    """Integration tests for the full diagnostic flow."""

    def test_full_diagnostic_flow(self, workspace, run_id, task_id, mock_llm_provider):
        """Test the complete diagnostic flow from logs to recommendations."""
        from codeframe.core.diagnostic_agent import DiagnosticAgent

        # Simulate a failed run with multiple log entries
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Starting task execution")
        logger.info(LogCategory.LLM_CALL, "Planning with Claude")
        logger.warning(LogCategory.VERIFICATION, "Initial lint check failed")
        logger.error(
            LogCategory.ERROR,
            "Task failed: Cannot understand requirements",
            {"step": 2, "phase": "planning"},
        )

        # Run diagnostic analysis
        agent = DiagnosticAgent(workspace, mock_llm_provider)
        report = agent.analyze(task_id, run_id)

        # Verify complete report
        assert report.task_id == task_id
        assert report.run_id == run_id
        assert report.root_cause is not None
        assert report.failure_category is not None
        assert report.severity is not None
        assert len(report.recommendations) > 0
        assert report.log_summary is not None
        assert report.created_at is not None
