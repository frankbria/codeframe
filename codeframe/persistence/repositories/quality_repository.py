"""Repository for Quality Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import logging

import aiosqlite

from codeframe.core.models import (
    ProjectStatus,
    ProjectPhase,
    SourceType,
    Project,
    Task,
    TaskStatus,
    AgentMaturity,
    Issue,
    IssueWithTaskCount,
    CallType,
)
from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class QualityRepository(BaseRepository):
    """Repository for quality repository operations."""


    def update_quality_gate_status(
        self,
        task_id: int,
        status: str,
        failures: List["QualityGateFailure"],
    ) -> None:
        """Update task quality gate status and failures.

        This method is called by QualityGates after running all gates to store
        the results in the tasks table. The status is stored in quality_gate_status
        column and failures are stored as JSON in quality_gate_failures column.

        Args:
            task_id: Task ID to update
            status: Gate status - 'pending', 'running', 'passed', or 'failed'
            failures: List of QualityGateFailure objects (empty if passed)

        Example:
            >>> from codeframe.core.models import QualityGateFailure, QualityGateType, Severity
            >>> failure = QualityGateFailure(
            ...     gate=QualityGateType.TESTS,
            ...     reason="2 tests failed",
            ...     severity=Severity.HIGH
            ... )
            >>> db.update_quality_gate_status(task_id=123, status='failed', failures=[failure])
        """

        cursor = self.conn.cursor()

        # Serialize failures to JSON
        failures_json = json.dumps(
            [
                {
                    "gate": f.gate.value if hasattr(f.gate, "value") else f.gate,
                    "reason": f.reason,
                    "details": f.details,
                    "severity": f.severity.value if hasattr(f.severity, "value") else f.severity,
                }
                for f in failures
            ]
        )

        cursor.execute(
            """
            UPDATE tasks
            SET quality_gate_status = ?,
                quality_gate_failures = ?
            WHERE id = ?
            """,
            (status, failures_json, task_id),
        )
        self.conn.commit()

        logger.info(
            f"Updated quality gate status for task {task_id}: "
            f"status={status}, failures={len(failures)}"
        )



    def get_quality_gate_status(self, task_id: int) -> Dict[str, Any]:
        """Get quality gate status for a task.

        Args:
            task_id: Task ID to query

        Returns:
            Dictionary with keys:
            - status: Gate status ('pending', 'running', 'passed', 'failed', or None)
            - failures: List of failure dictionaries (empty if passed or None if not run)
            - requires_human_approval: Boolean indicating if task requires approval

        Example:
            >>> result = db.get_quality_gate_status(task_id=123)
            >>> if result['status'] == 'failed':
            ...     for failure in result['failures']:
            ...         print(f"{failure['gate']}: {failure['reason']}")
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT quality_gate_status, quality_gate_failures, requires_human_approval
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        row = cursor.fetchone()

        if not row:
            return {
                "status": None,
                "failures": [],
                "requires_human_approval": False,
            }

        status, failures_json, requires_approval = row

        # Parse failures JSON
        failures = []
        if failures_json:
            try:
                failures = json.loads(failures_json)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse quality_gate_failures JSON for task {task_id}")
                failures = []

        return {
            "status": status,
            "failures": failures,
            "requires_human_approval": bool(requires_approval),
        }

