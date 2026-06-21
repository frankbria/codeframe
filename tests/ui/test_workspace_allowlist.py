"""Tests for workspace path allowlist (issue #655).

`get_v2_workspace` previously resolved an arbitrary client-supplied
`workspace_path` and only checked the `.codeframe` marker — authenticated
cross-tenant RCE the moment the server is exposed to >1 user. These tests
pin the allowlist + HOSTED-mode per-user binding.
"""

import shutil
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from codeframe.core.workspace import create_or_load_workspace
from codeframe.ui.dependencies import get_v2_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def root(tmp_path):
    """A permitted root dir containing one initialized workspace at <root>/proj."""
    proj = tmp_path / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    ws = create_or_load_workspace(proj)
    yield tmp_path, ws
    shutil.rmtree(tmp_path, ignore_errors=True)


def _request():
    """Minimal Request stand-in: only app.state is read."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


def _call(path, *, auth=None):
    return get_v2_workspace(
        workspace_path=str(path),
        request=_request(),
        auth=auth if auth is not None else {"user_id": None},
    )


def test_no_root_set_allows_any_path(root, monkeypatch):
    """Self-hosted default (no WORKSPACE_ROOT): behavior unchanged."""
    monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    _, ws = root
    assert _call(ws.repo_path).repo_path == ws.repo_path


def test_path_inside_root_allowed(root, monkeypatch):
    base, ws = root
    monkeypatch.setenv("WORKSPACE_ROOT", str(base))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    assert _call(ws.repo_path).repo_path == ws.repo_path


def test_path_outside_root_rejected(root, monkeypatch):
    base, ws = root
    # Allow a sibling dir, not the one the workspace lives in.
    monkeypatch.setenv("WORKSPACE_ROOT", str(base / "other"))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    with pytest.raises(HTTPException) as exc:
        _call(ws.repo_path)
    assert exc.value.status_code == 403


def test_traversal_escape_rejected(root, monkeypatch):
    base, ws = root
    monkeypatch.setenv("WORKSPACE_ROOT", str(base))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    # ../ escapes the root even though the literal string starts under it.
    with pytest.raises(HTTPException) as exc:
        _call(f"{base}/../{ws.repo_path.name}")
    assert exc.value.status_code == 403


def test_hosted_requires_root(root, monkeypatch):
    _, ws = root
    monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    with pytest.raises(HTTPException) as exc:
        _call(ws.repo_path, auth={"user_id": 1})
    assert exc.value.status_code == 500


def test_hosted_confines_to_user_subdir(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    # User 1 owns <root>/1/proj; user 2 must not reach it.
    proj = tmp_path / "1" / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    ws1 = create_or_load_workspace(proj)
    assert _call(ws1.repo_path, auth={"user_id": 1}).repo_path == ws1.repo_path
    with pytest.raises(HTTPException) as exc:
        _call(ws1.repo_path, auth={"user_id": 2})
    assert exc.value.status_code == 403
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_hosted_requires_authenticated_user(root, monkeypatch):
    base, ws = root
    monkeypatch.setenv("WORKSPACE_ROOT", str(base))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    with pytest.raises(HTTPException) as exc:
        _call(ws.repo_path, auth={"user_id": None})
    assert exc.value.status_code == 403


# --- Session creation must clear the same allowlist (codex P1 / #655) ---------
# create_session stores workspace_path, which terminal_ws later uses as a shell
# cwd — a bypass of get_v2_workspace's check unless validated here too.


@pytest.fixture
def sessions_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from codeframe.platform_store.database import Database
    from codeframe.ui.routers.interactive_sessions_v2 import router

    app = FastAPI()
    app.include_router(router)
    db = Database(":memory:")
    db.initialize()
    app.state.db = db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_session_create_rejects_path_outside_root(sessions_client, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "allowed"))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    resp = sessions_client.post(
        "/api/v2/sessions", json={"workspace_path": str(tmp_path / "elsewhere")}
    )
    assert resp.status_code == 403


def test_session_create_stores_resolved_path_inside_root(sessions_client, tmp_path, monkeypatch):
    base = tmp_path / "allowed"
    base.mkdir()
    monkeypatch.setenv("WORKSPACE_ROOT", str(base))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    resp = sessions_client.post(
        "/api/v2/sessions", json={"workspace_path": f"{base}/../allowed/proj"}
    )
    assert resp.status_code == 201
    # Stored path is resolved (traversal collapsed), so the terminal cwd is exactly
    # the validated path.
    assert resp.json()["workspace_path"] == str(base / "proj")


def test_session_create_persists_owner_user_id(sessions_client, tmp_path, monkeypatch):
    # Auth is off in tests → require_auth yields user_id=None; assert the column
    # is written (None here) so the terminal/chat ownership check has data to act
    # on once auth is enabled.
    monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    resp = sessions_client.post(
        "/api/v2/sessions", json={"workspace_path": str(tmp_path)}
    )
    assert resp.status_code == 201
    row = sessions_client.app.state.db.interactive_sessions.get(resp.json()["id"])
    assert "user_id" in row


# --- Workspace initialization must clear the allowlist too (codex P1 / #655) --


@pytest.fixture
def workspace_init_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from codeframe.ui.routers.workspace_v2 import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_workspace_init_rejects_path_outside_root(workspace_init_client, tmp_path, monkeypatch):
    base = tmp_path / "allowed"
    base.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    monkeypatch.setenv("WORKSPACE_ROOT", str(base))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    resp = workspace_init_client.post(
        "/api/v2/workspaces", json={"repo_path": str(outside)}
    )
    assert resp.status_code == 403
