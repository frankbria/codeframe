"""Tests for POST /auth/stream-ticket (issue #745).

Mints a short-lived, single-use ticket used to authenticate SSE/WS streams,
replacing the long-lived JWT-in-query-string pattern. The endpoint itself is
authenticated the normal way -- JWT Bearer or X-API-Key via ``require_auth``
-- and rate-limited like the other auth endpoints.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.auth import router as auth_router
from codeframe.auth.manager import reset_auth_engine
from codeframe.auth.stream_tickets import redeem_ticket, reset_stream_tickets
from codeframe.platform_store.database import Database
from tests.conftest import create_test_jwt_token, setup_test_user

pytestmark = pytest.mark.v2


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    reset_auth_engine()
    reset_stream_tickets()

    db = Database(db_path)
    db.initialize()
    setup_test_user(db, user_id=1)
    db.close()

    app = FastAPI()
    app.include_router(auth_router.router)
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    reset_auth_engine()
    reset_stream_tickets()


class TestStreamTicketEndpointAuthRequired:
    def test_unauthenticated_returns_401(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        resp = auth_client.post("/auth/stream-ticket")
        assert resp.status_code == 401

    def test_valid_jwt_returns_ticket(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        token = create_test_jwt_token(user_id=1)
        resp = auth_client.post(
            "/auth/stream-ticket", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["ticket"], str) and body["ticket"]
        assert body["expires_in"] == 60

    def test_minted_ticket_redeems_to_the_authenticated_user(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        token = create_test_jwt_token(user_id=1)
        resp = auth_client.post(
            "/auth/stream-ticket", headers={"Authorization": f"Bearer {token}"}
        )
        ticket = resp.json()["ticket"]
        assert redeem_ticket(ticket) == 1

    def test_invalid_bearer_returns_401(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        resp = auth_client.post(
            "/auth/stream-ticket", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert resp.status_code == 401


class TestStreamTicketEndpointAuthDisabled:
    def test_auth_disabled_returns_ticket_without_credentials(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        resp = auth_client.post("/auth/stream-ticket")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["ticket"], str) and body["ticket"]

    def test_auth_disabled_ticket_redeems_to_none_user(self, auth_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        resp = auth_client.post("/auth/stream-ticket")
        ticket = resp.json()["ticket"]
        assert redeem_ticket(ticket) is None
