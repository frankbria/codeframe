"""Issue #953 — platform_store write serialization, bounded reads, schema versioning.

Covers the five acceptance criteria:
1. Every sync repository write goes through ``BaseRepository._execute``/``_commit``
   under the shared lock; two threads writing concurrently lose no rows.
2. ``save_token_usage`` has a single INSERT path; ``session_id`` is gone from the model.
3. ``get_project_costs_aggregate`` is deleted; whole-table reads bound or stream.
4. A ``PRAGMA user_version`` migration registry applies pending migrations on init.
5. ``AUDIT_VERBOSITY`` is gone.
"""

import ast
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codeframe.core.models import CallType, TokenUsage
from codeframe.platform_store import schema_manager as schema_manager_module
from codeframe.platform_store.database import Database
from codeframe.platform_store.schema_manager import SchemaManager

pytestmark = pytest.mark.v2

REPO_DIR = Path(__file__).resolve().parents[2] / "codeframe" / "platform_store" / "repositories"


def _usage(**overrides) -> TokenUsage:
    defaults = dict(
        task_id="task-1",
        agent_id="agent-1",
        project_id=1,
        model_name="claude-sonnet-4-5",
        input_tokens=10,
        output_tokens=5,
        estimated_cost_usd=0.01,
        call_type=CallType.TASK_EXECUTION,
    )
    defaults.update(overrides)
    return TokenUsage(**defaults)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "platform.db")
    database.initialize()
    # The control-plane schema does not own token_usage (it is per-workspace);
    # create it here so the token repository has a table to write to.
    database.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT, agent_id TEXT, project_id TEXT, model_name TEXT,
            input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0, actual_cost_usd REAL,
            call_type TEXT, timestamp TEXT
        )
        """
    )
    database.conn.commit()
    yield database
    database.close()


# --- AC1: all sync writes serialized behind the shared lock ------------------


def test_no_repository_touches_the_raw_connection():
    """Static guard: no repository may use ``self.conn`` directly.

    Direct ``self.conn.cursor()``/``.commit()`` bypasses the shared lock, so one
    repository's commit can flush another thread's half-written transaction.
    """
    offenders = []
    for path in sorted(REPO_DIR.glob("*.py")):
        if path.name in ("base.py", "__init__.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "conn"
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "self"
            ):
                offenders.append(f"{path.name}:{node.lineno} self.conn.{node.attr}")
    assert offenders == [], "repositories must use BaseRepository._execute/_commit: " + str(offenders)


def test_every_write_path_uses_the_atomic_execute_write_helper():
    """Static guard: a write must not split ``_execute`` and ``_commit``.

    Two lock acquisitions is not one critical section — another thread can slip
    a write in between them, and whichever commit lands first flushes the other
    thread's half-written transaction. Raised by ``codex review`` on this issue.
    """
    offenders = []
    for path in sorted(REPO_DIR.glob("*.py")):
        if path.name in ("base.py", "__init__.py"):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() == "self._commit()":
                offenders.append(f"{path.name}:{lineno}")
    assert offenders == [], (
        "single-statement writes must use _execute_write (one locked "
        f"execute+commit), not _execute followed by _commit: {offenders}"
    )


class _CountingLock:
    """Delegating lock that records how many times it was acquired."""

    def __init__(self, real):
        self._real = real
        self.acquisitions = 0

    def acquire(self, *args, **kwargs):
        self.acquisitions += 1
        return self._real.acquire(*args, **kwargs)

    def release(self):
        return self._real.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


@pytest.mark.parametrize(
    "repo_name, write",
    [
        (
            "audit_logs",
            lambda repo: repo.create_audit_log(
                event_type="auth.login.success",
                user_id=1,
                resource_type="session",
                resource_id=1,
                ip_address=None,
                metadata=None,
                timestamp=datetime.now(timezone.utc),
            ),
        ),
        ("token_usage", lambda repo: repo.save_token_usage(_usage())),
    ],
)
def test_a_write_takes_the_lock_exactly_once(db, repo_name, write):
    """One write == one critical section spanning both the statement and its commit.

    ``_execute`` + ``_commit`` takes the lock **twice**, and the gap between the
    two acquisitions is where another thread's half-written transaction gets
    flushed by this one's commit. Counting acquisitions catches that directly;
    asserting "the lock is held during commit" does not (both shapes hold it).
    """
    repo = getattr(db, repo_name)
    counting = _CountingLock(db._sync_lock)
    repo._sync_lock = counting
    try:
        write(repo)
    finally:
        repo._sync_lock = db._sync_lock

    assert counting.acquisitions == 1, (
        "the shared lock was released between the statement and its commit "
        f"({counting.acquisitions} acquisitions)"
    )


def test_concurrent_audit_and_token_writes_lose_no_rows(db):
    """Two threads hammering different repositories keep every row."""
    errors: list[BaseException] = []
    n = 60

    def write_audit():
        try:
            for i in range(n):
                db.audit_logs.create_audit_log(
                    event_type="auth.login.success",
                    user_id=1,
                    resource_type="session",
                    resource_id=i,
                    ip_address="127.0.0.1",
                    metadata={"i": i},
                    timestamp=datetime.now(timezone.utc),
                )
        except BaseException as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    def write_tokens():
        try:
            for i in range(n):
                db.token_usage.save_token_usage(_usage(task_id=f"task-{i}"))
        except BaseException as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    threads = [threading.Thread(target=write_audit), threading.Thread(target=write_tokens)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert db.conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == n
    assert db.conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == n


# --- AC2: single INSERT path, no phantom session_id -------------------------


def test_save_token_usage_works_without_a_lock(tmp_path):
    """A repository built without a lock uses the same code path."""
    from codeframe.platform_store.repositories import TokenRepository

    conn = sqlite3.connect(tmp_path / "no_lock.db")
    conn.execute(
        "CREATE TABLE token_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,"
        " agent_id TEXT, project_id TEXT, model_name TEXT, input_tokens INTEGER,"
        " output_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL,"
        " call_type TEXT, timestamp TEXT)"
    )
    repo = TokenRepository(sync_conn=conn)  # no sync_lock

    row_id = repo.save_token_usage(_usage())

    assert row_id == 1
    stored = conn.execute("SELECT agent_id, call_type FROM token_usage").fetchone()
    assert stored["agent_id"] == "agent-1"
    assert stored["call_type"] == CallType.TASK_EXECUTION.value
    conn.close()


def test_token_usage_model_has_no_session_id():
    """session_id was accepted and silently dropped — it is gone from the model."""
    assert "session_id" not in TokenUsage.model_fields


# --- AC3: dead aggregate deleted, whole-table reads bounded or streamed ------


def test_get_project_costs_aggregate_is_deleted(db):
    assert not hasattr(db.token_usage, "get_project_costs_aggregate")


def test_workspace_and_filtered_reads_accept_a_limit(db):
    for i in range(5):
        db.token_usage.save_token_usage(_usage(task_id=f"task-{i}"))

    assert len(db.token_usage.get_workspace_token_usage(limit=2)) == 2
    assert len(db.token_usage.get_token_usage(project_id=1, limit=3)) == 3
    assert len(db.token_usage.get_batch_token_usage(["task-0", "task-1", "task-2"], limit=1)) == 1
    # No limit keeps the old, unbounded semantics.
    assert len(db.token_usage.get_workspace_token_usage()) == 5


def test_streaming_iterator_honours_project_and_agent_filters(db):
    db.token_usage.save_token_usage(_usage(agent_id="a", project_id=1))
    db.token_usage.save_token_usage(_usage(agent_id="b", project_id=1))
    db.token_usage.save_token_usage(_usage(agent_id="a", project_id=2))

    by_agent = list(db.token_usage.get_token_usage_iter(agent_id="a"))
    assert len(by_agent) == 2
    assert {r["agent_id"] for r in by_agent} == {"a"}

    by_project = list(db.token_usage.get_token_usage_iter(project_id=2))
    assert len(by_project) == 1
    assert str(by_project[0]["project_id"]) == "2"

    start = datetime.now(timezone.utc) + timedelta(days=1)
    assert list(db.token_usage.get_token_usage_iter(start_date=start)) == []


# --- AC4: schema versioning -------------------------------------------------


def test_fresh_database_is_stamped_at_the_current_schema_version(db):
    version = db.conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SchemaManager.SCHEMA_VERSION
    assert version > 0


def test_pending_migration_is_applied_to_a_preexisting_database(tmp_path, monkeypatch):
    """A column added by a new migration appears on an already-created DB."""
    db_path = tmp_path / "upgrade.db"

    first = Database(db_path)
    first.initialize()
    cols = {r[1] for r in first.conn.execute("PRAGMA table_info(audit_logs)")}
    assert "trace_id" not in cols
    first.close()

    def add_trace_id(cursor: sqlite3.Cursor) -> None:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN trace_id TEXT")

    next_version = SchemaManager.SCHEMA_VERSION + 1
    monkeypatch.setattr(
        schema_manager_module.SchemaManager,
        "MIGRATIONS",
        SchemaManager.MIGRATIONS + [(next_version, add_trace_id)],
    )
    monkeypatch.setattr(schema_manager_module.SchemaManager, "SCHEMA_VERSION", next_version)

    second = Database(db_path)
    second.initialize()
    cols = {r[1] for r in second.conn.execute("PRAGMA table_info(audit_logs)")}
    assert "trace_id" in cols
    assert second.conn.execute("PRAGMA user_version").fetchone()[0] == next_version
    second.close()

    # Re-running is a no-op, not a duplicate ALTER.
    third = Database(db_path)
    third.initialize()
    assert third.conn.execute("PRAGMA user_version").fetchone()[0] == next_version
    third.close()


def test_interactive_sessions_user_id_migration_upgrades_a_legacy_database(tmp_path):
    """The pre-#655 table shape gains user_id through the migration registry."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE interactive_sessions (
            id TEXT PRIMARY KEY, workspace_path TEXT NOT NULL, task_id TEXT,
            state TEXT NOT NULL DEFAULT 'active', agent_type TEXT NOT NULL DEFAULT 'claude',
            model TEXT, cost_usd REAL DEFAULT 0.0, input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, ended_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    db = Database(db_path)
    db.initialize()
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(interactive_sessions)")}
    assert "user_id" in cols
    db.close()


# --- AC5: AUDIT_VERBOSITY removed -------------------------------------------


def test_audit_verbosity_is_gone():
    from codeframe.platform_store import database as database_module

    assert not hasattr(database_module, "AUDIT_VERBOSITY")
