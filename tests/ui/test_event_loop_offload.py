"""Event-loop offload tests for blocking v2 handlers (#732).

A long-blocking core call (e.g. run_proof running a full test suite) executed
directly inside an ``async def`` handler freezes the event loop — SSE
heartbeats, WebSockets, and /health all stall. These tests assert the heavy
handlers offload to a worker thread so concurrent requests stay responsive.
"""

import asyncio
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.v2

BLOCK_SECONDS = 1.5
# A concurrent /health must complete well before the blocking call would
# release the loop. Generous margin for slow CI machines.
MAX_HEALTH_SECONDS = 1.0


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    yield create_or_load_workspace(workspace_path)

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def app(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import proof_v2

    app = FastAPI()
    app.include_router(proof_v2.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return app


async def test_proof_run_does_not_block_health(app, monkeypatch):
    """/health responds while a (blocking) proof run is in flight."""
    from codeframe.ui.routers import proof_v2

    def slow_run_proof(*args, **kwargs):
        time.sleep(BLOCK_SECONDS)
        return {}

    monkeypatch.setattr(proof_v2, "run_proof", slow_run_proof)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = time.monotonic()
        proof_task = asyncio.create_task(client.post("/api/v2/proof/run", json={}))
        # Yield so the proof handler starts (and, unfixed, blocks the loop).
        await asyncio.sleep(0.05)

        health_response = await client.get("/health")
        health_elapsed = time.monotonic() - start

        proof_response = await proof_task

    assert health_response.status_code == 200
    assert proof_response.status_code == 200
    assert health_elapsed < MAX_HEALTH_SECONDS, (
        f"/health took {health_elapsed:.2f}s — the proof run blocked the event loop"
    )
