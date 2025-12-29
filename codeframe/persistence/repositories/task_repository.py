"""Repository for Task Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
import sqlite3
from typing import List, Optional, Dict, Any, Union
import logging

import aiosqlite

from codeframe.core.models import (
    Task,
    TaskStatus,
)
from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Whitelist of allowed task fields for updates (prevents SQL injection)
ALLOWED_TASK_FIELDS = {
    "project_id",
    "issue_id",
    "task_number",
    "parent_issue_number",
    "title",
    "description",
    "status",
    "assigned_to",
    "depends_on",
    "can_parallelize",
    "priority",
    "workflow_step",
    "requires_mcp",
    "estimated_tokens",
    "actual_tokens",
    "commit_sha",
    "completed_at",
    "quality_gate_status",
    "quality_gate_failures",
    "requires_human_approval",
}


class TaskRepository(BaseRepository):
    """Repository for task repository operations."""


    def create_task(self, task: Task) -> int:
        """Create a new task."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                project_id, title, description, status, priority, workflow_step, requires_mcp, depends_on
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task.project_id,
                task.title,
                task.description,
                task.status.value,
                task.priority,
                task.workflow_step,
                task.requires_mcp,
                task.depends_on,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_task(self, task_id: int) -> Optional[Task]:
        """Get task by ID.

        Args:
            task_id: Task ID

        Returns:
            Task object or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return self._row_to_task(row) if row else None



    def update_task(self, task_id: int, updates: Dict[str, Any]) -> int:
        """Update task fields.

        Args:
            task_id: Task ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected

        Raises:
            ValueError: If any update key is not in the allowed fields whitelist
        """
        if not updates:
            return 0

        # Validate all keys against whitelist to prevent SQL injection
        invalid_fields = set(updates.keys()) - ALLOWED_TASK_FIELDS
        if invalid_fields:
            raise ValueError(
                f"Invalid task fields: {invalid_fields}. "
                f"Allowed fields: {ALLOWED_TASK_FIELDS}"
            )

        fields = []
        values = []
        for key, value in updates.items():
            # Safe to use key here since it's been validated against whitelist
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, TaskStatus):
                values.append(value.value)
            else:
                values.append(value)

        values.append(task_id)

        query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"

        if self._sync_lock is not None:
            with self._sync_lock:
                cursor = self.conn.cursor()
                cursor.execute(query, values)
                self.conn.commit()
                return cursor.rowcount
        else:
            cursor = self.conn.cursor()
            cursor.execute(query, values)
            self.conn.commit()
            return cursor.rowcount



    def create_task_with_issue(
        self,
        project_id: int,
        issue_id: int,
        task_number: str,
        parent_issue_number: str,
        title: str,
        description: str,
        status: TaskStatus,
        priority: int,
        workflow_step: int,
        can_parallelize: bool,
        requires_mcp: bool = False,
    ) -> int:
        """Create a new task with issue relationship.

        Args:
            project_id: Project ID
            issue_id: Parent issue ID
            task_number: Hierarchical task number (e.g., "1.5.1", "2.3.2")
            parent_issue_number: Parent issue number (e.g., "1.5")
            title: Task title
            description: Task description
            status: Task status
            priority: Task priority (0-4, 0 = highest)
            workflow_step: Workflow step (1-15)
            can_parallelize: Whether task can run in parallel
            requires_mcp: Whether task requires MCP tools

        Returns:
            Task ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                project_id, issue_id, task_number, parent_issue_number,
                title, description, status, priority, workflow_step,
                can_parallelize, requires_mcp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                issue_id,
                task_number,
                parent_issue_number,
                title,
                description,
                status.value,
                priority,
                workflow_step,
                can_parallelize,
                requires_mcp,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    async def get_tasks_by_issue(self, issue_id: int) -> List[Task]:
        """Get all tasks for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of Task objects ordered by task_number

        Note:
            Uses async connection with automatic health check and reconnection.
            Call close_async() when done to release database resources.
        """
        conn = await self._get_async_conn()

        async with conn.execute(
            "SELECT * FROM tasks WHERE issue_id = ? ORDER BY task_number",
            (issue_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_task(row) for row in rows]



    def get_tasks_by_parent_issue_number(self, parent_issue_number: str) -> List[Task]:
        """Get all tasks by parent issue number.

        Args:
            parent_issue_number: Parent issue number (e.g., "1.5")

        Returns:
            List of Task objects
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE parent_issue_number = ? ORDER BY task_number",
            (parent_issue_number,),
        )
        rows = cursor.fetchall()
        return [self._row_to_task(row) for row in rows]



    def get_pending_tasks(self, project_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Get next pending tasks for next actions queue.

        Args:
            project_id: Project ID
            limit: Maximum number of tasks to return

        Returns:
            Prioritized list with keys: id, title, priority, created_at
            (Ordered by priority: 0=Critical, 1=High, 2=Medium, 3=Low, 4=Nice-to-have)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, title, priority, created_at
            FROM tasks
            WHERE project_id = ? AND status = 'pending'
            ORDER BY priority ASC, created_at ASC
            LIMIT ?
            """,
            (project_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def add_task_dependency(self, task_id: int, depends_on_task_id: int) -> None:
        """Add a dependency relationship between tasks.

        Args:
            task_id: The task that depends on another
            depends_on_task_id: The task that must be completed first

        Raises:
            sqlite3.IntegrityError: If dependency would create a cycle
        """
        cursor = self.conn.cursor()

        # Insert into junction table
        cursor.execute(
            """
            INSERT INTO task_dependencies (task_id, depends_on_task_id)
            VALUES (?, ?)
        """,
            (task_id, depends_on_task_id),
        )

        # Update depends_on JSON array in tasks table
        cursor.execute("SELECT depends_on FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        if row and row[0]:
            depends_on = json.loads(row[0]) if row[0] else []
        else:
            depends_on = []

        if depends_on_task_id not in depends_on:
            depends_on.append(depends_on_task_id)

        cursor.execute(
            """
            UPDATE tasks SET depends_on = ? WHERE id = ?
        """,
            (json.dumps(depends_on), task_id),
        )

        self.conn.commit()



    def get_task_dependencies(self, task_id: int) -> list:
        """Get all tasks that the given task depends on.

        Args:
            task_id: The task ID to get dependencies for

        Returns:
            List of task IDs that must be completed first
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT depends_on_task_id 
            FROM task_dependencies 
            WHERE task_id = ?
        """,
            (task_id,),
        )

        return [row[0] for row in cursor.fetchall()]



    def _row_to_task(self, row: Union[sqlite3.Row, aiosqlite.Row]) -> Task:
        """Convert a database row to a Task object.

        Args:
            row: SQLite Row object from tasks table (sync or async)

        Returns:
            Task dataclass instance

        Note:
            Both sqlite3.Row and aiosqlite.Row support dictionary-style access
            via row["column_name"], which this method relies on.
        """
        row_id = row["id"]

        # Parse timestamps - created_at should never be NULL (enforced by schema)
        created_at = self._parse_datetime(row["created_at"], "created_at", row_id)
        if created_at is None:
            raise ValueError(
                f"Task {row_id} has NULL created_at - database integrity issue. "
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
                    f"Invalid task status '{row['status']}' for task {row_id}, defaulting to PENDING"
                )

        return Task(
            id=row_id,
            project_id=row["project_id"],
            issue_id=row["issue_id"],
            task_number=row["task_number"] or "",
            parent_issue_number=row["parent_issue_number"] or "",
            title=row["title"] or "",
            description=row["description"] or "",
            status=status,
            assigned_to=row["assigned_to"],
            depends_on=row["depends_on"] or "",
            can_parallelize=bool(row["can_parallelize"]),
            priority=row["priority"] if row["priority"] is not None else 2,
            workflow_step=row["workflow_step"] if row["workflow_step"] is not None else 1,
            requires_mcp=bool(row["requires_mcp"]),
            estimated_tokens=row["estimated_tokens"] if row["estimated_tokens"] is not None else 0,
            actual_tokens=row["actual_tokens"],
            created_at=created_at,
            completed_at=completed_at,
        )



    def get_dependent_tasks(self, task_id: int) -> list:
        """Get all tasks that depend on the given task.

        Args:
            task_id: The task ID to find dependents for

        Returns:
            List of task IDs that depend on this task
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT task_id 
            FROM task_dependencies 
            WHERE depends_on_task_id = ?
        """,
            (task_id,),
        )

        return [row[0] for row in cursor.fetchall()]



    def remove_task_dependency(self, task_id: int, depends_on_task_id: int) -> None:
        """Remove a dependency relationship between tasks.

        Args:
            task_id: The task that currently depends on another
            depends_on_task_id: The task dependency to remove
        """
        cursor = self.conn.cursor()

        # Remove from junction table
        cursor.execute(
            """
            DELETE FROM task_dependencies 
            WHERE task_id = ? AND depends_on_task_id = ?
        """,
            (task_id, depends_on_task_id),
        )

        # Update depends_on JSON array in tasks table
        cursor.execute("SELECT depends_on FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        if row and row[0]:
            depends_on = json.loads(row[0]) if row[0] else []
            if depends_on_task_id in depends_on:
                depends_on.remove(depends_on_task_id)

            cursor.execute(
                """
                UPDATE tasks SET depends_on = ? WHERE id = ?
            """,
                (json.dumps(depends_on), task_id),
            )

        self.conn.commit()



    def clear_all_task_dependencies(self, task_id: int) -> None:
        """Remove all dependencies for a given task.

        Args:
            task_id: The task ID to clear dependencies for
        """
        cursor = self.conn.cursor()

        # Remove from junction table
        cursor.execute(
            """
            DELETE FROM task_dependencies WHERE task_id = ?
        """,
            (task_id,),
        )

        # Clear depends_on JSON array
        cursor.execute(
            """
            UPDATE tasks SET depends_on = '[]' WHERE id = ?
        """,
            (task_id,),
        )

        self.conn.commit()



    def update_task_commit_sha(self, task_id: int, commit_sha: str) -> None:
        """Update task with git commit SHA.

        Args:
            task_id: Task ID
            commit_sha: Git commit hash
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE tasks SET commit_sha = ? WHERE id = ?
            """,
            (commit_sha, task_id),
        )
        self.conn.commit()



    def get_task_by_commit(self, commit_sha: str) -> Optional[dict]:
        """Find task by git commit SHA.

        Args:
            commit_sha: Git commit hash (full or short)

        Returns:
            Task dictionary or None if not found
        """
        cursor = self.conn.cursor()
        # Support both full (40 char) and short (7 char) hashes
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE commit_sha = ? OR commit_sha LIKE ?
            LIMIT 1
            """,
            (commit_sha, f"{commit_sha}%"),
        )
        row = cursor.fetchone()
        return dict(row) if row else None



    def get_recently_completed_tasks(
        self, project_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recently completed tasks for session summary.

        Args:
            project_id: Project ID
            limit: Maximum number of tasks to return

        Returns:
            List of dicts with keys: id, title, status, completed_at
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, title, status, completed_at
            FROM tasks
            WHERE project_id = ? AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_tasks_by_agent(
        self, agent_id: str, project_id: Optional[int] = None, limit: int = 100
    ) -> List[Task]:
        """Get all tasks assigned to an agent.

        Used for calculating agent maturity metrics based on task history.

        Args:
            agent_id: Agent ID to filter by (matches assigned_to field)
            project_id: Optional project ID to filter by
            limit: Maximum number of tasks to return (default: 100)

        Returns:
            List of Task objects ordered by created_at DESC (most recent first)
        """
        cursor = self.conn.cursor()

        if project_id is not None:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE assigned_to = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, project_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM tasks
                WHERE assigned_to = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, limit),
            )

        rows = cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    async def get_tasks_by_agent_async(
        self, agent_id: str, project_id: Optional[int] = None, limit: int = 100
    ) -> List[Task]:
        """Get all tasks assigned to an agent (async version).

        Used for calculating agent maturity metrics based on task history.
        This async version uses aiosqlite for non-blocking database access.

        Args:
            agent_id: Agent ID to filter by (matches assigned_to field)
            project_id: Optional project ID to filter by
            limit: Maximum number of tasks to return (default: 100)

        Returns:
            List of Task objects ordered by created_at DESC (most recent first)

        Note:
            Uses async connection with automatic health check and reconnection.
            Leverages idx_tasks_assigned_to index for optimal query performance.
        """
        conn = await self._get_async_conn()

        if project_id is not None:
            async with conn.execute(
                """
                SELECT * FROM tasks
                WHERE assigned_to = ? AND project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, project_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_task(row) for row in rows]
        else:
            async with conn.execute(
                """
                SELECT * FROM tasks
                WHERE assigned_to = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_task(row) for row in rows]

    # Code Review CRUD operations (Sprint 10: 015-review-polish)

