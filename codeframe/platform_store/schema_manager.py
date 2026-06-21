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

        Creates the minimal control-plane schema (auth, api keys, audit log,
        interactive sessions). v2 domain data lives in per-workspace DBs.
        This method is idempotent - safe to call multiple times.
        """
        cursor = self.conn.cursor()

        # Authentication tables (users, accounts, sessions, verification, api_keys)
        self._create_auth_tables(cursor)

        # Audit log table
        self._create_audit_log_table(cursor)

        # Interactive session tables
        self._create_interactive_session_tables(cursor)

        # Workspace registry table (issue #601)
        self._create_workspaces_registry_table(cursor)

        # Create indexes
        self._create_indexes(cursor)

        self.conn.commit()

        # Ensure default admin user exists
        self._ensure_default_admin_user()

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

    def _create_interactive_session_tables(self, cursor: sqlite3.Cursor) -> None:
        """Create interactive_sessions and session_messages tables."""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS interactive_sessions (
                id          TEXT PRIMARY KEY,
                workspace_path TEXT NOT NULL,
                task_id     TEXT,
                state       TEXT NOT NULL DEFAULT 'active'
                    CHECK (state IN ('active', 'paused', 'ended')),
                agent_type  TEXT NOT NULL DEFAULT 'claude',
                model       TEXT,
                cost_usd    REAL DEFAULT 0.0,
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                ended_at    TEXT,
                -- Owning user; the terminal/chat WebSockets reject a session
                -- whose owner != the authenticated user (issue #655). NULL in
                -- no-auth mode, where ownership is intentionally not enforced.
                user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        # Migrate pre-#655 databases that created the table without user_id.
        existing_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(interactive_sessions)")
        }
        if "user_id" not in existing_cols:
            cursor.execute(
                "ALTER TABLE interactive_sessions ADD COLUMN user_id INTEGER "
                "REFERENCES users(id) ON DELETE SET NULL"
            )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS session_messages (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL REFERENCES interactive_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL
                    CHECK (role IN ('user', 'assistant', 'tool_use', 'tool_result', 'thinking', 'system', 'error')),
                content     TEXT NOT NULL,
                metadata    TEXT,
                created_at  TEXT NOT NULL
            )
            """
        )

    def _create_workspaces_registry_table(self, cursor: sqlite3.Cursor) -> None:
        """Create the workspaces_registry table (issue #601).

        Stores cross-workspace, cross-device project metadata plus a pointer
        (``repo_path``) to each per-workspace ``.codeframe/state.db``. It does
        NOT hold any domain data — per-workspace isolation is unchanged. This is
        deliberately not a revival of the v1 global ``projects`` table.
        """
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces_registry (
                id TEXT PRIMARY KEY,
                repo_path TEXT UNIQUE NOT NULL,
                name TEXT,
                owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                tech_stack TEXT,
                created_at TEXT NOT NULL,
                last_opened_at TEXT NOT NULL
            )
            """
        )

    def _create_audit_log_table(self, cursor: sqlite3.Cursor) -> None:
        """Create the audit log table."""
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
        """Create indexes for the live platform tables."""
        # Interactive session indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactive_sessions_workspace "
            "ON interactive_sessions(workspace_path, state)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_interactive_sessions_state "
            "ON interactive_sessions(state, created_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_messages_session "
            "ON session_messages(session_id, created_at)"
        )

        # Audit log indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id "
            "ON audit_logs(user_id, timestamp DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type "
            "ON audit_logs(event_type, timestamp DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_resource "
            "ON audit_logs(resource_type, resource_id, timestamp DESC)"
        )

        # Authentication indexes (api_keys/accounts indexes are created inline
        # with their tables in _create_auth_tables)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"
        )

        # Workspace registry indexes (issue #601)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_registry_owner "
            "ON workspaces_registry(owner_user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_registry_last_opened "
            "ON workspaces_registry(last_opened_at DESC)"
        )

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
