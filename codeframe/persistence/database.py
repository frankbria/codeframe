"""Database management for CodeFRAME state."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING
import logging
from codeframe.core.models import ProjectStatus, Task, TaskStatus, AgentMaturity, Issue, CallType

if TYPE_CHECKING:
    from codeframe.core.models import CodeReview, QualityGateFailure, Checkpoint, CheckpointMetadata, TokenUsage

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for project state."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self.conn: Optional[sqlite3.Connection] = None

    def initialize(self, run_migrations: bool = True) -> None:
        """Initialize database schema.

        Args:
            run_migrations: Whether to run database migrations after schema creation
        """
        # Create parent directories if needed (skip for in-memory databases)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable foreign key constraints
        self.conn.execute("PRAGMA foreign_keys = ON")

        self._create_schema()

        # Run migrations if requested
        if run_migrations:
            self._run_migrations()

    def _create_schema(self) -> None:
        """Create database tables."""
        cursor = self.conn.cursor()

        # Projects table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,

                -- Source tracking (optional, can be set during setup or later)
                source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
                source_location TEXT,
                source_branch TEXT DEFAULT 'main',

                -- Managed workspace (always local to running instance)
                workspace_path TEXT NOT NULL,

                -- Git tracking (foundation for all projects)
                git_initialized BOOLEAN DEFAULT FALSE,
                current_commit TEXT,

                -- Workflow state
                status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
                phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                config JSON
            )
        """
        )

        # Issues table (cf-16.2: Hierarchical Issue/Task model)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                issue_number TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
                priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                workflow_step INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(project_id, issue_number)
            )
        """
        )

        # Create index for issues
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_issues_number
            ON issues(project_id, issue_number)
        """
        )

        # Tasks table (enhanced for Issue relationship)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                issue_id INTEGER REFERENCES issues(id),
                task_number TEXT,
                parent_issue_number TEXT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
                assigned_to TEXT,
                depends_on TEXT,
                can_parallelize BOOLEAN DEFAULT FALSE,
                priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                workflow_step INTEGER,
                requires_mcp BOOLEAN DEFAULT FALSE,
                estimated_tokens INTEGER,
                actual_tokens INTEGER,
                commit_sha TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """
        )

        # Create index for tasks by parent issue number
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_issue_number
            ON tasks(parent_issue_number)
        """
        )

        # Create composite index for get_pending_tasks query optimization
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority
            ON tasks(project_id, status, priority, created_at)
        """
        )

        # Agents table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Project-Agent junction table (many-to-many)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS project_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unassigned_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                CHECK(unassigned_at IS NULL OR unassigned_at >= assigned_at)
            )
        """
        )

        # Project-Agent indexes for query performance
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_project_active
            ON project_agents(project_id, is_active)
            WHERE is_active = TRUE
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_agent_active
            ON project_agents(agent_id, is_active)
            WHERE is_active = TRUE
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_assigned_at
            ON project_agents(assigned_at)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_project_agents_unassigned
            ON project_agents(unassigned_at)
            WHERE unassigned_at IS NOT NULL
        """
        )

        # Unique constraint: prevent duplicate active assignments
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_agents_unique_active
            ON project_agents(project_id, agent_id, is_active)
            WHERE is_active = TRUE
        """
        )

        # Blockers table (updated schema from migration 003)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blockers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL,
                task_id INTEGER,
                blocker_type TEXT NOT NULL CHECK(blocker_type IN ('SYNC', 'ASYNC')),
                question TEXT NOT NULL,
                answer TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'RESOLVED', 'EXPIRED')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """
        )

        # Blocker indexes (from migration 003)
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_blockers_status_created
            ON blockers(status, created_at)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_blockers_agent_status
            ON blockers(agent_id, status)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_blockers_task_id
            ON blockers(task_id)
        """
        )

        # Lint results table (Sprint 9)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS lint_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                linter TEXT NOT NULL CHECK(linter IN ('ruff', 'eslint', 'other')),
                error_count INTEGER NOT NULL DEFAULT 0,
                warning_count INTEGER NOT NULL DEFAULT 0,
                files_linted INTEGER NOT NULL DEFAULT 0,
                output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lint_results_task
            ON lint_results(task_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_lint_results_created
            ON lint_results(created_at DESC)
        """
        )

        # Memory table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                category TEXT CHECK(category IN ('pattern', 'decision', 'gotcha', 'preference', 'conversation', 'discovery_state', 'discovery_answers', 'prd')),
                key TEXT,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Context items table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS context_items (
                id TEXT PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                agent_id TEXT NOT NULL,
                item_type TEXT,
                content TEXT,
                importance_score FLOAT,
                importance_reasoning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                current_tier TEXT CHECK(current_tier IN ('hot', 'warm', 'cold')),
                manual_pin BOOLEAN DEFAULT FALSE
            )
        """
        )

        # Checkpoints table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                trigger TEXT,
                state_snapshot JSON,
                git_commit TEXT,
                db_backup_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Context checkpoints table (for flash save)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS context_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                checkpoint_data TEXT NOT NULL,
                items_count INTEGER NOT NULL,
                items_archived INTEGER NOT NULL,
                hot_items_retained INTEGER NOT NULL,
                token_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Index for context checkpoints
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_checkpoints_agent_created
            ON context_checkpoints(agent_id, created_at DESC)
        """
        )

        # Changelog table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS changelog (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                agent_id TEXT,
                task_id INTEGER,
                action TEXT,
                details JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Git branches table (cf-33: Git Branching & Deployment Workflow)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS git_branches (
                id INTEGER PRIMARY KEY,
                issue_id INTEGER REFERENCES issues(id),
                branch_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                merged_at TIMESTAMP,
                merge_commit TEXT,
                status TEXT CHECK(status IN ('active', 'merged', 'abandoned')) DEFAULT 'active'
            )
        """
        )

        # Deployments table (cf-33: Deployment tracking)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY,
                commit_hash TEXT NOT NULL,
                environment TEXT CHECK(environment IN ('staging', 'production')),
                status TEXT CHECK(status IN ('success', 'failed')),
                output TEXT,
                duration_seconds REAL,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Test Results table (cf-42: Test Runner Integration)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                status TEXT NOT NULL CHECK(status IN ('passed', 'failed', 'error', 'timeout', 'no_tests')),
                passed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                duration REAL DEFAULT 0.0,
                output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create index for test_results by task
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_test_results_task
            ON test_results(task_id)
        """
        )

        # Correction Attempts table (cf-43: Self-Correction Loop)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS correction_attempts (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
                error_analysis TEXT NOT NULL,
                fix_description TEXT NOT NULL,
                code_changes TEXT DEFAULT '',
                test_result_id INTEGER REFERENCES test_results(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create index for correction_attempts by task
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_correction_attempts_task
            ON correction_attempts(task_id)
        """
        )

        # Task Dependencies junction table (Sprint 4: Multi-Agent Coordination)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_dependencies (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL,
                depends_on_task_id INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
                UNIQUE(task_id, depends_on_task_id)
            )
        """
        )

        # Create index for task_dependencies queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_dependencies_task
            ON task_dependencies(task_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on
            ON task_dependencies(depends_on_task_id)
        """
        )

        self.conn.commit()

    def _run_migrations(self) -> None:
        """Run database migrations.

        Automatically discovers and runs migration scripts from the migrations directory.
        """
        try:
            from codeframe.persistence.migrations import MigrationRunner
            from codeframe.persistence.migrations.migration_001_remove_agent_type_constraint import (
                migration as migration_001,
            )
            from codeframe.persistence.migrations.migration_002_refactor_projects_schema import (
                migration as migration_002,
            )
            from codeframe.persistence.migrations.migration_003_update_blockers_schema import (
                migration as migration_003,
            )
            from codeframe.persistence.migrations.migration_004_add_context_checkpoints import (
                migration as migration_004,
            )
            from codeframe.persistence.migrations.migration_005_add_context_indexes import (
                migration as migration_005,
            )
            from codeframe.persistence.migrations.migration_006_mvp_completion import (
                migration as migration_006,
            )
            from codeframe.persistence.migrations.migration_007_sprint10_review_polish import (
                migration as migration_007,
            )

            # Skip migrations for in-memory databases
            if self.db_path == ":memory:":
                logger.debug("Skipping migrations for in-memory database")
                return

            runner = MigrationRunner(str(self.db_path))

            # Register migrations
            runner.register(migration_001)
            runner.register(migration_002)
            runner.register(migration_003)
            runner.register(migration_004)
            runner.register(migration_005)
            runner.register(migration_006)
            runner.register(migration_007)

            # Apply all pending migrations
            runner.apply_all()

        except ImportError as e:
            logger.warning(f"Migration system not available: {e}")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

    def create_project(
        self,
        name: str,
        description: str,
        source_type: str = "empty",
        source_location: Optional[str] = None,
        source_branch: str = "main",
        workspace_path: Optional[str] = None,
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
            **kwargs: Additional fields (config, status, etc.)

        Returns:
            Created project ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (
                name, description, source_type, source_location,
                source_branch, workspace_path, git_initialized, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_project(self, project_id: int) -> Optional[dict]:
        """Get project by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

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

    def get_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get issue by ID.

        Args:
            issue_id: Issue ID

        Returns:
            Issue dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_project_issues(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all issues for a project.

        Args:
            project_id: Project ID

        Returns:
            List of issue dictionaries ordered by issue_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM issues WHERE project_id = ? ORDER BY issue_number",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

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

    def get_project_tasks(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all tasks for a project (all statuses).

        Args:
            project_id: Project ID

        Returns:
            List of task dictionaries ordered by task_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY task_number",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_task(self, task_id: int, updates: Dict[str, Any]) -> int:
        """Update task fields.

        Args:
            task_id: Task ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected
        """
        if not updates:
            return 0

        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, TaskStatus):
                values.append(value.value)
            else:
                values.append(value)

        values.append(task_id)

        query = f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get task by ID.

        Args:
            task_id: Task ID

        Returns:
            Task dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> "Database":
        """Context manager entry."""
        if not self.conn:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    # Blocker CRUD operations (049-human-in-loop)

    def create_blocker(
        self,
        agent_id: str,
        project_id: int,
        task_id: Optional[int],
        blocker_type: str,
        question: str,
    ) -> int:
        """Create a new blocker with rate limiting.

        Rate limit: 10 blockers per minute per agent (T063).

        Args:
            agent_id: ID of the agent creating the blocker
            project_id: ID of the project this blocker belongs to
            task_id: Associated task ID (nullable for agent-level blockers)
            blocker_type: Type of blocker ('SYNC' or 'ASYNC')
            question: Question for the user (max 2000 chars)

        Returns:
            Blocker ID of the created blocker

        Raises:
            ValueError: If agent exceeds rate limit (10 blockers/minute)
        """
        cursor = self.conn.cursor()

        # Check rate limit: 10 blockers per minute per agent
        cursor.execute(
            """SELECT COUNT(*) as count
               FROM blockers
               WHERE agent_id = ?
                 AND datetime(created_at) > datetime('now', '-60 seconds')""",
            (agent_id,),
        )
        row = cursor.fetchone()
        recent_blocker_count = row["count"]

        if recent_blocker_count >= 10:
            raise ValueError(
                f"Rate limit exceeded: Agent {agent_id} has created {recent_blocker_count} "
                f"blockers in the last minute (limit: 10/minute)"
            )

        # Create the blocker
        cursor.execute(
            """INSERT INTO blockers (agent_id, project_id, task_id, blocker_type, question, status)
               VALUES (?, ?, ?, ?, ?, 'PENDING')""",
            (agent_id, project_id, task_id, blocker_type, question),
        )
        self.conn.commit()
        return cursor.lastrowid

    def resolve_blocker(self, blocker_id: int, answer: str) -> bool:
        """Resolve a blocker with user's answer.

        Args:
            blocker_id: ID of the blocker to resolve
            answer: User's answer (max 5000 chars)

        Returns:
            True if blocker was resolved, False if already resolved or not found
        """
        from datetime import datetime, UTC

        cursor = self.conn.cursor()
        resolved_at = datetime.now(UTC).isoformat()
        cursor.execute(
            """UPDATE blockers
               SET answer = ?, status = 'RESOLVED', resolved_at = ?
               WHERE id = ? AND status = 'PENDING'""",
            (answer, resolved_at, blocker_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_pending_blocker(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get oldest pending blocker for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Blocker dictionary or None if no pending blockers
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM blockers
               WHERE agent_id = ? AND status = 'PENDING'
               ORDER BY created_at ASC LIMIT 1""",
            (agent_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_blockers(self, project_id: int, status: Optional[str] = None) -> Dict[str, Any]:
        """List blockers with agent/task info joined.

        Args:
            project_id: Filter by project ID
            status: Optional status filter ('PENDING', 'RESOLVED', 'EXPIRED')

        Returns:
            Dictionary with blockers list and counts:
            - blockers: List of blocker dictionaries with enriched data
            - total: Total number of blockers
            - pending_count: Number of pending blockers
            - sync_count: Number of SYNC blockers
            - async_count: Number of ASYNC blockers
        """
        cursor = self.conn.cursor()

        # Build query with optional status filter
        query = """
            SELECT
                b.*,
                a.type as agent_name,
                t.title as task_title,
                (julianday('now') - julianday(b.created_at)) * 86400000 as time_waiting_ms
            FROM blockers b
            LEFT JOIN agents a ON b.agent_id = a.id
            LEFT JOIN tasks t ON b.task_id = t.id
            WHERE b.project_id = ?
        """
        params = [project_id]

        if status:
            query += " AND b.status = ?"
            params.append(status)

        query += " ORDER BY b.created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        blockers = [dict(row) for row in rows]
        pending_count = sum(1 for b in blockers if b.get("status") == "PENDING")
        sync_count = sum(1 for b in blockers if b.get("blocker_type") == "SYNC")
        async_count = sum(1 for b in blockers if b.get("blocker_type") == "ASYNC")

        return {
            "blockers": blockers,
            "total": len(blockers),
            "pending_count": pending_count,
            "sync_count": sync_count,
            "async_count": async_count,
        }

    def get_blocker(self, blocker_id: int) -> Optional[Dict[str, Any]]:
        """Get blocker details by ID.

        Args:
            blocker_id: ID of the blocker

        Returns:
            Blocker dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM blockers WHERE id = ?", (blocker_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def expire_stale_blockers(self, hours: int = 24) -> List[int]:
        """Expire blockers pending longer than specified hours.

        Args:
            hours: Number of hours before blocker is considered stale (default: 24)

        Returns:
            List of expired blocker IDs
        """
        cursor = self.conn.cursor()
        cursor.execute(
            f"""UPDATE blockers
               SET status = 'EXPIRED'
               WHERE status = 'PENDING'
                 AND datetime(created_at) < datetime('now', '-{hours} hours')
               RETURNING id"""
        )
        # Fetch results BEFORE commit (SQLite requirement for RETURNING clause)
        expired_ids = [row[0] for row in cursor.fetchall()]
        self.conn.commit()
        return expired_ids

    def get_blocker_metrics(self, project_id: int) -> Dict[str, Any]:
        """Calculate blocker metrics for a project.

        Tracks:
        - Average resolution time (seconds from created_at to resolved_at for RESOLVED blockers)
        - Expiration rate (percentage of blockers that expired vs resolved)
        - Total blocker counts by status and type

        Args:
            project_id: Project ID to calculate metrics for

        Returns:
            Dictionary with metrics:
            - avg_resolution_time_seconds: Average time to resolve (None if no resolved blockers)
            - expiration_rate_percent: Percentage of blockers that expired (0-100)
            - total_blockers: Total count of all blockers
            - resolved_count: Count of RESOLVED blockers
            - expired_count: Count of EXPIRED blockers
            - pending_count: Count of PENDING blockers
            - sync_count: Count of SYNC blockers
            - async_count: Count of ASYNC blockers
        """
        cursor = self.conn.cursor()

        # Get all blockers for tasks in this project
        cursor.execute(
            """
            SELECT
                b.status,
                b.blocker_type,
                b.created_at,
                b.resolved_at
            FROM blockers b
            INNER JOIN tasks t ON b.task_id = t.id
            WHERE t.project_id = ?
        """,
            (project_id,),
        )

        rows = cursor.fetchall()

        if not rows:
            return {
                "avg_resolution_time_seconds": None,
                "expiration_rate_percent": 0.0,
                "total_blockers": 0,
                "resolved_count": 0,
                "expired_count": 0,
                "pending_count": 0,
                "sync_count": 0,
                "async_count": 0,
            }

        # Calculate metrics
        total_blockers = len(rows)
        resolved_count = 0
        expired_count = 0
        pending_count = 0
        sync_count = 0
        async_count = 0
        resolution_times = []

        for row in rows:
            status = row["status"]
            blocker_type = row["blocker_type"]
            created_at = row["created_at"]
            resolved_at = row["resolved_at"]

            # Count by status
            if status == "RESOLVED":
                resolved_count += 1
                # Calculate resolution time
                if created_at and resolved_at:
                    from datetime import datetime, timezone

                    created = datetime.fromisoformat(created_at)
                    resolved = datetime.fromisoformat(resolved_at)

                    # Normalize both to timezone-aware (assume UTC if naive)
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if resolved.tzinfo is None:
                        resolved = resolved.replace(tzinfo=timezone.utc)

                    resolution_time_seconds = (resolved - created).total_seconds()
                    resolution_times.append(resolution_time_seconds)
            elif status == "EXPIRED":
                expired_count += 1
            elif status == "PENDING":
                pending_count += 1

            # Count by type
            if blocker_type == "SYNC":
                sync_count += 1
            elif blocker_type == "ASYNC":
                async_count += 1

        # Calculate average resolution time
        avg_resolution_time = None
        if resolution_times:
            avg_resolution_time = sum(resolution_times) / len(resolution_times)

        # Calculate expiration rate
        completed_blockers = resolved_count + expired_count
        expiration_rate = 0.0
        if completed_blockers > 0:
            expiration_rate = (expired_count / completed_blockers) * 100.0

        return {
            "avg_resolution_time_seconds": avg_resolution_time,
            "expiration_rate_percent": expiration_rate,
            "total_blockers": total_blockers,
            "resolved_count": resolved_count,
            "expired_count": expired_count,
            "pending_count": pending_count,
            "sync_count": sync_count,
            "async_count": async_count,
        }

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects with progress metrics.

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

    def update_project(self, project_id: int, updates: Dict[str, Any]) -> int:
        """Update project fields.

        Args:
            project_id: Project ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected
        """
        if not updates:
            return 0

        # Build UPDATE query dynamically
        fields = []
        values = []
        for key, value in updates.items():
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

        return cursor.rowcount

    def delete_project(self, project_id: int) -> None:
        """Delete a project.

        Args:
            project_id: Project ID to delete
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

    def create_agent(
        self,
        agent_id: str,
        agent_type: str,
        provider: str,
        maturity_level: AgentMaturity,
    ) -> str:
        """Create a new agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (lead, backend, frontend, test, review)
            provider: AI provider (claude, gpt4)
            maturity_level: Maturity level (D1-D4)

        Returns:
            Agent ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (id, type, provider, maturity_level, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, agent_type, provider, maturity_level.value, "idle"),
        )
        self.conn.commit()
        return agent_id

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents.

        Returns:
            List of agent dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents ORDER BY id")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> int:
        """Update agent fields.

        Args:
            agent_id: Agent ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected
        """
        if not updates:
            return 0

        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, AgentMaturity):
                values.append(value.value)
            else:
                values.append(value)

        values.append(agent_id)

        query = f"UPDATE agents SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount

    def assign_agent_to_project(
        self,
        project_id: int,
        agent_id: str,
        role: str = "worker"
    ) -> int:
        """Assign an agent to a project.

        Args:
            project_id: Project ID
            agent_id: Agent ID
            role: Agent's role in this project

        Returns:
            Assignment ID

        Raises:
            sqlite3.IntegrityError: If agent already assigned to project (while active)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO project_agents (project_id, agent_id, role, is_active)
            VALUES (?, ?, ?, TRUE)
            """,
            (project_id, agent_id, role)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_agents_for_project(
        self,
        project_id: int,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all agents assigned to a project.

        Args:
            project_id: Project ID
            active_only: If True, only return currently assigned agents

        Returns:
            List of agent dictionaries with assignment metadata
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                a.id AS agent_id,
                a.type,
                a.provider,
                a.maturity_level,
                a.status,
                a.current_task_id,
                a.last_heartbeat,
                pa.id AS assignment_id,
                pa.role,
                pa.assigned_at,
                pa.unassigned_at,
                pa.is_active
            FROM agents a
            JOIN project_agents pa ON a.id = pa.agent_id
            WHERE pa.project_id = ?
        """

        if active_only:
            query += " AND pa.is_active = TRUE"

        query += " ORDER BY pa.assigned_at DESC"

        cursor.execute(query, (project_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_projects_for_agent(
        self,
        agent_id: str,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all projects an agent is assigned to.

        Args:
            agent_id: Agent ID
            active_only: If True, only return active assignments

        Returns:
            List of project dictionaries with assignment metadata
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                p.id AS project_id,
                p.name,
                p.description,
                p.status,
                p.phase,
                pa.role,
                pa.assigned_at,
                pa.unassigned_at,
                pa.is_active
            FROM projects p
            JOIN project_agents pa ON p.id = pa.project_id
            WHERE pa.agent_id = ?
        """

        if active_only:
            query += " AND pa.is_active = TRUE"

        query += " ORDER BY pa.assigned_at DESC"

        cursor.execute(query, (agent_id,))
        return [dict(row) for row in cursor.fetchall()]

    def remove_agent_from_project(
        self,
        project_id: int,
        agent_id: str
    ) -> int:
        """Remove an agent from a project (soft delete).

        Args:
            project_id: Project ID
            agent_id: Agent ID

        Returns:
            Number of rows affected (0 if not assigned, 1 if unassigned)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE project_agents
            SET is_active = FALSE,
                unassigned_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
              AND agent_id = ?
              AND is_active = TRUE
            """,
            (project_id, agent_id)
        )
        self.conn.commit()
        return cursor.rowcount

    def get_agent_assignment(
        self,
        project_id: int,
        agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get assignment details for a specific agent-project pair.

        Args:
            project_id: Project ID
            agent_id: Agent ID

        Returns:
            Assignment dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                project_id,
                agent_id,
                role,
                assigned_at,
                unassigned_at,
                is_active
            FROM project_agents
            WHERE project_id = ? AND agent_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (project_id, agent_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def reassign_agent_role(
        self,
        project_id: int,
        agent_id: str,
        new_role: str
    ) -> int:
        """Update an agent's role on a project.

        Args:
            project_id: Project ID
            agent_id: Agent ID
            new_role: New role for the agent

        Returns:
            Number of rows affected
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE project_agents
            SET role = ?
            WHERE project_id = ?
              AND agent_id = ?
              AND is_active = TRUE
            """,
            (new_role, project_id, agent_id)
        )
        self.conn.commit()
        return cursor.rowcount

    def get_available_agents(
        self,
        agent_type: Optional[str] = None,
        exclude_project_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get agents available for assignment (not at capacity).

        Args:
            agent_type: Filter by agent type (optional)
            exclude_project_id: Exclude agents already on this project

        Returns:
            List of available agent dictionaries
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                a.*,
                COUNT(pa.id) AS active_assignments
            FROM agents a
            LEFT JOIN project_agents pa ON a.id = pa.agent_id
                AND pa.is_active = TRUE
        """

        params = []
        conditions = []

        if exclude_project_id:
            conditions.append("(pa.project_id IS NULL OR pa.project_id != ?)")
            params.append(exclude_project_id)

        if agent_type:
            conditions.append("a.type = ?")
            params.append(agent_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            GROUP BY a.id
            HAVING active_assignments < 3
            ORDER BY active_assignments ASC, a.last_heartbeat DESC
        """

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def create_memory(
        self,
        project_id: int,
        category: str,
        key: str,
        value: str,
    ) -> int:
        """Create a memory entry.

        Args:
            project_id: Project ID
            category: Memory category (pattern, decision, gotcha, preference, conversation)
            key: Memory key (role for conversation: user_1, assistant_1, etc.)
            value: Memory value (content)

        Returns:
            Memory ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory (project_id, category, key, value)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, category, key, value),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get memory entry by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM memory WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_project_memories(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all memory entries for a project.

        Args:
            project_id: Project ID

        Returns:
            List of memory dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, project_id: int) -> List[Dict[str, Any]]:
        """Get conversation history for a project.

        Conversation messages are stored in memory table with category='conversation'.

        Args:
            project_id: Project ID

        Returns:
            List of conversation message dictionaries ordered by insertion (id)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM memory
            WHERE project_id = ? AND category = 'conversation'
            ORDER BY id
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Additional Issue methods (cf-16.2)
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
        """
        if not updates:
            return 0

        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            values.append(value)

        values.append(issue_id)

        query = f"UPDATE issues SET {', '.join(fields)} WHERE id = ?"

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

    def get_tasks_by_issue(self, issue_id: int) -> List[Dict[str, Any]]:
        """Get all tasks for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of task dictionaries ordered by task_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE issue_id = ? ORDER BY task_number",
            (issue_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_tasks_by_parent_issue_number(self, parent_issue_number: str) -> List[Dict[str, Any]]:
        """Get all tasks by parent issue number.

        Args:
            parent_issue_number: Parent issue number (e.g., "1.5")

        Returns:
            List of task dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE parent_issue_number = ? ORDER BY task_number",
            (parent_issue_number,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_issue_with_task_counts(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get issue with count of associated tasks.

        Args:
            issue_id: Issue ID

        Returns:
            Issue dictionary with task_count field, or None if not found
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
        return dict(row) if row else None

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
    def get_prd(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get PRD for a project.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with prd_content, generated_at, updated_at or None if not found
        """
        from datetime import datetime

        cursor = self.conn.cursor()

        # Get PRD content
        cursor.execute(
            """
            SELECT value, created_at, updated_at
            FROM memory
            WHERE project_id = ? AND category = 'prd' AND key = 'prd_content'
            """,
            (project_id,),
        )
        prd_row = cursor.fetchone()

        if not prd_row:
            return None

        # Get generated_at timestamp
        cursor.execute(
            """
            SELECT value
            FROM memory
            WHERE project_id = ? AND category = 'prd' AND key = 'generated_at'
            """,
            (project_id,),
        )
        generated_row = cursor.fetchone()

        # Convert SQLite timestamps to RFC 3339 format
        def ensure_rfc3339(timestamp_str: str) -> str:
            """Ensure timestamp is in RFC 3339 format with timezone."""
            if not timestamp_str:
                return timestamp_str
            # If already has 'Z' or timezone, return as-is
            if "Z" in timestamp_str or "+" in timestamp_str:
                return timestamp_str
            # Parse and add Z suffix for UTC
            try:
                # SQLite format: "2025-10-17 22:01:56"
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + "Z"
            except ValueError:
                return timestamp_str

        # Determine generated_at
        generated_at = (
            generated_row["value"] if generated_row else ensure_rfc3339(prd_row["created_at"])
        )

        # Determine updated_at - use generated_at if updated_at is same as created_at
        updated_at = ensure_rfc3339(
            prd_row["updated_at"] if prd_row["updated_at"] else prd_row["created_at"]
        )

        # If updated_at == created_at (never been updated), use generated_at for both
        if prd_row["updated_at"] == prd_row["created_at"] and generated_row:
            updated_at = generated_at

        return {
            "prd_content": prd_row["value"],
            "generated_at": generated_at,
            "updated_at": updated_at,
        }

    # Issues/Tasks methods (cf-26)
    def get_issues_with_tasks(self, project_id: int, include_tasks: bool = False) -> Dict[str, Any]:
        """Get issues for a project with optional tasks.

        Args:
            project_id: Project ID
            include_tasks: Whether to include tasks in response

        Returns:
            Dictionary with issues, total_issues, total_tasks
        """
        from datetime import datetime

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

        # Helper function for RFC 3339 timestamps
        def ensure_rfc3339(timestamp_str: str) -> str:
            """Ensure timestamp is in RFC 3339 format with timezone."""
            if not timestamp_str:
                return timestamp_str
            if "Z" in timestamp_str or "+" in timestamp_str:
                return timestamp_str
            try:
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + "Z"
            except ValueError:
                return timestamp_str

        # Format issues according to API contract
        issues = []
        total_tasks = 0

        for issue_row in issue_rows:
            issue_dict = dict(issue_row)

            # Format issue according to API contract
            formatted_issue = {
                "id": str(issue_dict["id"]),
                "issue_number": issue_dict["issue_number"],
                "title": issue_dict["title"],
                "description": issue_dict["description"] or "",
                "status": issue_dict["status"],
                "priority": issue_dict["priority"],
                "depends_on": [],  # TODO: Parse from database if stored
                "proposed_by": "agent",  # Default for now
                "created_at": ensure_rfc3339(issue_dict["created_at"]),
                "updated_at": ensure_rfc3339(issue_dict["created_at"]),  # Use created_at for now
                "completed_at": (
                    ensure_rfc3339(issue_dict["completed_at"])
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
                        "created_at": ensure_rfc3339(task_dict["created_at"]),
                        "updated_at": ensure_rfc3339(
                            task_dict["created_at"]
                        ),  # Use created_at for now
                        "completed_at": (
                            ensure_rfc3339(task_dict["completed_at"])
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
    def create_git_branch(self, issue_id: int, branch_name: str) -> int:
        """Create a git branch record.

        Args:
            issue_id: Issue ID this branch belongs to
            branch_name: Git branch name

        Returns:
            Branch ID

        Raises:
            sqlite3.IntegrityError: If issue_id doesn't exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO git_branches (issue_id, branch_name, status)
            VALUES (?, ?, ?)
            """,
            (issue_id, branch_name, "active"),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_branch_for_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get the most recent active branch for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Branch dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM git_branches
            WHERE issue_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (issue_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def mark_branch_merged(self, branch_id: int, merge_commit: str) -> int:
        """Mark a branch as merged.

        Args:
            branch_id: Branch ID
            merge_commit: Git commit SHA of merge

        Returns:
            Number of rows updated
        """
        from datetime import datetime

        cursor = self.conn.cursor()
        merged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            UPDATE git_branches
            SET status = ?, merge_commit = ?, merged_at = ?
            WHERE id = ?
            """,
            ("merged", merge_commit, merged_at, branch_id),
        )
        self.conn.commit()
        return cursor.rowcount

    def mark_branch_abandoned(self, branch_id: int) -> int:
        """Mark a branch as abandoned.

        Args:
            branch_id: Branch ID

        Returns:
            Number of rows updated
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE git_branches SET status = ? WHERE id = ?",
            ("abandoned", branch_id),
        )
        self.conn.commit()
        return cursor.rowcount

    def delete_git_branch(self, branch_id: int) -> int:
        """Delete a git branch record.

        Args:
            branch_id: Branch ID

        Returns:
            Number of rows deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM git_branches WHERE id = ?", (branch_id,))
        self.conn.commit()
        return cursor.rowcount

    def get_branches_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all branches with given status.

        Args:
            status: Branch status (active, merged, abandoned)

        Returns:
            List of branch dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM git_branches WHERE status = ? ORDER BY id",
            (status,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_all_branches_for_issue(self, issue_id: int) -> List[Dict[str, Any]]:
        """Get all branches for an issue (all statuses).

        Args:
            issue_id: Issue ID

        Returns:
            List of branch dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM git_branches WHERE issue_id = ? ORDER BY id",
            (issue_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def count_branches_for_issue(self, issue_id: int) -> int:
        """Count branches for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Number of branches
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM git_branches WHERE issue_id = ?",
            (issue_id,),
        )
        return cursor.fetchone()[0]

    def get_branch_statistics(self) -> Dict[str, int]:
        """Get branch statistics across all statuses.

        Returns:
            Dictionary with total, active, merged, abandoned counts
        """
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM git_branches")
        total = cursor.fetchone()[0]

        # Count by status
        stats = {"total": total}
        for status in ["active", "merged", "abandoned"]:
            cursor.execute(
                "SELECT COUNT(*) FROM git_branches WHERE status = ?",
                (status,),
            )
            stats[status] = cursor.fetchone()[0]

        return stats

    # Test Results methods (cf-42)
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

    def create_correction_attempt(
        self,
        task_id: int,
        attempt_number: int,
        error_analysis: str,
        fix_description: str,
        code_changes: str = "",
        test_result_id: Optional[int] = None,
    ) -> int:
        """
        Create a correction attempt record for a task.

        Args:
            task_id: ID of the task being corrected
            attempt_number: Which attempt this is (1-3)
            error_analysis: Analysis of what went wrong
            fix_description: Description of the fix attempted
            code_changes: Actual code changes (diff format)
            test_result_id: Optional link to test result after fix

        Returns:
            ID of created correction attempt

        Raises:
            ValueError: If attempt_number not in 1-3 range
        """
        if not 1 <= attempt_number <= 3:
            raise ValueError(f"attempt_number must be between 1 and 3, got {attempt_number}")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO correction_attempts 
            (task_id, attempt_number, error_analysis, fix_description, code_changes, test_result_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                attempt_number,
                error_analysis,
                fix_description,
                code_changes,
                test_result_id,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_correction_attempts_by_task(self, task_id: int) -> list[dict]:
        """
        Get all correction attempts for a task, ordered by attempt number.

        Args:
            task_id: ID of the task

        Returns:
            List of correction attempt dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, task_id, attempt_number, error_analysis, 
                   fix_description, code_changes, test_result_id, created_at
            FROM correction_attempts
            WHERE task_id = ?
            ORDER BY attempt_number ASC
            """,
            (task_id,),
        )

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_latest_correction_attempt(self, task_id: int) -> Optional[dict]:
        """
        Get the most recent correction attempt for a task.

        Args:
            task_id: ID of the task

        Returns:
            Correction attempt dictionary or None if no attempts exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, task_id, attempt_number, error_analysis,
                   fix_description, code_changes, test_result_id, created_at
            FROM correction_attempts
            WHERE task_id = ?
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (task_id,),
        )

        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None

    def count_correction_attempts(self, task_id: int) -> int:
        """
        Count the number of correction attempts for a task.

        Args:
            task_id: ID of the task

        Returns:
            Number of correction attempts
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM correction_attempts WHERE task_id = ?", (task_id,))
        return cursor.fetchone()[0]

    # Task Dependency Management Methods (Sprint 4: cf-21)

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

    def get_recent_activity(self, project_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent activity/changelog entries for a project.

        Args:
            project_id: Project ID to filter activity
            limit: Maximum number of activity items to return

        Returns:
            List of activity dictionaries formatted for frontend
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                timestamp,
                agent_id,
                action,
                task_id,
                details
            FROM changelog
            WHERE project_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """,
            (project_id, limit),
        )

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        # Format for frontend
        activity_items = []
        for row in rows:
            activity_dict = dict(zip(columns, row))

            # Map database fields to frontend expected format
            activity_items.append(
                {
                    "timestamp": activity_dict["timestamp"],
                    "type": activity_dict["action"],
                    "agent": activity_dict["agent_id"] or "system",
                    "message": activity_dict.get("details") or activity_dict["action"],
                }
            )

        return activity_items

    # Context Management Methods (007-context-management)

    def create_context_item(
        self, project_id: int, agent_id: str, item_type: str, content: str
    ) -> str:
        """Create a new context item with auto-calculated importance score.

        Auto-calculates importance score using hybrid exponential decay algorithm:
        - Type weight (40%): Based on item_type
        - Age decay (40%): Exponential decay (new items get 1.0)
        - Access boost (20%): Log-normalized frequency (new items get 0.0)

        Args:
            project_id: Project ID this context belongs to
            agent_id: Agent ID that created this context
            item_type: Type of context (TASK, CODE, ERROR, TEST_RESULT, PRD_SECTION)
            content: The actual context content

        Returns:
            Created context item ID (UUID string)
        """
        import uuid
        from datetime import datetime, UTC
        from codeframe.lib.importance_scorer import calculate_importance_score, assign_tier

        # Auto-calculate importance score for new item
        created_at = datetime.now(UTC)
        importance_score = calculate_importance_score(
            item_type=item_type,
            created_at=created_at,
            access_count=0,  # New item has no accesses yet
            last_accessed=created_at,
        )

        # Auto-assign tier based on importance score (T040)
        # Convert to lowercase for current_tier column
        tier = assign_tier(importance_score).lower()

        # Generate UUID for id (actual schema uses TEXT PRIMARY KEY)
        item_id = str(uuid.uuid4())

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO context_items (
                id, project_id, agent_id, item_type, content, importance_score,
                current_tier, created_at, last_accessed, access_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                project_id,
                agent_id,
                item_type,
                content,
                importance_score,
                tier,
                created_at.isoformat(),
                created_at.isoformat(),
                0,
            ),
        )
        self.conn.commit()
        return item_id

    def get_context_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a context item by ID.

        Args:
            item_id: Context item ID (UUID string)

        Returns:
            Context item dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM context_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_context_items(
        self,
        project_id: int,
        agent_id: str,
        tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List context items for an agent on a project, optionally filtered by tier.

        Args:
            project_id: Project ID to filter by
            agent_id: Agent ID to filter by
            tier: Optional tier filter (HOT, WARM, COLD)
            limit: Maximum number of items to return
            offset: Number of items to skip

        Returns:
            List of context item dictionaries
        """
        cursor = self.conn.cursor()

        if tier:
            # Convert tier to lowercase for current_tier column
            tier_lower = tier.lower()
            query = """
                SELECT * FROM context_items
                WHERE project_id = ? AND agent_id = ? AND current_tier = ?
                ORDER BY importance_score DESC, last_accessed DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, (project_id, agent_id, tier_lower, limit, offset))
        else:
            query = """
                SELECT * FROM context_items
                WHERE project_id = ? AND agent_id = ?
                ORDER BY importance_score DESC, last_accessed DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, (project_id, agent_id, limit, offset))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_context_item_tier(self, item_id: str, tier: str, importance_score: float) -> None:
        """Update a context item's tier and importance score.

        Args:
            item_id: Context item ID (UUID string)
            tier: New tier (HOT, WARM, COLD)
            importance_score: Updated importance score
        """
        # Convert tier to lowercase for current_tier column
        tier_lower = tier.lower()

        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE context_items
            SET current_tier = ?, importance_score = ?
            WHERE id = ?
            """,
            (tier_lower, importance_score, item_id),
        )
        self.conn.commit()

    def delete_context_item(self, item_id: str) -> None:
        """Delete a context item.

        Args:
            item_id: Context item ID to delete (UUID string)
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM context_items WHERE id = ?", (item_id,))
        self.conn.commit()

    def update_context_item_access(self, item_id: str) -> None:
        """Update last_accessed timestamp and increment access_count.

        Args:
            item_id: Context item ID (UUID string)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE context_items
            SET last_accessed = CURRENT_TIMESTAMP,
                access_count = access_count + 1
            WHERE id = ?
            """,
            (item_id,),
        )
        self.conn.commit()

    def archive_cold_items(self, project_id: int, agent_id: str) -> int:
        """Archive (delete) all COLD tier items for an agent (T053).

        This method is called during flash save to reduce memory footprint.
        COLD tier items are fully archived in the checkpoint before deletion.

        Args:
            project_id: Project ID the agent is working on
            agent_id: Agent ID to archive COLD items for

        Returns:
            int: Number of items archived (deleted)

        Example:
            >>> db.archive_cold_items(123, "backend-worker-001")
            15  # 15 COLD items deleted
        """
        cursor = self.conn.cursor()

        # Delete all COLD tier items for this agent on this project
        cursor.execute(
            """DELETE FROM context_items
               WHERE project_id = ?
                 AND agent_id = ?
                 AND current_tier = 'cold'""",
            (project_id, agent_id),
        )

        deleted_count = cursor.rowcount
        self.conn.commit()

        return deleted_count

    def create_checkpoint(
        self,
        agent_id: str,
        checkpoint_data: str,
        items_count: int,
        items_archived: int,
        hot_items_retained: int,
        token_count: int,
    ) -> int:
        """Create a flash save checkpoint.

        Args:
            agent_id: Agent ID creating the checkpoint
            checkpoint_data: JSON serialized context state
            items_count: Total items before flash save
            items_archived: Number of COLD items archived
            hot_items_retained: Number of HOT items kept
            token_count: Total tokens before flash save

        Returns:
            Created checkpoint ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO context_checkpoints (
                agent_id, checkpoint_data, items_count, items_archived,
                hot_items_retained, token_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                checkpoint_data,
                items_count,
                items_archived,
                hot_items_retained,
                token_count,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def list_checkpoints(self, agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List checkpoints for an agent, most recent first.

        Args:
            agent_id: Agent ID to filter by
            limit: Maximum number of checkpoints to return

        Returns:
            List of checkpoint dictionaries ordered by created_at DESC
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM context_checkpoints
            WHERE agent_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (agent_id, limit),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_checkpoint(self, checkpoint_id: int) -> Optional[Dict[str, Any]]:
        """Get a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM context_checkpoints WHERE id = ?", (checkpoint_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    # Sprint 9: MVP Completion Database Methods

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

    # Code Review CRUD operations (Sprint 10: 015-review-polish)

    def save_code_review(self, review: 'CodeReview') -> int:
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
                review.severity.value if hasattr(review.severity, 'value') else review.severity,
                review.category.value if hasattr(review.category, 'value') else review.category,
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
    ) -> List['CodeReview']:
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
                    id=row_dict['id'],
                    task_id=row_dict['task_id'],
                    agent_id=row_dict['agent_id'],
                    project_id=row_dict['project_id'],
                    file_path=row_dict['file_path'],
                    line_number=row_dict['line_number'],
                    severity=Severity(row_dict['severity']),
                    category=ReviewCategory(row_dict['category']),
                    message=row_dict['message'],
                    recommendation=row_dict['recommendation'],
                    code_snippet=row_dict['code_snippet'],
                )
            )

        return reviews

    def get_code_reviews_by_severity(
        self,
        project_id: int,
        severity: str
    ) -> List['CodeReview']:
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
        self,
        project_id: int,
        severity: Optional[str] = None
    ) -> List['CodeReview']:
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

    def update_quality_gate_status(
        self,
        task_id: int,
        status: str,
        failures: List['QualityGateFailure'],
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
        failures_json = json.dumps([
            {
                'gate': f.gate.value if hasattr(f.gate, 'value') else f.gate,
                'reason': f.reason,
                'details': f.details,
                'severity': f.severity.value if hasattr(f.severity, 'value') else f.severity,
            }
            for f in failures
        ])

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
                'status': None,
                'failures': [],
                'requires_human_approval': False,
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
            'status': status,
            'failures': failures,
            'requires_human_approval': bool(requires_approval),
        }

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

    def save_checkpoint(
        self,
        project_id: int,
        name: str,
        description: Optional[str],
        trigger: str,
        git_commit: str,
        database_backup_path: str,
        context_snapshot_path: str,
        metadata: 'CheckpointMetadata'
    ) -> int:
        """Save a checkpoint to database.

        Args:
            project_id: Project ID
            name: Checkpoint name (max 100 chars)
            description: Optional description (max 500 chars)
            trigger: Trigger type (manual, auto, phase_transition)
            git_commit: Git commit SHA
            database_backup_path: Path to database backup file
            context_snapshot_path: Path to context snapshot JSON
            metadata: CheckpointMetadata object

        Returns:
            Created checkpoint ID
        """

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO checkpoints (
                project_id, name, description, trigger, git_commit,
                database_backup_path, context_snapshot_path, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                name,
                description,
                trigger,
                git_commit,
                database_backup_path,
                context_snapshot_path,
                json.dumps(metadata.model_dump())
            )
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_checkpoints(self, project_id: int) -> List['Checkpoint']:
        """Get all checkpoints for a project, sorted by created_at DESC.

        Args:
            project_id: Project ID

        Returns:
            List of Checkpoint objects, most recent first
        """
        from codeframe.core.models import Checkpoint, CheckpointMetadata

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id, project_id, name, description, trigger, git_commit,
                database_backup_path, context_snapshot_path, metadata, created_at
            FROM checkpoints
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,)
        )

        checkpoints = []
        for row in cursor.fetchall():
            # Parse metadata JSON
            metadata_dict = json.loads(row["metadata"]) if row["metadata"] else {}
            metadata = CheckpointMetadata(**metadata_dict)

            checkpoint = Checkpoint(
                id=row["id"],
                project_id=row["project_id"],
                name=row["name"],
                description=row["description"],
                trigger=row["trigger"],
                git_commit=row["git_commit"],
                database_backup_path=row["database_backup_path"],
                context_snapshot_path=row["context_snapshot_path"],
                metadata=metadata,
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc)
            )
            checkpoints.append(checkpoint)

        return checkpoints

    def get_checkpoint_by_id(self, checkpoint_id: int) -> Optional['Checkpoint']:
        """Get a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint object or None if not found
        """
        from codeframe.core.models import Checkpoint, CheckpointMetadata

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id, project_id, name, description, trigger, git_commit,
                database_backup_path, context_snapshot_path, metadata, created_at
            FROM checkpoints
            WHERE id = ?
            """,
            (checkpoint_id,)
        )

        row = cursor.fetchone()
        if not row:
            return None

        # Parse metadata JSON
        metadata_dict = json.loads(row["metadata"]) if row["metadata"] else {}
        metadata = CheckpointMetadata(**metadata_dict)

        return Checkpoint(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"],
            trigger=row["trigger"],
            git_commit=row["git_commit"],
            database_backup_path=row["database_backup_path"],
            context_snapshot_path=row["context_snapshot_path"],
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc)
        )

    # ============================================================================
    # Token Usage and Metrics Methods (Sprint 10 Phase 5)
    # ============================================================================

    def save_token_usage(self, token_usage: 'TokenUsage') -> int:
        """Save a token usage record to the database.

        Args:
            token_usage: TokenUsage model instance

        Returns:
            Database ID of the created record

        Example:
            >>> from codeframe.core.models import TokenUsage, CallType
            >>> usage = TokenUsage(
            ...     task_id=27,
            ...     agent_id="backend-001",
            ...     project_id=1,
            ...     model_name="claude-sonnet-4-5",
            ...     input_tokens=1000,
            ...     output_tokens=500,
            ...     estimated_cost_usd=0.0105,
            ...     call_type=CallType.TASK_EXECUTION
            ... )
            >>> usage_id = db.save_token_usage(usage)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage (
                task_id, agent_id, project_id, model_name,
                input_tokens, output_tokens, estimated_cost_usd,
                actual_cost_usd, call_type, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_usage.task_id,
                token_usage.agent_id,
                token_usage.project_id,
                token_usage.model_name,
                token_usage.input_tokens,
                token_usage.output_tokens,
                token_usage.estimated_cost_usd,
                token_usage.actual_cost_usd,
                token_usage.call_type.value if isinstance(token_usage.call_type, CallType) else token_usage.call_type,
                token_usage.timestamp.isoformat()
            )
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_token_usage(
        self,
        project_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get token usage records with optional filtering.

        Args:
            project_id: Filter by project ID (optional)
            agent_id: Filter by agent ID (optional)
            start_date: Filter by start date (inclusive, optional)
            end_date: Filter by end date (inclusive, optional)

        Returns:
            List of token usage records as dictionaries

        Example:
            >>> # Get all usage for a project
            >>> usage = db.get_token_usage(project_id=1)
            >>>
            >>> # Get usage for an agent in a date range
            >>> from datetime import datetime, timedelta
            >>> start = datetime.now() - timedelta(days=7)
            >>> usage = db.get_token_usage(agent_id="backend-001", start_date=start)
        """
        cursor = self.conn.cursor()

        # Build query with filters
        query = "SELECT * FROM token_usage WHERE 1=1"
        params = []

        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id)

        if start_date is not None:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date is not None:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_project_costs_aggregate(self, project_id: int) -> Dict[str, Any]:
        """Get aggregated cost statistics for a project.

        This is a convenience method that aggregates costs by agent and model
        in a single database query for better performance.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with aggregated costs:
            {
                "total_cost": float,
                "total_tokens": int,
                "by_agent": {...},
                "by_model": {...}
            }

        Example:
            >>> stats = db.get_project_costs_aggregate(project_id=1)
            >>> print(f"Total: ${stats['total_cost']:.2f}")
        """
        cursor = self.conn.cursor()

        # Get overall totals
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(estimated_cost_usd), 0) as total_cost,
                COALESCE(SUM(input_tokens + output_tokens), 0) as total_tokens,
                COUNT(*) as total_calls
            FROM token_usage
            WHERE project_id = ?
            """,
            (project_id,)
        )
        totals = cursor.fetchone()

        # Get breakdown by agent
        cursor.execute(
            """
            SELECT
                agent_id,
                SUM(estimated_cost_usd) as cost,
                SUM(input_tokens + output_tokens) as tokens,
                COUNT(*) as calls
            FROM token_usage
            WHERE project_id = ?
            GROUP BY agent_id
            ORDER BY cost DESC
            """,
            (project_id,)
        )
        by_agent = [dict(row) for row in cursor.fetchall()]

        # Get breakdown by model
        cursor.execute(
            """
            SELECT
                model_name,
                SUM(estimated_cost_usd) as cost,
                SUM(input_tokens + output_tokens) as tokens,
                COUNT(*) as calls
            FROM token_usage
            WHERE project_id = ?
            GROUP BY model_name
            ORDER BY cost DESC
            """,
            (project_id,)
        )
        by_model = [dict(row) for row in cursor.fetchall()]

        return {
            "total_cost": totals["total_cost"],
            "total_tokens": totals["total_tokens"],
            "total_calls": totals["total_calls"],
            "by_agent": by_agent,
            "by_model": by_model
        }
