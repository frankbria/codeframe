"""
Tests for proactive WebSocket messaging system.

This module tests the new proactive messaging features:
1. Connection acknowledgment after subscription
2. Periodic heartbeat messages every 30 seconds
3. Initial state snapshot delivery on subscription

These features transform the WebSocket from passive (only responding to client messages)
to proactive (actively sending connection health and state information).
"""

import asyncio
import json
import pytest
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocket, WebSocketDisconnect

from codeframe.ui.routers.websocket import websocket_endpoint, HEARTBEAT_INTERVAL_SECONDS


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection with authentication token."""
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    ws.query_params = MagicMock()
    ws.query_params.get = MagicMock(return_value="test-jwt-token")
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


@pytest.fixture
def mock_db():
    """Create a mock Database for project access and state queries."""
    db = MagicMock()
    db.user_has_project_access = MagicMock(return_value=True)
    # Mock project retrieval for initial state snapshot
    db.get_project = MagicMock(return_value={
        "id": 1,
        "name": "Test Project",
        "status": "active",
        "phase": "development",
    })
    return db


@pytest.fixture
def mock_jwt_auth():
    """Create mock JWT authentication that returns a valid user."""
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.is_active = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def mock_session_context():
        yield mock_session

    def mock_session_maker():
        return mock_session_context()

    return {
        "jwt_payload": {"sub": "1", "aud": "fastapi-users:auth"},
        "session_maker": mock_session_maker,
        "user": mock_user,
    }


@pytest.fixture(autouse=True)
def apply_jwt_auth_patches(mock_jwt_auth):
    """Auto-applied fixture that patches JWT auth for all WebSocket tests."""
    with patch(
        "codeframe.ui.routers.websocket.pyjwt.decode",
        return_value=mock_jwt_auth["jwt_payload"],
    ), patch(
        "codeframe.ui.routers.websocket.get_async_session_maker",
        return_value=mock_jwt_auth["session_maker"],
    ):
        yield


class TestConnectionAcknowledgment:
    """Tests for connection acknowledgment message sent after subscription."""

    @pytest.mark.asyncio
    async def test_sends_connection_ack_after_subscription(self, mock_websocket, mock_manager, mock_db):
        """Test that connection_ack is sent immediately after successful subscription."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Find connection_ack message in sent messages
        ack_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "connection_ack"
        ]
        assert len(ack_calls) >= 1, "Should send connection_ack after subscription"

        ack_message = ack_calls[0][0][0]
        assert ack_message["project_id"] == 1
        assert "timestamp" in ack_message
        assert ack_message["message"] == "Connected to real-time updates"

    @pytest.mark.asyncio
    async def test_connection_ack_sent_after_subscribed_message(self, mock_websocket, mock_manager, mock_db):
        """Test that connection_ack is sent AFTER the subscribed confirmation."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Get all message types in order
        message_types = [
            call[0][0].get("type") for call in mock_websocket.send_json.call_args_list
        ]

        # Find positions
        subscribed_pos = message_types.index("subscribed") if "subscribed" in message_types else -1
        ack_pos = message_types.index("connection_ack") if "connection_ack" in message_types else -1

        assert subscribed_pos >= 0, "Should send subscribed message"
        assert ack_pos >= 0, "Should send connection_ack message"
        assert ack_pos > subscribed_pos, "connection_ack should come after subscribed"

    @pytest.mark.asyncio
    async def test_connection_ack_has_valid_timestamp(self, mock_websocket, mock_manager, mock_db):
        """Test that connection_ack timestamp is a valid ISO8601 format."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        ack_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "connection_ack"
        ]

        timestamp = ack_calls[0][0][0]["timestamp"]
        # Should be parseable as ISO8601
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert parsed is not None

    @pytest.mark.asyncio
    async def test_no_connection_ack_on_failed_subscription(self, mock_websocket, mock_manager, mock_db):
        """Test that connection_ack is NOT sent when subscription fails."""
        mock_db.user_has_project_access = MagicMock(return_value=False)

        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Should NOT have connection_ack
        ack_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "connection_ack"
        ]
        assert len(ack_calls) == 0, "Should not send connection_ack when access denied"


class TestHeartbeatMechanism:
    """Tests for periodic heartbeat message functionality."""

    def test_heartbeat_interval_constant_exists(self):
        """Test that HEARTBEAT_INTERVAL_SECONDS constant is defined."""
        assert HEARTBEAT_INTERVAL_SECONDS == 30

    @pytest.mark.asyncio
    async def test_heartbeat_task_starts_after_subscription(self, mock_websocket, mock_manager, mock_db):
        """Test that heartbeat task is started after successful subscription."""
        # Use a short timeout to verify heartbeat task gets created
        received_messages = []
        call_count = 0

        async def receive_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "subscribe", "project_id": 1})
            # Wait a bit to allow heartbeat task to start, then disconnect
            await asyncio.sleep(0.1)
            raise WebSocketDisconnect()

        mock_websocket.receive_text = receive_with_timeout

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            with patch("codeframe.ui.routers.websocket.HEARTBEAT_INTERVAL_SECONDS", 0.05):
                # Start the endpoint in a task so we can cancel it
                task = asyncio.create_task(websocket_endpoint(mock_websocket, db=mock_db))
                try:
                    await asyncio.wait_for(task, timeout=0.3)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        # Check if heartbeat was sent
        heartbeat_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "heartbeat"
        ]
        # With 0.05 second interval and ~0.2 seconds of waiting, should have at least 1 heartbeat
        assert len(heartbeat_calls) >= 1, "Should send at least one heartbeat message"

    @pytest.mark.asyncio
    async def test_heartbeat_contains_required_fields(self, mock_websocket, mock_manager, mock_db):
        """Test that heartbeat messages contain required fields."""
        call_count = 0

        async def receive_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "subscribe", "project_id": 1})
            await asyncio.sleep(0.1)
            raise WebSocketDisconnect()

        mock_websocket.receive_text = receive_with_timeout

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            with patch("codeframe.ui.routers.websocket.HEARTBEAT_INTERVAL_SECONDS", 0.05):
                task = asyncio.create_task(websocket_endpoint(mock_websocket, db=mock_db))
                try:
                    await asyncio.wait_for(task, timeout=0.3)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        heartbeat_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "heartbeat"
        ]

        if len(heartbeat_calls) > 0:
            heartbeat = heartbeat_calls[0][0][0]
            assert heartbeat["type"] == "heartbeat"
            assert heartbeat["project_id"] == 1
            assert "timestamp" in heartbeat

    @pytest.mark.asyncio
    async def test_heartbeat_task_cancelled_on_disconnect(self, mock_websocket, mock_manager, mock_db):
        """Test that heartbeat task is properly cancelled when client disconnects."""
        call_count = 0

        async def receive_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "subscribe", "project_id": 1})
            await asyncio.sleep(0.05)
            raise WebSocketDisconnect()

        mock_websocket.receive_text = receive_with_timeout

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            with patch("codeframe.ui.routers.websocket.HEARTBEAT_INTERVAL_SECONDS", 0.1):
                # This should complete without hanging
                await asyncio.wait_for(
                    websocket_endpoint(mock_websocket, db=mock_db),
                    timeout=1.0
                )

        # If we get here without timeout, the heartbeat task was properly cancelled
        mock_manager.disconnect.assert_called_once()


class TestInitialStateSnapshot:
    """Tests for initial state snapshot sent on subscription."""

    @pytest.mark.asyncio
    async def test_sends_project_status_after_subscription(self, mock_websocket, mock_manager, mock_db):
        """Test that project_status is sent after successful subscription."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Find project_status message
        status_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "project_status"
        ]
        assert len(status_calls) >= 1, "Should send project_status after subscription"

        status_message = status_calls[0][0][0]
        assert status_message["project_id"] == 1
        assert "status" in status_message
        assert "phase" in status_message

    @pytest.mark.asyncio
    async def test_project_status_contains_project_data(self, mock_websocket, mock_manager, mock_db):
        """Test that project_status contains data from database."""
        mock_db.get_project = MagicMock(return_value={
            "id": 1,
            "name": "My Project",
            "status": "planning",
            "phase": "discovery",
        })

        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        status_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "project_status"
        ]

        status_message = status_calls[0][0][0]
        assert status_message["status"] == "planning"
        assert status_message["phase"] == "discovery"

    @pytest.mark.asyncio
    async def test_project_status_handles_missing_project(self, mock_websocket, mock_manager, mock_db):
        """Test graceful handling when project doesn't exist."""
        mock_db.get_project = MagicMock(return_value=None)

        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            # Should not raise exception
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Subscription should still succeed
        subscribed_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "subscribed"
        ]
        assert len(subscribed_calls) >= 1

    @pytest.mark.asyncio
    async def test_project_status_handles_db_exception(self, mock_websocket, mock_manager, mock_db):
        """Test graceful handling when database query fails."""
        mock_db.get_project = MagicMock(side_effect=Exception("DB error"))

        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            # Should not raise exception
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Subscription should still succeed even if project query fails
        subscribed_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "subscribed"
        ]
        assert len(subscribed_calls) >= 1


class TestMessageSequence:
    """Tests for correct ordering of proactive messages."""

    @pytest.mark.asyncio
    async def test_message_sequence_on_subscription(self, mock_websocket, mock_manager, mock_db):
        """Test the correct sequence: subscribed → connection_ack → project_status."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Get message types in order
        message_types = [
            call[0][0].get("type") for call in mock_websocket.send_json.call_args_list
        ]

        # Find positions
        subscribed_pos = message_types.index("subscribed") if "subscribed" in message_types else -1
        ack_pos = message_types.index("connection_ack") if "connection_ack" in message_types else -1
        status_pos = message_types.index("project_status") if "project_status" in message_types else -1

        # Verify sequence
        assert subscribed_pos >= 0, "Must have subscribed message"
        assert ack_pos > subscribed_pos, "connection_ack should follow subscribed"
        assert status_pos > subscribed_pos, "project_status should follow subscribed"

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_each_get_messages(self, mock_websocket, mock_manager, mock_db):
        """Test that each subscription gets its own set of proactive messages."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "subscribe", "project_id": 1}),
            json.dumps({"type": "subscribe", "project_id": 2}),
            WebSocketDisconnect(),
        ]

        with patch("codeframe.ui.routers.websocket.manager", mock_manager):
            await websocket_endpoint(mock_websocket, db=mock_db)

        # Count connection_ack messages
        ack_calls = [
            call for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "connection_ack"
        ]
        assert len(ack_calls) == 2, "Each subscription should get connection_ack"

        # Verify different project_ids
        project_ids = [call[0][0]["project_id"] for call in ack_calls]
        assert 1 in project_ids
        assert 2 in project_ids


class TestHeartbeatBroadcastHelper:
    """Tests for the broadcast_heartbeat helper function."""

    @pytest.mark.asyncio
    async def test_broadcast_heartbeat_function_exists(self):
        """Test that broadcast_heartbeat function is exported."""
        from codeframe.ui.websocket_broadcasts import broadcast_heartbeat
        assert callable(broadcast_heartbeat)

    @pytest.mark.asyncio
    async def test_broadcast_heartbeat_message_format(self):
        """Test that broadcast_heartbeat sends correct message format."""
        from codeframe.ui.websocket_broadcasts import broadcast_heartbeat

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock()

        await broadcast_heartbeat(mock_manager, project_id=1)

        mock_manager.broadcast.assert_called_once()
        message = mock_manager.broadcast.call_args[0][0]

        assert message["type"] == "heartbeat"
        assert message["project_id"] == 1
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_broadcast_heartbeat_handles_exception(self):
        """Test that broadcast_heartbeat handles broadcast exceptions gracefully."""
        from codeframe.ui.websocket_broadcasts import broadcast_heartbeat

        mock_manager = MagicMock()
        mock_manager.broadcast = AsyncMock(side_effect=Exception("Broadcast failed"))

        # Should not raise
        await broadcast_heartbeat(mock_manager, project_id=1)
