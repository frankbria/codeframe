"""
Comprehensive tests for WebSocketSubscriptionManager and ConnectionManager.

Tests cover:
- WebSocketSubscriptionManager: subscription tracking, cleanup
- ConnectionManager: broadcast filtering, disconnect handling
- Edge cases and concurrency
- Thread safety with asyncio.Lock
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from codeframe.ui.shared import WebSocketSubscriptionManager, ConnectionManager


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_websockets():
    """Create multiple mock WebSocket connections."""
    return [MagicMock() for _ in range(3)]


@pytest.fixture
def subscription_manager():
    """Create a fresh WebSocketSubscriptionManager instance."""
    return WebSocketSubscriptionManager()


@pytest.fixture
def connection_manager():
    """Create a fresh ConnectionManager instance."""
    return ConnectionManager()


# ============================================================================
# WebSocketSubscriptionManager Tests
# ============================================================================


class TestWebSocketSubscriptionManagerSubscribe:
    """Tests for subscribe() method."""

    @pytest.mark.asyncio
    async def test_subscribe_single_project(self, subscription_manager, mock_websocket):
        """Subscribe websocket to one project."""
        project_id = 1
        await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert project_id in subscriptions
        assert len(subscriptions) == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple_projects(self, subscription_manager, mock_websocket):
        """Subscribe websocket to multiple projects."""
        project_ids = [1, 2, 3, 4, 5]

        for project_id in project_ids:
            await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert subscriptions == set(project_ids)
        assert len(subscriptions) == 5

    @pytest.mark.asyncio
    async def test_subscribe_duplicate(self, subscription_manager, mock_websocket):
        """Subscribing twice to same project is idempotent."""
        project_id = 1

        # Subscribe twice to the same project
        await subscription_manager.subscribe(mock_websocket, project_id)
        await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert subscriptions == {project_id}
        assert len(subscriptions) == 1

    @pytest.mark.asyncio
    async def test_subscribe_creates_set_for_new_websocket(
        self, subscription_manager, mock_websocket
    ):
        """Subscribing to new websocket creates set."""
        project_id = 1

        # Initially no subscriptions
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 0

        # After subscribe, set is created
        await subscription_manager.subscribe(mock_websocket, project_id)
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 1


class TestWebSocketSubscriptionManagerUnsubscribe:
    """Tests for unsubscribe() method."""

    @pytest.mark.asyncio
    async def test_unsubscribe_existing(self, subscription_manager, mock_websocket):
        """Unsubscribe from subscribed project."""
        project_id = 1
        await subscription_manager.subscribe(mock_websocket, project_id)

        # Verify subscribed
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert project_id in subscriptions

        # Unsubscribe
        await subscription_manager.unsubscribe(mock_websocket, project_id)

        # Verify unsubscribed
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert project_id not in subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_not_subscribed(self, subscription_manager, mock_websocket):
        """Unsubscribe from project not subscribed to."""
        project_id = 1

        # Unsubscribe without subscribing (should not raise)
        await subscription_manager.unsubscribe(mock_websocket, project_id)

        # Verify still not subscribed
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert project_id not in subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_cleans_up_empty_subscriptions(
        self, subscription_manager, mock_websocket
    ):
        """Unsubscribing from last project removes websocket entry."""
        project_id = 1

        await subscription_manager.subscribe(mock_websocket, project_id)
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 1

        # Unsubscribe from only project
        await subscription_manager.unsubscribe(mock_websocket, project_id)

        # Should be removed completely
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_keeps_other_subscriptions(
        self, subscription_manager, mock_websocket
    ):
        """Unsubscribing from one project keeps others intact."""
        projects = [1, 2, 3]

        # Subscribe to multiple projects
        for project_id in projects:
            await subscription_manager.subscribe(mock_websocket, project_id)

        # Unsubscribe from one
        await subscription_manager.unsubscribe(mock_websocket, 2)

        # Should still have others
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert 1 in subscriptions
        assert 2 not in subscriptions
        assert 3 in subscriptions


class TestWebSocketSubscriptionManagerGetSubscribers:
    """Tests for get_subscribers() method."""

    @pytest.mark.asyncio
    async def test_get_subscribers_none(self, subscription_manager, mock_websocket):
        """No subscribers for project with no subscriptions."""
        project_id = 1

        subscribers = await subscription_manager.get_subscribers(project_id)
        assert subscribers == []

    @pytest.mark.asyncio
    async def test_get_subscribers_single(
        self, subscription_manager, mock_websocket, mock_websockets
    ):
        """One subscriber for project."""
        project_id = 1

        await subscription_manager.subscribe(mock_websocket, project_id)

        subscribers = await subscription_manager.get_subscribers(project_id)
        assert len(subscribers) == 1
        assert mock_websocket in subscribers

    @pytest.mark.asyncio
    async def test_get_subscribers_multiple(self, subscription_manager, mock_websockets):
        """Multiple subscribers for same project."""
        project_id = 1

        # Subscribe all to same project
        for ws in mock_websockets:
            await subscription_manager.subscribe(ws, project_id)

        subscribers = await subscription_manager.get_subscribers(project_id)
        assert len(subscribers) == 3
        for ws in mock_websockets:
            assert ws in subscribers

    @pytest.mark.asyncio
    async def test_get_subscribers_mixed_subscriptions(
        self, subscription_manager, mock_websockets
    ):
        """Get subscribers filters correctly with mixed subscriptions."""
        # Subscribe websockets to different projects
        await subscription_manager.subscribe(mock_websockets[0], 1)  # ws0 -> project 1
        await subscription_manager.subscribe(mock_websockets[1], 1)  # ws1 -> project 1
        await subscription_manager.subscribe(mock_websockets[1], 2)  # ws1 -> project 2
        await subscription_manager.subscribe(mock_websockets[2], 2)  # ws2 -> project 2

        # Get subscribers for project 1
        subscribers_1 = await subscription_manager.get_subscribers(1)
        assert len(subscribers_1) == 2
        assert mock_websockets[0] in subscribers_1
        assert mock_websockets[1] in subscribers_1
        assert mock_websockets[2] not in subscribers_1

        # Get subscribers for project 2
        subscribers_2 = await subscription_manager.get_subscribers(2)
        assert len(subscribers_2) == 2
        assert mock_websockets[1] in subscribers_2
        assert mock_websockets[2] in subscribers_2
        assert mock_websockets[0] not in subscribers_2


class TestWebSocketSubscriptionManagerCleanup:
    """Tests for cleanup() method."""

    @pytest.mark.asyncio
    async def test_cleanup_removes_all(self, subscription_manager, mock_websocket):
        """Cleanup removes all subscriptions for websocket."""
        projects = [1, 2, 3, 4, 5]

        # Subscribe to multiple projects
        for project_id in projects:
            await subscription_manager.subscribe(mock_websocket, project_id)

        # Verify subscribed to all
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 5

        # Cleanup
        await subscription_manager.cleanup(mock_websocket)

        # Should have no subscriptions
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 0

    @pytest.mark.asyncio
    async def test_cleanup_not_subscribed(self, subscription_manager, mock_websocket):
        """Cleanup on unsubscribed websocket is safe."""
        # Cleanup without subscribing (should not raise)
        await subscription_manager.cleanup(mock_websocket)

        # Should be empty
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 0

    @pytest.mark.asyncio
    async def test_cleanup_does_not_affect_others(
        self, subscription_manager, mock_websockets
    ):
        """Cleanup for one websocket doesn't affect others."""
        project_id = 1

        # Subscribe all to same project
        for ws in mock_websockets:
            await subscription_manager.subscribe(ws, project_id)

        # Verify all subscribed
        subscribers = await subscription_manager.get_subscribers(project_id)
        assert len(subscribers) == 3

        # Cleanup one
        await subscription_manager.cleanup(mock_websockets[0])

        # Other two should still be subscribed
        subscribers = await subscription_manager.get_subscribers(project_id)
        assert len(subscribers) == 2
        assert mock_websockets[1] in subscribers
        assert mock_websockets[2] in subscribers
        assert mock_websockets[0] not in subscribers


class TestWebSocketSubscriptionManagerGetSubscriptions:
    """Tests for get_subscriptions() method."""

    @pytest.mark.asyncio
    async def test_get_subscriptions_empty(self, subscription_manager, mock_websocket):
        """Get subscriptions for unsubscribed websocket."""
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)

        assert isinstance(subscriptions, set)
        assert len(subscriptions) == 0

    @pytest.mark.asyncio
    async def test_get_subscriptions_multiple(self, subscription_manager, mock_websocket):
        """Get subscriptions for multi-project websocket."""
        projects = [10, 20, 30, 40]

        for project_id in projects:
            await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)

        assert len(subscriptions) == 4
        assert subscriptions == set(projects)

    @pytest.mark.asyncio
    async def test_get_subscriptions_returns_copy(self, subscription_manager, mock_websocket):
        """get_subscriptions() returns copy, not reference."""
        project_id = 1
        await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions1 = await subscription_manager.get_subscriptions(mock_websocket)
        subscriptions2 = await subscription_manager.get_subscriptions(mock_websocket)

        # Both should have the subscription
        assert 1 in subscriptions1
        assert 1 in subscriptions2

        # But they should be different objects
        assert subscriptions1 is not subscriptions2

        # Modifying one shouldn't affect the other
        subscriptions1.add(999)
        assert 999 not in subscriptions2


# ============================================================================
# ConnectionManager Tests - Broadcasting
# ============================================================================


class TestConnectionManagerBroadcast:
    """Tests for ConnectionManager.broadcast() method."""

    @pytest.mark.asyncio
    async def test_broadcast_no_project_id_backward_compat(self, connection_manager, mock_websockets):
        """Broadcast to all connections without project_id (backward compatible)."""
        # Setup
        for ws in mock_websockets[:2]:
            ws.send_json = AsyncMock()
            ws.accept = AsyncMock()

        mock_ws1, mock_ws2 = mock_websockets[:2]

        # Connect both
        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)

        # Broadcast without project_id
        message = {"type": "test", "data": "broadcast"}
        await connection_manager.broadcast(message)

        # Both should receive
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_with_project_id_subscribed(self, connection_manager, mock_websockets):
        """Filtered broadcast to subscribers of project."""
        # Setup
        for ws in mock_websockets:
            ws.send_json = AsyncMock()
            ws.accept = AsyncMock()

        mock_ws1, mock_ws2, mock_ws3 = mock_websockets

        # Connect all
        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)
        await connection_manager.connect(mock_ws3)

        # Subscribe specific websockets to project 1
        await connection_manager.subscription_manager.subscribe(mock_ws1, 1)
        await connection_manager.subscription_manager.subscribe(mock_ws2, 1)
        await connection_manager.subscription_manager.subscribe(mock_ws3, 2)

        # Broadcast to project 1
        message = {"type": "test", "project_id": 1}
        await connection_manager.broadcast(message, project_id=1)

        # Only subscribers to project 1 should receive
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)
        mock_ws3.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_with_project_id_no_subscribers(self, connection_manager, mock_websocket):
        """Broadcast with project_id but no subscribers."""
        # Connect but don't subscribe
        await connection_manager.connect(mock_websocket)

        # Broadcast to project with no subscribers
        message = {"type": "test", "project_id": 999}
        await connection_manager.broadcast(message, project_id=999)

        # Should not receive
        mock_websocket.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_mixed_subscriptions(self, connection_manager, mock_websockets):
        """Some connections subscribed, some not (project-based filtering)."""
        for ws in mock_websockets:
            ws.send_json = AsyncMock()
            ws.accept = AsyncMock()

        mock_ws1, mock_ws2, mock_ws3 = mock_websockets

        # Connect all
        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)
        await connection_manager.connect(mock_ws3)

        # Mix of subscriptions
        await connection_manager.subscription_manager.subscribe(mock_ws1, 1)
        await connection_manager.subscription_manager.subscribe(mock_ws1, 2)
        await connection_manager.subscription_manager.subscribe(mock_ws2, 1)
        # mock_ws3 not subscribed to anything

        # Broadcast to project 1
        message = {"type": "update", "project_id": 1}
        await connection_manager.broadcast(message, project_id=1)

        # Only subscribers to project 1
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)
        mock_ws3.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_error(self, connection_manager, mock_websockets):
        """Broadcast handles send errors gracefully."""
        for ws in mock_websockets[:2]:
            ws.accept = AsyncMock()
            ws.close = AsyncMock()

        mock_ws1, mock_ws2 = mock_websockets[:2]
        mock_ws1.send_json = AsyncMock(side_effect=Exception("Send failed"))
        mock_ws2.send_json = AsyncMock()

        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)

        # Broadcast without project_id (to all)
        message = {"type": "test"}
        await connection_manager.broadcast(message)

        # Both tried to send
        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

        # Error client should be disconnected
        assert mock_ws1 not in connection_manager.active_connections


# ============================================================================
# ConnectionManager Tests - Lifecycle
# ============================================================================


class TestConnectionManagerLifecycle:
    """Tests for ConnectionManager connect/disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_subscriptions(self, connection_manager, mock_websocket):
        """Disconnect calls subscription cleanup."""
        # Connect and subscribe
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscription_manager.subscribe(mock_websocket, 1)

        # Verify subscribed
        subscriptions = await connection_manager.subscription_manager.get_subscriptions(
            mock_websocket
        )
        assert len(subscriptions) == 1

        # Disconnect
        await connection_manager.disconnect(mock_websocket)

        # Should be cleaned up
        subscriptions = await connection_manager.subscription_manager.get_subscriptions(
            mock_websocket
        )
        assert len(subscriptions) == 0

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_active(self, connection_manager, mock_websocket):
        """Disconnect removes from active connections."""
        await connection_manager.connect(mock_websocket)
        assert len(connection_manager.active_connections) == 1

        await connection_manager.disconnect(mock_websocket)
        assert len(connection_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, connection_manager, mock_websocket):
        """Disconnect can be called multiple times safely."""
        await connection_manager.connect(mock_websocket)

        # Disconnect twice
        await connection_manager.disconnect(mock_websocket)
        await connection_manager.disconnect(mock_websocket)  # Should not raise

        assert len(connection_manager.active_connections) == 0


# ============================================================================
# Concurrency and Thread Safety Tests
# ============================================================================


class TestConcurrency:
    """Tests for concurrent operations and thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_unsubscribe(self, subscription_manager, mock_websocket):
        """Concurrent subscribe/unsubscribe operations are safe."""
        projects = list(range(1, 11))  # 10 projects

        async def subscribe_all():
            for project_id in projects:
                await subscription_manager.subscribe(mock_websocket, project_id)

        async def unsubscribe_all():
            for project_id in projects:
                await subscription_manager.unsubscribe(mock_websocket, project_id)

        # Run concurrently
        await asyncio.gather(subscribe_all(), unsubscribe_all())

        # Should end in consistent state
        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        # Depending on interleaving, might have some subscriptions left
        # but shouldn't crash or corrupt state
        assert isinstance(subscriptions, set)

    @pytest.mark.asyncio
    async def test_concurrent_broadcast_to_same_project(self, connection_manager, mock_websocket):
        """Concurrent broadcasts to same project don't corrupt state."""
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscription_manager.subscribe(mock_websocket, 1)

        # Broadcast concurrently
        messages = [{"type": "msg", "num": i} for i in range(10)]
        await asyncio.gather(
            *[connection_manager.broadcast(msg, project_id=1) for msg in messages]
        )

        # All messages should be sent
        assert mock_websocket.send_json.call_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_connect_disconnect(self, connection_manager):
        """Concurrent connect/disconnect operations are safe."""
        mock_sockets = [MagicMock() for _ in range(5)]
        for ws in mock_sockets:
            ws.send_json = AsyncMock()
            ws.accept = AsyncMock()
            ws.close = AsyncMock()

        async def connect_disconnect(ws):
            await connection_manager.connect(ws)
            await asyncio.sleep(0.001)  # Small delay
            await connection_manager.disconnect(ws)

        # Connect and disconnect concurrently
        await asyncio.gather(*[connect_disconnect(ws) for ws in mock_sockets])

        # Should end with no active connections
        assert len(connection_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_multiple_websockets_concurrent_operations(self, subscription_manager):
        """Multiple websockets doing concurrent operations are safe."""
        sockets = [MagicMock() for _ in range(3)]

        async def socket_operations(ws, start_project):
            projects = range(start_project, start_project + 5)
            for project_id in projects:
                await subscription_manager.subscribe(ws, project_id)
                # Interleave other operations
                await asyncio.sleep(0.001)
                if project_id % 2 == 0:
                    await subscription_manager.unsubscribe(ws, project_id)

        # All sockets doing operations concurrently
        await asyncio.gather(
            socket_operations(sockets[0], 1),
            socket_operations(sockets[1], 6),
            socket_operations(sockets[2], 11),
        )

        # All should have consistent state
        for ws in sockets:
            subscriptions = await subscription_manager.get_subscriptions(ws)
            assert isinstance(subscriptions, set)
            # State is valid, no corruption


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_subscribe_after_disconnect(self, subscription_manager, mock_websocket):
        """Can subscribe to websocket after cleanup/disconnect."""
        project_id = 1

        # Subscribe and cleanup
        await subscription_manager.subscribe(mock_websocket, project_id)
        await subscription_manager.cleanup(mock_websocket)

        # Should be able to subscribe again
        project_id = 2
        await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert project_id in subscriptions

    @pytest.mark.asyncio
    async def test_large_number_of_subscriptions(self, subscription_manager, mock_websocket):
        """Handle large number of project subscriptions."""
        projects = list(range(1, 101))  # 100 projects

        for project_id in projects:
            await subscription_manager.subscribe(mock_websocket, project_id)

        subscriptions = await subscription_manager.get_subscriptions(mock_websocket)
        assert len(subscriptions) == 100

        # Get subscribers for each project
        for project_id in projects:
            subscribers = await subscription_manager.get_subscribers(project_id)
            assert len(subscribers) == 1
            assert mock_websocket in subscribers

    @pytest.mark.asyncio
    async def test_large_number_of_websockets(self, subscription_manager):
        """Handle large number of websockets."""
        sockets = [MagicMock() for _ in range(50)]
        project_id = 1

        for ws in sockets:
            await subscription_manager.subscribe(ws, project_id)

        # Get subscribers
        subscribers = await subscription_manager.get_subscribers(project_id)
        assert len(subscribers) == 50

        for ws in sockets:
            assert ws in subscribers

    @pytest.mark.asyncio
    async def test_broadcast_with_empty_message(self, connection_manager, mock_websocket):
        """Broadcast with empty message."""
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscription_manager.subscribe(mock_websocket, 1)

        # Broadcast empty message
        message = {}
        await connection_manager.broadcast(message, project_id=1)

        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_with_large_message(self, connection_manager, mock_websocket):
        """Broadcast with large message payload."""
        await connection_manager.connect(mock_websocket)
        await connection_manager.subscription_manager.subscribe(mock_websocket, 1)

        # Large message (1MB of data)
        large_data = "x" * (1024 * 1024)
        message = {"type": "large", "data": large_data}

        await connection_manager.broadcast(message, project_id=1)

        mock_websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_subscribers_order_independent(
        self, subscription_manager, mock_websockets
    ):
        """get_subscribers() returns correct set regardless of subscription order."""
        project_id = 1

        # Subscribe in different orders
        await subscription_manager.subscribe(mock_websockets[0], project_id)
        await subscription_manager.subscribe(mock_websockets[1], project_id)
        await subscription_manager.subscribe(mock_websockets[2], project_id)

        subscribers1 = await subscription_manager.get_subscribers(project_id)

        # Cleanup and resubscribe in different order
        await subscription_manager.cleanup(mock_websockets[0])
        await subscription_manager.cleanup(mock_websockets[1])
        await subscription_manager.cleanup(mock_websockets[2])

        await subscription_manager.subscribe(mock_websockets[2], project_id)
        await subscription_manager.subscribe(mock_websockets[0], project_id)
        await subscription_manager.subscribe(mock_websockets[1], project_id)

        subscribers2 = await subscription_manager.get_subscribers(project_id)

        # Should have same subscribers
        assert set(subscribers1) == set(subscribers2)

    @pytest.mark.asyncio
    async def test_broadcast_error_cleanup_is_atomic(self, connection_manager, mock_websockets):
        """Broadcast error handling doesn't leave partial state."""
        for ws in mock_websockets[:2]:
            ws.accept = AsyncMock()
            ws.close = AsyncMock()

        mock_ws1, mock_ws2 = mock_websockets[:2]
        mock_ws1.send_json = AsyncMock(side_effect=Exception("Error"))
        mock_ws2.send_json = AsyncMock()

        await connection_manager.connect(mock_ws1)
        await connection_manager.connect(mock_ws2)

        # Broadcast to both
        message = {"type": "test"}
        await connection_manager.broadcast(message)

        # ws1 should be disconnected despite error
        assert mock_ws1 not in connection_manager.active_connections
        # ws2 should still be connected
        assert mock_ws2 in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_subscription_manager_state_consistency(
        self, subscription_manager, mock_websockets
    ):
        """Subscription state remains consistent through complex operations."""
        # Perform complex sequence of operations
        await subscription_manager.subscribe(mock_websockets[0], 1)
        await subscription_manager.subscribe(mock_websockets[0], 2)
        await subscription_manager.subscribe(mock_websockets[1], 1)

        # Get snapshots
        subs_0 = await subscription_manager.get_subscriptions(mock_websockets[0])
        subs_1 = await subscription_manager.get_subscriptions(mock_websockets[1])
        subs_p1 = await subscription_manager.get_subscribers(1)
        subs_p2 = await subscription_manager.get_subscribers(2)

        # Verify consistency
        assert 1 in subs_0 and 2 in subs_0
        assert 1 in subs_1 and 2 not in subs_1
        assert mock_websockets[0] in subs_p1 and mock_websockets[1] in subs_p1
        assert mock_websockets[0] in subs_p2 and mock_websockets[1] not in subs_p2


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_subscription_lifecycle(self, connection_manager, mock_websocket):
        """Full lifecycle: connect, subscribe, broadcast, unsubscribe, disconnect."""
        # Connect
        await connection_manager.connect(mock_websocket)
        assert len(connection_manager.active_connections) == 1

        # Subscribe
        await connection_manager.subscription_manager.subscribe(mock_websocket, 1)
        subscriptions = await connection_manager.subscription_manager.get_subscriptions(
            mock_websocket
        )
        assert 1 in subscriptions

        # Broadcast - should receive
        await connection_manager.broadcast({"msg": "hello"}, project_id=1)
        assert mock_websocket.send_json.call_count == 1

        # Unsubscribe
        await connection_manager.subscription_manager.unsubscribe(mock_websocket, 1)
        subscriptions = await connection_manager.subscription_manager.get_subscriptions(
            mock_websocket
        )
        assert 1 not in subscriptions

        # Broadcast - should not receive
        mock_websocket.send_json.reset_mock()
        await connection_manager.broadcast({"msg": "hello again"}, project_id=1)
        mock_websocket.send_json.assert_not_called()

        # Disconnect
        await connection_manager.disconnect(mock_websocket)
        assert len(connection_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_multi_agent_scenario(self, connection_manager):
        """Simulate multi-agent scenario with multiple projects."""
        # Simulate 3 agents (websockets) working on 2 projects
        agent_sockets = [MagicMock() for _ in range(3)]
        for ws in agent_sockets:
            ws.send_json = AsyncMock()
            ws.accept = AsyncMock()
            ws.close = AsyncMock()

        # Connect all agents
        for ws in agent_sockets:
            await connection_manager.connect(ws)

        # Agent 1: subscribed to project 1
        await connection_manager.subscription_manager.subscribe(agent_sockets[0], 1)

        # Agent 2: subscribed to project 1 and 2
        await connection_manager.subscription_manager.subscribe(agent_sockets[1], 1)
        await connection_manager.subscription_manager.subscribe(agent_sockets[1], 2)

        # Agent 3: subscribed to project 2
        await connection_manager.subscription_manager.subscribe(agent_sockets[2], 2)

        # Broadcast to project 1
        await connection_manager.broadcast({"event": "task_update"}, project_id=1)

        # Agent 1 and 2 should receive, not 3
        assert agent_sockets[0].send_json.call_count == 1
        assert agent_sockets[1].send_json.call_count == 1
        assert agent_sockets[2].send_json.call_count == 0

        # Reset and broadcast to project 2
        for ws in agent_sockets:
            ws.send_json.reset_mock()

        await connection_manager.broadcast({"event": "blocker_created"}, project_id=2)

        # Agent 2 and 3 should receive, not 1
        assert agent_sockets[0].send_json.call_count == 0
        assert agent_sockets[1].send_json.call_count == 1
        assert agent_sockets[2].send_json.call_count == 1
