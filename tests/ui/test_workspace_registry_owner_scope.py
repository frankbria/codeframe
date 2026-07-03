"""Router-level owner scoping for the workspace registry (#720 / P0.9).

With auth enabled, `GET /api/v2/workspaces` and `DELETE /api/v2/workspaces/{id}`
must be owner-scoped: user B cannot see or deregister user A's registered
workspace.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from codeframe.auth.manager import reset_auth_engine
from codeframe.platform_store.database import Database
from tests.conftest import create_test_jwt_token

pytestmark = pytest.mark.v2


@pytest.fixture
def app_with_user_a_workspace(tmp_path, monkeypatch):
    """Auth-on server; users 1 & 2 seeded; one workspace owned by user 1."""
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    # The `with TestClient(app)` below runs the lifespan startup, which rejects
    # the default JWT secret unless this escape hatch is set (self-hosted only).
    # create_test_jwt_token signs with the same default secret the server then
    # validates with, so tokens stay valid.
    monkeypatch.setenv("CODEFRAME_ALLOW_INSECURE_SECRET", "1")
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified)
        VALUES (1,'a@x.co','A','!DISABLED!',1,0,1,1),
               (2,'b@x.co','B','!DISABLED!',1,0,1,1)
        """
    )
    db.conn.commit()
    entry = db.workspace_registry.upsert(
        repo_path="/home/a/projects/alpha", name="alpha", owner_user_id=1
    )
    db.close()

    from codeframe.ui import server

    importlib.reload(server)
    yield server.app, entry["id"]
    reset_auth_engine()


def _bearer(user_id):
    return {"Authorization": f"Bearer {create_test_jwt_token(user_id)}"}


def _list_paths(client, user_id):
    r = client.get("/api/v2/workspaces", headers=_bearer(user_id))
    assert r.status_code == 200, r.text
    return {w["repo_path"] for w in r.json()["workspaces"]}


def test_user_b_cannot_list_user_a_workspace(app_with_user_a_workspace):
    app, _ = app_with_user_a_workspace
    with TestClient(app) as client:  # context manager runs startup (wires app.state.db)
        assert "/home/a/projects/alpha" not in _list_paths(client, 2)


def test_user_a_sees_own_workspace(app_with_user_a_workspace):
    app, _ = app_with_user_a_workspace
    with TestClient(app) as client:
        assert "/home/a/projects/alpha" in _list_paths(client, 1)


def test_user_b_cannot_delete_user_a_workspace(app_with_user_a_workspace):
    app, wid = app_with_user_a_workspace
    with TestClient(app) as client:
        r = client.delete(f"/api/v2/workspaces/{wid}", headers=_bearer(2))
        assert r.status_code == 404  # not owned → not found for user B
        # ...and user A can still delete it.
        assert client.delete(f"/api/v2/workspaces/{wid}", headers=_bearer(1)).status_code == 204
