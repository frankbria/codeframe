"""Execution routes refuse a principal that used up its daily spend (#1303).

The limit is checked before any state is written, and what is left of it is
handed to the run (single task) or the batch (spend paths) to clamp the
workspace ``max_cost_usd``.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth.dependencies import require_auth
from codeframe.core import runtime, spend_limit, tasks
from codeframe.core.models import TokenUsage
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace
from codeframe.platform_store.database import Database
from codeframe.platform_store.repositories.token_repository import TokenRepository
from codeframe.ui.routers import batches_v2, tasks_v2

pytestmark = pytest.mark.v2

LIMIT_ENV = "CODEFRAME_USER_DAILY_COST_LIMIT_USD"
USER = 1  # the seeded admin row; the registry owner is a FK to users


def _record(repo: Path, cost: float) -> None:
    conn = sqlite3.connect(str(create_or_load_workspace(repo).db_path))
    try:
        TokenRepository(sync_conn=conn).save_token_usage(
            TokenUsage(
                task_id="x", agent_id="react", project_id=0,
                model_name="claude-sonnet-4-5", input_tokens=1, output_tokens=1,
                estimated_cost_usd=cost, timestamp=datetime.now(timezone.utc),
            )
        )
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _clean_holds():
    from codeframe.core import spend_limit

    spend_limit._held.clear()
    yield
    spend_limit._held.clear()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A workspace being run, a second one the user owns, and a client as USER."""
    root = tmp_path / "root"
    repo, other = root / "repo", root / "other"
    repo.mkdir(parents=True)
    other.mkdir()
    ws = create_or_load_workspace(repo)
    create_or_load_workspace(other)
    monkeypatch.setenv("WORKSPACE_ROOT", str(root))
    monkeypatch.setenv(LIMIT_ENV, "2")

    db = Database(tmp_path / "control.db")
    db.initialize()
    db.workspace_registry.upsert(str(other), owner_user_id=USER)

    app = FastAPI()
    app.include_router(tasks_v2.router)
    app.include_router(batches_v2.router)
    app.state.db = db
    app.dependency_overrides[require_auth] = lambda: {
        "type": "jwt", "user_id": USER, "scopes": ["read", "write"],
    }
    client = TestClient(app, raise_server_exceptions=False)
    yield client, ws, repo, other
    db.close()


def _q(repo: Path) -> str:
    return f"workspace_path={repo}"


class TestRefusedWhenExhausted:
    """Spend in ANOTHER owned workspace counts: the limit is per user."""

    def test_start(self, env):
        client, ws, repo, other = env
        _record(other, 2.0)
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

        resp = client.post(f"/api/v2/tasks/{task.id}/start?execute=true&{_q(repo)}")

        assert resp.status_code == 429, resp.text
        assert resp.json()["detail"]["code"] == "SPEND_LIMIT_EXCEEDED"
        assert runtime.get_active_run(ws, task.id) is None  # nothing started

    def test_start_without_execute_is_not_spend(self, env):
        client, ws, repo, other = env
        _record(other, 2.0)
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

        resp = client.post(f"/api/v2/tasks/{task.id}/start?{_q(repo)}")

        assert resp.status_code == 200, resp.text

    def test_execute(self, env):
        client, ws, repo, other = env
        _record(other, 2.5)
        tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

        resp = client.post(f"/api/v2/tasks/execute?{_q(repo)}", json={})

        assert resp.status_code == 429, resp.text

    def test_approve_and_start_writes_no_approval(self, env):
        client, ws, repo, other = env
        _record(repo, 2.0)
        task = tasks.create(ws, title="t", description="d")

        resp = client.post(
            f"/api/v2/tasks/approve?{_q(repo)}", json={"start_execution": True}
        )

        assert resp.status_code == 429, resp.text
        assert tasks.get(ws, task.id).status == TaskStatus.BACKLOG

    def test_resume(self, env):
        client, ws, repo, other = env
        _record(other, 2.0)

        resp = client.post(f"/api/v2/tasks/t1/resume?{_q(repo)}")

        assert resp.status_code == 429, resp.text

    def test_batch_resume(self, env):
        client, ws, repo, other = env
        _record(other, 2.0)

        resp = client.post(f"/api/v2/batches/b1/resume?{_q(repo)}", json={})

        assert resp.status_code == 429, resp.text


class TestRemainingBudgetIsHandedOn:
    def test_single_task_gets_the_remaining_ceiling(self, env, monkeypatch):
        client, ws, repo, other = env
        _record(other, 0.5)
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
        seen: dict = {}
        monkeypatch.setattr(
            tasks_v2, "_spawn_agent_worker", lambda *a, **kw: seen.update(kw)
        )

        resp = client.post(f"/api/v2/tasks/{task.id}/start?execute=true&{_q(repo)}")

        assert resp.status_code == 200, resp.text
        assert seen["cost_ceiling_usd"] == pytest.approx(1.5)

    def test_batch_gets_every_owned_workspace(self, env, monkeypatch):
        client, ws, repo, other = env
        tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
        seen: dict = {}
        monkeypatch.setattr(
            tasks_v2, "_start_batch_detached", lambda *a, **kw: seen.update(kw)
        )

        resp = client.post(f"/api/v2/tasks/execute?{_q(repo)}", json={})

        assert resp.status_code == 200, resp.text
        assert {p.resolve() for p in seen["spend_paths"]} == {repo.resolve(), other.resolve()}


def test_auth_off_operator_is_never_limited(env, monkeypatch):
    """user_id None is the single local operator — the limit is for tenants."""
    client, ws, repo, other = env
    client.app.dependency_overrides[require_auth] = lambda: {"user_id": None, "scopes": []}
    monkeypatch.setattr(tasks_v2, "_spawn_agent_worker", lambda *a, **kw: None)
    _record(repo, 99.0)
    task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

    resp = client.post(f"/api/v2/tasks/{task.id}/start?execute=true&{_q(repo)}")

    assert resp.status_code == 200, resp.text


def test_no_limit_configured_is_never_limited(env, monkeypatch):
    client, ws, repo, other = env
    monkeypatch.delenv(LIMIT_ENV)
    _record(repo, 99.0)

    resp = client.post(f"/api/v2/tasks/execute?{_q(repo)}", json={})

    assert resp.status_code != 429


def test_switching_to_an_unowned_workspace_does_not_reset_the_meter(env, tmp_path, monkeypatch):
    """Spend in a workspace the user merely worked in still counts (review #2)."""
    client, ws, repo, other = env
    monkeypatch.setattr(tasks_v2, "_spawn_agent_worker", lambda *a, **kw: None)
    third = repo.parent / "third"  # not owned by USER, never registered
    third.mkdir()
    ws3 = create_or_load_workspace(third)
    t3 = tasks.create(ws3, title="t", description="d", status=TaskStatus.READY)
    assert client.post(f"/api/v2/tasks/{t3.id}/start?execute=true&{_q(third)}").status_code == 200
    _record(third, 2.0)  # that run used the whole day's limit...
    spend_limit._held.clear()  # ...and ended (the stubbed worker never releases)
    task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)

    resp = client.post(f"/api/v2/tasks/{task.id}/start?execute=true&{_q(repo)}")

    assert resp.status_code == 429, resp.text


def test_a_failed_start_releases_its_hold(env):
    from codeframe.core import spend_limit

    client, ws, repo, other = env
    resp = client.post(f"/api/v2/tasks/no-such-task/start?execute=true&{_q(repo)}")

    assert resp.status_code == 404, resp.text
    assert spend_limit._held == {}


def test_the_worker_releases_its_hold_when_the_run_ends(env, monkeypatch):
    from codeframe.core import spend_limit

    client, ws, repo, other = env
    task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
    seen = {}

    def _agent(*a, **kw):
        seen["held"] = dict(spend_limit._held)

    monkeypatch.setattr(runtime, "execute_agent", _agent)
    started = threading.Event()
    real_thread = threading.Thread

    def _joined_thread(*a, **kw):
        t = real_thread(*a, **kw)
        original = t.start

        def _start():
            original()
            t.join(10)
            started.set()

        t.start = _start
        return t

    monkeypatch.setattr(tasks_v2.threading, "Thread", _joined_thread)
    resp = client.post(f"/api/v2/tasks/{task.id}/start?execute=true&{_q(repo)}")

    assert resp.status_code == 200, resp.text
    assert started.wait(10)
    assert seen["held"] == {USER: pytest.approx(2.0)}  # held while running
    assert spend_limit._held == {}  # and returned afterwards
