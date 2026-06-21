"""Unit tests for the terminal WebSocket router (terminal_ws.py).

These tests validate auth rejection, session lookup, and relay logic
using FastAPI's TestClient with mocked subprocess and database state.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
    def test_missing_token_closes_4001(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        app = _make_app()
        client = TestClient(app)
        with pytest.raises(Exception):
            # No token → closed before accepting; TestClient raises on non-101
            with client.websocket_connect("/ws/sessions/s1/terminal"):
                pass

    def test_invalid_token_closes_4001(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
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
            new=AsyncMock(return_value=(True, 1)),
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
            new=AsyncMock(return_value=(True, 1)),
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
            new=AsyncMock(return_value=(True, 1)),
        ):
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/sessions/s1/terminal?token=x"):
                    pass


# ---------------------------------------------------------------------------
# Relay tests
# ---------------------------------------------------------------------------


class TestTerminalWsRevalidation:
    """TOCTOU: the stored path is re-checked against the allowlist at connect (#704)."""

    def test_symlink_escape_rejected(self, tmp_path, monkeypatch):
        """A dir swapped for a symlink pointing outside the root → WS closes."""
        base = tmp_path / "allowed"
        base.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        swapped = base / "proj"
        swapped.symlink_to(outside)  # tenant replaced proj -> outside after create
        monkeypatch.setenv("WORKSPACE_ROOT", str(base))
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")

        app = _make_app(
            session_data={
                "state": "active",
                "workspace_path": str(swapped),
                "user_id": 1,
            }
        )
        client = TestClient(app)
        with patch(
            "codeframe.ui.routers.terminal_ws._authenticate_websocket",
            new=AsyncMock(return_value=(True, 1)),
        ):
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/ws/sessions/s1/terminal?token=x"):
                    pass
            # 4008 == revalidation reject (the session DOES have a workspace_path,
            # so this code can only come from the allowlist re-check, not "no cwd").
            assert exc.value.code == 4008

    def test_path_inside_root_still_connects(self, tmp_path, monkeypatch):
        """Revalidation does not break a legit path inside the root."""
        base = tmp_path / "allowed"
        proj = base / "proj"
        proj.mkdir(parents=True)
        monkeypatch.setenv("WORKSPACE_ROOT", str(base))
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")

        app = _make_app(
            session_data={"state": "active", "workspace_path": str(proj), "user_id": 1}
        )
        mock_proc = MagicMock()
        mock_proc.stdin = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.read = AsyncMock(return_value=b"$ ")
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch(
                "codeframe.ui.routers.terminal_ws._authenticate_websocket",
                new=AsyncMock(return_value=(True, 1)),
            ),
            patch(
                "asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=mock_proc),
            ) as spawn,
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws/sessions/s1/terminal?token=x"):
                pass
        # Shell spawned with the resolved, allowlisted path.
        assert spawn.call_args.kwargs["cwd"] == str(proj.resolve())


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
                new=AsyncMock(return_value=(True, 1)),
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

    def test_no_auth_mode_connects_without_token(self, monkeypatch):
        """With CODEFRAME_AUTH_REQUIRED=false, the terminal WS connects with no token."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        # Session has a user_id, but in no-auth mode (user_id=None) ownership is skipped.
        app = _make_app(
            session_data={"state": "active", "workspace_path": "/tmp", "user_id": 999}
        )

        mock_proc = MagicMock()
        mock_proc.stdin = AsyncMock()
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.read = AsyncMock(return_value=b"$ ")
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ):
            client = TestClient(app)
            # No ?token= and no auth patch — real auth helper must admit it.
            with client.websocket_connect("/ws/sessions/s1/terminal") as ws:
                pass  # Connected without error → no-auth path works

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
                new=AsyncMock(return_value=(True, 1)),
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
