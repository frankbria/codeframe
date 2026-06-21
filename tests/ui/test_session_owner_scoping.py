"""Session REST endpoints must be scoped by owner (issue #704).

`POST /api/v2/sessions` persists ``user_id`` and the terminal/chat WebSockets
enforce ownership, but the REST list/get/delete/messages endpoints queried
without an owner filter — in an authenticated multi-user deployment one tenant
could enumerate/read/modify/end another tenant's sessions. These tests pin the
owner-scoping (and the no-auth passthrough).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth.dependencies import require_auth
from codeframe.platform_store.database import Database
from codeframe.ui.routers.interactive_sessions_v2 import router

pytestmark = pytest.mark.v2


@pytest.fixture
def app(monkeypatch):
    # Owner-scoping is independent of the workspace allowlist; keep it off.
    monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    application = FastAPI()
    application.include_router(router)
    db = Database(":memory:")
    db.initialize()
    # Seed the two users that sessions are owned by (FK: sessions.user_id → users.id).
    for uid in (1, 2):
        db.conn.execute(
            "INSERT OR IGNORE INTO users (id, email, hashed_password) VALUES (?, ?, 'x')",
            (uid, f"u{uid}@example.com"),
        )
    db.conn.commit()
    application.state.db = db
    return application


def _as_user(app, user_id):
    """Override auth so requests act as ``user_id`` (None = no-auth mode)."""
    app.dependency_overrides[require_auth] = lambda: {"user_id": user_id}
    return TestClient(app, raise_server_exceptions=True)


def _create(client, path="/tmp/ws"):
    resp = client.post("/api/v2/sessions", json={"workspace_path": path})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class TestOwnerScoping:
    def test_list_only_returns_own_sessions(self, app):
        s1 = _create(_as_user(app, 1), "/tmp/a")
        _create(_as_user(app, 2), "/tmp/b")

        ids = [s["id"] for s in _as_user(app, 1).get("/api/v2/sessions").json()]
        assert ids == [s1]

    def test_get_other_users_session_404(self, app):
        other = _create(_as_user(app, 2))
        assert _as_user(app, 1).get(f"/api/v2/sessions/{other}").status_code == 404

    def test_get_own_session_200(self, app):
        mine = _create(_as_user(app, 1))
        assert _as_user(app, 1).get(f"/api/v2/sessions/{mine}").status_code == 200

    def test_delete_other_users_session_404(self, app):
        other = _create(_as_user(app, 2))
        client = _as_user(app, 1)
        assert client.delete(f"/api/v2/sessions/{other}").status_code == 404
        # And it is still active for its real owner.
        assert _as_user(app, 2).get(f"/api/v2/sessions/{other}").json()["state"] == "active"

    def test_post_message_to_other_users_session_404(self, app):
        other = _create(_as_user(app, 2))
        resp = _as_user(app, 1).post(
            f"/api/v2/sessions/{other}/messages",
            json={"role": "user", "content": "hi"},
        )
        assert resp.status_code == 404

    def test_get_messages_of_other_users_session_404(self, app):
        other = _create(_as_user(app, 2))
        assert (
            _as_user(app, 1).get(f"/api/v2/sessions/{other}/messages").status_code == 404
        )


class TestNoAuthPassthrough:
    """With auth off (user_id is None) ownership is not enforced — unchanged."""

    def test_list_returns_all(self, app):
        _create(_as_user(app, None), "/tmp/a")
        _create(_as_user(app, None), "/tmp/b")
        assert len(_as_user(app, None).get("/api/v2/sessions").json()) == 2

    def test_get_any_session(self, app):
        sid = _create(_as_user(app, None))
        assert _as_user(app, None).get(f"/api/v2/sessions/{sid}").status_code == 200
