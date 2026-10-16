"""Issue #953 — token repository write serialization and bounded reads.

1. Every sync repository write goes through ``BaseRepository._execute_write``
   under the shared lock; two threads writing concurrently lose no rows.
2. ``save_token_usage`` has a single INSERT path; ``session_id`` is gone from the model.
3. ``get_project_costs_aggregate`` is deleted; whole-table reads bound or stream.

The control-plane parts of #953 (schema versioning, audit verbosity) went with
the server in #1477.
"""

import ast
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codeframe.core.models import CallType, TokenUsage
from codeframe.platform_store.repositories import TokenRepository

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


class _Store:
    """A shared connection and lock, the way concurrent callers share them."""

    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self._sync_lock = threading.Lock()
        self.token_usage = TokenRepository(sync_conn=self.conn, sync_lock=self._sync_lock)


@pytest.fixture
def db(tmp_path):
    database = _Store(tmp_path / "state.db")
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
    database.conn.close()


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
    [("token_usage", lambda repo: repo.save_token_usage(_usage()))],
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


def test_concurrent_token_writes_lose_no_rows(db):
    """Two threads writing through the shared lock keep every row."""
    errors: list[BaseException] = []
    n = 60

    def write_tokens(prefix):
        try:
            for i in range(n):
                db.token_usage.save_token_usage(_usage(task_id=f"{prefix}-{i}"))
        except BaseException as exc:  # pragma: no cover - surfaced via assert
            errors.append(exc)

    threads = [threading.Thread(target=write_tokens, args=(p,)) for p in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert db.conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 2 * n


# --- AC2: single INSERT path, no phantom session_id -------------------------


def test_save_token_usage_works_without_a_lock(tmp_path):
    """A repository built without a lock uses the same code path."""
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


def test_session_id_is_gone_from_the_whole_token_usage_api():
    """The recording API must not offer a field that is never persisted.

    Pydantic ignores unknown kwargs by default, so ``MetricsTracker`` kept
    passing ``session_id=`` into ``TokenUsage`` after the field was removed and
    every test still passed — only mypy caught it. This asserts the parameter
    is gone from the callable surface, not just the model.
    """
    import inspect

    from codeframe.lib.metrics_tracker import MetricsTracker

    for name in ("record_token_usage", "record_token_usage_sync"):
        params = inspect.signature(getattr(MetricsTracker, name)).parameters
        assert "session_id" not in params, f"{name} still accepts a field nothing stores"


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
