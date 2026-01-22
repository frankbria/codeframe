"""Diagnostics and run logging for CodeFRAME v2.

This module provides:
- RunLogger: Structured logging for agent runs
- DiagnosticReport: Analysis results for failed runs
- RemediationAction: Suggested actions to fix issues

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from codeframe.core.workspace import Workspace, get_db_connection


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# Enums
# =============================================================================


class LogLevel(str, Enum):
    """Log level for run log entries."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogCategory(str, Enum):
    """Category of log entry."""

    AGENT_ACTION = "agent_action"
    LLM_CALL = "llm_call"
    ERROR = "error"
    STATE_CHANGE = "state_change"
    VERIFICATION = "verification"
    BLOCKER = "blocker"
    FILE_OPERATION = "file_operation"
    SHELL_COMMAND = "shell_command"


class RemediationAction(str, Enum):
    """Types of remediation actions that can be recommended."""

    UPDATE_TASK_DESCRIPTION = "update_task_description"
    ANSWER_BLOCKER = "answer_blocker"
    CHANGE_MODEL = "change_model"
    RESOLVE_DEPENDENCY = "resolve_dependency"
    FIX_ENVIRONMENT = "fix_environment"
    RETRY_WITH_CONTEXT = "retry_with_context"
    SPLIT_TASK = "split_task"
    ADD_TEST_DATA = "add_test_data"


class FailureCategory(str, Enum):
    """Categories of failure for diagnostic analysis."""

    TASK_DESCRIPTION = "task_description"
    BLOCKER_UNRESOLVED = "blocker_unresolved"
    MODEL_LIMITATION = "model_limitation"
    CODE_QUALITY = "code_quality"
    DEPENDENCY_ISSUE = "dependency_issue"
    ENVIRONMENT_ISSUE = "environment_issue"
    TECHNICAL_ERROR = "technical_error"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Severity level for diagnostic reports."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class RunLogEntry:
    """A single log entry for a run.

    Attributes:
        id: Unique entry identifier (auto-assigned from DB)
        run_id: Run this entry belongs to
        task_id: Task being executed
        timestamp: When the entry was created
        log_level: Severity level
        category: Type of log entry
        message: Human-readable message
        metadata: Additional structured data (JSON serializable)
    """

    run_id: str
    task_id: str
    timestamp: datetime
    log_level: LogLevel
    category: LogCategory
    message: str
    metadata: Optional[dict[str, Any]] = None
    id: Optional[int] = None


@dataclass
class DiagnosticRecommendation:
    """A single remediation recommendation.

    Attributes:
        action: Type of remediation action
        reason: Why this action is recommended
        command: CLI command to execute this action
        parameters: Parameters for the action
    """

    action: RemediationAction
    reason: str
    command: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticReport:
    """Analysis of a failed run with recommendations.

    Attributes:
        id: Unique report identifier (UUID)
        task_id: Task that failed
        run_id: Run that failed
        root_cause: Description of the root cause
        failure_category: Category of failure
        severity: How severe the issue is
        recommendations: List of recommended actions
        log_summary: Summary of relevant log entries
        created_at: When the report was created
    """

    task_id: str
    run_id: str
    root_cause: str
    failure_category: FailureCategory
    severity: Severity
    recommendations: list[DiagnosticRecommendation]
    log_summary: str
    created_at: datetime
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


# =============================================================================
# RunLogger Class
# =============================================================================


class RunLogger:
    """Structured logging for agent runs.

    Captures detailed information about agent execution for
    later analysis by the diagnostic system.

    Usage:
        logger = RunLogger(workspace, run_id, task_id)
        logger.info(LogCategory.AGENT_ACTION, "Starting planning phase")
        logger.error(LogCategory.ERROR, "Failed to create file", {"path": "main.py"})

        # Retrieve logs
        logs = get_run_logs(workspace, run_id)
    """

    def __init__(self, workspace: Workspace, run_id: str, task_id: str):
        """Initialize the run logger.

        Args:
            workspace: Target workspace
            run_id: ID of the run being logged
            task_id: ID of the task being executed
        """
        self.workspace = workspace
        self.run_id = run_id
        self.task_id = task_id
        self._buffer: list[RunLogEntry] = []
        self._auto_flush = True

    def log(
        self,
        level: LogLevel,
        category: LogCategory,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RunLogEntry:
        """Log an entry.

        Args:
            level: Log level
            category: Entry category
            message: Human-readable message
            metadata: Additional structured data

        Returns:
            The created log entry
        """
        entry = RunLogEntry(
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now(),
            log_level=level,
            category=category,
            message=message,
            metadata=metadata,
        )

        self._buffer.append(entry)

        if self._auto_flush:
            self.flush()

        return entry

    def debug(
        self,
        category: LogCategory,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RunLogEntry:
        """Log a DEBUG entry."""
        return self.log(LogLevel.DEBUG, category, message, metadata)

    def info(
        self,
        category: LogCategory,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RunLogEntry:
        """Log an INFO entry."""
        return self.log(LogLevel.INFO, category, message, metadata)

    def warning(
        self,
        category: LogCategory,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RunLogEntry:
        """Log a WARNING entry."""
        return self.log(LogLevel.WARNING, category, message, metadata)

    def error(
        self,
        category: LogCategory,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RunLogEntry:
        """Log an ERROR entry."""
        return self.log(LogLevel.ERROR, category, message, metadata)

    def flush(self) -> None:
        """Flush buffered entries to the database."""
        if not self._buffer:
            return

        conn = get_db_connection(self.workspace)
        try:
            cursor = conn.cursor()

            for entry in self._buffer:
                cursor.execute(
                    """
                    INSERT INTO run_logs (run_id, task_id, timestamp, log_level, category, message, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.run_id,
                        entry.task_id,
                        entry.timestamp.isoformat(),
                        entry.log_level.value,
                        entry.category.value,
                        entry.message,
                        json.dumps(entry.metadata) if entry.metadata else None,
                    ),
                )

            conn.commit()
            self._buffer.clear()
        finally:
            conn.close()

    def set_auto_flush(self, enabled: bool) -> None:
        """Enable or disable auto-flushing after each log entry.

        Args:
            enabled: Whether to auto-flush
        """
        self._auto_flush = enabled


# =============================================================================
# Run Log Functions
# =============================================================================


def get_run_logs(
    workspace: Workspace,
    run_id: str,
    level: Optional[LogLevel] = None,
    category: Optional[LogCategory] = None,
    limit: int = 1000,
) -> list[RunLogEntry]:
    """Get log entries for a run.

    Args:
        workspace: Target workspace
        run_id: Run to get logs for
        level: Optional level filter
        category: Optional category filter
        limit: Maximum entries to return

    Returns:
        List of log entries, oldest first
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()

        query = """
            SELECT id, run_id, task_id, timestamp, log_level, category, message, metadata
            FROM run_logs
            WHERE run_id = ?
        """
        params: list = [run_id]

        if level:
            query += " AND log_level = ?"
            params.append(level.value)

        if category:
            query += " AND category = ?"
            params.append(category.value)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [_row_to_log_entry(row) for row in rows]
    finally:
        conn.close()


def get_run_errors(workspace: Workspace, run_id: str, limit: int = 100) -> list[RunLogEntry]:
    """Get error log entries for a run.

    Args:
        workspace: Target workspace
        run_id: Run to get errors for
        limit: Maximum entries to return

    Returns:
        List of error entries, oldest first
    """
    return get_run_logs(workspace, run_id, level=LogLevel.ERROR, limit=limit)


def count_logs_by_level(workspace: Workspace, run_id: str) -> dict[str, int]:
    """Count log entries by level for a run.

    Args:
        workspace: Target workspace
        run_id: Run to count logs for

    Returns:
        Dict mapping level string to count
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT log_level, COUNT(*) as count
            FROM run_logs
            WHERE run_id = ?
            GROUP BY log_level
            """,
            (run_id,),
        )
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


def _row_to_log_entry(row: tuple) -> RunLogEntry:
    """Convert a database row to a RunLogEntry."""
    return RunLogEntry(
        id=row[0],
        run_id=row[1],
        task_id=row[2],
        timestamp=datetime.fromisoformat(row[3]),
        log_level=LogLevel(row[4]),
        category=LogCategory(row[5]),
        message=row[6],
        metadata=json.loads(row[7]) if row[7] else None,
    )


# =============================================================================
# Diagnostic Report Functions
# =============================================================================


def save_diagnostic_report(workspace: Workspace, report: DiagnosticReport) -> DiagnosticReport:
    """Save a diagnostic report to the database.

    Args:
        workspace: Target workspace
        report: Report to save

    Returns:
        The saved report (with ID if newly created)
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()

        # Serialize recommendations to JSON
        recommendations_json = json.dumps(
            [
                {
                    "action": r.action.value,
                    "reason": r.reason,
                    "command": r.command,
                    "parameters": r.parameters,
                }
                for r in report.recommendations
            ]
        )

        cursor.execute(
            """
            INSERT OR REPLACE INTO diagnostic_reports
            (id, task_id, run_id, root_cause, failure_category, severity, recommendations, log_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.id,
                report.task_id,
                report.run_id,
                report.root_cause,
                report.failure_category.value,
                report.severity.value,
                recommendations_json,
                report.log_summary,
                report.created_at.isoformat(),
            ),
        )
        conn.commit()

        return report
    finally:
        conn.close()


def get_diagnostic_report(workspace: Workspace, report_id: str) -> Optional[DiagnosticReport]:
    """Get a diagnostic report by ID.

    Args:
        workspace: Target workspace
        report_id: Report identifier

    Returns:
        DiagnosticReport if found, None otherwise
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, task_id, run_id, root_cause, failure_category, severity, recommendations, log_summary, created_at
            FROM diagnostic_reports
            WHERE id = ?
            """,
            (report_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return _row_to_diagnostic_report(row)
    finally:
        conn.close()


def get_latest_diagnostic_report(
    workspace: Workspace,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Optional[DiagnosticReport]:
    """Get the most recent diagnostic report.

    Args:
        workspace: Target workspace
        task_id: Optional task filter
        run_id: Optional run filter

    Returns:
        Most recent DiagnosticReport matching filters, or None
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()

        query = """
            SELECT id, task_id, run_id, root_cause, failure_category, severity, recommendations, log_summary, created_at
            FROM diagnostic_reports
            WHERE 1=1
        """
        params: list = []

        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)

        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)

        query += " ORDER BY created_at DESC LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()

        if not row:
            return None

        return _row_to_diagnostic_report(row)
    finally:
        conn.close()


def list_diagnostic_reports(
    workspace: Workspace,
    task_id: Optional[str] = None,
    limit: int = 20,
) -> list[DiagnosticReport]:
    """List diagnostic reports.

    Args:
        workspace: Target workspace
        task_id: Optional task filter
        limit: Maximum reports to return

    Returns:
        List of reports, newest first
    """
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()

        query = """
            SELECT id, task_id, run_id, root_cause, failure_category, severity, recommendations, log_summary, created_at
            FROM diagnostic_reports
            WHERE 1=1
        """
        params: list = []

        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [_row_to_diagnostic_report(row) for row in rows]
    finally:
        conn.close()


def _row_to_diagnostic_report(row: tuple) -> DiagnosticReport:
    """Convert a database row to a DiagnosticReport."""
    recommendations_data = json.loads(row[6]) if row[6] else []
    recommendations = [
        DiagnosticRecommendation(
            action=RemediationAction(r["action"]),
            reason=r["reason"],
            command=r["command"],
            parameters=r.get("parameters", {}),
        )
        for r in recommendations_data
    ]

    return DiagnosticReport(
        id=row[0],
        task_id=row[1],
        run_id=row[2],
        root_cause=row[3],
        failure_category=FailureCategory(row[4]),
        severity=Severity(row[5]),
        recommendations=recommendations,
        log_summary=row[7],
        created_at=datetime.fromisoformat(row[8]),
    )
