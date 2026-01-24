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

# Evidence imports (lazily imported to avoid circular dependencies)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codeframe.enforcement.evidence_verifier import Evidence

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
    # Effort estimation fields (Phase 1)
    "estimated_hours",
    "complexity_score",
    "uncertainty_level",
    "resource_requirements",
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
        estimated_hours: float | None = None,
        complexity_score: int | None = None,
        uncertainty_level: str | None = None,
        resource_requirements: str | None = None,
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
            estimated_hours: Time estimate in hours (optional)
            complexity_score: Complexity rating 1-5 (optional)
            uncertainty_level: "low", "medium", "high" (optional)
            resource_requirements: JSON string of required skills/tools (optional)

        Returns:
            Task ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                project_id, issue_id, task_number, parent_issue_number,
                title, description, status, priority, workflow_step,
                can_parallelize, requires_mcp,
                estimated_hours, complexity_score, uncertainty_level, resource_requirements
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                estimated_hours,
                complexity_score,
                uncertainty_level,
                resource_requirements,
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

        # Parse effort estimation fields (handle missing columns for backward compatibility)
        estimated_hours = None
        complexity_score = None
        uncertainty_level = None
        resource_requirements = None

        try:
            estimated_hours = row["estimated_hours"]
        except (KeyError, IndexError):
            pass

        try:
            complexity_score = row["complexity_score"]
        except (KeyError, IndexError):
            pass

        try:
            uncertainty_level = row["uncertainty_level"]
        except (KeyError, IndexError):
            pass

        try:
            resource_requirements = row["resource_requirements"]
        except (KeyError, IndexError):
            pass

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
            estimated_hours=estimated_hours,
            complexity_score=complexity_score,
            uncertainty_level=uncertainty_level,
            resource_requirements=resource_requirements,
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

    # Evidence Storage (Evidence-Based Quality Enforcement)

    def save_task_evidence(self, task_id: int, evidence: "Evidence", commit: bool = True) -> int:
        """Save task evidence to database.

        Args:
            task_id: Task ID
            evidence: Evidence object from EvidenceVerifier
            commit: Whether to commit immediately (default: True)

        Returns:
            Evidence record ID
        """
        # Import here to avoid circular dependencies
        from codeframe.enforcement.evidence_verifier import Evidence  # noqa: F401
        from codeframe.enforcement.adaptive_test_runner import TestResult  # noqa: F401
        from codeframe.enforcement.skip_pattern_detector import SkipViolation  # noqa: F401
        from codeframe.enforcement.quality_tracker import QualityMetrics  # noqa: F401

        # Validate evidence data before storage
        if not (0 <= evidence.test_result.pass_rate <= 100):
            raise ValueError(
                f"Invalid pass_rate: {evidence.test_result.pass_rate} (must be 0-100)"
            )

        if evidence.test_result.coverage is not None and not (
            0 <= evidence.test_result.coverage <= 100
        ):
            raise ValueError(
                f"Invalid coverage: {evidence.test_result.coverage} (must be 0-100)"
            )

        # Validate test count consistency
        total_calculated = (
            evidence.test_result.passed_tests
            + evidence.test_result.failed_tests
            + evidence.test_result.skipped_tests
        )
        if evidence.test_result.total_tests != total_calculated:
            raise ValueError(
                f"Test count mismatch: total_tests={evidence.test_result.total_tests}, "
                f"but passed+failed+skipped={total_calculated}"
            )

        cursor = self.conn.cursor()

        # Serialize skip violations to JSON with error handling
        try:
            skip_violations_json = json.dumps([
                {
                    "file": v.file,
                    "line": v.line,
                    "pattern": v.pattern,
                    "context": v.context
                }
                for v in evidence.skip_violations
            ])
        except (TypeError, ValueError) as e:
            raise ValueError(f"Failed to serialize skip violations to JSON: {e}") from e

        # Serialize quality metrics to JSON with error handling
        try:
            quality_metrics_json = json.dumps({
                "timestamp": evidence.quality_metrics.timestamp,
                "response_count": evidence.quality_metrics.response_count,
                "test_pass_rate": evidence.quality_metrics.test_pass_rate,
                "coverage_percentage": evidence.quality_metrics.coverage_percentage,
                "total_tests": evidence.quality_metrics.total_tests,
                "passed_tests": evidence.quality_metrics.passed_tests,
                "failed_tests": evidence.quality_metrics.failed_tests,
                "language": evidence.quality_metrics.language,
                "framework": evidence.quality_metrics.framework,
            })
        except (TypeError, ValueError) as e:
            raise ValueError(f"Failed to serialize quality metrics to JSON: {e}") from e

        # Serialize verification errors
        verification_errors = "\n".join(evidence.verification_errors) if evidence.verification_errors else None

        cursor.execute(
            """
            INSERT INTO task_evidence (
                task_id, agent_id, language, framework,
                total_tests, passed_tests, failed_tests, skipped_tests,
                pass_rate, coverage, test_output,
                skip_violations_count, skip_violations_json, skip_check_passed,
                quality_metrics_json,
                verified, verification_errors,
                timestamp, task_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                evidence.agent_id,
                evidence.language,
                evidence.framework,
                evidence.test_result.total_tests,
                evidence.test_result.passed_tests,
                evidence.test_result.failed_tests,
                evidence.test_result.skipped_tests,
                evidence.test_result.pass_rate,
                evidence.test_result.coverage,
                evidence.test_output,
                len(evidence.skip_violations),
                skip_violations_json,
                evidence.skip_check_passed,
                quality_metrics_json,
                evidence.verified,
                verification_errors,
                evidence.timestamp,
                evidence.task_description,
            ),
        )
        if commit:
            self.conn.commit()
        return cursor.lastrowid

    def get_task_evidence(self, task_id: int) -> Optional["Evidence"]:
        """Get latest evidence for a task.

        Args:
            task_id: Task ID

        Returns:
            Evidence object or None if not found
        """
        # Import here to avoid circular dependencies
        from codeframe.enforcement.evidence_verifier import Evidence  # noqa: F401
        from codeframe.enforcement.adaptive_test_runner import TestResult  # noqa: F401
        from codeframe.enforcement.skip_pattern_detector import SkipViolation  # noqa: F401
        from codeframe.enforcement.quality_tracker import QualityMetrics  # noqa: F401

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM task_evidence
            WHERE task_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (task_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_evidence(row)

    def get_task_evidence_history(self, task_id: int, limit: int = 10) -> List["Evidence"]:
        """Get evidence history for a task (for audit trail).

        Args:
            task_id: Task ID
            limit: Maximum number of records to return

        Returns:
            List of Evidence objects ordered by created_at DESC
        """
        # Import here to avoid circular dependencies
        from codeframe.enforcement.evidence_verifier import Evidence  # noqa: F401

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM task_evidence
            WHERE task_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (task_id, limit),
        )
        rows = cursor.fetchall()

        return [self._row_to_evidence(row) for row in rows]

    def _row_to_evidence(self, row: sqlite3.Row) -> "Evidence":
        """Convert database row to Evidence object.

        Args:
            row: SQLite Row from task_evidence table

        Returns:
            Evidence object

        Raises:
            ValueError: If JSON data fails validation
        """
        # Import here to avoid circular dependencies
        from codeframe.enforcement.evidence_verifier import Evidence
        from codeframe.enforcement.adaptive_test_runner import TestResult
        from codeframe.enforcement.skip_pattern_detector import SkipViolation
        from codeframe.enforcement.quality_tracker import QualityMetrics

        # Deserialize and validate skip violations (defense in depth)
        skip_violations_data = json.loads(row["skip_violations_json"]) if row["skip_violations_json"] else []

        if skip_violations_data:
            if not isinstance(skip_violations_data, list):
                raise ValueError("skip_violations_json must be a list")
            for v in skip_violations_data:
                if not isinstance(v, dict):
                    raise ValueError("Each skip violation must be a dict")
                required_keys = {"file", "line", "pattern", "context"}
                if not required_keys.issubset(v.keys()):
                    raise ValueError(f"Skip violation missing required keys: {required_keys - v.keys()}")

        skip_violations = [
            SkipViolation(
                file=v["file"],
                line=v["line"],
                pattern=v["pattern"],
                context=v["context"]
            )
            for v in skip_violations_data
        ]

        # Deserialize and validate quality metrics (defense in depth)
        quality_metrics_data = json.loads(row["quality_metrics_json"])

        if not isinstance(quality_metrics_data, dict):
            raise ValueError("quality_metrics_json must be a dict")
        required_metrics_keys = {
            "timestamp", "response_count", "test_pass_rate", "coverage_percentage",
            "total_tests", "passed_tests", "failed_tests", "language"
        }
        if not required_metrics_keys.issubset(quality_metrics_data.keys()):
            raise ValueError(
                f"Quality metrics missing required keys: {required_metrics_keys - quality_metrics_data.keys()}"
            )

        quality_metrics = QualityMetrics(
            timestamp=quality_metrics_data["timestamp"],
            response_count=quality_metrics_data["response_count"],
            test_pass_rate=quality_metrics_data["test_pass_rate"],
            coverage_percentage=quality_metrics_data["coverage_percentage"],
            total_tests=quality_metrics_data["total_tests"],
            passed_tests=quality_metrics_data["passed_tests"],
            failed_tests=quality_metrics_data["failed_tests"],
            language=quality_metrics_data["language"],
            framework=quality_metrics_data.get("framework"),
        )

        # Reconstruct test result
        test_result = TestResult(
            success=row["pass_rate"] == 100.0,
            output=row["test_output"],
            total_tests=row["total_tests"],
            passed_tests=row["passed_tests"],
            failed_tests=row["failed_tests"],
            skipped_tests=row["skipped_tests"],
            pass_rate=row["pass_rate"],
            coverage=row["coverage"],
            duration=0.0,  # Duration not stored in evidence table
        )

        # Parse verification errors
        verification_errors = (
            row["verification_errors"].split("\n")
            if row["verification_errors"]
            else []
        )

        return Evidence(
            test_result=test_result,
            test_output=row["test_output"],
            skip_violations=skip_violations,
            skip_check_passed=bool(row["skip_check_passed"]),
            quality_metrics=quality_metrics,
            timestamp=row["timestamp"],
            language=row["language"],
            framework=row["framework"],
            agent_id=row["agent_id"],
            task_description=row["task_description"],
            verified=bool(row["verified"]),
            verification_errors=verification_errors if verification_errors else None,
        )

    def delete_all_project_tasks(self, project_id: int, cursor: sqlite3.Cursor = None) -> int:
        """Delete all tasks for a project, handling FK constraints.

        This method deletes all dependent records before deleting tasks:
        - task_dependencies (both task_id and depends_on_task_id)
        - test_results
        - correction_attempts

        Note: code_reviews and task_evidence have ON DELETE CASCADE and are handled
        automatically by the database.

        Args:
            project_id: Project ID to delete tasks for
            cursor: Optional cursor for transaction support. If provided,
                    the caller is responsible for commit/rollback.

        Returns:
            Number of tasks deleted
        """
        own_cursor = cursor is None
        if own_cursor:
            cursor = self.conn.cursor()

        try:
            # Get all task IDs for this project
            cursor.execute(
                "SELECT id FROM tasks WHERE project_id = ?",
                (project_id,),
            )
            task_ids = [row[0] for row in cursor.fetchall()]

            if not task_ids:
                return 0

            # Create placeholders for IN clause
            placeholders = ",".join("?" * len(task_ids))

            # Delete from task_dependencies (both FK columns)
            cursor.execute(
                f"DELETE FROM task_dependencies WHERE task_id IN ({placeholders}) OR depends_on_task_id IN ({placeholders})",
                task_ids + task_ids,
            )

            # Delete from test_results
            cursor.execute(
                f"DELETE FROM test_results WHERE task_id IN ({placeholders})",
                task_ids,
            )

            # Delete from correction_attempts
            cursor.execute(
                f"DELETE FROM correction_attempts WHERE task_id IN ({placeholders})",
                task_ids,
            )

            # Now delete the tasks (code_reviews and task_evidence cascade automatically)
            cursor.execute(
                "DELETE FROM tasks WHERE project_id = ?",
                (project_id,),
            )
            task_count = cursor.rowcount

            if own_cursor:
                self.conn.commit()

            return task_count

        except Exception:
            if own_cursor:
                self.conn.rollback()
            raise

    # Code Review CRUD operations (Sprint 10: 015-review-polish)

