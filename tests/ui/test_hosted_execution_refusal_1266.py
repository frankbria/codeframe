"""Hosted mode refuses execution until per-tenant OS isolation exists (#1266).

Every process these routes start runs as the server's uid, with the server's
filesystem view: a tenant could read ``../<other_user>/`` or the parent's
``/proc/$PPID/environ``. Path confinement at create time is not a boundary.
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from unittest.mock import MagicMock

from codeframe.auth.dependencies import authenticate_websocket
from codeframe.auth.manager import reset_auth_engine
from codeframe.auth.stream_tickets import mint_ticket, reset_stream_tickets
from codeframe.platform_store.database import Database
from codeframe.ui.routers import (
    batches_v2,
    gates_v2,
    proof_v2,
    tasks_v2,
    terminal_ws,
)

pytestmark = pytest.mark.v2

HOSTED_DETAIL = "per-tenant OS isolation"


@pytest.fixture(autouse=True)
def _reset_tickets():
    reset_stream_tickets()
    yield
    reset_stream_tickets()


# ---------------------------------------------------------------------------
# Terminal WebSocket — a real shell, no subprocess mocks
# ---------------------------------------------------------------------------


def _terminal_app(workspace: str, user_id=None) -> FastAPI:
    app = FastAPI()
    app.include_router(terminal_ws.router)
    db = MagicMock()
    db.interactive_sessions.get.return_value = {
        "state": "active",
        "workspace_path": workspace,
        "user_id": user_id,
    }
    app.state.db = db
    return app


def _prove_no_shell(ws) -> None:
    """Reached only if the socket was accepted. A live shell answers, so a
    broken gate fails with DID NOT RAISE instead of hanging on a silent bash."""
    ws.send_text("echo SPAWNED\n")
    _read_until(ws, b"SPAWNED")


def _read_until(ws, marker: bytes, limit: int = 50) -> bytes:
    seen = b""
    for _ in range(limit):
        seen += ws.receive_bytes()
        if marker in seen:
            break
    return seen


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "root" / "proj"
    ws.mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    return ws


def test_self_hosted_terminal_runs_a_real_shell(workspace, monkeypatch):
    """Control: the same harness really spawns bash, so the refusal below is real."""
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    client = TestClient(_terminal_app(str(workspace)))

    with client.websocket_connect("/ws/sessions/s1/terminal") as ws:
        ws.send_text("echo MARK_$((6*7))\n")
        assert b"MARK_42" in _read_until(ws, b"MARK_42")


def test_hosted_terminal_refuses_before_spawning_a_shell(workspace, monkeypatch):
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    spawned = []
    real_exec = asyncio.create_subprocess_exec

    async def recording_exec(*args, **kwargs):
        spawned.append(args)
        return await real_exec(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_exec)
    client = TestClient(_terminal_app(str(workspace)))

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/sessions/s1/terminal") as ws:
            _prove_no_shell(ws)

    assert exc.value.code == 4403
    assert spawned == []


# ---------------------------------------------------------------------------
# Terminal WebSocket — admin scope
# ---------------------------------------------------------------------------


def _seed_user(db_path, user_id: int, *, superuser: bool) -> None:
    db = Database(db_path)
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (?, ?, 'User', '!DISABLED!', 1, ?, 1, 1)
        """,
        (user_id, f"u{user_id}@example.com", int(superuser)),
    )
    db.conn.commit()
    db.close()


@pytest.fixture
def auth_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    reset_auth_engine()
    _seed_user(tmp_path / "state.db", 1, superuser=True)
    _seed_user(tmp_path / "state.db", 2, superuser=False)
    yield
    reset_auth_engine()


def _ws(ticket):
    ws = MagicMock()
    ws.query_params = {"ticket": ticket}

    async def close(**kwargs):
        ws.closed_with = kwargs

    ws.close = close
    return ws


@pytest.mark.asyncio
async def test_admin_ticket_opens_an_admin_socket(auth_db):
    ws = _ws(mint_ticket(1, admin=True))

    ok, user_id = await authenticate_websocket(ws, close_code=4001, require_admin=True)

    assert (ok, user_id) == (True, 1)


@pytest.mark.asyncio
async def test_non_admin_ticket_is_refused_with_4403(auth_db):
    ws = _ws(mint_ticket(2, admin=False))

    ok, _ = await authenticate_websocket(ws, close_code=4001, require_admin=True)

    assert ok is False
    assert ws.closed_with["code"] == 4403


@pytest.mark.asyncio
async def test_superusers_write_scoped_ticket_is_refused(auth_db):
    """Admin comes from the minting principal, not from the account: a
    write-scoped key owned by a superuser must not open an admin terminal."""
    ws = _ws(mint_ticket(1, admin=False))

    ok, _ = await authenticate_websocket(ws, close_code=4001, require_admin=True)

    assert ok is False
    assert ws.closed_with["code"] == 4403


@pytest.mark.asyncio
async def test_non_admin_ticket_still_opens_non_admin_sockets(auth_db):
    """The chat socket does not require admin; nothing changes for it."""
    ws = _ws(mint_ticket(2, admin=False))

    ok, user_id = await authenticate_websocket(ws, close_code=1008)

    assert (ok, user_id) == (True, 2)


def test_terminal_route_requires_admin(tmp_path, auth_db, monkeypatch):
    """End to end on the route: a valid non-admin ticket is closed 4403."""
    ws_dir = tmp_path / "root" / "proj"
    ws_dir.mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "root"))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    client = TestClient(_terminal_app(str(ws_dir), user_id=2))

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws/sessions/s1/terminal?ticket={mint_ticket(2, admin=False)}"
        ) as ws:
            _prove_no_shell(ws)

    assert exc.value.code == 4403


# ---------------------------------------------------------------------------
# REST execution routes
# ---------------------------------------------------------------------------

GATED = [
    (tasks_v2, "/api/v2/tasks/execute", {}),
    (tasks_v2, "/api/v2/tasks/t1/start", {}),
    (tasks_v2, "/api/v2/tasks/t1/resume", {}),
    (tasks_v2, "/api/v2/tasks/approve", {"start_execution": True}),
    (batches_v2, "/api/v2/batches/b1/resume", {}),
    (gates_v2, "/api/v2/gates/run", {}),
    (proof_v2, "/api/v2/proof/run", {}),
]


def _rest_client(module) -> TestClient:
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("module, path, body", GATED, ids=[g[1] for g in GATED])
def test_hosted_mode_refuses_execution_routes(module, path, body, monkeypatch, tmp_path):
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    resp = _rest_client(module).post(path, json=body)

    assert resp.status_code == 403
    assert HOSTED_DETAIL in resp.text


@pytest.mark.parametrize("module, path, body", GATED, ids=[g[1] for g in GATED])
def test_self_hosted_mode_does_not_refuse(module, path, body, monkeypatch, tmp_path):
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    resp = _rest_client(module).post(path, json=body)

    assert HOSTED_DETAIL not in resp.text


def test_hosted_approve_without_execution_is_not_refused(monkeypatch, tmp_path):
    """Approving tasks runs nothing; only start_execution is execution."""
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    resp = _rest_client(tasks_v2).post("/api/v2/tasks/approve", json={"start_execution": False})

    assert HOSTED_DETAIL not in resp.text


def test_hosted_approve_with_execution_persists_nothing(monkeypatch, tmp_path):
    """The refusal must come before approvals are written, not after."""
    from codeframe.core import tasks
    from codeframe.core.state_machine import TaskStatus
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    ws = create_or_load_workspace(repo)
    task = tasks.create(ws, title="t", description="d")
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    resp = _rest_client(tasks_v2).post(
        f"/api/v2/tasks/approve?workspace_path={repo}", json={"start_execution": True}
    )

    assert resp.status_code == 403
    assert tasks.get(ws, task.id).status == TaskStatus.BACKLOG



@pytest.mark.asyncio
async def test_admin_ticket_of_a_since_demoted_account_is_refused(auth_db):
    """A ticket minted while admin must not outlive a demotion within its TTL."""
    ws = _ws(mint_ticket(2, admin=True))

    ok, _ = await authenticate_websocket(ws, close_code=4001, require_admin=True)

    assert ok is False
    assert ws.closed_with["code"] == 4403
