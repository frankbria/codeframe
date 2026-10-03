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

import atexit
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
#: How long a delegated CLI gets between SIGTERM and SIGKILL.
CHILD_GRACE_S = 5.0
#: A batch worker gets more: on SIGTERM it first tears down its own CLI, which
#: can take a full CHILD_GRACE_S of TERM plus the KILL. A shorter outer grace
#: would SIGKILL the worker mid-teardown and orphan a slow CLI (review).
WORKER_GRACE_S = 2 * CHILD_GRACE_S + 2

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
        self._prev_handlers: Optional[dict] = None

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
        # Only an explicit non-RUNNING status is a Stop; a missing row is not.
        self._cancelled = row is not None and row[0] != "RUNNING"
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
        if self._prev_handlers is not None:
            for sig, handler in self._prev_handlers.items():
                signal.signal(sig, handler)
            self._prev_handlers = None


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
    control._prev_handlers = exit_on_sigterm()
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


def mark_stopped(workspace: "Workspace", run_id: str) -> None:
    """Record that the user stopped ``run_id``. A FAILED run row alone cannot
    say whether it failed or was stopped, and the batch retry needs to know."""
    # ponytail: one empty file per stopped run, never pruned; a ledger column if it ever matters.
    path = Path(workspace.state_dir) / _HEARTBEAT_DIR / "stopped" / run_id
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    except OSError:
        logger.warning("Could not record that run %s was stopped", run_id, exc_info=True)


def was_stopped(workspace: "Workspace", run_id: str) -> bool:
    return (Path(workspace.state_dir) / _HEARTBEAT_DIR / "stopped" / run_id).exists()


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


#: macOS (and some other POSIX systems) has no os.waitid, so ownership of a
#: pid cannot be proven there; only the direct child is ever signalled.
_HAS_WAITID = hasattr(os, "waitid")


def _owned_unreaped(pid: int) -> bool:
    """Is ``pid`` our own child, running or an unreaped zombie?

    WNOWAIT leaves a zombie in place, so the answer stays true until we reap
    it. While a pid is unreaped, the kernel cannot hand it, or a process
    group with that id, to anyone else.
    """
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return False  # not our child, or already reaped (its pid may be reused)
    return True


def _verified_group(proc: object) -> Optional[int]:
    """The process group we may signal for ``proc``, or None.

    All of these must hold:
    * ``pid`` is a real int above 1. ``killpg(1)`` is ``kill(-1)``, which
      signals every process the user owns; ``killpg(0)`` is our own group. A
      MagicMock's pid coerces to 1, which is how the #1279 tests once killed
      every session on the machine.
    * It is our child and unreaped, so the pid cannot have been recycled.
    * It leads its own group, which means it was started with
      `new_session_kwargs()`.
    * That group is not ours.

    The group is verified when this is called, not remembered from spawn.
    `terminate_tree` keeps the leader unreaped until it has finished
    signalling, so the verified id cannot be recycled in between. A leader
    that was already reaped (by `poll()` or `wait()`) cannot be verified, so
    its group is **not** signalled. Any survivors of that group go unkilled.
    That is the price of never guessing. In practice a delegated CLI is its
    own group, and its adapter kills that group on the way out.
    """
    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        logger.warning("Refusing to signal process group for pid %r: not a real child pid", pid)
        return None
    if not _owned_unreaped(pid):
        logger.warning("Refusing to signal process group %d: not an unreaped child", pid)
        return None
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        logger.warning("Refusing to signal process group %d: process is gone", pid)
        return None
    if pgid != pid:
        logger.warning("Refusing to signal process group of %d: it leads no group of its own", pid)
        return None
    if pgid == os.getpgrp():
        logger.warning("Refusing to signal process group %d: it is our own group", pid)
        return None
    return pgid


def _leader_exited(pid: int) -> bool:
    """Has the leader exited? It is left unreaped either way."""
    try:
        return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
    except ChildProcessError:
        return True  # reaped elsewhere; the caller re-verifies before SIGKILL


def terminate_tree(proc: subprocess.Popen, grace_s: float = CHILD_GRACE_S) -> None:
    """Stop ``proc`` and everything in its process group.

    The child must have been started with `new_session_kwargs()`. Only a group
    that `_verified_group` proves is ours is ever signalled: SIGTERM, a
    grace period, then SIGKILL. The leader is reaped only after that, so a
    child that ignores SIGTERM after its leader obeyed is still killed. If the
    group cannot be proven, only the direct child is signalled, by pid, and
    only when it is ours and unreaped. Anything else is refused and logged.
    """
    if os.name != "posix" or not _HAS_WAITID:
        # No way to prove a group is ours (Windows has none; macOS lacks
        # waitid): stop the direct child through Popen, which reaps safely.
        _terminate_popen(proc, grace_s)
        return

    pgid = _verified_group(proc)
    if pgid is None:
        _terminate_direct_child(proc, grace_s)
        return

    _killpg(pgid, signal.SIGTERM)
    deadline = time.monotonic() + grace_s
    while time.monotonic() < deadline and not _leader_exited(pgid):
        time.sleep(0.05)
    # Re-verify immediately before escalating. If another thread reaped the
    # leader meanwhile, the id is no longer provably ours.
    if _verified_group(proc) == pgid:
        _killpg(pgid, signal.SIGKILL)
    try:
        proc.wait(timeout=grace_s)  # reap the leader, now we are done
    except subprocess.TimeoutExpired:
        logger.warning("Process %d did not exit after SIGKILL", pgid)


def _killpg(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass  # every member already gone


#: Captured at import: tests patch ``subprocess.Popen`` with a mock, which
#: would make an isinstance check against the live attribute raise TypeError.
_POPEN = subprocess.Popen


def _terminate_popen(proc: object, grace_s: float) -> None:
    """terminate/kill through Popen alone. It polls before signalling, so it
    never signals a pid it has already reaped."""
    if not isinstance(proc, _POPEN) or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            logger.warning("Process %d did not exit after kill", proc.pid)


def _terminate_direct_child(proc: object, grace_s: float) -> None:
    """Signal ``proc`` alone, by pid. Only a real, unreaped child of ours."""
    if not isinstance(proc, _POPEN):
        return  # a mock or stand-in: nothing real to stop
    pid = proc.pid
    if not isinstance(pid, int) or pid <= 1 or not _owned_unreaped(pid):
        return
    proc.terminate()
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        if _owned_unreaped(pid):
            proc.kill()
        try:
            proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            logger.warning("Process %d did not exit after SIGKILL", pid)


def exit_on_sigterm() -> Optional[dict]:
    """Turn SIGTERM and SIGHUP into SystemExit, so `finally`/`except
    BaseException` blocks run and a delegated CLI's session is torn down with
    its worker. SIGHUP matters because a child in its own session no longer
    hears the terminal close; the worker has to pass that on.

    Only valid on the main thread; elsewhere (the server's worker threads) it
    is a no-op. Returns the previous handlers, or None when nothing changed.
    """
    if os.name != "posix" or threading.current_thread() is not threading.main_thread():
        return None

    def _raise(signum, frame):  # noqa: ARG001
        raise SystemExit(128 + signum)

    return {sig: signal.signal(sig, _raise) for sig in (signal.SIGTERM, signal.SIGHUP)}


def terminate_trees(procs: list[subprocess.Popen], grace_s: float = CHILD_GRACE_S) -> None:
    """`terminate_tree` for several processes at once, so the last one is not
    left running while the first ones wait out their grace (review)."""
    threads = [
        threading.Thread(target=terminate_tree, args=(p, grace_s), daemon=True) for p in procs
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


# -- children that must not outlive this process ------------------------------
#
# A child in its own session does not receive the terminal's Ctrl+C or SIGHUP,
# so an exiting CLI or server would leave it running. Spawners register their
# children here; whatever is still registered at interpreter exit is stopped.

_live_children: set = set()
_live_lock = threading.Lock()


def register_child(proc: subprocess.Popen) -> None:
    with _live_lock:
        _live_children.add(proc)


def release_child(proc: subprocess.Popen) -> None:
    with _live_lock:
        _live_children.discard(proc)


@atexit.register
def _stop_live_children() -> None:
    with _live_lock:
        procs = list(_live_children)
        _live_children.clear()
    if procs:
        terminate_trees(procs, grace_s=2.0)
