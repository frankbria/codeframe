"""Integration tests for /ws/sessions/{session_id}/chat WebSocket endpoint.

Uses FastAPI's TestClient WebSocket support (starlette.testclient).
Tests are class-scoped to reuse server setup, with per-test DB cleanup
via the autouse fixture in conftest.py.

Note: The autouse `clean_database_between_tests` fixture clears most tables
but not interactive_sessions — we rely on the class_temp_db_path isolation
and explicit teardown within tests where needed.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.api.conftest import create_test_jwt_token


pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_session(client: TestClient, workspace_path: str = "/tmp/ws-test") -> str:
    """Create an interactive session and return its ID."""
    resp = client.post(
        "/api/v2/sessions",
        json={"workspace_path": workspace_path, "agent_type": "claude"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _ws_url(session_id: str, token: str) -> str:
    return f"/ws/sessions/{session_id}/chat?token={token}"


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestSessionChatWSAuth:
    """WebSocket endpoint rejects unauthenticated and invalid connections."""

    def test_rejects_missing_token(self, api_client: TestClient):
        session_id = _create_session(api_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(f"/ws/sessions/{session_id}/chat") as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008

    def test_rejects_invalid_token(self, api_client: TestClient):
        session_id = _create_session(api_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(
                f"/ws/sessions/{session_id}/chat?token=not-a-valid-jwt"
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008

    def test_rejects_expired_token(self, api_client: TestClient):
        from datetime import datetime, timedelta, timezone
        from codeframe.auth.manager import SECRET
        import jwt as pyjwt

        payload = {
            "sub": "1",
            "aud": ["fastapi-users:auth"],
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = pyjwt.encode(payload, SECRET, algorithm="HS256")

        session_id = _create_session(api_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(
                f"/ws/sessions/{session_id}/chat?token={expired_token}"
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008

    def test_accepts_valid_token(self, api_client: TestClient):
        """A valid JWT connects successfully (responds to ping)."""
        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


# ---------------------------------------------------------------------------
# Session validation tests
# ---------------------------------------------------------------------------


class TestSessionChatWSSession:
    """WebSocket endpoint validates session state before accepting."""

    def test_rejects_nonexistent_session(self, api_client: TestClient):
        token = create_test_jwt_token(user_id=1)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(
                f"/ws/sessions/does-not-exist/chat?token={token}"
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 4008

    def test_rejects_ended_session(self, api_client: TestClient):
        session_id = _create_session(api_client)
        # End the session via REST API
        resp = api_client.delete(f"/api/v2/sessions/{session_id}")
        assert resp.status_code == 200

        token = create_test_jwt_token(user_id=1)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
                ws.receive_json()
        assert exc_info.value.code == 4008

    def test_accepts_active_session(self, api_client: TestClient):
        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestSessionChatWSProtocol:
    """WebSocket endpoint correctly handles the message protocol."""

    def test_ping_returns_pong(self, api_client: TestClient):
        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data == {"type": "pong"}

    def test_message_streams_text_delta_events(self, api_client: TestClient):
        """Sending a message triggers streaming text_delta events followed by done."""
        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)

        async def fake_adapter(session_id, user_message, token_queue, interrupt_event):
            await token_queue.put({"type": "text_delta", "content": "Hello"})
            await token_queue.put({"type": "text_delta", "content": " world"})
            await token_queue.put({"type": "cost_update", "cost_usd": 0.001, "input_tokens": 10, "output_tokens": 5})
            await token_queue.put({"type": "done"})

        with patch(
            "codeframe.ui.routers.session_chat_ws._run_streaming_adapter",
            side_effect=fake_adapter,
        ):
            with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
                ws.send_json({"type": "message", "content": "Hi"})

                events = []
                while True:
                    msg = ws.receive_json()
                    events.append(msg)
                    if msg["type"] == "done":
                        break

                types = [e["type"] for e in events]
                assert "text_delta" in types
                assert types[-1] == "done"

                # Verify individual text_delta events (not buffered)
                deltas = [e for e in events if e["type"] == "text_delta"]
                assert len(deltas) == 2
                assert deltas[0]["content"] == "Hello"
                assert deltas[1]["content"] == " world"

    def test_interrupt_stops_generation(self, api_client: TestClient):
        """Sending interrupt signals the adapter to stop early."""
        import asyncio

        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)

        async def slow_adapter(session_id, user_message, token_queue, interrupt_event):
            for i in range(10):
                if interrupt_event.is_set():
                    await token_queue.put({"type": "done"})
                    return
                await token_queue.put({"type": "text_delta", "content": f"chunk{i}"})
                await asyncio.sleep(0.01)
            await token_queue.put({"type": "done"})

        with patch(
            "codeframe.ui.routers.session_chat_ws._run_streaming_adapter",
            side_effect=slow_adapter,
        ):
            with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
                ws.send_json({"type": "message", "content": "stream lots"})
                # Receive first delta
                first = ws.receive_json()
                assert first["type"] == "text_delta"
                # Send interrupt
                ws.send_json({"type": "interrupt"})
                # Drain until done
                events = [first]
                for _ in range(20):
                    msg = ws.receive_json()
                    events.append(msg)
                    if msg["type"] == "done":
                        break

                types = [e["type"] for e in events]
                assert "done" in types
                # Should have fewer than all 10 chunks (interrupt fired)
                deltas = [e for e in events if e["type"] == "text_delta"]
                assert len(deltas) < 10

    def test_cost_update_written_to_db(self, api_client: TestClient):
        """Cost/token update from adapter is persisted to DB after each turn."""
        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)

        async def fake_adapter(session_id, user_message, token_queue, interrupt_event):
            await token_queue.put(
                {"type": "cost_update", "cost_usd": 0.005, "input_tokens": 100, "output_tokens": 50}
            )
            await token_queue.put({"type": "done"})

        with patch(
            "codeframe.ui.routers.session_chat_ws._run_streaming_adapter",
            side_effect=fake_adapter,
        ):
            with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
                ws.send_json({"type": "message", "content": "Hi"})
                while True:
                    msg = ws.receive_json()
                    if msg["type"] == "done":
                        break

        # Check DB was updated
        resp = api_client.get(f"/api/v2/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cost_usd"] == pytest.approx(0.005, abs=1e-6)
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


class TestSessionChatWSCleanup:
    """Disconnect cleans up SessionChatManager state — no leaked coroutines."""

    def test_disconnect_cleans_up_manager(self, api_client: TestClient):
        from codeframe.ui.routers.session_chat_ws import session_chat_manager

        session_id = _create_session(api_client)
        token = create_test_jwt_token(user_id=1)

        with api_client.websocket_connect(_ws_url(session_id, token)) as ws:
            ws.send_json({"type": "ping"})
            ws.receive_json()
            # At this point the session should be registered
            # (we just verify no error and disconnect cleans up)

        # After disconnect, session should not be in manager
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            q = loop.run_until_complete(session_chat_manager.get_token_queue(session_id))
            assert q is None, "Token queue should be cleaned up after disconnect"
        finally:
            loop.close()
