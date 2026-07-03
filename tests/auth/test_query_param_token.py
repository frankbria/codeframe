"""Tests for the ?ticket=<value> query-param fallback in get_current_user (issue #745).

Browser EventSource (SSE) cannot send an Authorization header, so on the
ALLOWLISTED SSE routes only (``_QUERY_TICKET_PATHS``), get_current_user falls
back to a ``ticket`` query parameter — a short-lived, single-use value minted
by ``POST /auth/stream-ticket``, redeemed here rather than decoded as a JWT.
This replaces the earlier ``?token=<JWT>`` fallback (issue #336): a long-lived
credential in the URL is a standing exposure (proxy/access logs, browser
history), so it is now a 60-second single-use ticket instead. Everywhere
else, query-string credentials are rejected (codex review P2): the fallback
must not become an API-wide authentication mechanism.
"""

import pytest
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient

from codeframe.auth import manager
from codeframe.auth.dependencies import get_current_user, get_current_user_optional
from codeframe.auth.manager import reset_auth_engine
from codeframe.auth.stream_tickets import mint_ticket, reset_stream_tickets
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

# An allowlisted SSE path (matches _QUERY_TICKET_PATHS in auth.dependencies).
SSE_PATH = "/api/v2/tasks/abc/stream"
# A path NOT on the allowlist — query tickets must be rejected here.
PLAIN_PATH = "/whoami"


def _make_token(user_id: int = 1, secret: str = None) -> str:
    # Read manager.SECRET live, not at import. get_current_user verifies against
    # the live global, and any test that starts the app via TestClient refreshes
    # it from .env (lifespan -> refresh_secret). Binding at import would make
    # these tokens unverifiable once that happens — an order-dependent flake.
    import jwt as pyjwt
    from codeframe.auth.manager import JWT_ALGORITHM
    from datetime import datetime, timedelta, timezone

    if secret is None:
        secret = manager.SECRET
    payload = {
        "sub": str(user_id),
        "aud": ["fastapi-users:auth"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


@pytest.fixture
def app_with_user(tmp_path, monkeypatch):
    """App with protected routes (one SSE-allowlisted, one plain) and a real
    test user in the DB."""
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    reset_auth_engine()
    reset_stream_tickets()

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

    @app.get(PLAIN_PATH)
    async def whoami(user=Depends(get_current_user)):
        return {"id": user.id}

    # Mounted at the real SSE path so the allowlist matches.
    @app.get("/api/v2/tasks/{task_id}/stream")
    async def fake_stream(task_id: str, user=Depends(get_current_user)):
        return {"id": user.id}

    @app.get("/maybe")
    async def maybe(request: Request):
        user = await get_current_user_optional(request)
        return {"id": user.id if user else None}

    yield app
    reset_auth_engine()
    reset_stream_tickets()


class TestQueryParamTicketOnSSERoutes:
    def test_valid_ticket_authenticates_on_sse_path(self, app_with_user):
        client = TestClient(app_with_user)
        ticket = mint_ticket(user_id=1)
        resp = client.get(f"{SSE_PATH}?ticket={ticket}")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_missing_ticket_unauthorized_on_sse_path(self, app_with_user):
        client = TestClient(app_with_user)
        resp = client.get(SSE_PATH)
        assert resp.status_code == 401

    def test_unknown_ticket_unauthorized_on_sse_path(self, app_with_user):
        client = TestClient(app_with_user)
        resp = client.get(f"{SSE_PATH}?ticket=not-a-real-ticket")
        assert resp.status_code == 401

    def test_reused_ticket_unauthorized_on_second_use(self, app_with_user):
        client = TestClient(app_with_user)
        ticket = mint_ticket(user_id=1)
        first = client.get(f"{SSE_PATH}?ticket={ticket}")
        assert first.status_code == 200

        second = client.get(f"{SSE_PATH}?ticket={ticket}")
        assert second.status_code == 401

    def test_header_still_works_on_sse_path(self, app_with_user):
        client = TestClient(app_with_user)
        token = _make_token(1)
        resp = client.get(SSE_PATH, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_query_jwt_token_no_longer_authenticates_sse_path(self, app_with_user):
        """?token=<JWT> is removed (issue #745): only ?ticket= is accepted now."""
        client = TestClient(app_with_user)
        token = _make_token(1)
        resp = client.get(f"{SSE_PATH}?token={token}")
        assert resp.status_code == 401


class TestQueryParamTicketRejectedElsewhere:
    def test_query_ticket_rejected_on_plain_route(self, app_with_user):
        """A valid ticket must NOT authenticate non-SSE routes — query
        credentials are SSE-only (codex review P2)."""
        client = TestClient(app_with_user)
        ticket = mint_ticket(user_id=1)
        resp = client.get(f"{PLAIN_PATH}?ticket={ticket}")
        assert resp.status_code == 401

    def test_header_works_on_plain_route(self, app_with_user):
        client = TestClient(app_with_user)
        token = _make_token(1)
        resp = client.get(PLAIN_PATH, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_optional_does_not_raise_on_invalid_query_ticket(self, app_with_user):
        """get_current_user_optional must keep swallowing failures."""
        client = TestClient(app_with_user)
        resp = client.get("/maybe?ticket=not-a-real-ticket")
        assert resp.status_code == 200
        assert resp.json()["id"] is None

    def test_optional_ignores_query_ticket_on_plain_route(self, app_with_user):
        """Even a valid ticket yields anonymous on non-SSE routes."""
        client = TestClient(app_with_user)
        ticket = mint_ticket(user_id=1)
        resp = client.get(f"/maybe?ticket={ticket}")
        assert resp.status_code == 200
        assert resp.json()["id"] is None


class TestTicketUserLookupFailure:
    def test_db_error_during_user_load_degrades_to_401_not_500(
        self, app_with_user, monkeypatch
    ):
        """An unexpected DB failure while loading the ticket's user must be a
        controlled 401 (like the bearer path and authenticate_websocket), not
        an unhandled 500 (CodeRabbit PR #800 Major)."""
        from codeframe.auth import dependencies

        async def boom(user_id):
            raise RuntimeError("db exploded")

        monkeypatch.setattr(dependencies, "_load_active_user", boom)
        client = TestClient(app_with_user, raise_server_exceptions=False)
        ticket = mint_ticket(user_id=1)
        resp = client.get(f"{SSE_PATH}?ticket={ticket}")
        assert resp.status_code == 401
