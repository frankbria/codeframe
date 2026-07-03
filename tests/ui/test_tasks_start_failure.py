"""Background agent-launch failure must not strand the task (#722 / P0.11).

POST /tasks/{id}/start?execute=true creates the run (task -> IN_PROGRESS) and
runs the agent in a background thread. If the agent raises *before* its own
try (e.g. missing ANTHROPIC_API_KEY / unknown provider), the handler used to
only log + emit an SSE error, leaving the run RUNNING forever — every retry
then 400s with "already has an active run". The fix calls runtime.fail_run so
the task returns to a retryable (FAILED) state.
"""

import shutil
import tempfile
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _wait_until(predicate, timeout=5.0, interval=0.05):
    """Poll until predicate() is truthy or timeout — the agent runs in a real
    daemon thread, and a launch that fails up front resolves in milliseconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def client_and_task(monkeypatch):
    tmp = Path(tempfile.mkdtemp())
    ws_dir = tmp / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws = create_or_load_workspace(ws_dir)
    task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

    from codeframe.ui.routers import tasks_v2
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.core import runtime

    # Agent launch fails up front (as a missing API key would), before
    # execute_agent's own try/except — so only the router handler can reset it.
    def _boom(*a, **k):
        raise ValueError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr(runtime, "execute_agent", _boom)

    app = FastAPI()
    app.include_router(tasks_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: ws
    client = TestClient(app)
    yield client, ws, task.id
    shutil.rmtree(tmp, ignore_errors=True)


def test_failed_launch_leaves_task_retryable(client_and_task):
    client, ws, task_id = client_and_task

    r = client.post(f"/api/v2/tasks/{task_id}/start", params={"execute": "true"})
    assert r.status_code == 200  # start still returns 200; failure is async

    # The task must NOT stay IN_PROGRESS — fail_run resets it to FAILED.
    assert _wait_until(lambda: tasks.get(ws, task_id).status == TaskStatus.FAILED), (
        f"task stayed {tasks.get(ws, task_id).status}, expected FAILED"
    )


def test_failed_launch_allows_restart(client_and_task):
    client, ws, task_id = client_and_task
    client.post(f"/api/v2/tasks/{task_id}/start", params={"execute": "true"})
    _wait_until(lambda: tasks.get(ws, task_id).status == TaskStatus.FAILED)

    # A second start must not 400 with "already has an active run".
    r2 = client.post(f"/api/v2/tasks/{task_id}/start", params={"execute": "true"})
    assert r2.status_code != 400
