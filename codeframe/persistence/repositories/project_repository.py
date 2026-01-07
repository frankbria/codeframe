"""Repository for Project Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Union
import logging

import aiosqlite

from codeframe.core.models import (
    ProjectStatus,
    ProjectPhase,
    SourceType,
    Project,
    Task,
)
from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"

# Whitelist of allowed project fields for updates (prevents SQL injection)
ALLOWED_PROJECT_FIELDS = {
    "name",
    "description",
    "user_id",
    "source_type",
    "source_location",
    "source_branch",
    "workspace_path",
    "git_initialized",
    "current_commit",
    "status",
    "phase",
    "paused_at",
    "config",
}


class ProjectRepository(BaseRepository):
    """Repository for project repository operations."""



    def create_project(
        self,
        name: str,
        description: str,
        source_type: str = "empty",
        source_location: Optional[str] = None,
        source_branch: str = "main",
        workspace_path: Optional[str] = None,
        user_id: Optional[int] = None,
        **kwargs,
    ) -> int:
        """Create a new project.

        Args:
            name: Project name
            description: Project description/purpose
            source_type: Source type (git_remote, local_path, upload, empty)
            source_location: Git URL, local path, or upload filename
            source_branch: Git branch (for git_remote)
            workspace_path: Path to workspace directory
            user_id: ID of the user creating the project (owner)
            **kwargs: Additional fields (config, status, etc.)

        Returns:
            Created project ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (
                name, description, source_type, source_location,
                source_branch, workspace_path, git_initialized, status, user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                description,
                source_type,
                source_location,
                source_branch,
                workspace_path or "",
                False,  # Will be set to True after workspace initialization
                "init",  # Default status
                user_id,
            ),
        )
        self.conn.commit()
        project_id = cursor.lastrowid

        # Automatically add owner to project_users table
        if user_id is not None:
            cursor.execute(
                """
                INSERT INTO project_users (project_id, user_id, role)
                VALUES (?, ?, 'owner')
                """,
                (project_id, user_id),
            )
            self.conn.commit()

        # Log project creation
        if user_id is not None:
            from codeframe.lib.audit_logger import AuditLogger, AuditEventType
            audit = AuditLogger(self._database if self._database else self)
            audit.log_project_event(
                event_type=AuditEventType.PROJECT_CREATED,
                user_id=user_id,
                project_id=project_id,
                ip_address=None,  # TODO: Pass from request context
                metadata={"name": name, "source_type": source_type},
            )

        return project_id



    def get_project(self, project_identifier: int | str) -> Optional[dict]:
        """Get project by ID or name.

        Args:
            project_identifier: Project ID (int) or project name (str)

        Returns:
            Project dictionary or None if not found
        """
        if self._sync_lock is not None:
            with self._sync_lock:
                cursor = self.conn.cursor()
                if isinstance(project_identifier, int):
                    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_identifier,))
                else:
                    cursor.execute("SELECT * FROM projects WHERE name = ?", (project_identifier,))
                row = cursor.fetchone()
                return dict(row) if row else None
        else:
            cursor = self.conn.cursor()
            if isinstance(project_identifier, int):
                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_identifier,))
            else:
                cursor.execute("SELECT * FROM projects WHERE name = ?", (project_identifier,))
            row = cursor.fetchone()
            return dict(row) if row else None



    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects with progress metrics.

        Note:
            Returns dicts rather than Project objects because this method adds
            computed 'progress' metrics that aren't part of the Project schema.
            Use get_project() for typed Project returns.

        Returns:
            List of project dictionaries, each with a 'progress' field containing:
            - completed_tasks: Number of tasks with status='completed'
            - total_tasks: Total number of tasks
            - percentage: Completion percentage (0.0-100.0)
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
        rows = cursor.fetchall()

        projects = []
        for row in rows:
            project = dict(row)
            project_id = project["id"]

            # Calculate progress metrics for this project
            progress = self._calculate_project_progress(project_id)
            project["progress"] = progress

            projects.append(project)

        return projects



    def update_project(
        self,
        project_id: int,
        updates: Dict[str, Any],
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        """Update project fields.

        Args:
            project_id: Project ID to update
            updates: Dictionary of fields to update
            user_id: ID of user performing update (for audit logging)
            ip_address: Client IP address (for audit logging)

        Returns:
            Number of rows affected

        Raises:
            ValueError: If any update key is not in the allowed fields whitelist
        """
        if not updates:
            return 0

        # Validate all keys against whitelist to prevent SQL injection
        invalid_fields = set(updates.keys()) - ALLOWED_PROJECT_FIELDS
        if invalid_fields:
            raise ValueError(
                f"Invalid project fields: {invalid_fields}. "
                f"Allowed fields: {ALLOWED_PROJECT_FIELDS}"
            )

        # Build UPDATE query dynamically
        fields = []
        values = []
        for key, value in updates.items():
            # Safe to use key here since it's been validated against whitelist
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, ProjectStatus):
                values.append(value.value)
            else:
                values.append(value)

        values.append(project_id)

        query = f"UPDATE projects SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        rows_affected = cursor.rowcount

        # Log project update if user_id is provided
        if user_id is not None and rows_affected > 0:
            from codeframe.lib.audit_logger import AuditLogger, AuditEventType
            audit = AuditLogger(self._database if self._database else self)
            audit.log_project_event(
                event_type=AuditEventType.PROJECT_UPDATED,
                user_id=user_id,
                project_id=project_id,
                ip_address=ip_address,
                metadata={"updated_fields": list(updates.keys())},
            )

        return rows_affected



    def delete_project(
        self,
        project_id: int,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Delete a project.

        Args:
            project_id: Project ID to delete
            user_id: ID of user performing deletion (for audit logging)
            ip_address: Client IP address (for audit logging)
        """
        # Get project name before deletion for audit log
        project_name = None
        if user_id is not None:
            project = self.get_project(project_id)
            if project:
                project_name = project.get("name")

        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

        # Log project deletion if user_id is provided
        if user_id is not None:
            from codeframe.lib.audit_logger import AuditLogger, AuditEventType
            audit = AuditLogger(self._database if self._database else self)
            audit.log_project_event(
                event_type=AuditEventType.PROJECT_DELETED,
                user_id=user_id,
                project_id=project_id,
                ip_address=ip_address,
                metadata={"name": project_name} if project_name else None,
            )



    def _row_to_project(self, row: Union[sqlite3.Row, aiosqlite.Row]) -> Project:
        """Convert a database row to a Project object.

        Args:
            row: SQLite Row object from projects table (sync or async)

        Returns:
            Project dataclass instance

        Note:
            Both sqlite3.Row and aiosqlite.Row support dictionary-style access
            via row["column_name"], which this method relies on.
        """
        row_id = row["id"]

        # Parse timestamps
        created_at = self._parse_datetime(row["created_at"], "created_at", row_id)
        if created_at is None:
            logger.warning(
                f"Project {row_id} has NULL created_at - using datetime.now() as fallback"
            )
            created_at = datetime.now()
        paused_at = self._parse_datetime(row["paused_at"], "paused_at", row_id)

        # Convert status string to enum
        status = ProjectStatus.INIT
        if row["status"]:
            try:
                status = ProjectStatus(row["status"])
            except ValueError:
                logger.warning(
                    f"Invalid project status '{row['status']}' for project {row_id}, defaulting to INIT"
                )

        # Convert phase string to enum
        phase = ProjectPhase.DISCOVERY
        if row["phase"]:
            try:
                phase = ProjectPhase(row["phase"])
            except ValueError:
                logger.warning(
                    f"Invalid project phase '{row['phase']}' for project {row_id}, defaulting to DISCOVERY"
                )

        # Convert source_type string to enum
        source_type = SourceType.EMPTY
        if row["source_type"]:
            try:
                source_type = SourceType(row["source_type"])
            except ValueError:
                logger.warning(
                    f"Invalid source_type '{row['source_type']}' for project {row_id}, defaulting to EMPTY"
                )

        # Parse config JSON
        config = None
        if row["config"]:
            try:
                config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse config for project {row_id}: {e}")

        return Project(
            id=row_id,
            name=row["name"] or "",
            description=row["description"] or "",
            source_type=source_type,
            source_location=row["source_location"],
            source_branch=row["source_branch"] or "main",
            workspace_path=row["workspace_path"] or "",
            git_initialized=bool(row["git_initialized"]),
            current_commit=row["current_commit"],
            status=status,
            phase=phase,
            created_at=created_at,
            paused_at=paused_at,
            config=config,
        )



    def _calculate_project_progress(self, project_id: int) -> Dict[str, Any]:
        """Calculate task completion progress for a project.

        Uses a single SQL query to efficiently get both total and completed task counts.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with completed_tasks, total_tasks, and percentage
        """
        cursor = self.conn.cursor()

        # Get both counts in a single query using SUM with CASE
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
            FROM tasks
            WHERE project_id = ?
            """,
            (project_id,),
        )
        row = cursor.fetchone()

        total_tasks = row["total_tasks"]
        completed_tasks = row["completed_tasks"] or 0  # Handle NULL when no tasks

        # Calculate completion percentage
        percentage = (completed_tasks / total_tasks * 100.0) if total_tasks > 0 else 0.0

        return {
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "percentage": percentage,
        }



    def get_project_tasks(self, project_id: int) -> List[Task]:
        """Get all tasks for a project (all statuses).

        Args:
            project_id: Project ID

        Returns:
            List of Task objects ordered by task_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY task_number",
            (project_id,),
        )
        rows = cursor.fetchall()
        # Use TaskRepository's _row_to_task method (cross-repository call)
        if self._database:
            return [self._database.tasks._row_to_task(row) for row in rows]
        # Fallback for standalone repository usage (testing)
        from codeframe.persistence.repositories.task_repository import TaskRepository
        task_repo = TaskRepository(sync_conn=self.conn)
        return [task_repo._row_to_task(row) for row in rows]



    def get_project_stats(self, project_id: int) -> Dict[str, int]:
        """Get project statistics for progress calculation.

        Args:
            project_id: Project ID

        Returns:
            Dict with keys: total_tasks, completed_tasks
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
            FROM tasks
            WHERE project_id = ?
            """,
            (project_id,),
        )
        row = cursor.fetchone()
        return {
            "total_tasks": row["total_tasks"] or 0,
            "completed_tasks": row["completed_tasks"] or 0,
        }

    # Checkpoint Management Methods (Sprint 10 Phase 4: US-3)



    def get_user_projects(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all projects accessible to a user with progress metrics.

        Returns projects where the user is either:
        - The owner (projects.user_id matches)
        - A collaborator/viewer (exists in project_users table)

        Performance: Single query using LEFT JOIN to calculate progress for all projects.

        Args:
            user_id: ID of the user

        Returns:
            List of project dictionaries with progress metrics
        """
        cursor = self.conn.cursor()

        # Single query with progress calculation using LEFT JOIN and aggregation
        # Fixes N+1 query issue: 100 projects = 1 query instead of 101
        cursor.execute(
            """
            SELECT DISTINCT
                p.*,
                COALESCE(task_stats.total_tasks, 0) as total_tasks,
                COALESCE(task_stats.completed_tasks, 0) as completed_tasks,
                COALESCE(task_stats.percentage, 0.0) as percentage
            FROM projects p
            LEFT JOIN project_users pu ON p.id = pu.project_id
            LEFT JOIN (
                SELECT
                    project_id,
                    COUNT(*) as total_tasks,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks,
                    CASE
                        WHEN COUNT(*) > 0
                        THEN CAST(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100.0
                        ELSE 0.0
                    END as percentage
                FROM tasks
                GROUP BY project_id
            ) task_stats ON p.id = task_stats.project_id
            WHERE p.user_id = ? OR pu.user_id = ?
            ORDER BY p.created_at DESC
            """,
            (user_id, user_id),
        )
        rows = cursor.fetchall()

        projects = []
        for row in rows:
            project = dict(row)

            # Extract progress metrics from the joined columns
            progress = {
                "completed_tasks": project.pop("completed_tasks"),
                "total_tasks": project.pop("total_tasks"),
                "percentage": project.pop("percentage"),
            }
            project["progress"] = progress

            projects.append(project)

        return projects



    def user_has_project_access(self, user_id: int, project_id: int) -> bool:
        """Check if a user has access to a project.

        Checks both ownership (projects.user_id) and collaborator access (project_users table).

        Performance Note:
            By default, only access DENIALS are logged to avoid excessive DB writes.
            Set AUDIT_VERBOSITY=high to log all access checks (owner + collaborator grants).

        Args:
            user_id: ID of the user
            project_id: ID of the project

        Returns:
            True if user is owner or has collaborator/viewer access, False otherwise
        """
        cursor = self.conn.cursor()

        # Check if user is the project owner
        cursor.execute(
            "SELECT 1 FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        )
        if cursor.fetchone():
            # Only log if verbose auditing enabled (performance optimization)
            if AUDIT_VERBOSITY == "high":
                from codeframe.lib.audit_logger import AuditLogger, AuditEventType
                audit = AuditLogger(self._database if self._database else self)
                audit.log_authz_event(
                    event_type=AuditEventType.AUTHZ_ACCESS_GRANTED,
                    user_id=user_id,
                    resource_type="project",
                    resource_id=project_id,
                    granted=True,
                    ip_address=None,  # TODO: Pass from request context
                    metadata={"access_type": "owner"},
                )
            return True

        # Check if user has collaborator/viewer access
        cursor.execute(
            "SELECT 1 FROM project_users WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        )
        has_access = cursor.fetchone() is not None

        # Log authorization result
        from codeframe.lib.audit_logger import AuditLogger, AuditEventType
        audit = AuditLogger(self._database if self._database else self)
        if has_access:
            # Only log if verbose auditing enabled (performance optimization)
            if AUDIT_VERBOSITY == "high":
                audit.log_authz_event(
                    event_type=AuditEventType.AUTHZ_ACCESS_GRANTED,
                    user_id=user_id,
                    resource_type="project",
                    resource_id=project_id,
                    granted=True,
                    ip_address=None,  # TODO: Pass from request context
                    metadata={"access_type": "collaborator"},
                )
        else:
            # ALWAYS log access denials for security monitoring
            audit.log_authz_event(
                event_type=AuditEventType.AUTHZ_ACCESS_DENIED,
                user_id=user_id,
                resource_type="project",
                resource_id=project_id,
                granted=False,
                ip_address=None,  # TODO: Pass from request context
                metadata={"reason": "No access"},
            )

        return has_access

    async def cleanup_expired_sessions(self) -> int:
        """Delete expired sessions from the database.

        This should be called periodically (e.g., every hour) to prevent
        the sessions table from growing indefinitely.

        Returns:
            Number of sessions deleted
        """
        conn = await self._get_async_conn()

        # Delete sessions where expires_at < now
        cursor = await conn.execute(
            """
            DELETE FROM sessions
            WHERE datetime(expires_at) < datetime(?)
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )

        deleted_count = cursor.rowcount
        await conn.commit()

        return deleted_count

    async def cleanup_old_audit_logs(self, retention_days: int = 90) -> int:
        """Delete audit logs older than the retention period.

        This should be called periodically (e.g., daily) to prevent
        the audit_logs table from growing indefinitely.

        Args:
            retention_days: Number of days to retain audit logs (default: 90)

        Returns:
            Number of audit log entries deleted
        """
        conn = await self._get_async_conn()

        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Delete audit logs older than retention period
        cursor = await conn.execute(
            """
            DELETE FROM audit_logs
            WHERE datetime(timestamp) < datetime(?)
            """,
            (cutoff_date.isoformat(),),
        )

        deleted_count = cursor.rowcount
        await conn.commit()

        return deleted_count

