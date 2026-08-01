"""Resuming a blocked task must actually run it (#1005 / P0.26).

``POST /tasks/{id}/resume`` called ``runtime.resume_run()`` and returned. That
flips the run to RUNNING and the task to IN_PROGRESS — and nothing executes it.
``start`` spawns a background thread for exactly this; resume had no equivalent.

The task is then *wedged*: it holds an active run, so ``start_task_run`` rejects
any attempt to start it again, and there is no other way to drive it. Every
BLOCKED task resumed from the web UI hits this.

Asserted on outcome — did a worker actually run the resumed run — not on the
endpoint returning 200, which it always did.
"""

import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import blockers, runtime, tasks
from codeframe.core.runtime import RunStatus
from codeframe.core.state_machine import TaskStatus

pytestmark = pytest.mark.v2


def _wait_until(predicate, timeout=5.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def blocked(monkeypatch):
    """A workspace whose one task holds a BLOCKED run, ready to resume."""
    from codeframe.core.workspace import create_or_load_workspace

    tmp = Path(tempfile.mkdtemp())
    ws_dir = tmp / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws = create_or_load_workspace(ws_dir)
    task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

    run = runtime.start_task_run(ws, task.id)
    blocker = blockers.create(ws, task_id=task.id, question="why?")
    runtime.block_run(ws, run.id, blocker.id)

    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import tasks_v2

    app = FastAPI()
    app.include_router(tasks_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: ws
    yield TestClient(app), ws, task.id, run.id
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def recorder(monkeypatch):
    """Record every execute_agent call and let the test wait for one."""
    calls: list[dict] = []
    seen = threading.Event()

    def _record(workspace, run, **kwargs):
        calls.append({"run": run, "kwargs": kwargs})
        seen.set()

        class _State:
            status = None

        return _State()

    monkeypatch.setattr(runtime, "execute_agent", _record)
    return calls, seen


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------


def test_resume_actually_runs_the_agent(blocked, recorder):
    client, ws, task_id, run_id = blocked
    calls, seen = recorder

    r = client.post(f"/api/v2/tasks/{task_id}/resume")
    assert r.status_code == 200

    assert seen.wait(5.0), (
        "resume returned 200 but no worker ever ran — the task now holds an "
        "active run that nothing is executing"
    )
    assert len(calls) == 1


def test_the_worker_gets_the_resumed_run(blocked, recorder):
    """Not a fresh run — the one resume_run returned, or the blocked run leaks."""
    client, ws, task_id, run_id = blocked
    calls, seen = recorder

    client.post(f"/api/v2/tasks/{task_id}/resume")
    assert seen.wait(5.0)

    assert calls[0]["run"].id == run_id


def test_resume_does_not_wedge_the_task(blocked, monkeypatch):
    """The user-visible symptom: after resume, nothing can drive the task.

    With no worker the run stays RUNNING forever, so `start` 400s on
    "already has an active run" and there is no way out but editing the DB.
    """
    client, ws, task_id, run_id = blocked

    def _boom(*a, **k):
        raise ValueError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(runtime, "execute_agent", _boom)

    client.post(f"/api/v2/tasks/{task_id}/resume")

    # A worker that fails up front must fail the run (#722), leaving the task
    # retryable rather than permanently RUNNING.
    assert _wait_until(lambda: tasks.get(ws, task_id).status == TaskStatus.FAILED), (
        f"task stayed {tasks.get(ws, task_id).status} — wedged with an active run"
    )
    assert client.post(f"/api/v2/tasks/{task_id}/start").status_code == 200


def test_execute_false_keeps_the_flip_only_behaviour(blocked, recorder):
    """The old behaviour stays reachable for a caller that wants it."""
    client, ws, task_id, run_id = blocked
    calls, seen = recorder

    r = client.post(f"/api/v2/tasks/{task_id}/resume", params={"execute": "false"})

    assert r.status_code == 200
    assert not seen.wait(0.5)
    assert calls == []


def test_the_default_executes_because_the_web_ui_sends_no_params(blocked, recorder):
    """`tasksApi.resumeExecution` posts with no query params (api.ts), so any
    other default leaves the bug in place for the only real caller."""
    client, ws, task_id, run_id = blocked
    calls, seen = recorder

    client.post(f"/api/v2/tasks/{task_id}/resume")

    assert seen.wait(5.0)


def test_start_still_works_through_the_shared_helper(monkeypatch, blocked, recorder):
    """start and resume now share one worker body — start must not regress."""
    client, ws, task_id, run_id = blocked
    calls, seen = recorder

    # Clear the blocked run so start is allowed — the purpose-built helper.
    runtime.reset_blocked_run(ws, task_id)

    r = client.post(f"/api/v2/tasks/{task_id}/start", params={"execute": "true"})

    assert r.status_code == 200
    assert seen.wait(5.0)


# ---------------------------------------------------------------------------
# The CLI has the same gap, and no escape hatch at all
# ---------------------------------------------------------------------------


def test_cli_resume_executes(blocked, recorder, monkeypatch):
    """`cf work resume` flipped state and returned too — and unlike the web UI
    there was no follow-up command, since `start` rejects the active run."""
    from typer.testing import CliRunner

    _, ws, task_id, _ = blocked
    calls, seen = recorder

    from codeframe.cli.app import app
    from codeframe.core import workspace as ws_module

    monkeypatch.setattr(ws_module, "get_workspace", lambda p: ws)

    result = CliRunner().invoke(app, ["work", "resume", task_id[:8]])

    assert result.exit_code == 0, result.output
    assert calls, "cf work resume did not execute the resumed run"


def test_cli_resume_no_execute_opts_out(blocked, recorder, monkeypatch):
    from typer.testing import CliRunner

    _, ws, task_id, _ = blocked
    calls, seen = recorder

    from codeframe.cli.app import app
    from codeframe.core import workspace as ws_module

    monkeypatch.setattr(ws_module, "get_workspace", lambda p: ws)

    result = CliRunner().invoke(app, ["work", "resume", task_id[:8], "--no-execute"])

    assert result.exit_code == 0, result.output
    assert calls == []


def test_cli_resume_does_not_wedge_when_the_agent_raises(blocked, monkeypatch):
    """Review finding (bot, [major]): the CLI path re-introduced the very wedge
    this change fixes.

    `resume_run` has already flipped the run to RUNNING and the task to
    IN_PROGRESS. `execute_agent` then raises up front for a missing key — before
    its own try — and the CLI's outer `except ValueError` printed and exited
    without failing the run. `work start` then rejects the task on "already has
    an active run", with `work stop` the only way out.

    The web worker recovers from exactly this via fail_run (#722); the CLI had
    no equivalent, and the recorder in the tests above returns a fake state
    rather than raising, so nothing covered it.
    """
    from typer.testing import CliRunner

    _, ws, task_id, run_id = blocked

    def _boom(*a, **k):
        raise ValueError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(runtime, "execute_agent", _boom)

    from codeframe.cli.app import app
    from codeframe.core import workspace as ws_module

    monkeypatch.setattr(ws_module, "get_workspace", lambda p: ws)

    result = CliRunner().invoke(app, ["work", "resume", task_id[:8]])

    assert result.exit_code == 1
    assert runtime.get_run(ws, run_id).status != RunStatus.RUNNING, (
        "run left RUNNING with no worker — the task is wedged"
    )
    assert tasks.get(ws, task_id).status == TaskStatus.FAILED


def test_cli_resume_reports_the_real_error_when_recovery_also_fails(
    blocked, monkeypatch
):
    """The nested except must not itself raise.

    It caught a NameError in review: `logger` is not defined in cli/app.py, so
    the recovery handler would have masked the actual failure with its own.
    """
    from typer.testing import CliRunner

    _, ws, task_id, run_id = blocked

    def _boom(*a, **k):
        raise ValueError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(runtime, "execute_agent", _boom)
    monkeypatch.setattr(
        runtime, "fail_run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("nope"))
    )

    from codeframe.cli.app import app
    from codeframe.core import workspace as ws_module

    monkeypatch.setattr(ws_module, "get_workspace", lambda p: ws)

    result = CliRunner().invoke(app, ["work", "resume", task_id[:8]])

    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY is not set" in result.output, (
        f"the real error was masked: {result.output!r}"
    )
