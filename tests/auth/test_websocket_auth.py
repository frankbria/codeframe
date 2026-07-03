"""Tests for the shared WebSocket auth helper (issue #676, updated for #745).

`authenticate_websocket()` is the single source of truth that lets terminal and
session-chat WebSockets honor `CODEFRAME_AUTH_REQUIRED` the same way `require_auth()`
does for REST:
- auth disabled -> (True, None) without requiring a ticket (synthetic local principal)
- auth enabled  -> redeem the ?ticket= single-use ticket (issue #745), or close
  the socket with the given code
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import codeframe.auth.stream_tickets as stream_tickets
from codeframe.auth.dependencies import authenticate_websocket
from codeframe.auth.manager import reset_auth_engine
from codeframe.auth.stream_tickets import mint_ticket, reset_stream_tickets
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


def _make_ws(ticket: str | None = None):
    """Minimal WebSocket double with query_params and an awaitable close()."""
    ws = MagicMock()
    ws.query_params = {} if ticket is None else {"ticket": ticket}
    ws.close = AsyncMock()
    return ws


def _seed_active_user(db_path, user_id: int = 1) -> None:
    db = Database(db_path)
    db.initialize()
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (?, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """,
        (user_id,),
    )
    db.conn.commit()
    db.close()


@pytest.fixture(autouse=True)
def _reset_tickets():
    reset_stream_tickets()
    yield
    reset_stream_tickets()


class TestNoAuthMode:
    @pytest.mark.asyncio
    async def test_disabled_returns_local_principal_without_ticket(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        ws = _make_ws(ticket=None)

        ok, user_id = await authenticate_websocket(ws, close_code=4001)

        assert ok is True
        assert user_id is None
        ws.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_ignores_provided_ticket(self, monkeypatch):
        """A stale/garbage ticket must not break the connection in no-auth mode."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        ws = _make_ws(ticket="not-a-real-ticket")

        ok, user_id = await authenticate_websocket(ws, close_code=1008)

        assert ok is True
        assert user_id is None
        ws.close.assert_not_awaited()


class TestAuthEnabled:
    @pytest.mark.asyncio
    async def test_enabled_missing_ticket_closes(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        ws = _make_ws(ticket=None)

        ok, user_id = await authenticate_websocket(ws, close_code=4001)

        assert ok is False
        assert user_id is None
        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs["code"] == 4001

    @pytest.mark.asyncio
    async def test_enabled_unknown_ticket_closes_with_given_code(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        ws = _make_ws(ticket="not-a-real-ticket")

        ok, user_id = await authenticate_websocket(ws, close_code=1008)

        assert ok is False
        assert user_id is None
        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs["code"] == 1008

    @pytest.mark.asyncio
    async def test_enabled_expired_ticket_closes(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        current = [1_000.0]
        monkeypatch.setattr(stream_tickets, "_now", lambda: current[0])

        ticket = mint_ticket(user_id=1)
        current[0] += stream_tickets.TICKET_TTL_SECONDS + 1
        ws = _make_ws(ticket=ticket)

        ok, user_id = await authenticate_websocket(ws, close_code=1008)

        assert ok is False
        assert user_id is None
        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs["code"] == 1008

    @pytest.mark.asyncio
    async def test_enabled_reused_ticket_closes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
        reset_auth_engine()
        _seed_active_user(tmp_path / "state.db")

        ticket = mint_ticket(user_id=1)
        first_ws = _make_ws(ticket=ticket)
        ok1, user_id1 = await authenticate_websocket(first_ws, close_code=1008)
        assert ok1 is True
        assert user_id1 == 1
        first_ws.close.assert_not_awaited()

        second_ws = _make_ws(ticket=ticket)
        ok2, user_id2 = await authenticate_websocket(second_ws, close_code=1008)

        assert ok2 is False
        assert user_id2 is None
        second_ws.close.assert_awaited_once()
        assert second_ws.close.await_args.kwargs["code"] == 1008
        reset_auth_engine()

    @pytest.mark.asyncio
    async def test_enabled_valid_ticket_passes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
        reset_auth_engine()
        _seed_active_user(tmp_path / "state.db")

        ticket = mint_ticket(user_id=1)
        ws = _make_ws(ticket=ticket)

        ok, user_id = await authenticate_websocket(ws, close_code=1008)

        assert ok is True
        assert user_id == 1
        ws.close.assert_not_awaited()
        reset_auth_engine()
