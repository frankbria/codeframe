"""Repository for Issue Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
import sqlite3
from typing import List, Optional, Dict, Any, Union
import logging

import aiosqlite

from codeframe.core.models import (
    TaskStatus,
    Issue,
    IssueWithTaskCount,
)
from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Whitelist of allowed issue fields for updates (prevents SQL injection)
ALLOWED_ISSUE_FIELDS = {
    "project_id",
    "issue_number",
    "title",
    "description",
    "status",
    "priority",
    "workflow_step",
    "completed_at",
    "depends_on",
}


class IssueRepository(BaseRepository):
    """Repository for issue repository operations."""


    def create_issue(self, issue: Issue | dict) -> int:
        """Create a new issue.

        Args:
            issue: Issue object or dict to create

        Returns:
            Created issue ID

        Raises:
            sqlite3.IntegrityError: If issue_number already exists for project
        """
        # Handle both Issue objects and dicts for test flexibility
        if isinstance(issue, dict):
            project_id = issue.get("project_id")
            issue_number = issue.get("issue_number")
            title = issue.get("title", "")
            description = issue.get("description", "")
            status = issue.get("status", "pending")
            priority = issue.get("priority", 2)
            workflow_step = issue.get("workflow_step", 1)
        else:
            project_id = issue.project_id
            issue_number = issue.issue_number
            title = issue.title
            description = issue.description
            status = issue.status.value if hasattr(issue.status, "value") else issue.status
            priority = issue.priority
            workflow_step = issue.workflow_step

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO issues (
                project_id, issue_number, title, description,
                status, priority, workflow_step
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                project_id,
                issue_number,
                title,
                description,
                status,
                priority,
                workflow_step,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_issue(self, issue_id: int) -> Optional[Issue]:
        """Get issue by ID.

        Args:
            issue_id: Issue ID

        Returns:
            Issue object or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
        row = cursor.fetchone()
        return self._row_to_issue(row) if row else None



    def get_project_issues(self, project_id: int) -> List[Issue]:
        """Get all issues for a project.

        Args:
            project_id: Project ID

        Returns:
            List of Issue objects ordered by issue_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM issues WHERE project_id = ? ORDER BY issue_number",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [self._row_to_issue(row) for row in rows]


    def get_issues_with_tasks(self, project_id: int, include_tasks: bool = False) -> Dict[str, Any]:
        """Get issues for a project with optional tasks.

        Args:
            project_id: Project ID
            include_tasks: Whether to include tasks in response

        Returns:
            Dictionary with issues, total_issues, total_tasks
        """

        cursor = self.conn.cursor()

        # Get all issues for project
        cursor.execute(
            """
            SELECT * FROM issues
            WHERE project_id = ?
            ORDER BY issue_number
            """,
            (project_id,),
        )
        issue_rows = cursor.fetchall()

        # Format issues according to API contract
        issues = []
        total_tasks = 0

        for issue_row in issue_rows:
            issue_dict = dict(issue_row)

            # Parse depends_on from JSON
            depends_on = []
            depends_on_str = issue_dict.get("depends_on")
            if depends_on_str:
                try:
                    parsed = json.loads(depends_on_str)
                    # Ensure it's a list
                    if isinstance(parsed, list):
                        depends_on = parsed
                except (json.JSONDecodeError, TypeError):
                    # If parsing fails, return empty list
                    pass

            # Format issue according to API contract
            formatted_issue = {
                "id": str(issue_dict["id"]),
                "issue_number": issue_dict["issue_number"],
                "title": issue_dict["title"],
                "description": issue_dict["description"] or "",
                "status": issue_dict["status"],
                "priority": issue_dict["priority"],
                "depends_on": depends_on,
                "proposed_by": "agent",  # Default for now
                "created_at": self._ensure_rfc3339(issue_dict["created_at"]),
                "updated_at": self._ensure_rfc3339(issue_dict["created_at"]),  # Use created_at for now
                "completed_at": (
                    self._ensure_rfc3339(issue_dict["completed_at"])
                    if issue_dict.get("completed_at")
                    else None
                ),
            }

            # Include tasks if requested
            if include_tasks:
                # Get tasks for this issue
                cursor.execute(
                    """
                    SELECT * FROM tasks
                    WHERE issue_id = ?
                    ORDER BY task_number
                    """,
                    (issue_dict["id"],),
                )
                task_rows = cursor.fetchall()

                # Format tasks according to API contract
                tasks = []
                for task_row in task_rows:
                    task_dict = dict(task_row)

                    # Parse depends_on from JSON
                    depends_on = []
                    depends_on_str = task_dict.get("depends_on")
                    if depends_on_str:
                        try:
                            depends_on = json.loads(depends_on_str)
                            # Ensure it's a list
                            if not isinstance(depends_on, list):
                                depends_on = []
                        except (json.JSONDecodeError, TypeError):
                            # If parsing fails, return empty list
                            depends_on = []

                    formatted_task = {
                        "id": str(task_dict["id"]),
                        "task_number": task_dict["task_number"],
                        "title": task_dict["title"],
                        "description": task_dict["description"] or "",
                        "status": task_dict["status"],
                        "depends_on": depends_on,
                        "proposed_by": "agent",  # Default for now
                        "created_at": self._ensure_rfc3339(task_dict["created_at"]),
                        "updated_at": self._ensure_rfc3339(
                            task_dict["created_at"]
                        ),  # Use created_at for now
                        "completed_at": (
                            self._ensure_rfc3339(task_dict["completed_at"])
                            if task_dict.get("completed_at")
                            else None
                        ),
                    }
                    tasks.append(formatted_task)
                    total_tasks += 1

                formatted_issue["tasks"] = tasks
            else:
                # Count tasks even if not including them
                cursor.execute(
                    "SELECT COUNT(*) FROM tasks WHERE issue_id = ?",
                    (issue_dict["id"],),
                )
                task_count = cursor.fetchone()[0]
                total_tasks += task_count

            issues.append(formatted_issue)

        return {
            "issues": issues,
            "total_issues": len(issues),
            "total_tasks": total_tasks,
        }

    # Git Branches methods (cf-33)


    def list_issues_with_progress(self, project_id: int) -> List[Dict[str, Any]]:
        """List issues with their progress metrics.

        Args:
            project_id: Project ID

        Returns:
            List of issue dictionaries with task_count field
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT i.*, COUNT(t.id) as task_count
            FROM issues i
            LEFT JOIN tasks t ON t.issue_id = i.id
            WHERE i.project_id = ?
            GROUP BY i.id
            ORDER BY i.issue_number
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # PRD methods (cf-26)


    def get_issue_with_task_counts(self, issue_id: int) -> Optional[IssueWithTaskCount]:
        """Get issue with count of associated tasks.

        Args:
            issue_id: Issue ID

        Returns:
            IssueWithTaskCount object (using composition) or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT i.*, COUNT(t.id) as task_count
            FROM issues i
            LEFT JOIN tasks t ON t.issue_id = i.id
            WHERE i.id = ?
            GROUP BY i.id
            """,
            (issue_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        # Use _row_to_issue for consistent parsing, then wrap with task count
        issue = self._row_to_issue(row)
        return IssueWithTaskCount(
            issue=issue,
            task_count=row["task_count"],
        )



    def _row_to_issue(self, row: Union[sqlite3.Row, aiosqlite.Row]) -> Issue:
        """Convert a database row to an Issue object.

        Args:
            row: SQLite Row object from issues table (sync or async)

        Returns:
            Issue dataclass instance

        Note:
            Both sqlite3.Row and aiosqlite.Row support dictionary-style access
            via row["column_name"], which this method relies on.
        """
        row_id = row["id"]

        # Parse timestamps - created_at should never be NULL (enforced by schema)
        created_at = self._parse_datetime(row["created_at"], "created_at", row_id)
        if created_at is None:
            raise ValueError(
                f"Issue {row_id} has NULL created_at - database integrity issue. "
                "The schema enforces NOT NULL on created_at."
            )
        completed_at = self._parse_datetime(row["completed_at"], "completed_at", row_id)

        # Convert status string to enum
        status = TaskStatus.PENDING
        if row["status"]:
            try:
                status = TaskStatus(row["status"])
            except ValueError:
                logger.warning(
                    f"Invalid issue status '{row['status']}' for issue {row_id}, defaulting to PENDING"
                )

        return Issue(
            id=row_id,
            project_id=row["project_id"],
            issue_number=row["issue_number"] or "",
            title=row["title"] or "",
            description=row["description"] or "",
            status=status,
            priority=row["priority"] if row["priority"] is not None else 2,
            workflow_step=row["workflow_step"] if row["workflow_step"] is not None else 1,
            created_at=created_at,
            completed_at=completed_at,
        )


    def list_issues(self, project_id: int) -> List[Dict[str, Any]]:
        """Alias for get_project_issues for test compatibility."""
        return self.get_project_issues(project_id)



    def update_issue(self, issue_id: int, updates: Dict[str, Any]) -> int:
        """Update issue fields.

        Args:
            issue_id: Issue ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected

        Raises:
            ValueError: If any update key is not in the allowed fields whitelist
        """
        if not updates:
            return 0

        # Validate all keys against whitelist to prevent SQL injection
        invalid_fields = set(updates.keys()) - ALLOWED_ISSUE_FIELDS
        if invalid_fields:
            raise ValueError(
                f"Invalid issue fields: {invalid_fields}. "
                f"Allowed fields: {ALLOWED_ISSUE_FIELDS}"
            )

        fields = []
        values = []
        for key, value in updates.items():
            # Safe to use key here since it's been validated against whitelist
            fields.append(f"{key} = ?")
            values.append(value)

        values.append(issue_id)

        query = f"UPDATE issues SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount



    def get_issue_completion_status(self, issue_id: int) -> Dict[str, Any]:
        """Calculate issue completion based on task statuses.

        Args:
            issue_id: Issue ID

        Returns:
            Dictionary with total_tasks, completed_tasks, completion_percentage
        """
        cursor = self.conn.cursor()

        # Get total task count
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE issue_id = ?", (issue_id,))
        total_tasks = cursor.fetchone()[0]

        # Get completed task count
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE issue_id = ? AND status = ?",
            (issue_id, "completed"),
        )
        completed_tasks = cursor.fetchone()[0]

        # Calculate percentage
        completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_percentage": completion_percentage,
        }

