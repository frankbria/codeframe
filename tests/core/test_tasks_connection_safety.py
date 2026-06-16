"""Robustness tests for codeframe.core.tasks (issue #650).

Covers two low-severity robustness fixes:

1. Connection leak-on-exception: every DB path in ``tasks.py`` must release its
   SQLite connection even when an error is raised between opening it and the
   normal ``conn.close()`` call (i.e. the path is wrapped in ``try/finally``).
2. Fire-and-forget retention: the GitHub auto-close task scheduled by
   ``_close_issue_background`` in an async context must be retained by a strong
   reference until it completes (asyncio only keeps a weak reference, so an
   un-retained task can be garbage-collected mid-flight).
"""

import asyncio

import pytest

from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


class _TrackingCursor:
    """Wraps a real cursor, optionally raising on execute()."""

    def __init__(self, real, fail_on):
        self._real = real
        self._fail_on = fail_on

    def execute(self, *args, **kwargs):
        if self._fail_on == "execute":
            raise RuntimeError("boom-execute")
        return self._real.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _TrackingConn:
    """Wraps a real SQLite connection, recording close() and optionally
    raising on a chosen operation to simulate a mid-operation failure.

    ``fail_on`` may be ``"execute"`` (raise inside the SQL call, so the
    function's body — including branch selection — is reached) or ``"commit"``
    (raise after the write executes, exercising the write path's ``finally``)."""

    def __init__(self, real, fail_on, registry):
        self._real = real
        self._fail_on = fail_on
        self.closed = False
        registry.append(self)

    def cursor(self):
        return _TrackingCursor(self._real.cursor(), self._fail_on)

    def commit(self):
        if self._fail_on == "commit":
            raise RuntimeError("boom-commit")
        return self._real.commit()

    def close(self):
        self.closed = True
        self._real.close()

    def __getattr__(self, name):
        return getattr(self._real, name)


def _patch_connections(monkeypatch, fail_on):
    """Make tasks.get_db_connection hand out tracking connections that fail
    on ``fail_on``. Returns the registry of every connection handed out."""
    registry: list[_TrackingConn] = []

    def fake(ws):
        return _TrackingConn(get_db_connection(ws), fail_on, registry)

    monkeypatch.setattr(tasks, "get_db_connection", fake)
    return registry


class TestConnectionReleasedOnException:
    """All tasks.py DB paths release the connection on exception (#650)."""

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(lambda ws, tid: tasks.get(ws, tid), id="get"),
            pytest.param(lambda ws, tid: tasks.list_tasks(ws), id="list_tasks"),
            pytest.param(
                lambda ws, tid: tasks.list_tasks(ws, status=TaskStatus.READY),
                id="list_tasks_status_filter",
            ),
            pytest.param(
                lambda ws, tid: tasks.count_by_status(ws), id="count_by_status"
            ),
            pytest.param(lambda ws, tid: tasks.delete(ws, tid), id="delete"),
            pytest.param(lambda ws, tid: tasks.delete_all(ws), id="delete_all"),
        ],
    )
    def test_paths_release_on_execute_error(
        self, workspace, monkeypatch, operation
    ):
        # Failing inside execute() reaches the function body (and, for
        # list_tasks, both SQL branches), so the leak guard is exercised in
        # situ rather than at connection setup.
        task = tasks.create(workspace, title="leak-test")
        registry = _patch_connections(monkeypatch, fail_on="execute")

        with pytest.raises(RuntimeError, match="boom-execute"):
            operation(workspace, task.id)

        assert registry, "expected at least one connection to be opened"
        assert all(c.closed for c in registry), "connection leaked on exception"

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(
                lambda ws, tid: tasks.update_depends_on(ws, tid, []),
                id="update_depends_on",
            ),
            pytest.param(
                lambda ws, tid: tasks.update_requirement_ids(ws, tid, []),
                id="update_requirement_ids",
            ),
            pytest.param(lambda ws, tid: tasks.delete(ws, tid), id="delete"),
            pytest.param(lambda ws, tid: tasks.delete_all(ws), id="delete_all"),
        ],
    )
    def test_write_paths_release_on_commit_error(
        self, workspace, monkeypatch, operation
    ):
        # Every write path commits; failing on commit (after the SQL executes)
        # exercises each write path's finally specifically. update_* also call
        # get() first (read, no commit) — that connection must close too.
        task = tasks.create(workspace, title="leak-test")
        registry = _patch_connections(monkeypatch, fail_on="commit")

        with pytest.raises(RuntimeError, match="boom-commit"):
            operation(workspace, task.id)

        assert registry, "expected at least one connection to be opened"
        assert all(c.closed for c in registry), "connection leaked on exception"


class TestFireAndForgetRetention:
    """The auto-close async task is retained until completion (#650)."""

    @pytest.mark.asyncio
    async def test_async_close_task_is_retained_then_discarded(self, monkeypatch):
        gate = asyncio.Event()
        ran = asyncio.Event()

        async def fake_close(pat, repo, issue_number):
            ran.set()
            await gate.wait()

        monkeypatch.setattr(tasks, "_safe_close_issue", fake_close)
        # Snapshot + restore so this test never leaves the module set dirty for
        # subsequent tests, even if an assertion fails before the task drains.
        saved = set(tasks._background_tasks)
        tasks._background_tasks.clear()
        try:
            tasks._close_issue_background("pat", "owner/repo", 7)

            # Retained synchronously so asyncio cannot GC it mid-flight.
            assert len(tasks._background_tasks) == 1
            task = next(iter(tasks._background_tasks))

            await ran.wait()
            gate.set()
            await task
            await asyncio.sleep(0)  # let the done-callback (call_soon) run

            # Discarded after completion so the set does not grow unbounded.
            assert task not in tasks._background_tasks
        finally:
            tasks._background_tasks.clear()
            tasks._background_tasks.update(saved)
