"""Database management for CodeFRAME state."""

import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
from codeframe.core.models import ProjectStatus, Task, TaskStatus, AgentMaturity, Issue

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
        cursor.execute("""
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
        """)

        # Issues table (cf-16.2: Hierarchical Issue/Task model)
        cursor.execute("""
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
        """)

        # Create index for issues
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_number
            ON issues(project_id, issue_number)
        """)

        # Tasks table (enhanced for Issue relationship)
        cursor.execute("""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Create index for tasks by parent issue number
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_issue_number
            ON tasks(parent_issue_number)
        """)

        # Agents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        """)

        # Blockers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockers (
                id INTEGER PRIMARY KEY,
                task_id INTEGER REFERENCES tasks(id),
                severity TEXT CHECK(severity IN ('sync', 'async')),
                reason TEXT,
                question TEXT,
                resolution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        """)

        # Memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                category TEXT CHECK(category IN ('pattern', 'decision', 'gotcha', 'preference', 'conversation', 'discovery_state', 'discovery_answers', 'prd')),
                key TEXT,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Context items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context_items (
                id TEXT PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
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
        """)

        # Checkpoints table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                trigger TEXT,
                state_snapshot JSON,
                git_commit TEXT,
                db_backup_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Changelog table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS changelog (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                agent_id TEXT,
                task_id INTEGER,
                action TEXT,
                details JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Git branches table (cf-33: Git Branching & Deployment Workflow)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS git_branches (
                id INTEGER PRIMARY KEY,
                issue_id INTEGER REFERENCES issues(id),
                branch_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                merged_at TIMESTAMP,
                merge_commit TEXT,
                status TEXT CHECK(status IN ('active', 'merged', 'abandoned')) DEFAULT 'active'
            )
        """)

        # Deployments table (cf-33: Deployment tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY,
                commit_hash TEXT NOT NULL,
                environment TEXT CHECK(environment IN ('staging', 'production')),
                status TEXT CHECK(status IN ('success', 'failed')),
                output TEXT,
                duration_seconds REAL,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Test Results table (cf-42: Test Runner Integration)
        cursor.execute("""
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
        """)

        # Create index for test_results by task
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_test_results_task
            ON test_results(task_id)
        """)

        # Correction Attempts table (cf-43: Self-Correction Loop)
        cursor.execute("""
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
        """)

        # Create index for correction_attempts by task
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_correction_attempts_task
            ON correction_attempts(task_id)
        """)

        # Task Dependencies junction table (Sprint 4: Multi-Agent Coordination)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_dependencies (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL,
                depends_on_task_id INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (depends_on_task_id) REFERENCES tasks(id),
                UNIQUE(task_id, depends_on_task_id)
            )
        """)

        # Create index for task_dependencies queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_dependencies_task
            ON task_dependencies(task_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on
            ON task_dependencies(depends_on_task_id)
        """)

        self.conn.commit()

    def _run_migrations(self) -> None:
        """Run database migrations.

        Automatically discovers and runs migration scripts from the migrations directory.
        """
        try:
            from codeframe.persistence.migrations import MigrationRunner
            from codeframe.persistence.migrations.migration_001_remove_agent_type_constraint import migration as migration_001
            from codeframe.persistence.migrations.migration_002_refactor_projects_schema import migration as migration_002

            # Skip migrations for in-memory databases
            if self.db_path == ":memory:":
                logger.debug("Skipping migrations for in-memory database")
                return

            runner = MigrationRunner(str(self.db_path))

            # Register migrations
            runner.register(migration_001)
            runner.register(migration_002)

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
        status: ProjectStatus,
        description: str = "Have not set a description yet. Prompt the user to complete it.",
        workspace_path: str = ""
    ) -> int:
        """Create a new project record."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO projects (name, description, workspace_path, status) VALUES (?, ?, ?, ?)",
            (name, description, workspace_path, status.value)
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
            status = issue.status.value if hasattr(issue.status, 'value') else issue.status
            priority = issue.priority
            workflow_step = issue.workflow_step

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO issues (
                project_id, issue_number, title, description,
                status, priority, workflow_step
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            issue_number,
            title,
            description,
            status,
            priority,
            workflow_step,
        ))
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
        cursor.execute("""
            INSERT INTO tasks (
                project_id, title, description, status, priority, workflow_step, requires_mcp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task.project_id,
            task.title,
            task.description,
            task.status.value,
            task.priority,
            task.workflow_step,
            task.requires_mcp
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_pending_tasks(self, project_id: int) -> List[Task]:
        """Get all pending tasks for a project."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = ?",
            (project_id, TaskStatus.PENDING.value)
        )
        rows = cursor.fetchall()
        # TODO: Convert rows to Task objects
        return []

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
            (project_id,)
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

    def get_tasks_by_parent_issue_number(
        self, parent_issue_number: str
    ) -> List[Dict[str, Any]]:
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
        completion_percentage = (
            (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0
        )

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
            if 'Z' in timestamp_str or '+' in timestamp_str:
                return timestamp_str
            # Parse and add Z suffix for UTC
            try:
                # SQLite format: "2025-10-17 22:01:56"
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + 'Z'
            except:
                return timestamp_str

        # Determine generated_at
        generated_at = generated_row["value"] if generated_row else ensure_rfc3339(prd_row["created_at"])

        # Determine updated_at - use generated_at if updated_at is same as created_at
        updated_at = ensure_rfc3339(prd_row["updated_at"] if prd_row["updated_at"] else prd_row["created_at"])

        # If updated_at == created_at (never been updated), use generated_at for both
        if prd_row["updated_at"] == prd_row["created_at"] and generated_row:
            updated_at = generated_at

        return {
            "prd_content": prd_row["value"],
            "generated_at": generated_at,
            "updated_at": updated_at,
        }

    # Issues/Tasks methods (cf-26)
    def get_issues_with_tasks(
        self, project_id: int, include_tasks: bool = False
    ) -> Dict[str, Any]:
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
            if 'Z' in timestamp_str or '+' in timestamp_str:
                return timestamp_str
            try:
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + 'Z'
            except:
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
                "completed_at": ensure_rfc3339(issue_dict["completed_at"]) if issue_dict.get("completed_at") else None,
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

                    # Parse depends_on if it's a string
                    depends_on = []
                    if task_dict.get("depends_on"):
                        # depends_on might be a comma-separated string or single value
                        depends_on_str = task_dict["depends_on"]
                        if depends_on_str:
                            depends_on = [depends_on_str] if ',' not in depends_on_str else depends_on_str.split(',')

                    formatted_task = {
                        "id": str(task_dict["id"]),
                        "task_number": task_dict["task_number"],
                        "title": task_dict["title"],
                        "description": task_dict["description"] or "",
                        "status": task_dict["status"],
                        "depends_on": depends_on,
                        "proposed_by": "agent",  # Default for now
                        "created_at": ensure_rfc3339(task_dict["created_at"]),
                        "updated_at": ensure_rfc3339(task_dict["created_at"]),  # Use created_at for now
                        "completed_at": ensure_rfc3339(task_dict["completed_at"]) if task_dict.get("completed_at") else None,
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
        test_result_id: Optional[int] = None
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
            (task_id, attempt_number, error_analysis, fix_description, code_changes, test_result_id)
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
            (task_id,)
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
            (task_id,)
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
        cursor.execute(
            "SELECT COUNT(*) FROM correction_attempts WHERE task_id = ?",
            (task_id,)
        )
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
        cursor.execute("""
            INSERT INTO task_dependencies (task_id, depends_on_task_id)
            VALUES (?, ?)
        """, (task_id, depends_on_task_id))
        
        # Update depends_on JSON array in tasks table
        cursor.execute("SELECT depends_on FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        
        if row and row[0]:
            import json
            depends_on = json.loads(row[0]) if row[0] else []
        else:
            depends_on = []
            
        if depends_on_task_id not in depends_on:
            depends_on.append(depends_on_task_id)
            
        cursor.execute("""
            UPDATE tasks SET depends_on = ? WHERE id = ?
        """, (json.dumps(depends_on), task_id))
        
        self.conn.commit()
    
    def get_task_dependencies(self, task_id: int) -> list:
        """Get all tasks that the given task depends on.
        
        Args:
            task_id: The task ID to get dependencies for
            
        Returns:
            List of task IDs that must be completed first
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT depends_on_task_id 
            FROM task_dependencies 
            WHERE task_id = ?
        """, (task_id,))
        
        return [row[0] for row in cursor.fetchall()]
    
    def get_dependent_tasks(self, task_id: int) -> list:
        """Get all tasks that depend on the given task.
        
        Args:
            task_id: The task ID to find dependents for
            
        Returns:
            List of task IDs that depend on this task
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT task_id 
            FROM task_dependencies 
            WHERE depends_on_task_id = ?
        """, (task_id,))
        
        return [row[0] for row in cursor.fetchall()]
    
    def remove_task_dependency(self, task_id: int, depends_on_task_id: int) -> None:
        """Remove a dependency relationship between tasks.
        
        Args:
            task_id: The task that currently depends on another
            depends_on_task_id: The task dependency to remove
        """
        cursor = self.conn.cursor()
        
        # Remove from junction table
        cursor.execute("""
            DELETE FROM task_dependencies 
            WHERE task_id = ? AND depends_on_task_id = ?
        """, (task_id, depends_on_task_id))
        
        # Update depends_on JSON array in tasks table
        cursor.execute("SELECT depends_on FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        
        if row and row[0]:
            import json
            depends_on = json.loads(row[0]) if row[0] else []
            if depends_on_task_id in depends_on:
                depends_on.remove(depends_on_task_id)
                
            cursor.execute("""
                UPDATE tasks SET depends_on = ? WHERE id = ?
            """, (json.dumps(depends_on), task_id))
        
        self.conn.commit()
    
    def clear_all_task_dependencies(self, task_id: int) -> None:
        """Remove all dependencies for a given task.
        
        Args:
            task_id: The task ID to clear dependencies for
        """
        cursor = self.conn.cursor()
        
        # Remove from junction table
        cursor.execute("""
            DELETE FROM task_dependencies WHERE task_id = ?
        """, (task_id,))
        
        # Clear depends_on JSON array
        cursor.execute("""
            UPDATE tasks SET depends_on = '[]' WHERE id = ?
        """, (task_id,))
        
        self.conn.commit()

    def get_blockers(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Get all unresolved blockers for a project.

        Args:
            project_id: Project ID to filter blockers

        Returns:
            List of blocker dictionaries with task info
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                b.id,
                b.task_id,
                b.severity,
                b.question,
                b.reason,
                b.created_at
            FROM blockers b
            JOIN tasks t ON b.task_id = t.id
            WHERE t.project_id = ?
                AND b.resolved_at IS NULL
            ORDER BY b.created_at DESC
        """, (project_id,))

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

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
        cursor.execute("""
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
        """, (project_id, limit))

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        # Format for frontend
        activity_items = []
        for row in rows:
            activity_dict = dict(zip(columns, row))
            
            # Map database fields to frontend expected format
            activity_items.append({
                "timestamp": activity_dict["timestamp"],
                "type": activity_dict["action"],
                "agent": activity_dict["agent_id"] or "system",
                "message": activity_dict.get("details") or activity_dict["action"],
            })

        return activity_items
