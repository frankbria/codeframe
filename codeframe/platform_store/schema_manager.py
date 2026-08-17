"""Database schema management for CodeFRAME.

Handles schema creation, migrations, and database initialization.
Extracted from the monolithic Database class for better maintainability.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

# Password placeholder for the seeded bootstrap admin (id=1). It cannot match any
# bcrypt hash, so that account can never log in and must never be counted as a
# real user.
#
# THE single definition — ``codeframe.auth`` imports this one (that direction is
# DAG-legal; the reverse is not). It must not be duplicated: the registration
# gate, the bootstrap promotion and the admin backfill all compare against it,
# so two copies drifting apart would silently make a fresh deploy unclaimable
# AND strip an upgraded deploy's only admin, with no error anywhere.
DISABLED_PASSWORD = "!DISABLED!"

# Back-compat alias for readers of this module's private name.
_DISABLED_PASSWORD = DISABLED_PASSWORD


def _migration_001_interactive_sessions_user_id(cursor: sqlite3.Cursor) -> None:
    """Add ``interactive_sessions.user_id`` to databases created before #655."""
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(interactive_sessions)")}
    if not existing:
        # Table absent entirely — PRAGMA table_info returns no rows for an
        # unknown table, and ALTERing it would raise "no such table".
        return
    if "user_id" not in existing:
        cursor.execute(
            "ALTER TABLE interactive_sessions ADD COLUMN user_id INTEGER "
            "REFERENCES users(id) ON DELETE SET NULL"
        )


def _migration_002_drop_dead_auth_tables(cursor: sqlite3.Cursor) -> None:
    """Drop the three BetterAuth tables no query ever touched (#968).

    ``create_schema`` is idempotent CREATE-IF-NOT-EXISTS against a long-lived
    ``state.db``, so deleting the DDL alone would leave these sitting in every
    deployed database forever — including their ``REFERENCES users(id) ON DELETE
    CASCADE`` foreign keys, which are still enforced. SQLite drops a table's
    indexes with the table, so no separate DROP INDEX is needed.
    """
    for table in ("accounts", "sessions", "verification"):
        cursor.execute(f"DROP TABLE IF EXISTS {table}")


class SchemaManager:
    """Manages database schema creation and migrations.

    Responsible for creating all database tables, indexes, and ensuring
    schema consistency across the application.

    Schema versioning (#953)
    ------------------------
    ``CREATE TABLE IF NOT EXISTS`` is a no-op against an existing table, so a
    column added to a DDL block never reached an already-deployed database —
    the upgrade looked clean and then failed on the first query naming the new
    column. Every schema change after the initial create must therefore ship as
    a ``MIGRATIONS`` entry.

    The applied version lives in SQLite's native ``PRAGMA user_version``, so no
    bookkeeping table is needed. ``_apply_migrations`` runs every entry whose
    target version exceeds the stored one, in order, stamping as it goes; a
    fresh database still runs them (they are written to be idempotent) and then
    lands on the same version as an upgraded one.

    To add a migration: append ``(SCHEMA_VERSION + 1, fn)`` to ``MIGRATIONS``
    and bump ``SCHEMA_VERSION`` to match.
    """

    #: Version a fully-migrated database reports via ``PRAGMA user_version``.
    SCHEMA_VERSION = 2

    #: Ordered ``(target_version, callable(cursor))`` pairs. Each callable must
    #: be idempotent — it also runs once against a freshly created database.
    MIGRATIONS = [
        (1, _migration_001_interactive_sessions_user_id),
        (2, _migration_002_drop_dead_auth_tables),
    ]

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

        # Authentication tables (users, api_keys)
        self._create_auth_tables(cursor)

        # Audit log table
        self._create_audit_log_table(cursor)

        # Interactive session tables
        self._create_interactive_session_tables(cursor)

        # Workspace registry table (issue #601)
        self._create_workspaces_registry_table(cursor)

        # Create indexes
        self._create_indexes(cursor)

        # Apply any pending schema migrations (must run after the CREATE TABLE
        # block so a migration can ALTER a table this call just created).
        self._apply_migrations(cursor)

        self.conn.commit()

        # Ensure default admin user exists
        self._ensure_default_admin_user()

        # Backfill admin for instances upgraded across issue #898
        self._ensure_bootstrap_superuser()

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

        # NOTE (#968): `accounts`, `sessions` and `verification` used to be created
        # here for a BetterAuth migration that never happened. No query ever touched
        # them — auth is stateless JWT (users) plus `api_keys` — so they are dropped
        # by migration 002 rather than recreated.

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
        # The pre-#655 shape (no user_id) is upgraded by migration 1, not by an
        # ad-hoc ALTER here — see SchemaManager's class docstring.

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

        # Authentication indexes (the api_keys index is created inline with its
        # table in _create_auth_tables)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")

        # Workspace registry indexes (issue #601)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_registry_owner "
            "ON workspaces_registry(owner_user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_registry_last_opened "
            "ON workspaces_registry(last_opened_at DESC)"
        )

    def _apply_migrations(self, cursor: sqlite3.Cursor) -> None:
        """Run every migration newer than the database's stored version."""
        current = cursor.execute("PRAGMA user_version").fetchone()[0]

        for version, migrate in sorted(self.MIGRATIONS, key=lambda m: m[0]):
            if version <= current:
                continue
            migrate(cursor)
            # PRAGMA does not accept a bound parameter; `version` comes from our
            # own literal table and is asserted to be an int, so no injection.
            if not isinstance(version, int):
                raise TypeError(f"migration version must be an int, got {version!r}")
            cursor.execute(f"PRAGMA user_version = {version}")
            current = version
            logger.info("Applied platform_store schema migration to version %d", version)

        if current < self.SCHEMA_VERSION:
            # A fresh DB with no migration covering the latest version still has
            # to be stamped, or every later start replays from 0.
            cursor.execute(f"PRAGMA user_version = {int(self.SCHEMA_VERSION)}")

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
            VALUES (1, 'admin@localhost', 'Admin User', ?, 1, 1, 1, 1)
            """,
            (_DISABLED_PASSWORD,),
        )
        user_created = cursor.rowcount > 0

        if user_created:
            logger.debug(
                "Created default admin user (id=1) for test fixtures. "
                "This account has a disabled password and cannot be used for login."
            )

        self.conn.commit()

    def _ensure_bootstrap_superuser(self) -> None:
        """Give the operator admin back after issue #898 (upgrade backfill).

        Admin scope now derives from ``users.is_superuser``, and every account
        registered before that change has it set to 0 (fastapi-users forces the
        field False on registration). An in-place upgrade would therefore strip
        admin from the only human on the instance, with no in-product way to
        restore it.

        So: when no *login-capable* superuser exists, promote the earliest
        login-capable account. The seeded id=1 admin holds is_superuser=1 but
        carries a password placeholder that cannot match any bcrypt hash, so it
        never counts on either side of the check. Idempotent — the second run
        finds a superuser and does nothing.

        Note this runs on *every* ``initialize()``, not once, so demoting the
        only login-capable account does not stick. That is deliberate: an
        instance without a reachable admin cannot store credentials or merge
        PRs and has no in-product way back. Demoting a non-earliest account
        still sticks, since an admin then exists.
        """
        # ponytail: earliest-id heuristic, not an ownership record. Fine while
        # registration admits exactly one account (#336/#897); revisit if the
        # product ever grows multi-user signup.
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE users SET is_superuser = 1
            WHERE id = (
                SELECT MIN(id) FROM users WHERE hashed_password != ?
            )
            AND NOT EXISTS (
                SELECT 1 FROM users
                WHERE is_superuser = 1 AND hashed_password != ?
            )
            """,
            (_DISABLED_PASSWORD, _DISABLED_PASSWORD),
        )
        if cursor.rowcount > 0:
            logger.info(
                "Granted admin (is_superuser) to the earliest login-capable "
                "account: this instance had none after the scope change (#898)."
            )
        self.conn.commit()
