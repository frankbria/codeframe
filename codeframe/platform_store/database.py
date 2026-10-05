"""Control-plane database management for CodeFRAME.

The global database is a **control-plane store** only: auth (users), API keys,
audit logs, interactive sessions, and token usage. All v2 domain data
(tasks/blockers/PRD/...) lives in the per-workspace
``.codeframe/state.db`` via ``codeframe.core.workspace`` — not here.

The class acts as a thin facade, delegating to the surviving control-plane
repositories. Supports both synchronous (sqlite3) and asynchronous (aiosqlite)
operations.
"""

import contextlib
import os
import sqlite3
import stat
import tempfile
import threading
from pathlib import Path
from typing import Optional
import logging

import asyncio
import aiosqlite

from codeframe.platform_store.schema_manager import DISABLED_PASSWORD, SchemaManager
from codeframe.platform_store.repositories import (
    TokenRepository,
    AuditRepository,
    APIKeyRepository,
    WorkspaceRegistryRepository,
)
from codeframe.platform_store.repositories.interactive_sessions import InteractiveSessionRepository

logger = logging.getLogger(__name__)

_warned_legacy: set[str] = set()


def default_database_path() -> str:
    """The control-plane DB path: ``DATABASE_PATH``, else ``.codeframe/platform.db``.

    It used to default to ``.codeframe/state.db``, the workspace's own DB
    (#1287): serving first left a ``state.db`` that ``cf init`` refused, and
    serving second wrote users and API keys into the repo's domain data. An
    install that already keeps real accounts in ``state.db`` stays there, so
    the operator does not silently lose them on upgrade; it is never moved
    automatically, because a live SQLite file has WAL sidecars.
    """
    env = os.getenv("DATABASE_PATH")
    if env:
        return env
    state_dir = Path.cwd() / ".codeframe"
    platform_db = state_dir / "platform.db"
    legacy = state_dir / "state.db"
    kind = None if platform_db.exists() else _legacy_kind(legacy)
    if kind is None:
        return str(platform_db)
    if str(legacy) not in _warned_legacy:
        _warned_legacy.add(str(legacy))
        if kind == "shared":
            advice = (
                "It also holds this workspace, so do not move it: stop the server "
                "and copy it to %s, or set DATABASE_PATH."
            )
        else:
            advice = (
                "It holds no workspace, so `cf init` cannot use this directory "
                "until it is renamed: stop the server and rename it, with any "
                "-wal/-shm files, to %s."
            )
        logger.warning(
            "Using the legacy control-plane DB %s (#1287). " + advice, legacy, platform_db
        )
    return str(legacy)


class LegacyControlPlaneError(RuntimeError):
    """The legacy control-plane ``state.db`` cannot be moved safely right now."""


def _move_legacy_aside(state_dir: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        part = state_dir / f"state.db{suffix}"
        if part.exists():
            os.replace(part, state_dir / f"state.db{suffix}.pre-1287")


def _refuse_unsafe_move(state_dir: Path, legacy: Path) -> None:
    # An operator who pointed DATABASE_PATH at this file would, after a move,
    # restart onto the workspace DB that replaces it: accounts unreachable.
    # A relative value resolves against the server's cwd, which need not be
    # init's: check the workspace root's spelling too (GLM review).
    env = os.getenv("DATABASE_PATH")
    if env and any(
        base.joinpath(env).resolve() == legacy.resolve()
        for base in (Path.cwd(), state_dir.parent)
    ):
        raise LegacyControlPlaneError(
            f"DATABASE_PATH points at {legacy}, which holds your accounts, not a "
            "workspace. Stop the server, move it (with any -wal/-shm files) out "
            ".codeframe/, set DATABASE_PATH to the new location, then run "
            "`cf init` again."
        )

    # In use? Closing the last connection checkpoints and deletes the -wal and
    # -shm, so if they survive ours, a server still has the file open, and a
    # copy now would miss its later writes (codex review).
    probe = sqlite3.connect(legacy)
    try:
        probe.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    finally:
        probe.close()
    if any((state_dir / f"state.db{s}").exists() for s in ("-wal", "-shm")):
        raise LegacyControlPlaneError(
            f"{legacy} holds this install's accounts and is still open — a server "
            "is probably running from this directory. Stop it, then run `cf init` "
            "again to move the accounts to platform.db."
        )


def migrate_legacy_control_plane(state_dir: Path) -> bool:
    """Move a serve-first control-plane ``state.db`` to ``platform.db`` (#1376).

    Only when ``state.db`` holds login-capable accounts and no workspace
    (``_legacy_kind == "control_plane"``) and there is no ``platform.db`` yet,
    so nothing is ever overwritten. The copy uses SQLite's backup API, which
    is consistent and includes rows still in the ``-wal``; it lands under a
    temp name and is renamed into place, then the original and its sidecars
    move aside to ``*.pre-1287``. Returns True when it moved the file.

    Called from ``cf init`` (``create_or_load_workspace``), before anything
    loads the file as a workspace — one explicit,
    operator-driven moment — never from the resolver, which runs on every
    auth lookup while a server may hold the file open.
    """
    # Serialized across processes, with every check redone under the lock: two
    # concurrent inits could otherwise both pass them and the second would
    # replace the first's platform.db and preserved original (codex review).
    from codeframe.core.atomic_io import fsync_directory, read_modify_write_lock

    # Cheap, read-only and lock-free, so a normal workspace load pays one
    # open and leaves no lock file behind.
    if (
        not (state_dir / ".control-plane-migration.pending").exists()
        and _legacy_kind(state_dir / "state.db") != "control_plane"
    ):
        return False

    with read_modify_write_lock(state_dir / ".control-plane-migration.lock"):
        legacy = state_dir / "state.db"
        platform_db = state_dir / "platform.db"
        # Set before platform.db is published, cleared once the original has
        # moved aside: a run that dies in between is finished by the next one,
        # instead of leaving a platform.db that blocks every retry (codex).
        marker = state_dir / ".control-plane-migration.pending"
        if marker.exists() and platform_db.exists():
            moved = _legacy_kind(legacy) == "control_plane"
            if moved:  # never move a workspace DB aside
                _refuse_unsafe_move(state_dir, legacy)  # same guards as a first run
                _move_legacy_aside(state_dir)
                fsync_directory(state_dir)
            marker.unlink()  # only once nothing is left to finish
            return moved
        if platform_db.exists() or _legacy_kind(legacy) != "control_plane":
            return False

        _refuse_unsafe_move(state_dir, legacy)

        # Unique, created 0600 before any account data goes in, then given the
        # source's exact mode, so a 0600 file never becomes a 0644 copy; removed
        # if the copy fails, so a retry is not blocked by it (codex review).
        fd, tmp_name = tempfile.mkstemp(prefix=".platform.db.", suffix=".tmp", dir=state_dir)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            os.chmod(tmp, stat.S_IMODE(legacy.stat().st_mode))
            src = sqlite3.connect(legacy)
            try:
                dst = sqlite3.connect(tmp)
                try:
                    src.backup(dst)
                    # The source may already carry the *workspace* user_version
                    # (main's failing cf init stamped it) and SchemaManager
                    # would then skip every control-plane migration at or
                    # below it. Its true version is unknowable; the migrations
                    # are idempotent, so let them all replay (GLM review).
                    dst.execute("PRAGMA user_version = 0")
                finally:
                    dst.close()
            finally:
                src.close()
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        # Each step durable before the next, so a power loss cannot keep
        # platform.db while losing the marker that finishes the job (codex).
        marker.touch()
        fsync_directory(state_dir)
        os.replace(tmp, platform_db)
        fsync_directory(state_dir)
        _move_legacy_aside(state_dir)
        fsync_directory(state_dir)
        marker.unlink()
        logger.warning(
            "Moved the legacy control-plane DB %s to %s (#1376); the original is kept "
            "as %s.",
            legacy, platform_db, state_dir / "state.db.pre-1287",
        )
        return True


def _legacy_kind(db_path: Path) -> Optional[str]:
    """``"shared"`` / ``"control_plane"`` when ``db_path`` holds a login-capable
    account, else ``None``. The seeded ``!DISABLED!`` admin alone does not count:
    the old ``cf stats`` (#943) planted it in workspace DBs that never had a
    server."""
    if not db_path.is_file():
        return None
    try:
        # as_uri() percent-encodes: a raw path with '#', '?' or '%' names
        # another file in a SQLite URI (codex review).
        conn = sqlite3.connect(f"{db_path.absolute().as_uri()}?mode=ro", uri=True)
        try:
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "users" not in tables or conn.execute(
                "SELECT 1 FROM users WHERE hashed_password != ? LIMIT 1",
                (DISABLED_PASSWORD,),
            ).fetchone() is None:
                return None
            has_workspace = "workspace" in tables and conn.execute(
                "SELECT 1 FROM workspace LIMIT 1"
            ).fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error as e:
        # Never silently: if accounts are in this file, the server is about to
        # start on an empty platform.db, and with no login-capable user the
        # bootstrap registration route reopens (GLM review).
        logger.error(
            "Could not read %s to check for existing accounts (%s); using "
            "platform.db. If your accounts live there, set DATABASE_PATH to it.",
            db_path,
            e,
        )
        return None
    return "shared" if has_workspace else "control_plane"


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
        self.workspace_registry: Optional[WorkspaceRegistryRepository] = None

    def connect_readonly(self) -> None:
        """Open the DB and wire repositories WITHOUT creating control-plane schema.

        `initialize()` runs SchemaManager, which is correct for the control-plane
        store but wrong for a per-workspace `state.db`: it injected users,
        api_keys and audit_logs tables plus a seeded admin row into the domain
        database as a side effect of `cf stats` (#943). Callers that only read
        an existing workspace DB use this instead.
        """
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self._initialize_repositories()

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
        self.workspace_registry = WorkspaceRegistryRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)

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
        for repo in [self.token_usage, self.audit_logs, self.api_keys, self.interactive_sessions, self.workspace_registry]:
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

    def get_token_usage_iter(self, *args, **kwargs):
        """Delegate to token_usage.get_token_usage_iter()."""
        return self.token_usage.get_token_usage_iter(*args, **kwargs)

    def get_costs_by_model(self, *args, **kwargs):
        """Delegate to token_usage.get_costs_by_model()."""
        return self.token_usage.get_costs_by_model(*args, **kwargs)

    # ----- Audit log -----
    def create_audit_log(self, *args, **kwargs):
        """Delegate to audit_logs.create_audit_log()."""
        return self.audit_logs.create_audit_log(*args, **kwargs)


def open_control_plane_db() -> Database:
    """Resolve and open the control-plane DB, as the server does on start.

    Under the migration's lock when a legacy ``state.db`` is present (#1427):
    the migration checks that no server has the file open and then moves it,
    and a server that opened it between the two kept writing accounts into the
    copy being moved aside. Waiting here, the server either opens the file
    first (and the migration's live-use check refuses) or opens the
    ``platform.db`` the migration published. Only a file the migration could
    move takes the lock: a workspace's own ``state.db`` (every ``cf init``ed
    repo) or a "shared" one is never moved, so a normal start pays nothing
    (review). The same test the migration's own fast path uses.
    """
    state_dir = Path.cwd() / ".codeframe"
    movable = (state_dir / ".control-plane-migration.pending").exists() or (
        _legacy_kind(state_dir / "state.db") == "control_plane"
    )
    if os.getenv("DATABASE_PATH") or not movable:
        lock: contextlib.AbstractContextManager = contextlib.nullcontext()
    else:
        from codeframe.core.atomic_io import read_modify_write_lock

        lock = read_modify_write_lock(state_dir / ".control-plane-migration.lock")
    with lock:
        db = Database(default_database_path())
        db.initialize()
    return db
