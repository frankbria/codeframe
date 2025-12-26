"""Database schema management for CodeFRAME.

Handles schema creation, migrations, and database initialization.
Extracted from the monolithic Database class for better maintainability.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


class SchemaManager:
    """Manages database schema creation and migrations.

    Responsible for creating all database tables, indexes, and ensuring
    schema consistency across the application.
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize schema manager with database connection.

        Args:
            conn: Active sqlite3.Connection
        """
        self.conn = conn

    def create_schema(self) -> None:
        """Create all database tables and indexes.

        Creates the complete v1.0 flattened schema with all migrations applied.
        This method is idempotent - safe to call multiple times.
        """
        cursor = self.conn.cursor()

        # Authentication tables
        self._create_auth_tables(cursor)

        # Core project tables
        self._create_project_tables(cursor)

        # Issue and task tables
        self._create_issue_task_tables(cursor)

        # Agent management tables
        self._create_agent_tables(cursor)

        # Blocker management tables
        self._create_blocker_tables(cursor)

        # Quality and testing tables
        self._create_quality_tables(cursor)

        # Memory and context tables
        self._create_memory_context_tables(cursor)

        # Checkpoint and git tracking tables
        self._create_checkpoint_git_tables(cursor)

        # Metrics and audit tables
        self._create_metrics_audit_tables(cursor)

        # Create all indexes
        self._create_indexes(cursor)

        self.conn.commit()

        # Ensure default admin user exists
        self._ensure_default_admin_user()

    def _create_auth_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create authentication and authorization tables."""
        # Users table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Sessions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

    def _create_project_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create project and project_users tables."""
        # Projects table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')) DEFAULT 'empty',
                source_location TEXT,
                source_branch TEXT DEFAULT 'main',
                workspace_path TEXT NOT NULL,
                git_initialized BOOLEAN DEFAULT FALSE,
                current_commit TEXT,
                status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
                phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paused_at TIMESTAMP NULL,
                config JSON
            )
        """
        )

        # Project users table (authorization)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS project_users (
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('owner', 'collaborator', 'viewer')),
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_id, user_id)
            )
        """
        )

    def _create_issue_task_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create issues and tasks tables."""
        # Issues table
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
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(project_id, issue_number)
            )
        """
        )

        # Tasks table
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
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                quality_gate_status TEXT CHECK(quality_gate_status IN ('pending', 'running', 'passed', 'failed')) DEFAULT 'pending',
                quality_gate_failures JSON,
                requires_human_approval BOOLEAN DEFAULT FALSE
            )
        """
        )

        # Task dependencies junction table
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

    def _create_agent_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create agent and project_agents tables."""
        # Agents table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
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

    def _create_blocker_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create blockers table."""
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

    def _create_quality_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create quality, testing, and code review tables."""
        # Lint results table
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

        # Test results table
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

        # Correction attempts table
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

        # Code reviews table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS code_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                line_number INTEGER,
                severity TEXT NOT NULL CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
                category TEXT NOT NULL CHECK(category IN ('security', 'performance', 'quality', 'maintainability', 'style')),
                message TEXT NOT NULL,
                recommendation TEXT,
                code_snippet TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

    def _create_memory_context_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create memory and context management tables."""
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

    def _create_checkpoint_git_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create checkpoint, git tracking, and deployment tables."""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                name TEXT,
                description TEXT,
                database_backup_path TEXT,
                context_snapshot_path TEXT,
                metadata JSON
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

        # Git branches table
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

        # Deployments table
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

    def _create_metrics_audit_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create metrics, token usage, and audit log tables."""
        # Token usage table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                agent_id TEXT NOT NULL,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                model_name TEXT NOT NULL,
                input_tokens INTEGER NOT NULL CHECK(input_tokens >= 0),
                output_tokens INTEGER NOT NULL CHECK(output_tokens >= 0),
                estimated_cost_usd REAL NOT NULL CHECK(estimated_cost_usd >= 0),
                actual_cost_usd REAL CHECK(actual_cost_usd >= 0),
                call_type TEXT CHECK(call_type IN ('task_execution', 'code_review', 'coordination', 'other')),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT DEFAULT NULL
            )
        """
        )

        # Audit logs table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                resource_type TEXT NOT NULL,
                resource_id INTEGER,
                ip_address TEXT,
                metadata TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

    def _create_indexes(self, cursor: sqlite3.Cursor) -> None:
        """Create all database indexes for performance."""
        # Issues indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_issues_number ON issues(project_id, issue_number)"
        )

        # Tasks indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_issue_number ON tasks(parent_issue_number)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_pending_priority ON tasks(project_id, status, priority, created_at)"
        )
        # Index for agent maturity queries (get_tasks_by_agent)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to, project_id, created_at DESC)"
        )

        # Project-Agent indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_agents_project_active ON project_agents(project_id, is_active) WHERE is_active = TRUE"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_agents_agent_active ON project_agents(agent_id, is_active) WHERE is_active = TRUE"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_agents_assigned_at ON project_agents(assigned_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_agents_unassigned ON project_agents(unassigned_at) WHERE unassigned_at IS NOT NULL"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_agents_unique_active ON project_agents(project_id, agent_id, is_active) WHERE is_active = TRUE"
        )

        # Blocker indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_blockers_status_created ON blockers(status, created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_blockers_agent_status ON blockers(agent_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_blockers_task_id ON blockers(task_id)"
        )

        # Lint results indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_lint_results_task ON lint_results(task_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_lint_results_created ON lint_results(created_at DESC)"
        )

        # Context items indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_context_project_agent ON context_items(project_id, agent_id, current_tier)"
        )

        # Context checkpoints indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_checkpoints_agent_created ON context_checkpoints(agent_id, created_at DESC)"
        )

        # Test results indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_test_results_task ON test_results(task_id)"
        )

        # Correction attempts indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_correction_attempts_task ON correction_attempts(task_id)"
        )

        # Task dependencies indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_dependencies_task ON task_dependencies(task_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_dependencies_depends_on ON task_dependencies(depends_on_task_id)"
        )

        # Code reviews indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_task ON code_reviews(task_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_severity ON code_reviews(severity, created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_project ON code_reviews(project_id, created_at)"
        )

        # Token usage indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_agent ON token_usage(agent_id, timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_project ON token_usage(project_id, timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_task ON token_usage(task_id)"
        )

        # Checkpoints indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project_id, created_at DESC)"
        )

        # Audit logs indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id, timestamp DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type, timestamp DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id, timestamp DESC)"
        )

        # Authentication indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_users_user_id ON project_users(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_users_user_project ON project_users(user_id, project_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)"
        )

    def _ensure_default_admin_user(self) -> None:
        """Ensure default admin user exists in database.

        Creates admin user with id=1 if it doesn't exist. This is used
        when AUTH_REQUIRED=false to provide a default user for development.

        Uses INSERT OR IGNORE to avoid conflicts with test fixtures.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (id, email, password_hash, name)
            VALUES (1, 'admin@localhost', '', 'Admin User')
            """
        )
        if cursor.rowcount > 0:
            logger.info("Created default admin user (id=1, email='admin@localhost')")
        self.conn.commit()
