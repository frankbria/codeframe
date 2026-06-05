"""Tests for ?token=<JWT> query-param fallback in get_current_user (issue #336).

Browser EventSource (SSE) cannot send an Authorization header, so when no
Bearer credentials are present, get_current_user falls back to a ``token``
query parameter validated through the same JWT path.
"""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient

from codeframe.auth.dependencies import get_current_user, get_current_user_optional
from codeframe.auth.manager import SECRET, JWT_ALGORITHM, reset_auth_engine
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


def _make_token(user_id: int = 1, secret: str = SECRET) -> str:
    payload = {
        "sub": str(user_id),
        "aud": ["fastapi-users:auth"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


@pytest.fixture
def app_with_user(tmp_path, monkeypatch):
    """App with a single protected route and a real test user in the DB."""
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (1, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """
    )
    db.conn.commit()
    db.close()

    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user=Depends(get_current_user)):
        return {"id": user.id}

    @app.get("/maybe")
    async def maybe(request: Request):
        user = await get_current_user_optional(request)
        return {"id": user.id if user else None}

    yield app
    reset_auth_engine()


class TestQueryParamToken:
    def test_valid_query_token_authenticates(self, app_with_user):
        client = TestClient(app_with_user)
        token = _make_token(1)
        resp = client.get(f"/whoami?token={token}")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_missing_token_unauthorized(self, app_with_user):
        client = TestClient(app_with_user)
        resp = client.get("/whoami")
        assert resp.status_code == 401

    def test_invalid_query_token_unauthorized(self, app_with_user):
        client = TestClient(app_with_user)
        resp = client.get("/whoami?token=not-a-jwt")
        assert resp.status_code == 401

    def test_header_still_works(self, app_with_user):
        client = TestClient(app_with_user)
        token = _make_token(1)
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_optional_does_not_raise_on_invalid_query_token(self, app_with_user):
        """get_current_user_optional must keep swallowing failures."""
        client = TestClient(app_with_user)
        resp = client.get("/maybe?token=not-a-jwt")
        assert resp.status_code == 200
        assert resp.json()["id"] is None

    def test_optional_authenticates_via_query_token(self, app_with_user):
        client = TestClient(app_with_user)
        token = _make_token(1)
        resp = client.get(f"/maybe?token={token}")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1
