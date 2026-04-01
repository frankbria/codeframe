"""Unit tests for the terminal WebSocket router (terminal_ws.py).

These tests validate auth rejection, session lookup, and relay logic
using FastAPI's TestClient with mocked subprocess and database state.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.ui.routers.terminal_ws import router

pytestmark = pytest.mark.v2

# ---------------------------------------------------------------------------
# Minimal app fixture
# ---------------------------------------------------------------------------


def _make_app(session_data: dict | None = None, user_data=None):
    """Build a minimal FastAPI app with the terminal_ws router mounted."""
    app = FastAPI()
    app.include_router(router)

    # Attach a fake db to app state
    fake_db = MagicMock()
    fake_db.interactive_sessions.get.return_value = session_data
    app.state.db = fake_db

    return app


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestTerminalWsAuth:
    def test_missing_token_closes_4001(self):
        app = _make_app()
        client = TestClient(app)
        with pytest.raises(Exception):
            # No token → closed before accepting; TestClient raises on non-101
            with client.websocket_connect("/ws/sessions/s1/terminal"):
                pass

    def test_invalid_token_closes_4001(self):
        app = _make_app()
        client = TestClient(app)
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/sessions/s1/terminal?token=not-a-jwt"):
                pass

    def test_valid_token_session_not_found(self):
        """Valid token but session does not exist → closed."""
        app = _make_app(session_data=None)
        client = TestClient(app)

        # Patch auth to succeed and return user_id=1
        with patch(
            "codeframe.ui.routers.terminal_ws._authenticate_websocket",
            new=AsyncMock(return_value=1),
        ):
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/sessions/missing/terminal?token=x"):
                    pass

    def test_valid_token_ended_session(self):
        """Valid token but session is ended → closed."""
        app = _make_app(session_data={"state": "ended", "workspace_path": "/tmp"})
        client = TestClient(app)

        with patch(
            "codeframe.ui.routers.terminal_ws._authenticate_websocket",
            new=AsyncMock(return_value=1),
        ):
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/sessions/s1/terminal?token=x"):
                    pass

    def test_ownership_mismatch_closes(self):
        """Token user_id does not match session user_id → closed."""
        app = _make_app(
            session_data={"state": "active", "workspace_path": "/tmp", "user_id": 999}
        )
        client = TestClient(app)

        with patch(
            "codeframe.ui.routers.terminal_ws._authenticate_websocket",
            new=AsyncMock(return_value=1),
        ):
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/sessions/s1/terminal?token=x"):
                    pass


# ---------------------------------------------------------------------------
# Relay tests
# ---------------------------------------------------------------------------


class TestTerminalWsRelay:
    def _make_authenticated_app(self, workspace_path: str = "/tmp"):
        """App with auth mocked to succeed and a valid active session."""
        session = {
            "state": "active",
            "workspace_path": workspace_path,
            "user_id": 1,
        }
        app = _make_app(session_data=session)
        return app

    def test_connects_and_accepts(self):
        """With auth mocked and subprocess mocked, connection should be accepted."""
        app = self._make_authenticated_app()

        mock_proc = MagicMock()
        mock_proc.stdin = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.read = AsyncMock(return_value=b"$ ")
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "codeframe.ui.routers.terminal_ws._authenticate_websocket",
                new=AsyncMock(return_value=1),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=mock_proc),
            ),
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws/sessions/s1/terminal?token=x") as ws:
                # Connection was accepted; we can receive bytes
                # (mock stdout.read returns b"$ " then b"" to end relay)
                pass  # Just verify it connected without error

    def test_resize_message_does_not_crash(self):
        """Sending a resize JSON message should be silently ignored."""
        app = self._make_authenticated_app()

        stdout_chunks = [b"$ ", b""]
        chunk_iter = iter(stdout_chunks)

        mock_proc = MagicMock()
        mock_proc.stdin = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.read = AsyncMock(side_effect=lambda n: next(chunk_iter, b""))
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "codeframe.ui.routers.terminal_ws._authenticate_websocket",
                new=AsyncMock(return_value=1),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=mock_proc),
            ),
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws/sessions/s1/terminal?token=x") as ws:
                # Sending a resize message should not raise
                ws.send_text(json.dumps({"type": "resize", "cols": 80, "rows": 24}))
