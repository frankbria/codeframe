"""
Tests for WebSocket router message handlers (cf-45.2).

Tests ensure that the WebSocket router correctly handles:
- Subscribe messages with validation and subscription tracking
- Unsubscribe messages with validation and cleanup
- Error handling for invalid messages
- Edge cases like missing or invalid project_id
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient

from codeframe.ui.routers.websocket import router, websocket_endpoint
from codeframe.ui.server import app


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_manager():
    """Create a mock ConnectionManager."""
    manager = MagicMock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    manager.subscription_manager = MagicMock()
    manager.subscription_manager.subscribe = AsyncMock()
    manager.subscription_manager.unsubscribe = AsyncMock()
    return manager


class TestSubscribeHandler:
    """Tests for subscribe message handler."""

    @pytest.mark.asyncio
    async def test_subscribe_valid_project_id(self, mock_websocket, mock_manager):
        """Test subscribe with valid project_id."""
        # Setup: Subscribe then disconnect
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify subscription was tracked
        mock_manager.subscription_manager.subscribe.assert_called_once_with(mock_websocket, 1)

        # Verify confirmation was sent
        assert mock_websocket.send_json.call_count >= 1
        confirm_call = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "subscribed"
        ]
        assert len(confirm_call) > 0
        assert confirm_call[0][0][0]["project_id"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_missing_project_id(self, mock_websocket, mock_manager):
        """Test subscribe with missing project_id."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call subscribe
        mock_manager.subscription_manager.subscribe.assert_not_called()

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "project_id" in error_calls[0][0][0].get("error", "").lower()

    @pytest.mark.asyncio
    async def test_subscribe_invalid_project_id_type_string(self, mock_websocket, mock_manager):
        """Test subscribe with string project_id (invalid type)."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": "not_an_int"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call subscribe
        mock_manager.subscription_manager.subscribe.assert_not_called()

        # Should send error about type
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "integer" in error_calls[0][0][0].get("error", "").lower()

    @pytest.mark.asyncio
    async def test_subscribe_invalid_project_id_type_float(self, mock_websocket, mock_manager):
        """Test subscribe with float project_id (invalid type)."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1.5}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call subscribe (float is not int)
        mock_manager.subscription_manager.subscribe.assert_not_called()

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_subscribe_negative_project_id(self, mock_websocket, mock_manager):
        """Test subscribe with negative project_id."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": -1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call subscribe
        mock_manager.subscription_manager.subscribe.assert_not_called()

        # Should send error about positive integer
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "positive" in error_calls[0][0][0].get("error", "").lower()

    @pytest.mark.asyncio
    async def test_subscribe_zero_project_id(self, mock_websocket, mock_manager):
        """Test subscribe with zero project_id."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 0}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call subscribe
        mock_manager.subscription_manager.subscribe.assert_not_called()

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_subscribe_exception_handling(self, mock_websocket, mock_manager):
        """Test subscribe handles exceptions gracefully."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        # Make subscribe raise an exception
        mock_manager.subscription_manager.subscribe.side_effect = Exception("DB error")

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should send error response
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "subscribe" in error_calls[0][0][0].get("error", "").lower()

    @pytest.mark.asyncio
    async def test_subscribe_multiple_projects(self, mock_websocket, mock_manager):
        """Test subscribing to multiple projects."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            json.dumps({"type": "subscribe", "project_id": 2}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should call subscribe twice
        assert mock_manager.subscription_manager.subscribe.call_count == 2

        # Verify calls
        calls = mock_manager.subscription_manager.subscribe.call_args_list
        assert calls[0][0][1] == 1
        assert calls[1][0][1] == 2


class TestUnsubscribeHandler:
    """Tests for unsubscribe message handler."""

    @pytest.mark.asyncio
    async def test_unsubscribe_valid_project_id(self, mock_websocket, mock_manager):
        """Test unsubscribe with valid project_id."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify unsubscription was tracked
        mock_manager.subscription_manager.unsubscribe.assert_called_once_with(mock_websocket, 1)

        # Verify confirmation was sent
        confirm_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "unsubscribed"
        ]
        assert len(confirm_calls) > 0
        assert confirm_calls[0][0][0]["project_id"] == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_missing_project_id(self, mock_websocket, mock_manager):
        """Test unsubscribe with missing project_id."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call unsubscribe
        mock_manager.subscription_manager.unsubscribe.assert_not_called()

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "project_id" in error_calls[0][0][0].get("error", "").lower()

    @pytest.mark.asyncio
    async def test_unsubscribe_invalid_project_id_type(self, mock_websocket, mock_manager):
        """Test unsubscribe with string project_id (invalid type)."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe", "project_id": "not_an_int"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call unsubscribe
        mock_manager.subscription_manager.unsubscribe.assert_not_called()

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_unsubscribe_negative_project_id(self, mock_websocket, mock_manager):
        """Test unsubscribe with negative project_id."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe", "project_id": -1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should NOT call unsubscribe
        mock_manager.subscription_manager.unsubscribe.assert_not_called()

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0

    @pytest.mark.asyncio
    async def test_unsubscribe_exception_handling(self, mock_websocket, mock_manager):
        """Test unsubscribe handles exceptions gracefully."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        # Make unsubscribe raise an exception
        mock_manager.subscription_manager.unsubscribe.side_effect = Exception("DB error")

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should send error response
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "unsubscribe" in error_calls[0][0][0].get("error", "").lower()

    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self, mock_websocket, mock_manager):
        """Test unsubscribe from project not subscribed to."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "unsubscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        # unsubscribe should still succeed (idempotent)
        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should call unsubscribe
        mock_manager.subscription_manager.unsubscribe.assert_called_once_with(mock_websocket, 1)

        # Should send confirmation (even if wasn't subscribed)
        confirm_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "unsubscribed"
        ]
        assert len(confirm_calls) > 0


class TestSubscribeUnsubscribeSequence:
    """Tests for complex subscription sequences."""

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_sequence(self, mock_websocket, mock_manager):
        """Test subscribe then unsubscribe sequence."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            json.dumps({"type": "unsubscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify both calls were made
        mock_manager.subscription_manager.subscribe.assert_called_once_with(mock_websocket, 1)
        mock_manager.subscription_manager.unsubscribe.assert_called_once_with(mock_websocket, 1)

    @pytest.mark.asyncio
    async def test_ping_subscribe_ping_sequence(self, mock_websocket, mock_manager):
        """Test ping, subscribe, then ping again."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "ping"}),
            json.dumps({"type": "subscribe", "project_id": 1}),
            json.dumps({"type": "ping"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify subscribe was called
        mock_manager.subscription_manager.subscribe.assert_called_once_with(mock_websocket, 1)

        # Verify pongs were sent
        pong_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "pong"
        ]
        assert len(pong_calls) == 2

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_messages(self, mock_websocket, mock_manager):
        """Test handling mix of valid and invalid messages."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            json.dumps({"type": "subscribe"}),  # Invalid - missing project_id
            json.dumps({"type": "subscribe", "project_id": 2}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should call subscribe twice (for valid messages)
        assert mock_manager.subscription_manager.subscribe.call_count == 2

        # Verify the calls
        calls = mock_manager.subscription_manager.subscribe.call_args_list
        assert calls[0][0][1] == 1
        assert calls[1][0][1] == 2

        # Should have sent one error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) == 1


class TestDisconnectCleanup:
    """Tests for disconnect cleanup behavior."""

    @pytest.mark.asyncio
    async def test_disconnect_calls_cleanup(self, mock_websocket, mock_manager):
        """Test that disconnect calls subscription cleanup."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify disconnect was called
        mock_manager.disconnect.assert_called_once_with(mock_websocket)

    @pytest.mark.asyncio
    async def test_disconnect_on_exception(self, mock_websocket, mock_manager):
        """Test that disconnect is called even on exception."""
        mock_websocket.receive_text.side_effect = Exception("Connection error")

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify disconnect was called despite exception
        mock_manager.disconnect.assert_called_once_with(mock_websocket)

    @pytest.mark.asyncio
    async def test_websocket_close_on_disconnect(self, mock_websocket, mock_manager):
        """Test that WebSocket is closed on disconnect."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "ping"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Verify close was called
        mock_websocket.close.assert_called_once()


class TestMalformedJsonHandling:
    """Tests for malformed JSON handling."""

    @pytest.mark.asyncio
    async def test_malformed_json_error_response(self, mock_websocket, mock_manager):
        """Test malformed JSON sends error response."""
        mock_websocket.receive_text.side_effect = [
            '{"type": "subscribe" invalid json}',
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should send error
        error_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "error"
        ]
        assert len(error_calls) > 0
        assert "JSON" in error_calls[0][0][0].get("error", "")

    @pytest.mark.asyncio
    async def test_continues_after_malformed_json(self, mock_websocket, mock_manager):
        """Test connection continues after malformed JSON."""
        mock_websocket.receive_text.side_effect = [
            '{"type": "subscribe" invalid json}',
            json.dumps({"type": "ping"}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Should send pong response (shows connection continued)
        pong_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "pong"
        ]
        assert len(pong_calls) > 0


class TestDocstringCompliance:
    """Tests to verify WebSocket endpoint follows documented behavior."""

    @pytest.mark.asyncio
    async def test_documented_message_types_supported(self, mock_websocket, mock_manager):
        """Test that all documented message types are handled."""
        # From docstring: ping, subscribe
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "ping"}),
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket)

        # Both should be handled without error
        assert mock_manager.subscription_manager.subscribe.called
        pong_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "pong"
        ]
        assert len(pong_calls) > 0


class TestWebSocketHealthEndpoint:
    """Tests for /ws/health HTTP endpoint."""

    def test_websocket_health_endpoint_returns_ready_status(self):
        """Test /ws/health endpoint returns ready status."""
        # Create test client with the router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app) as client:
            response = client.get("/ws/health")

            assert response.status_code == 200
            assert response.json() == {"status": "ready"}

    def test_websocket_health_endpoint_is_http_get(self):
        """Test /ws/health endpoint only accepts GET requests."""
        # Create test client with the router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app) as client:
            # GET should work
            response = client.get("/ws/health")
            assert response.status_code == 200

            # POST should fail
            response = client.post("/ws/health")
            assert response.status_code == 405  # Method Not Allowed

    def test_websocket_health_endpoint_content_type(self):
        """Test /ws/health endpoint returns JSON content type."""
        # Create test client with the router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app) as client:
            response = client.get("/ws/health")

            assert response.status_code == 200
            assert "application/json" in response.headers["content-type"]

    def test_websocket_health_endpoint_is_fast(self):
        """Test /ws/health endpoint responds quickly (<100ms)."""
        import time
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)

        with TestClient(test_app) as client:
            start_time = time.time()
            response = client.get("/ws/health")
            elapsed_time = time.time() - start_time

            assert response.status_code == 200
            assert elapsed_time < 0.1  # Should respond in less than 100ms
