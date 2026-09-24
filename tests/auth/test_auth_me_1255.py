"""Tests for GET /auth/me (issue #1255).

The web UI needs to know whether the session holds ``admin`` scope so it can
disable admin-only actions up front instead of failing on submit. The endpoint
reports the principal ``require_auth`` resolved — the same one every
``require_scope(SCOPE_ADMIN)`` guard sees — so the UI cannot disagree with it.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth import router as auth_router
from codeframe.auth.manager import reset_auth_engine
from codeframe.platform_store.database import Database
from tests.conftest import create_test_jwt_token, setup_test_user

pytestmark = pytest.mark.v2


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    reset_auth_engine()
    db = Database(path)
    db.initialize()
    setup_test_user(db, user_id=1)
    db.close()
    yield path
    reset_auth_engine()


@pytest.fixture
def client(db_path):
    app = FastAPI()
    app.include_router(auth_router.router)
    return TestClient(app, raise_server_exceptions=False)


def _make_superuser(db_path):
    db = Database(db_path)
    db.initialize()
    db.conn.execute("UPDATE users SET is_superuser = 1 WHERE id = 1")
    db.conn.commit()
    db.close()


def _bearer():
    return {"Authorization": f"Bearer {create_test_jwt_token(user_id=1)}"}


def test_unauthenticated_returns_401(client, monkeypatch):
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    assert client.get("/auth/me").status_code == 401


def test_non_superuser_session_is_not_admin(client, monkeypatch):
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    resp = client.get("/auth/me", headers=_bearer())
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"scopes": ["read", "write"], "is_admin": False}


def test_superuser_session_is_admin(client, db_path, monkeypatch):
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    _make_superuser(db_path)
    resp = client.get("/auth/me", headers=_bearer())
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_admin"] is True
    assert "admin" in resp.json()["scopes"]


def test_auth_disabled_operator_is_admin(client, monkeypatch):
    """The auth-off synthetic principal is the local operator, not 'unknown'."""
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    resp = client.get("/auth/me")
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_admin"] is True


def test_admin_key_owned_by_non_superuser_is_not_admin(client, db_path, monkeypatch):
    """Admin comes from the clamped scopes (#898), not the key's stored ones."""
    from codeframe.auth.api_keys import SCOPE_ADMIN
    from codeframe.core.api_key_service import ApiKeyService

    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    db = Database(db_path)
    db.initialize()
    # Another account holds admin, so no later initialize() backfills it onto
    # user 1 as the instance's sole account (#898).
    db.conn.execute("UPDATE users SET is_superuser = 0 WHERE id = 1")
    db.conn.execute(
        "INSERT INTO users (id, email, name, hashed_password, is_active, is_superuser,"
        " is_verified, email_verified) VALUES (2, 'admin@example.com', 'Admin',"
        " 'x', 1, 1, 1, 1)"
    )
    db.conn.commit()
    key = ApiKeyService(db).create_api_key(user_id=1, name="a", scopes=[SCOPE_ADMIN]).key
    db.close()

    resp = client.get("/auth/me", headers={"X-API-Key": key})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_admin"] is False
