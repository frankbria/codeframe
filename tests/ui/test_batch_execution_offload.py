"""Batch execution never blocks the event loop (#901 / P0.7).

``POST /api/v2/tasks/execute`` and ``/tasks/approve`` called
``conductor.start_batch(...)`` directly from an ``async def`` handler.
``start_batch`` does not detach — it drives every task through
``_execute_task_subprocess``, ending in ``process.wait()`` — so the complete
agent execution of the whole batch ran on the uvicorn event loop. Every other
request, SSE stream, WebSocket and ``/health`` froze for its duration, which
for a real batch is minutes to hours. The web UI calls this endpoint.

The tests below assert the two properties that actually matter: the handler
**returns while the batch is still running**, and a concurrent request is
served meanwhile. Asserting only "200 OK" would pass on the broken code.
"""

import asyncio
import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.v2

# Upper bound on how long the stand-in batch will block if a test forgets to
# release it — keeps a regression from hanging the suite instead of failing.
MAX_BLOCK_SECONDS = 10.0
# The handler / a concurrent request must land far inside that. Generous for CI.
MAX_CONCURRENT_SECONDS = 2.0


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    yield create_or_load_workspace(workspace_path)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def slow_batch(monkeypatch):
    """Replace the execution half with a stand-in that blocks until released.

    Held on an Event rather than a fixed sleep: "is the batch still running?"
    becomes a fact the test controls instead of a race against wall-clock, and
    teardown releases it so a detached thread never leaks into the next test's
    timing budget.
    """
    from codeframe.ui.routers import tasks_v2

    state = {
        "started": threading.Event(),
        "finished": threading.Event(),
        "release": threading.Event(),
        "thread": None,
    }

    def _blocking_execute(workspace, batch, max_retries=0, on_event=None):
        state["thread"] = threading.current_thread()
        state["started"].set()
        state["release"].wait(timeout=MAX_BLOCK_SECONDS)
        state["finished"].set()
        return batch

    monkeypatch.setattr(tasks_v2.conductor, "execute_batch", _blocking_execute)
    yield state
    state["release"].set()
    state["finished"].wait(timeout=5)


@pytest.fixture
def app(test_workspace, monkeypatch):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import tasks_v2

    # The batch record is real; only task validation is stubbed so the test
    # needs no seeded tasks.
    monkeypatch.setattr(
        tasks_v2.conductor.tasks, "get", lambda ws, tid: object()
    )
    monkeypatch.setattr(
        tasks_v2.runtime,
        "check_assignment_status",
        lambda ws: type("S", (), {"can_assign": True, "reason": ""})(),
    )

    app = FastAPI()
    app.include_router(tasks_v2.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return app


async def test_execute_returns_while_the_batch_is_still_running(app, slow_batch):
    """The handler must return batch_id immediately, not after the batch ends."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.monotonic()
        resp = await client.post(
            "/api/v2/tasks/execute", json={"task_ids": ["t1", "t2"]}
        )
        elapsed = time.monotonic() - start

    assert resp.status_code == 200, resp.text
    assert resp.json()["batch_id"], "handler must return a batch id"
    assert elapsed < MAX_CONCURRENT_SECONDS, (
        f"POST /tasks/execute took {elapsed:.2f}s — it waited for the batch"
    )
    # The batch really is still running: the handler did not simply skip it.
    assert slow_batch["started"].wait(timeout=5), "execution never started"
    assert not slow_batch["finished"].is_set(), (
        "the batch finished before the handler returned — it was not detached"
    )


async def test_health_responds_while_a_batch_runs(app, slow_batch):
    """A concurrent request is served while the batch executes.

    The execute POST is left **in flight** rather than awaited first: awaiting
    it would let a blocking handler finish before /health is even issued, so
    the timing would look fine on the very code this is meant to catch.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.monotonic()
        execute_task = asyncio.create_task(
            client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})
        )
        # Yield so the handler starts (and, unfixed, blocks the loop here).
        await asyncio.sleep(0.05)

        health = await client.get("/health")
        elapsed = time.monotonic() - start

        execute_response = await execute_task

    assert health.status_code == 200
    assert execute_response.status_code == 200, execute_response.text
    assert elapsed < MAX_CONCURRENT_SECONDS, (
        f"/health took {elapsed:.2f}s while a batch ran — the loop was blocked"
    )


async def test_execution_runs_off_the_event_loop_thread(app, slow_batch):
    """Positive control: the work happens, and not on the serving thread."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})

    assert slow_batch["started"].wait(timeout=5)
    assert slow_batch["thread"] is not threading.current_thread()
    slow_batch["release"].set()
    assert slow_batch["finished"].wait(timeout=5), (
        "the detached batch never completed"
    )


async def test_approve_with_execution_also_returns_immediately(
    app, slow_batch, monkeypatch
):
    """/tasks/approve shares the defect and the fix."""
    from codeframe.ui.routers import tasks_v2

    monkeypatch.setattr(
        tasks_v2.runtime,
        "approve_tasks",
        lambda ws, excluded_task_ids=None: type(
            "R",
            (),
            {
                "approved_count": 2,
                "excluded_count": 0,
                "approved_task_ids": ["t1", "t2"],
                "excluded_task_ids": [],
            },
        )(),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.monotonic()
        resp = await client.post(
            "/api/v2/tasks/approve", json={"start_execution": True}
        )
        elapsed = time.monotonic() - start

    assert resp.status_code == 200, resp.text
    assert resp.json()["batch_id"]
    assert elapsed < MAX_CONCURRENT_SECONDS, (
        f"POST /tasks/approve took {elapsed:.2f}s — it waited for the batch"
    )
    assert slow_batch["started"].wait(timeout=5)


async def test_batch_is_visible_immediately_after_the_handler_returns(
    app, slow_batch, test_workspace
):
    """The record is persisted before the response, so a client can poll it."""
    from codeframe.core import conductor

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})

    batch_id = resp.json()["batch_id"]
    assert conductor.get_batch(test_workspace, batch_id) is not None
