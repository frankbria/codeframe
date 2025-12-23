"""Repository for Lint Repository operations.

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


class LintRepository(BaseRepository):
    """Repository for lint repository operations."""


    def create_lint_result(
        self,
        task_id: int,
        linter: str,
        error_count: int,
        warning_count: int,
        files_linted: int,
        output: str,
    ) -> int:
        """Store lint execution result.

        Args:
            task_id: Task ID
            linter: Linter tool name ('ruff', 'eslint', 'other')
            error_count: Number of errors
            warning_count: Number of warnings
            files_linted: Number of files checked
            output: Full lint output (JSON or text)

        Returns:
            Lint result ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO lint_results (task_id, linter, error_count, warning_count, files_linted, output)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, linter, error_count, warning_count, files_linted, output),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_lint_results_for_task(self, task_id: int) -> list[dict]:
        """Get all lint results for a task.

        Args:
            task_id: Task ID

        Returns:
            List of lint result dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, task_id, linter, error_count, warning_count, files_linted, output, created_at
            FROM lint_results
            WHERE task_id = ?
            ORDER BY created_at DESC
            """,
            (task_id,),
        )
        return [dict(row) for row in cursor.fetchall()]



    def get_lint_trend(self, project_id: int, days: int = 7) -> list[dict]:
        """Get lint error trend for project over time.

        Args:
            project_id: Project ID
            days: Number of days to look back

        Returns:
            List of {date, linter, error_count, warning_count} dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                DATE(lr.created_at) as date,
                lr.linter,
                SUM(lr.error_count) as error_count,
                SUM(lr.warning_count) as warning_count
            FROM lint_results lr
            JOIN tasks t ON lr.task_id = t.id
            WHERE t.project_id = ?
              AND lr.created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY DATE(lr.created_at), lr.linter
            ORDER BY date DESC
            """,
            (project_id, days),
        )
        return [dict(row) for row in cursor.fetchall()]

