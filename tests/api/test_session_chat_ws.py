"""Integration tests for /ws/sessions/{session_id}/chat WebSocket endpoint.

Uses FastAPI's TestClient WebSocket support (starlette.testclient).
Tests are class-scoped to reuse server setup, with per-test DB cleanup
via the autouse fixture in conftest.py.

Note: The autouse `clean_database_between_tests` fixture clears most tables
but not interactive_sessions — we rely on the class_temp_db_path isolation
and explicit teardown within tests where needed.
"""

import os

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from codeframe.auth.stream_tickets import mint_ticket, reset_stream_tickets
import codeframe.auth.stream_tickets as stream_tickets


pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_session(client: TestClient, workspace_path: str | None = None) -> str:
    """Create an interactive session and return its ID.

    Defaults to a path under the test ``WORKSPACE_ROOT`` (set by the api
    conftest) so it clears the workspace allowlist (#655).
    """
    if workspace_path is None:
        workspace_path = os.path.join(os.environ.get("WORKSPACE_ROOT", "/tmp"), "ws-test")
    resp = client.post(
        "/api/v2/sessions",
        json={"workspace_path": workspace_path, "agent_type": "claude"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _ws_url(session_id: str, ticket: str) -> str:
    return f"/ws/sessions/{session_id}/chat?ticket={ticket}"


@pytest.fixture(autouse=True)
def _reset_tickets():
    reset_stream_tickets()
    yield
    reset_stream_tickets()


def test_chat_ws_ownership_mismatch_closes():
    """A session owned by another user is refused (issue #655)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from codeframe.ui.routers.session_chat_ws import router

    app = FastAPI()
    app.include_router(router)
    fake_db = MagicMock()
    fake_db.interactive_sessions.get.return_value = {
        "state": "active",
        "workspace_path": "/tmp",
        "user_id": 999,
    }
    app.state.db = fake_db
    client = TestClient(app)

    with patch(
        "codeframe.ui.routers.session_chat_ws._authenticate_websocket",
        new=AsyncMock(return_value=(True, 1)),
    ):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/sessions/s1/chat?ticket=x"):
                pass
        assert exc.value.code == 1008


def test_chat_ws_symlink_escape_rejected(tmp_path, monkeypatch):
    """TOCTOU: stored path swapped to a symlink outside the root → WS closes (#704)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from codeframe.ui.routers.session_chat_ws import router

    base = tmp_path / "allowed"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    swapped = base / "proj"
    swapped.symlink_to(outside)
    monkeypatch.setenv("WORKSPACE_ROOT", str(base))
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")

    app = FastAPI()
    app.include_router(router)
    fake_db = MagicMock()
    fake_db.interactive_sessions.get.return_value = {
        "state": "active",
        "workspace_path": str(swapped),
        "user_id": 1,
    }
    app.state.db = fake_db
    client = TestClient(app)

    with patch(
        "codeframe.ui.routers.session_chat_ws._authenticate_websocket",
        new=AsyncMock(return_value=(True, 1)),
    ):
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/sessions/s1/chat?ticket=x"):
                pass
        assert exc.value.code == 1008


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestSessionChatWSAuth:
    """WebSocket endpoint rejects unauthenticated and invalid connections."""

    def test_rejects_missing_ticket(self, api_client: TestClient, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        session_id = _create_session(api_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(f"/ws/sessions/{session_id}/chat") as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008

    def test_rejects_unknown_ticket(self, api_client: TestClient, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        session_id = _create_session(api_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(
                f"/ws/sessions/{session_id}/chat?ticket=not-a-real-ticket"
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008

    def test_rejects_expired_ticket(self, api_client: TestClient, monkeypatch):
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        current = [1_000.0]
        monkeypatch.setattr(stream_tickets, "_now", lambda: current[0])

        ticket = mint_ticket(user_id=1)
        current[0] += stream_tickets.TICKET_TTL_SECONDS + 1

        session_id = _create_session(api_client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008

    def test_no_auth_mode_connects_without_ticket(self, api_client: TestClient, monkeypatch):
        """With CODEFRAME_AUTH_REQUIRED=false, the chat WS connects with no ticket (matches REST)."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        session_id = _create_session(api_client)
        with api_client.websocket_connect(f"/ws/sessions/{session_id}/chat") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_accepts_valid_ticket(self, api_client: TestClient, monkeypatch):
        """A valid, freshly minted ticket connects successfully (responds to ping)."""
        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
        session_id = _create_session(api_client)
        ticket = mint_ticket(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


# ---------------------------------------------------------------------------
# Session validation tests
# ---------------------------------------------------------------------------


class TestSessionChatWSSession:
    """WebSocket endpoint validates session state before accepting."""

    def test_rejects_nonexistent_session(self, api_client: TestClient):
        ticket = mint_ticket(user_id=1)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(
                f"/ws/sessions/does-not-exist/chat?ticket={ticket}"
            ) as ws:
                ws.receive_json()
        assert exc_info.value.code == 4008

    def test_rejects_ended_session(self, api_client: TestClient):
        session_id = _create_session(api_client)
        # End the session via REST API
        resp = api_client.delete(f"/api/v2/sessions/{session_id}")
        assert resp.status_code == 200

        ticket = mint_ticket(user_id=1)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
                ws.receive_json()
        assert exc_info.value.code == 4008

    def test_accepts_active_session(self, api_client: TestClient):
        session_id = _create_session(api_client)
        ticket = mint_ticket(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_rejects_second_concurrent_connection(self, api_client: TestClient):
        """A second socket for the same session_id is refused with 4009 (#759).

        The first connection's interrupt event / token queue must NOT be
        overwritten — the second is rejected instead, leaving tab 1 intact.
        """
        session_id = _create_session(api_client)
        ticket1 = mint_ticket(user_id=1)
        ticket2 = mint_ticket(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, ticket1)) as ws1:
            ws1.send_json({"type": "ping"})
            assert ws1.receive_json()["type"] == "pong"

            # Second connection to the same session is rejected with 4009.
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with api_client.websocket_connect(_ws_url(session_id, ticket2)) as ws2:
                    ws2.receive_json()
            assert exc_info.value.code == 4009

            # First connection is unaffected and still responsive.
            ws1.send_json({"type": "ping"})
            assert ws1.receive_json()["type"] == "pong"


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestSessionChatWSProtocol:
    """WebSocket endpoint correctly handles the message protocol."""

    def test_ping_returns_pong(self, api_client: TestClient):
        session_id = _create_session(api_client)
        ticket = mint_ticket(user_id=1)
        with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data == {"type": "pong"}

    def test_message_streams_text_delta_events(self, api_client: TestClient):
        """Sending a message triggers streaming text_delta events followed by done."""
        session_id = _create_session(api_client)
        ticket = mint_ticket(user_id=1)

        async def fake_adapter(session_id, user_message, token_queue, interrupt_event, db_repo, workspace_path, agent_type=None, model=None):
            await token_queue.put({"type": "text_delta", "content": "Hello"})
            await token_queue.put({"type": "text_delta", "content": " world"})
            await token_queue.put({"type": "cost_update", "cost_usd": 0.001, "input_tokens": 10, "output_tokens": 5})
            await token_queue.put({"type": "done"})

        with patch(
            "codeframe.ui.routers.session_chat_ws._run_streaming_adapter",
            side_effect=fake_adapter,
        ):
            with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
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
        ticket = mint_ticket(user_id=1)

        async def slow_adapter(session_id, user_message, token_queue, interrupt_event, db_repo, workspace_path, agent_type=None, model=None):
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
            with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
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
        ticket = mint_ticket(user_id=1)

        async def fake_adapter(session_id, user_message, token_queue, interrupt_event, db_repo, workspace_path, agent_type=None, model=None):
            await token_queue.put(
                {"type": "cost_update", "cost_usd": 0.005, "input_tokens": 100, "output_tokens": 50}
            )
            await token_queue.put({"type": "done"})

        with patch(
            "codeframe.ui.routers.session_chat_ws._run_streaming_adapter",
            side_effect=fake_adapter,
        ):
            with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
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
# Provider / model resolution (#764)
# ---------------------------------------------------------------------------


class TestRunStreamingAdapterResolution:
    """`_run_streaming_adapter` resolves provider + model from the session (#764)."""

    @staticmethod
    def _fake_adapter_factory(captured: dict):
        """Return a StreamingChatAdapter stand-in that records ctor kwargs."""

        class _FakeAdapter:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            async def send_message(self, content, history, interrupt_event):
                return
                yield  # pragma: no cover - makes this an async generator

        return _FakeAdapter

    def _run(self, agent_type, model):
        """Drive _run_streaming_adapter once, returning (ctor_kwargs, events)."""
        import asyncio
        from unittest.mock import MagicMock, patch

        import codeframe.ui.routers.session_chat_ws as mod

        captured: dict = {}
        events: list = []

        async def drive():
            q = asyncio.Queue()
            await mod._run_streaming_adapter(
                "sess-1", "hi", q, asyncio.Event(), MagicMock(), object(),
                agent_type, model,
            )
            while not q.empty():
                events.append(q.get_nowait())

        with patch.object(mod, "StreamingChatAdapter", self._fake_adapter_factory(captured)), \
                patch("codeframe.adapters.llm.get_provider") as get_provider:
            get_provider.return_value = MagicMock(name="provider")
            asyncio.run(drive())
            self._last_get_provider = get_provider
        return captured, events

    def test_claude_session_resolves_anthropic_and_honors_model(self):
        captured, events = self._run("claude", "claude-opus-4-6")
        self._last_get_provider.assert_called_once_with("anthropic")
        assert captured["model"] == "claude-opus-4-6"
        assert captured["provider"] is self._last_get_provider.return_value
        assert not any(e["type"] == "error" for e in events)

    def test_missing_agent_type_defaults_to_claude(self):
        captured, events = self._run(None, None)
        self._last_get_provider.assert_called_once_with("anthropic")
        # No model override → adapter default used (no "model" kwarg passed).
        assert "model" not in captured
        assert not any(e["type"] == "error" for e in events)

    def test_unsupported_agent_type_errors_without_anthropic_fallback(self):
        captured, events = self._run("codex", "gpt-4o")
        # No provider constructed, no adapter built — a clear error is emitted.
        self._last_get_provider.assert_not_called()
        assert captured == {}
        assert events and events[0]["type"] == "error"
        assert "codex" in events[0]["message"]


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


class TestSessionChatWSCleanup:
    """Disconnect cleans up SessionChatManager state — no leaked coroutines."""

    def test_disconnect_cleans_up_manager(self, api_client: TestClient):
        from codeframe.ui.routers.session_chat_ws import session_chat_manager

        session_id = _create_session(api_client)
        ticket = mint_ticket(user_id=1)

        with api_client.websocket_connect(_ws_url(session_id, ticket)) as ws:
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
