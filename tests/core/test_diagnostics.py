"""Tests for diagnostics module.

Tests the RunLogger, diagnostic reports, and related functions.
"""

import json
import pytest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from codeframe.core.diagnostics import (
    DiagnosticRecommendation,
    DiagnosticReport,
    FailureCategory,
    LogCategory,
    LogLevel,
    RemediationAction,
    RunLogEntry,
    RunLogger,
    Severity,
    count_logs_by_level,
    get_diagnostic_report,
    get_latest_diagnostic_report,
    get_run_errors,
    get_run_logs,
    list_diagnostic_reports,
    save_diagnostic_report,
)
from codeframe.core.workspace import create_or_load_workspace, get_db_connection


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


class TestRunLogEntry:
    """Tests for RunLogEntry dataclass."""

    def test_create_entry(self, run_id, task_id):
        """Test creating a log entry."""
        entry = RunLogEntry(
            run_id=run_id,
            task_id=task_id,
            timestamp=datetime.now(timezone.utc),
            log_level=LogLevel.INFO,
            category=LogCategory.AGENT_ACTION,
            message="Starting task",
        )

        assert entry.run_id == run_id
        assert entry.task_id == task_id
        assert entry.log_level == LogLevel.INFO
        assert entry.category == LogCategory.AGENT_ACTION
        assert entry.message == "Starting task"
        assert entry.metadata is None
        assert entry.id is None

    def test_create_entry_with_metadata(self, run_id, task_id):
        """Test creating a log entry with metadata."""
        metadata = {"step": 1, "file": "main.py"}
        entry = RunLogEntry(
            run_id=run_id,
            task_id=task_id,
            timestamp=datetime.now(timezone.utc),
            log_level=LogLevel.DEBUG,
            category=LogCategory.FILE_OPERATION,
            message="Creating file",
            metadata=metadata,
        )

        assert entry.metadata == metadata


class TestRunLogger:
    """Tests for RunLogger class."""

    def test_create_logger(self, workspace, run_id, task_id):
        """Test creating a run logger."""
        logger = RunLogger(workspace, run_id, task_id)

        assert logger.workspace == workspace
        assert logger.run_id == run_id
        assert logger.task_id == task_id

    def test_log_info(self, workspace, run_id, task_id):
        """Test logging an INFO entry."""
        logger = RunLogger(workspace, run_id, task_id)

        entry = logger.info(LogCategory.AGENT_ACTION, "Starting planning phase")

        assert entry.log_level == LogLevel.INFO
        assert entry.category == LogCategory.AGENT_ACTION
        assert entry.message == "Starting planning phase"

    def test_log_error_with_metadata(self, workspace, run_id, task_id):
        """Test logging an ERROR entry with metadata."""
        logger = RunLogger(workspace, run_id, task_id)

        entry = logger.error(
            LogCategory.ERROR,
            "Failed to create file",
            {"path": "main.py", "error": "Permission denied"},
        )

        assert entry.log_level == LogLevel.ERROR
        assert entry.category == LogCategory.ERROR
        assert entry.metadata["path"] == "main.py"

    def test_log_levels(self, workspace, run_id, task_id):
        """Test all log level methods."""
        logger = RunLogger(workspace, run_id, task_id)

        debug = logger.debug(LogCategory.LLM_CALL, "Debug message")
        info = logger.info(LogCategory.AGENT_ACTION, "Info message")
        warning = logger.warning(LogCategory.VERIFICATION, "Warning message")
        error = logger.error(LogCategory.ERROR, "Error message")

        assert debug.log_level == LogLevel.DEBUG
        assert info.log_level == LogLevel.INFO
        assert warning.log_level == LogLevel.WARNING
        assert error.log_level == LogLevel.ERROR

    def test_auto_flush(self, workspace, run_id, task_id):
        """Test that entries are automatically flushed to database."""
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Test message")

        # Retrieve from database
        logs = get_run_logs(workspace, run_id)

        assert len(logs) == 1
        assert logs[0].message == "Test message"

    def test_disable_auto_flush(self, workspace, run_id, task_id):
        """Test disabling auto-flush."""
        logger = RunLogger(workspace, run_id, task_id)
        logger.set_auto_flush(False)

        logger.info(LogCategory.AGENT_ACTION, "Test 1")
        logger.info(LogCategory.AGENT_ACTION, "Test 2")

        # Not flushed yet
        logs = get_run_logs(workspace, run_id)
        assert len(logs) == 0

        # Manual flush
        logger.flush()

        logs = get_run_logs(workspace, run_id)
        assert len(logs) == 2

    def test_multiple_entries(self, workspace, run_id, task_id):
        """Test logging multiple entries."""
        logger = RunLogger(workspace, run_id, task_id)

        logger.info(LogCategory.AGENT_ACTION, "Step 1")
        logger.info(LogCategory.LLM_CALL, "Calling LLM")
        logger.debug(LogCategory.FILE_OPERATION, "Creating file")
        logger.error(LogCategory.ERROR, "Something failed")

        logs = get_run_logs(workspace, run_id)

        assert len(logs) == 4
        # Verify order (oldest first)
        assert logs[0].message == "Step 1"
        assert logs[3].message == "Something failed"


class TestGetRunLogs:
    """Tests for get_run_logs function."""

    def test_get_logs_empty(self, workspace, run_id):
        """Test getting logs when none exist."""
        logs = get_run_logs(workspace, run_id)
        assert logs == []

    def test_get_logs_with_level_filter(self, workspace, run_id, task_id):
        """Test filtering logs by level."""
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Info 1")
        logger.error(LogCategory.ERROR, "Error 1")
        logger.info(LogCategory.AGENT_ACTION, "Info 2")

        errors = get_run_logs(workspace, run_id, level=LogLevel.ERROR)

        assert len(errors) == 1
        assert errors[0].message == "Error 1"

    def test_get_logs_with_category_filter(self, workspace, run_id, task_id):
        """Test filtering logs by category."""
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Action 1")
        logger.info(LogCategory.LLM_CALL, "LLM call")
        logger.info(LogCategory.AGENT_ACTION, "Action 2")

        actions = get_run_logs(workspace, run_id, category=LogCategory.AGENT_ACTION)

        assert len(actions) == 2
        assert all(log.category == LogCategory.AGENT_ACTION for log in actions)

    def test_get_logs_with_limit(self, workspace, run_id, task_id):
        """Test limiting log results."""
        logger = RunLogger(workspace, run_id, task_id)
        for i in range(10):
            logger.info(LogCategory.AGENT_ACTION, f"Message {i}")

        logs = get_run_logs(workspace, run_id, limit=5)

        assert len(logs) == 5


class TestGetRunErrors:
    """Tests for get_run_errors function."""

    def test_get_errors_only(self, workspace, run_id, task_id):
        """Test that only ERROR entries are returned."""
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Info message")
        logger.error(LogCategory.ERROR, "Error 1")
        logger.warning(LogCategory.VERIFICATION, "Warning")
        logger.error(LogCategory.ERROR, "Error 2")

        errors = get_run_errors(workspace, run_id)

        assert len(errors) == 2
        assert all(e.log_level == LogLevel.ERROR for e in errors)


class TestCountLogsByLevel:
    """Tests for count_logs_by_level function."""

    def test_count_logs(self, workspace, run_id, task_id):
        """Test counting logs by level."""
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Info 1")
        logger.info(LogCategory.AGENT_ACTION, "Info 2")
        logger.error(LogCategory.ERROR, "Error 1")
        logger.debug(LogCategory.LLM_CALL, "Debug 1")

        counts = count_logs_by_level(workspace, run_id)

        assert counts.get("INFO") == 2
        assert counts.get("ERROR") == 1
        assert counts.get("DEBUG") == 1
        assert counts.get("WARNING") is None


class TestDiagnosticRecommendation:
    """Tests for DiagnosticRecommendation dataclass."""

    def test_create_recommendation(self):
        """Test creating a recommendation."""
        rec = DiagnosticRecommendation(
            action=RemediationAction.UPDATE_TASK_DESCRIPTION,
            reason="Task description is ambiguous",
            command="cf tasks update 123 --description 'New description'",
            parameters={"task_id": "123"},
        )

        assert rec.action == RemediationAction.UPDATE_TASK_DESCRIPTION
        assert "ambiguous" in rec.reason
        assert "cf tasks update" in rec.command


class TestDiagnosticReport:
    """Tests for DiagnosticReport dataclass."""

    def test_create_report(self, task_id, run_id):
        """Test creating a diagnostic report."""
        report = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause="Task description lacks clear acceptance criteria",
            failure_category=FailureCategory.TASK_DESCRIPTION,
            severity=Severity.HIGH,
            recommendations=[
                DiagnosticRecommendation(
                    action=RemediationAction.UPDATE_TASK_DESCRIPTION,
                    reason="Add acceptance criteria",
                    command=f"cf tasks update {task_id} --description '...'",
                )
            ],
            log_summary="Agent failed during planning phase",
            created_at=datetime.now(timezone.utc),
        )

        assert report.task_id == task_id
        assert report.run_id == run_id
        assert report.failure_category == FailureCategory.TASK_DESCRIPTION
        assert len(report.recommendations) == 1

    def test_report_has_uuid(self, task_id, run_id):
        """Test that report gets a UUID automatically."""
        report = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause="Test",
            failure_category=FailureCategory.UNKNOWN,
            severity=Severity.LOW,
            recommendations=[],
            log_summary="",
            created_at=datetime.now(timezone.utc),
        )

        assert report.id is not None
        assert len(report.id) == 36  # UUID format


class TestSaveAndGetDiagnosticReport:
    """Tests for saving and retrieving diagnostic reports."""

    def test_save_and_get_report(self, workspace, task_id, run_id):
        """Test saving and retrieving a report."""
        report = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause="Test failure",
            failure_category=FailureCategory.TECHNICAL_ERROR,
            severity=Severity.MEDIUM,
            recommendations=[
                DiagnosticRecommendation(
                    action=RemediationAction.RETRY_WITH_CONTEXT,
                    reason="Transient error",
                    command=f"cf work start {task_id} --execute",
                )
            ],
            log_summary="Error in step 3",
            created_at=datetime.now(timezone.utc),
        )

        saved = save_diagnostic_report(workspace, report)
        retrieved = get_diagnostic_report(workspace, saved.id)

        assert retrieved is not None
        assert retrieved.id == report.id
        assert retrieved.root_cause == "Test failure"
        assert retrieved.failure_category == FailureCategory.TECHNICAL_ERROR
        assert len(retrieved.recommendations) == 1
        assert retrieved.recommendations[0].action == RemediationAction.RETRY_WITH_CONTEXT

    def test_get_nonexistent_report(self, workspace):
        """Test getting a report that doesn't exist."""
        report = get_diagnostic_report(workspace, "nonexistent-id")
        assert report is None

    def test_get_latest_report(self, workspace, task_id, run_id):
        """Test getting the most recent report."""
        # Create two reports
        report1 = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause="First failure",
            failure_category=FailureCategory.TECHNICAL_ERROR,
            severity=Severity.LOW,
            recommendations=[],
            log_summary="",
            created_at=datetime.now(timezone.utc),
        )
        save_diagnostic_report(workspace, report1)

        report2 = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause="Second failure",
            failure_category=FailureCategory.MODEL_LIMITATION,
            severity=Severity.HIGH,
            recommendations=[],
            log_summary="",
            created_at=datetime.now(timezone.utc),
        )
        save_diagnostic_report(workspace, report2)

        latest = get_latest_diagnostic_report(workspace, task_id=task_id)

        assert latest is not None
        assert latest.root_cause == "Second failure"

    def test_get_latest_report_by_run(self, workspace, task_id, run_id):
        """Test getting the latest report filtered by run."""
        run_id_2 = str(uuid.uuid4())

        report1 = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause="Run 1 failure",
            failure_category=FailureCategory.TECHNICAL_ERROR,
            severity=Severity.LOW,
            recommendations=[],
            log_summary="",
            created_at=datetime.now(timezone.utc),
        )
        save_diagnostic_report(workspace, report1)

        report2 = DiagnosticReport(
            task_id=task_id,
            run_id=run_id_2,
            root_cause="Run 2 failure",
            failure_category=FailureCategory.MODEL_LIMITATION,
            severity=Severity.HIGH,
            recommendations=[],
            log_summary="",
            created_at=datetime.now(timezone.utc),
        )
        save_diagnostic_report(workspace, report2)

        latest = get_latest_diagnostic_report(workspace, run_id=run_id)

        assert latest is not None
        assert latest.root_cause == "Run 1 failure"


class TestListDiagnosticReports:
    """Tests for list_diagnostic_reports function."""

    def test_list_reports(self, workspace, task_id, run_id):
        """Test listing reports."""
        # Create multiple reports
        for i in range(3):
            report = DiagnosticReport(
                task_id=task_id,
                run_id=run_id,
                root_cause=f"Failure {i}",
                failure_category=FailureCategory.UNKNOWN,
                severity=Severity.LOW,
                recommendations=[],
                log_summary="",
                created_at=datetime.now(timezone.utc),
            )
            save_diagnostic_report(workspace, report)

        reports = list_diagnostic_reports(workspace, task_id=task_id)

        assert len(reports) == 3

    def test_list_reports_with_limit(self, workspace, task_id, run_id):
        """Test listing reports with limit."""
        for i in range(5):
            report = DiagnosticReport(
                task_id=task_id,
                run_id=run_id,
                root_cause=f"Failure {i}",
                failure_category=FailureCategory.UNKNOWN,
                severity=Severity.LOW,
                recommendations=[],
                log_summary="",
                created_at=datetime.now(timezone.utc),
            )
            save_diagnostic_report(workspace, report)

        reports = list_diagnostic_reports(workspace, limit=3)

        assert len(reports) == 3


class TestEnums:
    """Tests for enum values."""

    def test_log_levels(self):
        """Test LogLevel enum values."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"

    def test_log_categories(self):
        """Test LogCategory enum values."""
        assert LogCategory.AGENT_ACTION.value == "agent_action"
        assert LogCategory.LLM_CALL.value == "llm_call"
        assert LogCategory.ERROR.value == "error"
        assert LogCategory.VERIFICATION.value == "verification"

    def test_remediation_actions(self):
        """Test RemediationAction enum values."""
        assert RemediationAction.UPDATE_TASK_DESCRIPTION.value == "update_task_description"
        assert RemediationAction.RETRY_WITH_CONTEXT.value == "retry_with_context"

    def test_failure_categories(self):
        """Test FailureCategory enum values."""
        assert FailureCategory.TASK_DESCRIPTION.value == "task_description"
        assert FailureCategory.MODEL_LIMITATION.value == "model_limitation"

    def test_severity_levels(self):
        """Test Severity enum values."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
