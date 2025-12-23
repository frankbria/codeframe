"""Repository for Review Repository operations.

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


class ReviewRepository(BaseRepository):
    """Repository for review repository operations."""


    def save_code_review(self, review: "CodeReview") -> int:
        """Save a code review finding to database.

        Args:
            review: CodeReview object to save

        Returns:
            ID of the created code_reviews record
        """

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO code_reviews (
                task_id, agent_id, project_id, file_path, line_number,
                severity, category, message, recommendation, code_snippet
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.task_id,
                review.agent_id,
                review.project_id,
                review.file_path,
                review.line_number,
                review.severity.value if hasattr(review.severity, "value") else review.severity,
                review.category.value if hasattr(review.category, "value") else review.category,
                review.message,
                review.recommendation,
                review.code_snippet,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_code_reviews(
        self,
        task_id: Optional[int] = None,
        project_id: Optional[int] = None,
        severity: Optional[str] = None,
    ) -> List["CodeReview"]:
        """Get code review findings.

        Args:
            task_id: Filter by task ID
            project_id: Filter by project ID
            severity: Filter by severity level

        Returns:
            List of CodeReview objects
        """
        from codeframe.core.models import CodeReview, Severity, ReviewCategory

        cursor = self.conn.cursor()

        # Build query dynamically based on filters
        conditions = []
        params = []

        if task_id is not None:
            conditions.append("task_id = ?")
            params.append(task_id)

        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)

        if severity is not None:
            conditions.append("severity = ?")
            params.append(severity)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        cursor.execute(
            f"""
            SELECT id, task_id, agent_id, project_id, file_path, line_number,
                   severity, category, message, recommendation, code_snippet, created_at
            FROM code_reviews
            WHERE {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )

        reviews = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            # Convert string severity/category back to enums
            reviews.append(
                CodeReview(
                    id=row_dict["id"],
                    task_id=row_dict["task_id"],
                    agent_id=row_dict["agent_id"],
                    project_id=row_dict["project_id"],
                    file_path=row_dict["file_path"],
                    line_number=row_dict["line_number"],
                    severity=Severity(row_dict["severity"]),
                    category=ReviewCategory(row_dict["category"]),
                    message=row_dict["message"],
                    recommendation=row_dict["recommendation"],
                    code_snippet=row_dict["code_snippet"],
                )
            )

        return reviews



    def get_code_reviews_by_severity(self, project_id: int, severity: str) -> List["CodeReview"]:
        """Get code reviews filtered by severity.

        Convenience method that calls get_code_reviews with severity filter.

        Args:
            project_id: Project ID to filter by
            severity: Severity level (critical, high, medium, low, info)

        Returns:
            List of CodeReview objects
        """
        return self.get_code_reviews(project_id=project_id, severity=severity)



    def get_code_reviews_by_project(
        self, project_id: int, severity: Optional[str] = None
    ) -> List["CodeReview"]:
        """Get all code review findings for a project.

        Convenience method for fetching project-level review aggregations.
        Returns all code reviews across all tasks in the project.

        Args:
            project_id: Project ID to fetch reviews for
            severity: Optional severity filter (critical, high, medium, low, info)

        Returns:
            List of CodeReview objects ordered by creation time (newest first)
        """
        return self.get_code_reviews(project_id=project_id, severity=severity)

    # ========================================================================
    # Quality Gate Methods (Sprint 10 Phase 3 - US-2)
    # ========================================================================

