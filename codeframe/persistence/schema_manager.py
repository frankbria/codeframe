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

        # Apply schema migrations for existing databases BEFORE creating indexes
        # (indexes may reference columns added by migrations)
        self._apply_migrations(cursor)

        # Create all indexes (after migrations so all columns exist)
        self._create_indexes(cursor)

        self.conn.commit()

        # Ensure default admin user exists
        self._ensure_default_admin_user()

    def _apply_migrations(self, cursor: sqlite3.Cursor) -> None:
        """Apply schema migrations for existing databases.

        Handles adding new columns to existing tables.
        These are idempotent - safe to run multiple times.
        """
        # Migration: Add depends_on column to issues table (cf-207)
        self._add_column_if_not_exists(
            cursor, "issues", "depends_on", "TEXT"
        )

        # Migration: Add missing columns to tasks table for older databases
        # Core columns that may be missing
        self._add_column_if_not_exists(
            cursor, "tasks", "project_id", "INTEGER"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "issue_id", "INTEGER"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "parent_issue_number", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "task_number", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "description", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "status", "TEXT", "'pending'"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "priority", "INTEGER", "0"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "workflow_step", "INTEGER"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "depends_on", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "created_at", "TIMESTAMP", "CURRENT_TIMESTAMP"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "completed_at", "TIMESTAMP"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "assigned_to", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "can_parallelize", "BOOLEAN", "FALSE"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "requires_mcp", "BOOLEAN", "FALSE"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "estimated_tokens", "INTEGER"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "actual_tokens", "INTEGER"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "commit_sha", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "quality_gate_status", "TEXT", "'pending'"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "quality_gate_failures", "JSON"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "requires_human_approval", "BOOLEAN", "FALSE"
        )

        # Migration: Add effort estimation columns to tasks table (Phase 1)
        self._add_column_if_not_exists(
            cursor, "tasks", "estimated_hours", "REAL"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "complexity_score", "INTEGER"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "uncertainty_level", "TEXT"
        )
        self._add_column_if_not_exists(
            cursor, "tasks", "resource_requirements", "TEXT"
        )

        # Migration: Add supervisor intervention context to tasks table
        self._add_column_if_not_exists(
            cursor, "tasks", "intervention_context", "JSON"
        )

    def _add_column_if_not_exists(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        column_name: str,
        column_type: str,
        default_value: str = None,
    ) -> None:
        """Add a column to a table if it doesn't exist.

        Args:
            cursor: SQLite cursor
            table_name: Table to modify
            column_name: Column to add
            column_type: SQLite column type
            default_value: Optional default value for the column

        Raises:
            ValueError: If table_name, column_name, or column_type contain invalid characters
        """
        # SECURITY: Validate identifiers to prevent SQL injection.
        # Only alphanumeric + underscore allowed (standard SQL identifier rules).
        import re
        identifier_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        for name, value in [("table_name", table_name), ("column_name", column_name), ("column_type", column_type)]:
            if not identifier_pattern.match(value):
                raise ValueError(f"Invalid SQL identifier for {name}: {value}")

        # SECURITY: Validate default_value to only allow safe SQL literals.
        # Allowed: NULL, TRUE, FALSE, CURRENT_TIMESTAMP, integers, floats,
        # or single-quoted strings (with no embedded quotes).
        if default_value is not None:
            safe_literal_pattern = re.compile(
                r"^(NULL|TRUE|FALSE|CURRENT_TIMESTAMP|"  # SQL keywords
                r"-?\d+|"  # Integers (including negative)
                r"-?\d+\.\d+|"  # Floats
                r"'[^']*')$",  # Single-quoted strings (no embedded quotes)
                re.IGNORECASE
            )
            if not safe_literal_pattern.match(default_value):
                raise ValueError(
                    f"Invalid SQL literal for default_value: {default_value}. "
                    "Only NULL, TRUE, FALSE, CURRENT_TIMESTAMP, numbers, or "
                    "single-quoted strings (without embedded quotes) are allowed."
                )

        # Check if column exists
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = {row[1] for row in cursor.fetchall()}

        if column_name not in columns:
            # Add the column
            if default_value is not None:
                cursor.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"
                )
            else:
                cursor.execute(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                )
            logger.info(f"Added column {column_name} to {table_name}")

    def _create_auth_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create authentication tables (fastapi-users compatible)."""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                hashed_password TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                is_superuser INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                email_verified INTEGER DEFAULT 0,
                image TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Accounts table (BetterAuth compatible - stores passwords and OAuth)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                password TEXT,
                access_token TEXT,
                refresh_token TEXT,
                id_token TEXT,
                access_token_expires_at TIMESTAMP,
                refresh_token_expires_at TIMESTAMP,
                scope TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider_id)
            )
        """
        )

        # Create index on user_id for faster login lookups
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id)
        """
        )

        # Sessions table (BetterAuth compatible)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                token TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMP NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Verification table (BetterAuth compatible)
        # Used for email verification tokens when requireEmailVerification is enabled
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS verification (
                id TEXT PRIMARY KEY,
                identifier TEXT NOT NULL,
                value TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
        """
        )

        # API Keys table for programmatic access
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                prefix TEXT NOT NULL,
                scopes TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                expires_at TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """
        )

        # Indexes for api_keys table
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(prefix)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)
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
                depends_on TEXT,
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
                requires_human_approval BOOLEAN DEFAULT FALSE,
                -- Effort estimation fields (Phase 1)
                estimated_hours REAL,
                complexity_score INTEGER CHECK(complexity_score BETWEEN 1 AND 5),
                uncertainty_level TEXT CHECK(uncertainty_level IN ('low', 'medium', 'high')),
                resource_requirements TEXT,
                -- Supervisor intervention context (JSON for flexible structure)
                intervention_context JSON
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

        # Task evidence table (for evidence-based quality enforcement)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                agent_id TEXT NOT NULL,
                language TEXT NOT NULL,
                framework TEXT,

                -- Test results
                total_tests INTEGER NOT NULL,
                passed_tests INTEGER NOT NULL,
                failed_tests INTEGER NOT NULL,
                skipped_tests INTEGER NOT NULL,
                pass_rate REAL NOT NULL,
                coverage REAL,
                test_output TEXT NOT NULL,

                -- Skip violations
                skip_violations_count INTEGER NOT NULL DEFAULT 0,
                skip_violations_json TEXT,
                skip_check_passed BOOLEAN NOT NULL,

                -- Quality metrics
                quality_metrics_json TEXT NOT NULL,

                -- Verification status
                verified BOOLEAN NOT NULL,
                verification_errors TEXT,

                -- Metadata
                timestamp TEXT NOT NULL,
                task_description TEXT NOT NULL,

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

        # Add unique constraint on memory table to prevent duplicate keys
        # First, check if the index already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_memory_unique_key'"
        )
        index_exists = cursor.fetchone() is not None

        if not index_exists:
            # Migration: Clean up duplicate entries before creating unique index
            # Keep the most recent entry (highest id) for each (project_id, category, key)
            cursor.execute(
                """
                DELETE FROM memory
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM memory
                    GROUP BY project_id, category, key
                )
            """
            )
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                logger.info(
                    f"Migration: Removed {deleted_count} duplicate memory entries"
                )

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_unique_key
            ON memory(project_id, category, key)
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

        # Pull requests table (Sprint 11 - GitHub PR integration)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pull_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                issue_id INTEGER REFERENCES issues(id) ON DELETE SET NULL,
                branch_name TEXT NOT NULL,
                pr_number INTEGER,
                pr_url TEXT,
                title TEXT NOT NULL,
                body TEXT,
                base_branch TEXT DEFAULT 'main',
                head_branch TEXT NOT NULL,
                status TEXT CHECK(status IN ('draft', 'open', 'merged', 'closed')) DEFAULT 'open',
                merge_commit_sha TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                merged_at TIMESTAMP,
                closed_at TIMESTAMP,
                github_created_at TIMESTAMP,
                github_updated_at TIMESTAMP
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
            "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to, project_id, created_at)"
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blockers_task_id ON blockers(task_id)")

        # Lint results indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lint_results_task ON lint_results(task_id)")
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_results_task ON test_results(task_id)")

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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_task ON code_reviews(task_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_severity ON code_reviews(severity, created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reviews_project ON code_reviews(project_id, created_at)"
        )

        # Task evidence indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_evidence_task ON task_evidence(task_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_evidence_verified ON task_evidence(verified, created_at DESC)"
        )

        # Token usage indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_agent ON token_usage(agent_id, timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_token_usage_project ON token_usage(project_id, timestamp)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_task ON token_usage(task_id)")

        # Checkpoints indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project_id, created_at DESC)"
        )

        # Pull requests indexes (Sprint 11 - GitHub PR integration)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pull_requests_project ON pull_requests(project_id, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pull_requests_issue ON pull_requests(issue_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pull_requests_branch ON pull_requests(project_id, branch_name)"
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_users_user_id ON project_users(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_users_user_project ON project_users(user_id, project_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)")

    def _ensure_default_admin_user(self) -> None:
        """Ensure default admin user exists in database for initial setup.

        Creates admin user with id=1 if it doesn't exist. This provides
        a bootstrap user for test fixtures and initial database setup.

        SECURITY: The admin user has a disabled password placeholder
        that cannot match any bcrypt hash, so it cannot be used for
        direct login. Users must register through the auth system.

        Uses INSERT OR IGNORE to avoid conflicts with test fixtures.
        """
        cursor = self.conn.cursor()

        # Create user record (FastAPI Users compatible)
        # hashed_password uses a placeholder that cannot match any bcrypt hash
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (
                id, email, name, hashed_password,
                is_active, is_superuser, is_verified, email_verified
            )
            VALUES (1, 'admin@localhost', 'Admin User', '!DISABLED!', 1, 1, 1, 1)
            """
        )
        user_created = cursor.rowcount > 0

        if user_created:
            logger.debug(
                "Created default admin user (id=1) for test fixtures. "
                "This account has a disabled password and cannot be used for login."
            )

        self.conn.commit()
