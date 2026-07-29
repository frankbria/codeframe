"""The remaining hot paths no longer block the event loop (#902 / P0.8).

Several `async def` handlers called synchronous core work inline, so one slow
caller stalled every SSE stream, WebSocket terminal and concurrent request:
review (tree-sitter/radon/bandit), all six git_v2 GitPython handlers, discovery
LLM round trips, `/env/check` and `/env/doctor` (a subprocess per tool), and
the API-key auth SELECT+UPDATE on every request.

Each test holds the core function inside a worker thread and asserts `/health`
is still served — the property that distinguishes offloaded from inline. A
status-code assertion alone passes on the broken code.
"""

import asyncio
import shutil
import tempfile
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.v2

# A concurrent /health must land far inside the blocked window. Generous for CI.
MAX_HEALTH_SECONDS = 2.0
# Upper bound if a test forgets to release, so a regression fails rather than hangs.
MAX_BLOCK_SECONDS = 10.0


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    yield create_or_load_workspace(workspace_path)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def blocker():
    """A stand-in that blocks until released, recording that it was entered."""
    state = {"started": threading.Event(), "release": threading.Event()}

    def _block(*args, **kwargs):
        state["started"].set()
        state["release"].wait(timeout=MAX_BLOCK_SECONDS)
        return state.get("result")

    state["fn"] = _block
    yield state
    state["release"].set()


def _app_with(router_module, test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace

    app = FastAPI()
    app.include_router(router_module.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return app


async def _assert_health_served_during(app, method, path, blocker, **kw):
    """Fire the slow request, prove it is in flight, then time /health."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        slow = asyncio.create_task(getattr(client, method)(path, **kw))

        # Prove the handler actually reached the blocking call before measuring,
        # so a merely-slow-to-start request cannot make this pass vacuously.
        await asyncio.get_running_loop().run_in_executor(
            None, blocker["started"].wait, 5
        )
        assert blocker["started"].is_set(), "handler never reached the core call"

        loop = asyncio.get_running_loop()
        start = loop.time()
        health = await client.get("/health")
        elapsed = loop.time() - start

        blocker["release"].set()
        await slow

    assert health.status_code == 200
    assert elapsed < MAX_HEALTH_SECONDS, (
        f"/health took {elapsed:.2f}s while {method.upper()} {path} ran — "
        "the handler blocked the event loop"
    )


class TestReviewOffload:
    async def test_health_responds_during_review_files(
        self, test_workspace, blocker, monkeypatch
    ):
        from codeframe.ui.routers import review_v2

        blocker["result"] = review_v2.review.ReviewResult("approved", 100.0, [], "ok")
        monkeypatch.setattr(review_v2.review, "review_files", blocker["fn"])

        await _assert_health_served_during(
            _app_with(review_v2, test_workspace),
            "post",
            "/api/v2/review/files",
            blocker,
            json={"files": ["a.py"]},
        )


class TestGitOffload:
    async def test_health_responds_during_git_status(
        self, test_workspace, blocker, monkeypatch
    ):
        from codeframe.core.git import GitStatus
        from codeframe.ui.routers import git_v2

        blocker["result"] = GitStatus(
            current_branch="main",
            is_dirty=False,
            modified_files=[],
            untracked_files=[],
            staged_files=[],
        )
        monkeypatch.setattr(git_v2.git, "get_status", blocker["fn"])

        await _assert_health_served_during(
            _app_with(git_v2, test_workspace), "get", "/api/v2/git/status", blocker
        )

    async def test_health_responds_during_git_diff(
        self, test_workspace, blocker, monkeypatch
    ):
        from codeframe.ui.routers import git_v2

        blocker["result"] = "diff --git a/x b/x\n"
        monkeypatch.setattr(git_v2.git, "get_diff", blocker["fn"])

        await _assert_health_served_during(
            _app_with(git_v2, test_workspace), "get", "/api/v2/git/diff", blocker
        )


class TestEnvironmentOffload:
    async def test_health_responds_during_env_check(
        self, test_workspace, blocker, monkeypatch
    ):
        from codeframe.ui.routers import environment_v2

        monkeypatch.setattr(
            environment_v2.EnvironmentValidator,
            "validate_environment",
            lambda self, *a, **kw: blocker["fn"](),
        )
        monkeypatch.setattr(
            environment_v2,
            "_result_to_response",
            lambda result: environment_v2.ValidationResultResponse(
                project_type="python",
                detected_tools={},
                missing_tools=[],
                optional_missing=[],
                health_score=1.0,
                health_percent=100,
                is_healthy=True,
                recommendations=[],
                warnings=[],
                conflicts=[],
            ),
        )

        await _assert_health_served_during(
            _app_with(environment_v2, test_workspace),
            "get",
            "/api/v2/env/check",
            blocker,
        )


class TestDiscoveryOffload:
    async def test_health_responds_during_discovery_start(
        self, test_workspace, blocker, monkeypatch
    ):
        from codeframe.ui.routers import discovery_v2

        monkeypatch.setattr(
            discovery_v2.prd_discovery, "get_active_session", lambda ws: None
        )
        monkeypatch.setattr(
            discovery_v2.prd_discovery, "start_discovery_session", blocker["fn"]
        )

        transport = ASGITransport(app=_app_with(discovery_v2, test_workspace))
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            slow = asyncio.create_task(client.post("/api/v2/discovery/start"))
            await asyncio.get_running_loop().run_in_executor(
                None, blocker["started"].wait, 5
            )
            assert blocker["started"].is_set()

            loop = asyncio.get_running_loop()
            start = loop.time()
            health = await client.get("/health")
            elapsed = loop.time() - start

            blocker["release"].set()
            await slow

        assert health.status_code == 200
        assert elapsed < MAX_HEALTH_SECONDS, (
            f"/health took {elapsed:.2f}s during an LLM discovery call"
        )
