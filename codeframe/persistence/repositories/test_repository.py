"""Repository for Test Repository operations.

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


class TestRepository(BaseRepository):
    """Repository for test repository operations."""

    def create_test_result(
        self,
        task_id: int,
        status: str,
        passed: int = 0,
        failed: int = 0,
        errors: int = 0,
        skipped: int = 0,
        duration: float = 0.0,
        output: Optional[str] = None,
    ) -> int:
        """Create a test result record.

        Args:
            task_id: Task ID this result belongs to
            status: Test status (passed, failed, error, timeout, no_tests)
            passed: Number of tests that passed
            failed: Number of tests that failed
            errors: Number of tests with errors
            skipped: Number of tests skipped
            duration: Test execution duration in seconds
            output: Raw test output (JSON string or plain text)

        Returns:
            Test result ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO test_results (
                task_id, status, passed, failed, errors, skipped, duration, output
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, status, passed, failed, errors, skipped, duration, output),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_test_results_by_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Get all test results for a task.

        Args:
            task_id: Task ID

        Returns:
            List of test result dictionaries ordered by created_at (newest first)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM test_results
            WHERE task_id = ?
            ORDER BY created_at DESC
            """,
            (task_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Correction Attempts Methods (cf-43: Self-Correction Loop)

