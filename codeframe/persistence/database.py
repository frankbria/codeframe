"""Control-plane database management for CodeFRAME.

The global database is a **control-plane store** only: auth (users/accounts/
sessions/verification), API keys, audit logs, interactive sessions, and token
usage. All v2 domain data (tasks/blockers/PRD/...) lives in the per-workspace
``.codeframe/state.db`` via ``codeframe.core.workspace`` — not here.

The class acts as a thin facade, delegating to the surviving control-plane
repositories. Supports both synchronous (sqlite3) and asynchronous (aiosqlite)
operations.
"""

import contextlib
import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional
import logging

import asyncio
import aiosqlite

from codeframe.persistence.schema_manager import SchemaManager
from codeframe.persistence.repositories import (
    TokenRepository,
    AuditRepository,
    APIKeyRepository,
)
from codeframe.persistence.repositories.interactive_sessions import InteractiveSessionRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class Database:
    """SQLite manager for the global control-plane store.

    Repositories:
        - api_keys: API key issuance and lookup
        - audit_logs: Audit logging
        - interactive_sessions: Interactive agent session records
        - token_usage: LLM token usage tracking (also used per-workspace)
    """

    def __init__(self, db_path: Path | str):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file or ":memory:"
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._async_conn: Optional[aiosqlite.Connection] = None
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # Reentrant lock for thread-safe access

        # Control-plane repositories (set after connections are created)
        self.token_usage: Optional[TokenRepository] = None
        self.audit_logs: Optional[AuditRepository] = None
        self.api_keys: Optional[APIKeyRepository] = None
        self.interactive_sessions: Optional[InteractiveSessionRepository] = None

    def initialize(self) -> None:
        """Initialize database schema and repositories."""
        # Create parent directories if needed
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create sync connection
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrent access (allows reads during writes)
        self.conn.execute("PRAGMA journal_mode = WAL")
        # Set busy timeout to handle concurrent access contention
        self.conn.execute("PRAGMA busy_timeout = 5000")

        # Create schema using SchemaManager
        schema_mgr = SchemaManager(self.conn)
        schema_mgr.create_schema()

        # Initialize all repositories with sync connection
        self._initialize_repositories()

    def _initialize_repositories(self) -> None:
        """Initialize all repository instances."""
        # Pass both sync and async connections to support mixed operations.
        # Also pass self (Database instance) for cross-repository operations,
        # and sync_lock for thread-safe access to the shared connection.
        self.token_usage = TokenRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.audit_logs = AuditRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.api_keys = APIKeyRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.interactive_sessions = InteractiveSessionRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)

    # Connection management methods
    def close(self) -> None:
        """Close database connection (sync only)."""
        if self.conn:
            self.conn.close()
            self.conn = None

    async def close_async(self) -> None:
        """Close async database connection."""
        if self._async_conn:
            await self._async_conn.close()
            self._async_conn = None

    async def close_all(self) -> None:
        """Close both sync and async database connections."""
        self.close()
        await self.close_async()

    def __del__(self) -> None:
        """Destructor with warning for unclosed connections."""
        if self._async_conn is not None:
            logger.warning(
                f"Database async connection for {self.db_path} was not explicitly closed. "
                "Use 'async with db:' or call close_async() to properly close async connections."
            )
        if self.conn is not None:
            self.close()

    async def initialize_async(self) -> None:
        """Explicitly initialize the async database connection."""
        async with self._async_lock:
            if self._async_conn is None:
                self._async_conn = await aiosqlite.connect(str(self.db_path))
                self._async_conn.row_factory = aiosqlite.Row
                # Match sync connection pragmas for consistency
                await self._async_conn.execute("PRAGMA foreign_keys = ON")
                await self._async_conn.execute("PRAGMA journal_mode = WAL")
                await self._async_conn.execute("PRAGMA busy_timeout = 5000")
                logger.debug(f"Async connection initialized for {self.db_path}")
                # Update repository async connections
                if self.token_usage:
                    self._update_repository_async_connections()

    def _update_repository_async_connections(self) -> None:
        """Update async connections in all repositories."""
        for repo in [self.token_usage, self.audit_logs, self.api_keys, self.interactive_sessions]:
            if repo:
                repo._async_conn = self._async_conn

    async def _get_async_conn(self) -> aiosqlite.Connection:
        """Get async connection with health check and automatic reconnection."""
        async with self._async_lock:
            if self._async_conn is None:
                self._async_conn = await aiosqlite.connect(str(self.db_path))
                self._async_conn.row_factory = aiosqlite.Row
                # Match sync connection pragmas for consistency
                await self._async_conn.execute("PRAGMA foreign_keys = ON")
                await self._async_conn.execute("PRAGMA journal_mode = WAL")
                await self._async_conn.execute("PRAGMA busy_timeout = 5000")
                logger.debug(f"Async connection created (lazy init) for {self.db_path}")
                self._update_repository_async_connections()
                return self._async_conn

            try:
                await self._async_conn.execute("SELECT 1")
                return self._async_conn
            except Exception as e:
                logger.warning(f"Async connection health check failed: {e}, reconnecting...")
                try:
                    await self._async_conn.close()
                except Exception:
                    pass

                self._async_conn = await aiosqlite.connect(str(self.db_path))
                self._async_conn.row_factory = aiosqlite.Row
                # Match sync connection pragmas for consistency
                await self._async_conn.execute("PRAGMA foreign_keys = ON")
                await self._async_conn.execute("PRAGMA journal_mode = WAL")
                await self._async_conn.execute("PRAGMA busy_timeout = 5000")
                logger.info(f"Async connection reconnected for {self.db_path}")
                self._update_repository_async_connections()
                return self._async_conn

    # Context managers
    def __enter__(self) -> "Database":
        """Context manager entry."""
        if not self.conn:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    async def __aenter__(self) -> "Database":
        """Async context manager entry."""
        if not self.conn:
            self.initialize()
        await self.initialize_async()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_async()

    @contextlib.contextmanager
    def transaction(self):
        """Context manager for explicit transaction control.

        Yields:
            self: The database instance for chaining operations

        Raises:
            RuntimeError: If called while already inside a transaction
        """
        if not self.conn:
            self.initialize()

        # Acquire reentrant lock to ensure thread-safe access to connection state
        with self._sync_lock:
            # Guard against nested transactions
            if self.conn.in_transaction:
                raise RuntimeError(
                    "Cannot start a nested transaction. "
                    "Complete the current transaction first."
                )

            # SQLite uses autocommit by default; disable it for this transaction
            old_isolation = self.conn.isolation_level
            self.conn.isolation_level = None  # Manual transaction mode
            cursor = self.conn.cursor()

            try:
                cursor.execute("BEGIN")
                yield self
                self.conn.commit()
            except Exception:
                # Only rollback if a transaction was actually started
                if self.conn.in_transaction:
                    self.conn.rollback()
                raise
            finally:
                self.conn.isolation_level = old_isolation

    # ----- Token usage (dual-use facade) -----
    # Note: ``token_usage`` is the one repository whose backing table is NOT in
    # ``SchemaManager`` (control-plane). It is also created by the per-workspace
    # schema in ``core/workspace.py``, and ``react_agent``/``stats_commands``
    # instantiate ``Database(workspace.db_path)`` to record token usage via
    # ``MetricsTracker``. Keep the delegations alongside the control-plane ones.
    def save_token_usage(self, *args, **kwargs):
        """Delegate to token_usage.save_token_usage()."""
        return self.token_usage.save_token_usage(*args, **kwargs)

    def get_token_usage(self, *args, **kwargs):
        """Delegate to token_usage.get_token_usage()."""
        return self.token_usage.get_token_usage(*args, **kwargs)

    def get_task_token_summary(self, *args, **kwargs):
        """Delegate to token_usage.get_task_token_summary()."""
        return self.token_usage.get_task_token_summary(*args, **kwargs)

    def get_batch_token_usage(self, *args, **kwargs):
        """Delegate to token_usage.get_batch_token_usage()."""
        return self.token_usage.get_batch_token_usage(*args, **kwargs)

    def get_workspace_token_usage(self, *args, **kwargs):
        """Delegate to token_usage.get_workspace_token_usage()."""
        return self.token_usage.get_workspace_token_usage(*args, **kwargs)

    # ----- Audit log -----
    def create_audit_log(self, *args, **kwargs):
        """Delegate to audit_logs.create_audit_log()."""
        return self.audit_logs.create_audit_log(*args, **kwargs)
