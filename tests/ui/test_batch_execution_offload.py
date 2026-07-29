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
    app.state.workspace = test_workspace
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
        # Wait for the batch to be genuinely in flight before measuring, so a
        # merely-slow-to-start thread cannot make this pass vacuously. Awaited
        # via the executor so the wait itself never blocks the loop; on the
        # unfixed code the POST holds the loop and this times out, which is the
        # failure we want.
        await asyncio.get_running_loop().run_in_executor(
            None, slow_batch["started"].wait, 5
        )
        assert slow_batch["started"].is_set(), "batch never started"

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


class TestOneBatchPerWorkspace:
    """Offloading removed an accidental safety property (#901 review).

    While execution ran inline on the event loop, a second POST could not even
    be *served* until the first batch finished — the bug serialized batches.
    Nothing replaced that: ``check_assignment_status`` counts IN_PROGRESS tasks,
    but tasks only move inside the detached thread, long after the handler has
    responded. Two clicks would both pass and run two agent subprocesses against
    the same git worktree.
    """

    async def test_second_execute_is_refused_while_one_runs(self, app, slow_batch):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})
            assert first.status_code == 200, first.text
            assert slow_batch["started"].wait(timeout=5)

            second = await client.post("/api/v2/tasks/execute", json={"task_ids": ["t2"]})

        assert second.status_code == 409, second.text

    async def test_concurrent_executes_admit_exactly_one(self, app, slow_batch):
        """The race itself: both requests in flight at once."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            results = await asyncio.gather(
                client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]}),
                client.post("/api/v2/tasks/execute", json={"task_ids": ["t2"]}),
            )

        codes = sorted(r.status_code for r in results)
        assert codes == [200, 409], f"expected exactly one to win, got {codes}"

    async def test_approve_is_guarded_too(self, app, slow_batch, monkeypatch):
        """/approve never called the assignment guard at all."""
        from codeframe.ui.routers import tasks_v2

        monkeypatch.setattr(
            tasks_v2.runtime,
            "approve_tasks",
            lambda ws, excluded_task_ids=None: type(
                "R",
                (),
                {
                    "approved_count": 1,
                    "excluded_count": 0,
                    "approved_task_ids": ["t1"],
                    "excluded_task_ids": [],
                },
            )(),
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})
            assert slow_batch["started"].wait(timeout=5)

            resp = await client.post(
                "/api/v2/tasks/approve", json={"start_execution": True}
            )

        assert resp.status_code == 409, resp.text

    async def test_a_finished_batch_does_not_block_the_next_one(self, app, slow_batch):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})
            assert slow_batch["started"].wait(timeout=5)
            slow_batch["release"].set()
            assert slow_batch["finished"].wait(timeout=5)

            # The stand-in returns the batch without finalizing it, so mark it
            # terminal the way a real run would before asserting the gate lifts.
            from codeframe.core import conductor

            for batch in conductor.list_batches(app.state.workspace, limit=5):
                conductor.fail_batch(app.state.workspace, batch.id, reason="test")

            second = await client.post("/api/v2/tasks/execute", json={"task_ids": ["t2"]})

        assert second.status_code == 200, second.text


class TestWedgedBatchIsFinalized:
    """A crash in the detached thread must not leave the batch RUNNING forever.

    The client already has its 200 + batch_id, and ``resume_batch`` accepts only
    PARTIAL/FAILED/CANCELLED — so a wedged RUNNING batch could not even be
    resumed. Work before ``_execute_parallel``'s own try (plan building,
    starting the reconciliation thread) is exactly what can raise here.
    """

    async def test_thread_failure_marks_the_batch_failed(
        self, app, test_workspace, monkeypatch
    ):
        from codeframe.core import conductor
        from codeframe.ui.routers import tasks_v2

        def _boom(workspace, batch, max_retries=0, on_event=None):
            raise RuntimeError("plan building exploded")

        monkeypatch.setattr(tasks_v2.conductor, "execute_batch", _boom)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v2/tasks/execute", json={"task_ids": ["t1"]})

        batch_id = resp.json()["batch_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            batch = conductor.get_batch(test_workspace, batch_id)
            if batch and batch.status in conductor.TERMINAL_BATCH_STATUSES:
                break
            time.sleep(0.05)

        batch = conductor.get_batch(test_workspace, batch_id)
        assert batch is not None
        assert batch.status == conductor.BatchStatus.FAILED, (
            f"batch left {batch.status} — a wedged batch cannot even be resumed"
        )
