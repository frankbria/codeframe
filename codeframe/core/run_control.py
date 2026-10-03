"""Per-run cancellation and process-tree termination (#1279).

Stopping a run used to change only its database row. Nothing running the
agent ever read that row, and every kill path signalled only the direct child,
so a delegated CLI (and whatever it had spawned) carried on after Stop.

Three pieces, all headless:

* **The signal** is the run's own status. `runtime.stop_run` already writes
  FAILED, so `RunControl.cancelled()` reads that row. It is a database read
  rather than an in-process Event because Stop arrives from anywhere: `cf work
  stop` in another terminal, the web UI, or the conductor for a batch child.
* **Liveness** is a heartbeat file per task, touched by a daemon thread while
  the agent runs and removed when it returns. `start_task_run` refuses a new
  run while the old one's heartbeat is fresh, so two agents never share a
  tree. A worker that dies without cleaning up goes stale and stops blocking.
* **Process trees**: delegated CLIs and batch workers start in their own
  session, and `terminate_tree` signals the whole group (SIGTERM, then
  SIGKILL), not only the direct child.

The current run's control is bound to a ContextVar, so the ReAct loop and the
adapters call `cancellation_requested()` without any signature change. Each
adapter runs on the thread that called `execute_agent`.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Optional

if TYPE_CHECKING:
    from codeframe.core.runtime import Run
    from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

#: How often a live agent touches its heartbeat file.
HEARTBEAT_INTERVAL_S = 5.0
#: A heartbeat older than this belongs to a worker that died without cleanup.
STALE_AFTER_S = 30.0

_HEARTBEAT_DIR = "run_heartbeats"
_current: contextvars.ContextVar[Optional["RunControl"]] = contextvars.ContextVar(
    "codeframe_run_control", default=None
)


def _heartbeat_path(workspace: "Workspace", task_id: str) -> Path:
    return Path(workspace.state_dir) / _HEARTBEAT_DIR / task_id


class RunControl:
    """Cancellation and liveness for one run."""

    def __init__(self, workspace: "Workspace", run: "Run") -> None:
        self.workspace = workspace
        self.run_id = run.id
        self.task_id = run.task_id
        self._cancelled = False
        self._last_check = 0.0
        self._done = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._token: Optional[contextvars.Token] = None
        self._prev_sigterm: object = None

    def cancelled(self, min_interval_s: float = 0.0) -> bool:
        """True once the run has been stopped. Sticky.

        ``min_interval_s`` throttles the database read for callers that poll
        in a tight loop. Any status other than RUNNING means the run is no
        longer this agent's to continue.
        """
        if self._cancelled:
            return True
        now = time.monotonic()
        if min_interval_s and now - self._last_check < min_interval_s:
            return False
        self._last_check = now
        from codeframe.core.workspace import get_db_connection

        try:
            conn = get_db_connection(self.workspace)
            try:
                row = conn.execute(
                    "SELECT status FROM runs WHERE id = ?", (self.run_id,)
                ).fetchone()
            finally:
                conn.close()
        except Exception:
            # An unreadable DB is not a Stop. Keep working, and let the run's
            # own error handling deal with a DB that is really gone.
            logger.warning("Could not read run %s status", self.run_id, exc_info=True)
            return False
        self._cancelled = row is None or row[0] != "RUNNING"
        return self._cancelled

    # -- liveness ----------------------------------------------------------

    def _beat(self) -> None:
        path = _heartbeat_path(self.workspace, self.task_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.run_id)
        except OSError:
            logger.warning("Could not write heartbeat %s", path, exc_info=True)

    def _heartbeat_loop(self) -> None:
        while not self._done.wait(HEARTBEAT_INTERVAL_S):
            self._beat()

    def _stop_heartbeat(self) -> None:
        self._done.set()
        if self._thread is not None:
            self._thread.join(timeout=HEARTBEAT_INTERVAL_S + 1)

    def stop(self) -> None:
        """The agent has returned: stop beating, and release the task."""
        self._stop_heartbeat()
        path = _heartbeat_path(self.workspace, self.task_id)
        try:
            if path.read_text() == self.run_id:  # never remove a successor's
                path.unlink()
        except OSError:
            pass
        if self._token is not None:
            _current.reset(self._token)
            self._token = None
        if self._prev_sigterm is not None:
            signal.signal(signal.SIGTERM, self._prev_sigterm)  # type: ignore[arg-type]
            self._prev_sigterm = None


def start(workspace: "Workspace", run: "Run") -> RunControl:
    """Start beating for ``run`` and bind it as the current run."""
    control = RunControl(workspace, run)
    control._beat()
    control._thread = threading.Thread(
        target=control._heartbeat_loop, name=f"heartbeat-{run.id[:8]}", daemon=True
    )
    control._thread.start()
    control._token = _current.set(control)
    # A batch worker (`cf work start --execute`) is stopped with SIGTERM. Let
    # it unwind, so the adapter's except-block takes its CLI's group down.
    control._prev_sigterm = exit_on_sigterm()
    return control


@contextlib.contextmanager
def supervise(workspace: "Workspace", run: "Run") -> Iterator[RunControl]:
    control = start(workspace, run)
    try:
        yield control
    finally:
        control.stop()


def current() -> Optional[RunControl]:
    return _current.get()


def cancellation_requested(min_interval_s: float = 0.0) -> bool:
    """Has the run executing on this thread been stopped?"""
    control = _current.get()
    return bool(control and control.cancelled(min_interval_s))


def previous_run_alive(workspace: "Workspace", task_id: str) -> bool:
    """Is an agent for ``task_id`` still running, even if its run was stopped?"""
    path = _heartbeat_path(workspace, task_id)
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age < STALE_AFTER_S


# -- process trees -----------------------------------------------------------


def new_session_kwargs() -> dict:
    """Popen kwargs that make the child the leader of its own process group."""
    return {"start_new_session": True} if os.name == "posix" else {}


def terminate_tree(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    """Stop ``proc`` and everything in its process group.

    The child must have been started with `new_session_kwargs()`. The group
    is signalled even when the leader has already exited, because its
    children can outlive it.
    """
    if os.name != "posix":
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=grace_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        return

    def _signal(sig: int) -> None:
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass  # group already gone, or the pid was reused outside our session

    _signal(signal.SIGTERM)
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass
    # Unconditional: a child that ignores SIGTERM survives a leader that obeyed.
    _signal(signal.SIGKILL)
    proc.wait()


def exit_on_sigterm() -> object:
    """Turn SIGTERM into SystemExit, so `finally`/`except BaseException`
    blocks run and a delegated CLI's session is torn down with its worker.

    Only valid on the main thread; elsewhere (the server's worker threads) it
    is a no-op. Returns the previous handler, or None when nothing changed.
    """
    if os.name != "posix" or threading.current_thread() is not threading.main_thread():
        return None

    def _raise(signum, frame):  # noqa: ARG001
        raise SystemExit(128 + signum)

    return signal.signal(signal.SIGTERM, _raise)
