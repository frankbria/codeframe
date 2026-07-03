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


class TestStreamTicketScopeEnforcement:
    """A ticket redeems as a full user session on WS routes (terminal input
    mutates state), so minting requires write scope. Read-only API keys must
    not be able to escalate to WS access via a ticket (codex review P1); they
    never need tickets anyway -- header-capable clients authenticate SSE with
    X-API-Key directly."""

    @pytest.fixture
    def api_keys(self, auth_client, tmp_path):
        from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE
        from codeframe.core.api_key_service import ApiKeyService

        db = Database(tmp_path / "state.db")
        db.initialize()
        svc = ApiKeyService(db)
        keys = {
            "read": svc.create_api_key(user_id=1, name="r", scopes=[SCOPE_READ]).key,
            "write": svc.create_api_key(
                user_id=1, name="w", scopes=[SCOPE_READ, SCOPE_WRITE]
            ).key,
        }
        db.close()
        return keys

    def test_read_only_api_key_returns_403(self, auth_client, api_keys, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        resp = auth_client.post(
            "/auth/stream-ticket", headers={"X-API-Key": api_keys["read"]}
        )
        assert resp.status_code == 403

    def test_write_api_key_returns_ticket(self, auth_client, api_keys, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        resp = auth_client.post(
            "/auth/stream-ticket", headers={"X-API-Key": api_keys["write"]}
        )
        assert resp.status_code == 200, resp.text
        assert redeem_ticket(resp.json()["ticket"]) == 1
