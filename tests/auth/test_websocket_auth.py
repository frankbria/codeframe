"""Tests for the shared WebSocket auth helper (issue #676).

`authenticate_websocket()` is the single source of truth that lets terminal and
session-chat WebSockets honor `CODEFRAME_AUTH_REQUIRED` the same way `require_auth()`
does for REST:
- auth disabled -> (True, None) without requiring a token (synthetic local principal)
- auth enabled  -> validate the ?token= JWT, or close the socket with the given code
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codeframe.auth.dependencies import authenticate_websocket

pytestmark = pytest.mark.v2


def _make_ws(token: str | None = None):
    """Minimal WebSocket double with query_params and an awaitable close()."""
    ws = MagicMock()
    ws.query_params = {} if token is None else {"token": token}
    ws.close = AsyncMock()
    return ws


class TestNoAuthMode:
    @pytest.mark.asyncio
    async def test_disabled_returns_local_principal_without_token(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        ws = _make_ws(token=None)

        ok, user_id = await authenticate_websocket(ws, close_code=4001)

        assert ok is True
        assert user_id is None
        ws.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_ignores_provided_token(self, monkeypatch):
        """A stale/garbage token must not break the connection in no-auth mode."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        ws = _make_ws(token="not-a-jwt")

        ok, user_id = await authenticate_websocket(ws, close_code=1008)

        assert ok is True
        assert user_id is None
        ws.close.assert_not_awaited()


class TestAuthEnabled:
    @pytest.mark.asyncio
    async def test_enabled_missing_token_closes(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        ws = _make_ws(token=None)

        ok, user_id = await authenticate_websocket(ws, close_code=4001)

        assert ok is False
        assert user_id is None
        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs["code"] == 4001

    @pytest.mark.asyncio
    async def test_enabled_invalid_token_closes_with_given_code(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        ws = _make_ws(token="not-a-jwt")

        ok, user_id = await authenticate_websocket(ws, close_code=1008)

        assert ok is False
        assert user_id is None
        ws.close.assert_awaited_once()
        assert ws.close.await_args.kwargs["code"] == 1008
