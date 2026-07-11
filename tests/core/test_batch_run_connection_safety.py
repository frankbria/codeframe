"""Connection leak-on-exception tests for batch/run readers and writers (#762).

Mirrors the tasks.py robustness suite (#650): every DB path in
``conductor.py`` (batch readers) and ``runtime.py`` (run readers/writers) must
release its SQLite connection even when an error is raised between opening the
connection and the normal ``conn.close()`` call — i.e. the path is wrapped in
``try/finally``. Before #762 these hot-path readers closed only on the happy
path, so an ``OperationalError`` (e.g. "database is locked" under parallel
load) leaked the connection.
"""

import pytest

from codeframe.core import conductor, runtime, tasks
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
    """Wraps a real SQLite connection, recording close() and optionally raising
    on a chosen operation to simulate a mid-operation failure.

    ``fail_on`` may be ``"execute"`` (raise inside the SQL call, so the
    function body is reached) or ``"commit"`` (raise after the write executes,
    exercising each write path's ``finally``)."""

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


def _patch_connections(monkeypatch, module, fail_on):
    """Make ``module.get_db_connection`` hand out tracking connections that fail
    on ``fail_on``. Returns the registry of every connection handed out."""
    registry: list[_TrackingConn] = []

    def fake(ws):
        return _TrackingConn(get_db_connection(ws), fail_on, registry)

    monkeypatch.setattr(module, "get_db_connection", fake)
    return registry


class TestConductorReadersReleaseOnException:
    """conductor.py batch readers release the connection on query failure."""

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(lambda ws: conductor.get_batch(ws, "bid"), id="get_batch"),
            pytest.param(lambda ws: conductor.list_batches(ws), id="list_batches"),
            pytest.param(
                lambda ws: conductor.list_batches(ws, status=None, limit=5),
                id="list_batches_no_status",
            ),
        ],
    )
    def test_release_on_execute_error(self, workspace, monkeypatch, operation):
        registry = _patch_connections(monkeypatch, conductor, fail_on="execute")

        with pytest.raises(RuntimeError, match="boom-execute"):
            operation(workspace)

        assert registry, "expected at least one connection to be opened"
        assert all(c.closed for c in registry), "connection leaked on exception"


class TestRuntimeReadersReleaseOnException:
    """runtime.py run readers release the connection on query failure."""

    @pytest.mark.parametrize(
        "operation",
        [
            pytest.param(lambda ws, tid: runtime.get_run(ws, "rid"), id="get_run"),
            pytest.param(
                lambda ws, tid: runtime.get_active_run(ws, tid), id="get_active_run"
            ),
            pytest.param(
                lambda ws, tid: runtime.get_latest_run(ws, tid), id="get_latest_run"
            ),
            pytest.param(lambda ws, tid: runtime.list_runs(ws), id="list_runs"),
            pytest.param(
                lambda ws, tid: runtime.list_runs(ws, task_id=tid, limit=5),
                id="list_runs_filtered",
            ),
        ],
    )
    def test_release_on_execute_error(self, workspace, monkeypatch, operation):
        task = tasks.create(workspace, title="leak-test")
        registry = _patch_connections(monkeypatch, runtime, fail_on="execute")

        with pytest.raises(RuntimeError, match="boom-execute"):
            operation(workspace, task.id)

        assert registry, "expected at least one connection to be opened"
        assert all(c.closed for c in registry), "connection leaked on exception"


class TestRuntimeWritersReleaseOnException:
    """runtime.py run writers release the connection when commit fails."""

    def test_reset_blocked_run_release_on_commit_error(
        self, workspace, monkeypatch
    ):
        task = tasks.create(workspace, title="leak-test")
        registry = _patch_connections(monkeypatch, runtime, fail_on="commit")

        with pytest.raises(RuntimeError, match="boom-commit"):
            runtime.reset_blocked_run(workspace, task.id)

        assert registry, "expected at least one connection to be opened"
        assert all(c.closed for c in registry), "connection leaked on exception"
