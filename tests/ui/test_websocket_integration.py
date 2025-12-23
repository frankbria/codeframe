"""
Integration tests for end-to-end WebSocket subscription workflow.

This test suite validates the complete WebSocket subscription lifecycle including:
- Full subscription workflow (connect → subscribe → receive filtered messages → unsubscribe)
- Multi-client scenarios with independent subscriptions
- Subscribe/unsubscribe flow and message filtering
- Disconnect cleanup and subscription recovery
- Backward compatibility with unfiltered broadcasts
- Invalid message handling and error responses

The tests use real WebSocket connections via the `websockets` library to
validate message routing correctness against a running FastAPI server.
"""

import asyncio
import json
import pytest
import requests
import websockets

from codeframe.ui.shared import manager


async def trigger_broadcast(server_url: str, message: dict, project_id: int = None):
    """Trigger a broadcast via the test API endpoint.

    Args:
        server_url: Base server URL (e.g., http://localhost:8080)
        message: Message dict to broadcast
        project_id: Optional project ID for filtered broadcasts
    """
    url = f"{server_url}/test/broadcast"
    params = {"project_id": project_id} if project_id is not None else {}
    response = requests.post(url, json=message, params=params, timeout=5.0)
    response.raise_for_status()
    return response.json()


class TestFullSubscriptionWorkflow:
    """Test complete subscription workflow: connect → subscribe → receive → unsubscribe."""

    @pytest.mark.asyncio
    async def test_connect_and_subscribe_single_project(self, running_server, ws_url):
        """Test connecting and subscribing to a single project."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Send subscribe message
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))

            # Receive subscription confirmation
            data = json.loads(await websocket.recv())
            assert data["type"] == "subscribed"
            assert data["project_id"] == 1

    @pytest.mark.asyncio
    async def test_receive_filtered_broadcast_after_subscribe(self, running_server, ws_url):
        """Test that client receives broadcasts for subscribed project."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            data = json.loads(await websocket.recv())  # subscription confirmation
            assert data["type"] == "subscribed"

            # Trigger broadcast via test API endpoint
            await trigger_broadcast(
                running_server,
                {"type": "task_status_changed", "task_id": 42, "status": "completed"},
                project_id=1
            )

            # Client should receive the message
            data = json.loads(await websocket.recv())
            assert data["type"] == "task_status_changed"
            assert data["task_id"] == 42
            assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_receiving_messages(self, running_server, ws_url):
        """Test that client stops receiving messages after unsubscribe."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket.recv()  # confirmation

            # Unsubscribe from project 1
            await websocket.send(json.dumps({"type": "unsubscribe", "project_id": 1}))
            unsubscribe_response = json.loads(await websocket.recv())
            assert unsubscribe_response["type"] == "unsubscribed"
            assert unsubscribe_response["project_id"] == 1

            # Broadcast to project 1 should NOT be received
            await trigger_broadcast(running_server, 
                {"type": "task_status_changed", "task_id": 99, "status": "failed"},
                project_id=1
            )

            # Client should NOT receive this message
            # Use asyncio.wait_for with timeout to verify no message arrives
            try:
                await asyncio.wait_for(websocket.recv(), timeout=0.2)
                pytest.fail("Should not receive message after unsubscribe")
            except asyncio.TimeoutError:
                # Expected: no message received
                pass

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self, running_server, ws_url):
        """Test that disconnect properly cleans up subscriptions."""
        # Create first WebSocket connection
        websocket1 = await websockets.connect(f"{ws_url}/ws")

        try:
            # Subscribe to projects
            await websocket1.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket1.recv()

            await websocket1.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await websocket1.recv()

            # Verify subscriptions work by receiving a broadcast
            await trigger_broadcast(
                running_server,
                {"type": "test_message", "data": "before_disconnect"},
                project_id=1
            )
            msg = json.loads(await websocket1.recv())
            assert msg["type"] == "test_message"

            # Disconnect
            await websocket1.close()

            # Give server time to process disconnect
            await asyncio.sleep(0.2)

            # Create second connection and subscribe to same project
            websocket2 = await websockets.connect(f"{ws_url}/ws")
            await websocket2.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket2.recv()

            # Trigger broadcast - only websocket2 should receive it
            await trigger_broadcast(
                running_server,
                {"type": "test_message", "data": "after_disconnect"},
                project_id=1
            )

            # websocket2 receives the message
            msg = json.loads(await websocket2.recv())
            assert msg["data"] == "after_disconnect"

            await websocket2.close()

        finally:
            if websocket1.close_code is None:
                await websocket1.close()


class TestMultiClientScenario:
    """Test multi-client scenarios with independent subscriptions."""

    @pytest.mark.asyncio
    async def test_three_clients_with_independent_subscriptions(self, running_server, ws_url):
        """Test 3 clients with different project subscriptions."""
        # Create 3 WebSocket connections
        ws1 = await websockets.connect(f"{ws_url}/ws")
        ws2 = await websockets.connect(f"{ws_url}/ws")
        ws3 = await websockets.connect(f"{ws_url}/ws")

        try:
            # Client 1: subscribe to project 1
            await ws1.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await ws1.recv()

            # Client 2: subscribe to project 2
            await ws2.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await ws2.recv()

            # Client 3: subscribe to both projects
            await ws3.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await ws3.recv()
            await ws3.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await ws3.recv()

            # Broadcast to project 1
            await trigger_broadcast(running_server, 
                {"type": "task_status_changed", "project_id": 1, "task_id": 101},
                project_id=1
            )

            # Client 1 should receive (subscribed to project 1)
            data1 = json.loads(await ws1.recv())
            assert data1["project_id"] == 1
            assert data1["task_id"] == 101

            # Client 3 should receive (subscribed to project 1)
            data3 = json.loads(await ws3.recv())
            assert data3["project_id"] == 1
            assert data3["task_id"] == 101

            # Broadcast to project 2
            await trigger_broadcast(running_server, 
                {"type": "task_status_changed", "project_id": 2, "task_id": 202},
                project_id=2
            )

            # Client 2 should receive (subscribed to project 2)
            data2 = json.loads(await ws2.recv())
            assert data2["project_id"] == 2
            assert data2["task_id"] == 202

            # Client 3 should receive (subscribed to project 2)
            data3 = json.loads(await ws3.recv())
            assert data3["project_id"] == 2
            assert data3["task_id"] == 202

        finally:
            # Cleanup
            await ws1.close()
            await ws2.close()
            await ws3.close()

    @pytest.mark.asyncio
    async def test_broadcast_isolation_between_projects(self, running_server, ws_url):
        """Test that broadcasts to one project don't leak to other project subscribers."""
        ws1 = await websockets.connect(f"{ws_url}/ws")
        ws2 = await websockets.connect(f"{ws_url}/ws")

        try:
            # Client 1: subscribe to project 1 only
            await ws1.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await ws1.recv()

            # Client 2: subscribe to project 2 only
            await ws2.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await ws2.recv()

            # Broadcast to project 1
            await trigger_broadcast(running_server, 
                {"type": "test_result", "project_id": 1, "status": "passed"},
                project_id=1
            )

            # Client 1 receives message
            data1 = json.loads(await ws1.recv())
            assert data1["project_id"] == 1

            # Client 2 should NOT receive anything (timeout)
            try:
                await asyncio.wait_for(ws2.recv(), timeout=0.2)
                pytest.fail("Client 2 should not receive project 1 broadcasts")
            except asyncio.TimeoutError:
                pass

        finally:
            await ws1.close()
            await ws2.close()


class TestSubscribeUnsubscribeFlow:
    """Test subscribe/unsubscribe flow and message filtering."""

    @pytest.mark.asyncio
    async def test_subscribe_to_multiple_projects_sequentially(self, running_server, ws_url):
        """Test subscribing to multiple projects one after another."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            resp1 = json.loads(await websocket.recv())
            assert resp1["project_id"] == 1

            # Subscribe to project 2
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 2}))
            resp2 = json.loads(await websocket.recv())
            assert resp2["project_id"] == 2

            # Subscribe to project 3
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 3}))
            resp3 = json.loads(await websocket.recv())
            assert resp3["project_id"] == 3

            # Verify all subscriptions are active (check manager's internal state)
            subs_count = len([
                ws for ws, projects in manager.subscription_manager._subscriptions.items()
                if ws == websocket and 1 in projects and 2 in projects and 3 in projects
            ])
            assert subs_count == 1

    @pytest.mark.asyncio
    async def test_resubscribe_to_same_project(self, running_server, ws_url):
        """Test that resubscribing to same project doesn't cause issues."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket.recv()

            # Subscribe to same project again
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket.recv()

            # Should still work - single subscription
            subs = manager.subscription_manager._subscriptions.get(websocket, set())
            assert len(subs) == 1
            assert 1 in subs

    @pytest.mark.asyncio
    async def test_unsubscribe_then_resubscribe(self, running_server, ws_url):
        """Test unsubscribing and then resubscribing to project."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket.recv()

            # Unsubscribe
            await websocket.send(json.dumps({"type": "unsubscribe", "project_id": 1}))
            await websocket.recv()

            # Resubscribe
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await websocket.recv()

            # Verify subscription is active
            is_subscribed = 1 in manager.subscription_manager._subscriptions.get(websocket, set())
            assert is_subscribed


class TestDisconnectCleanup:
    """Test disconnect cleanup and subscription removal."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_all_subscriptions(self, running_server, ws_url):
        """Test that disconnect removes all subscriptions for a client."""
        # Create connection
        websocket = await websockets.connect(f"{ws_url}/ws")

        # Subscribe to multiple projects
        for project_id in [1, 2, 3]:
            await websocket.send(json.dumps({"type": "subscribe", "project_id": project_id}))
            await websocket.recv()

        # Verify subscriptions before disconnect
        subs = manager.subscription_manager._subscriptions.get(websocket, set())
        count_before = len(subs)
        assert count_before == 3

        # Disconnect
        await websocket.close()
        await asyncio.sleep(0.1)  # Give server time to process disconnect

        # Verify subscriptions are gone
        count_after = len(manager.subscription_manager._subscriptions.get(websocket, set()))
        assert count_after == 0

    @pytest.mark.asyncio
    async def test_disconnect_during_subscription_cleanup(self, running_server, ws_url):
        """Test that disconnect properly cleans up even with active subscriptions."""
        websocket_refs = []

        # Create multiple connections with subscriptions
        for i in range(3):
            ws = await websockets.connect(f"{ws_url}/ws")
            websocket_refs.append(ws)

            # Subscribe to projects
            await ws.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await ws.recv()

        # Verify all subscriptions exist
        count = len([
            ws for ws, projects in manager.subscription_manager._subscriptions.items()
            if 1 in projects
        ])
        assert count == 3

        # Disconnect first client
        await websocket_refs[0].close()
        await asyncio.sleep(0.1)

        # Verify subscription count decreased
        count = len([
            ws for ws, projects in manager.subscription_manager._subscriptions.items()
            if 1 in projects
        ])
        assert count == 2

        # Cleanup remaining
        for ws in websocket_refs[1:]:
            await ws.close()

        await asyncio.sleep(0.1)

        # Verify all cleaned up
        count = len([
            ws for ws, projects in manager.subscription_manager._subscriptions.items()
            if 1 in projects
        ])
        assert count == 0


class TestBackwardCompatibility:
    """Test backward compatibility with unfiltered broadcasts."""

    @pytest.mark.asyncio
    async def test_broadcast_without_project_id_reaches_all_clients(self, running_server, ws_url):
        """Test that broadcasts without project_id reach all connected clients."""
        ws1 = await websockets.connect(f"{ws_url}/ws")
        ws2 = await websockets.connect(f"{ws_url}/ws")

        try:
            # Don't subscribe - just connected

            # Broadcast WITHOUT project_id (backward compatible)
            await trigger_broadcast(running_server, 
                {"type": "agent_started", "agent_id": "lead-1"}
                # Note: no project_id parameter
            )

            # Both clients should receive the message
            data1 = json.loads(await ws1.recv())
            assert data1["type"] == "agent_started"

            data2 = json.loads(await ws2.recv())
            assert data2["type"] == "agent_started"

        finally:
            await ws1.close()
            await ws2.close()

    @pytest.mark.asyncio
    async def test_mixed_subscription_and_unsubscribed_clients(self, running_server, ws_url):
        """Test mix of subscribed and unsubscribed clients with broadcasts."""
        # Client 1: subscribed to project 1
        ws1 = await websockets.connect(f"{ws_url}/ws")
        await ws1.send(json.dumps({"type": "subscribe", "project_id": 1}))
        await ws1.recv()

        # Client 2: not subscribed to anything
        ws2 = await websockets.connect(f"{ws_url}/ws")

        try:
            # Broadcast to project 1 (filtered)
            await trigger_broadcast(running_server, 
                {"type": "task_status_changed", "task_id": 42},
                project_id=1
            )

            # Client 1 should receive (subscribed)
            data1 = json.loads(await ws1.recv())
            assert data1["type"] == "task_status_changed"

            # Client 2 should NOT receive (not subscribed)
            try:
                await asyncio.wait_for(ws2.recv(), timeout=0.2)
                pytest.fail("Unsubscribed client should not receive filtered broadcasts")
            except asyncio.TimeoutError:
                pass

            # Now broadcast to ALL (no project_id)
            await trigger_broadcast(running_server, 
                {"type": "agent_status_changed", "agent_id": "worker-1"}
                # No project_id
            )

            # Both should receive unfiltered broadcast
            data1 = json.loads(await ws1.recv())
            assert data1["type"] == "agent_status_changed"

            data2 = json.loads(await ws2.recv())
            assert data2["type"] == "agent_status_changed"

        finally:
            await ws1.close()
            await ws2.close()


class TestInvalidMessageHandling:
    """Test error handling for invalid subscribe messages."""

    @pytest.mark.asyncio
    async def test_subscribe_with_invalid_project_id_string(self, running_server, ws_url):
        """Test error handling when project_id is string instead of int."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Send subscribe with string project_id
            await websocket.send(json.dumps({"type": "subscribe", "project_id": "invalid"}))

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"
            assert "invalid" in response["error"].lower() or "project_id" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_subscribe_with_null_project_id(self, running_server, ws_url):
        """Test error handling when project_id is null."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Send subscribe with null project_id
            await websocket.send(json.dumps({"type": "subscribe", "project_id": None}))

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"

    @pytest.mark.asyncio
    async def test_subscribe_with_missing_project_id(self, running_server, ws_url):
        """Test error handling when project_id is missing."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Send subscribe without project_id
            await websocket.send(json.dumps({"type": "subscribe"}))

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"

    @pytest.mark.asyncio
    async def test_malformed_json_handling(self, running_server, ws_url):
        """Test error handling for malformed JSON."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Send malformed JSON
            await websocket.send("{ invalid json")

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"
            assert "JSON" in response["error"] or "json" in response["error"]

    @pytest.mark.asyncio
    async def test_invalid_message_type(self, running_server, ws_url):
        """Test handling of unknown message types."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Send message with unknown type
            await websocket.send(json.dumps({"type": "unknown_type", "data": "something"}))

            # Connection should still work - send a valid message after
            await websocket.send(json.dumps({"type": "ping"}))
            response = json.loads(await websocket.recv())
            assert response["type"] == "pong"


class TestWebSocketSubscriptionManager:
    """Unit tests for WebSocketSubscriptionManager class."""

    @pytest.mark.asyncio
    async def test_subscribe_new_websocket(self):
        """Test subscribing a new websocket."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, project_id=1)

        subs = await manager.get_subscriptions(ws)
        assert 1 in subs
        assert len(subs) == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple_projects(self):
        """Test subscribing to multiple projects."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, 1)
        await manager.subscribe(ws, 2)
        await manager.subscribe(ws, 3)

        subs = await manager.get_subscriptions(ws)
        assert subs == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_project(self):
        """Test unsubscribing from a project."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, 1)
        await manager.subscribe(ws, 2)

        await manager.unsubscribe(ws, 1)

        subs = await manager.get_subscriptions(ws)
        assert 1 not in subs
        assert 2 in subs

    @pytest.mark.asyncio
    async def test_unsubscribe_all_removes_websocket(self):
        """Test that unsubscribing from all projects removes websocket."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, 1)
        await manager.unsubscribe(ws, 1)

        subs = await manager.get_subscriptions(ws)
        assert len(subs) == 0

    @pytest.mark.asyncio
    async def test_cleanup_removes_all_subscriptions(self):
        """Test cleanup removes all subscriptions for a websocket."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, 1)
        await manager.subscribe(ws, 2)
        await manager.subscribe(ws, 3)

        await manager.cleanup(ws)

        subs = await manager.get_subscriptions(ws)
        assert len(subs) == 0

    @pytest.mark.asyncio
    async def test_get_subscribers_for_project(self):
        """Test getting all subscribers for a specific project."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        # ws1 and ws3 subscribe to project 1
        await manager.subscribe(ws1, 1)
        await manager.subscribe(ws3, 1)

        # ws2 subscribes to project 2
        await manager.subscribe(ws2, 2)

        # Get subscribers for project 1
        subs_p1 = await manager.get_subscribers(1)
        assert ws1 in subs_p1
        assert ws3 in subs_p1
        assert ws2 not in subs_p1
        assert len(subs_p1) == 2

        # Get subscribers for project 2
        subs_p2 = await manager.get_subscribers(2)
        assert ws2 in subs_p2
        assert ws1 not in subs_p2
        assert len(subs_p2) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_project(self):
        """Test unsubscribing from a project that wasn't subscribed."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, 1)

        # Unsubscribe from non-existent project
        await manager.unsubscribe(ws, 99)

        # Original subscription should remain
        subs = await manager.get_subscriptions(ws)
        assert 1 in subs

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent_websocket(self):
        """Test cleanup on websocket that has no subscriptions."""
        from unittest.mock import AsyncMock
        from codeframe.ui.shared import WebSocketSubscriptionManager

        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        # Should not raise error
        await manager.cleanup(ws)

        subs = await manager.get_subscriptions(ws)
        assert len(subs) == 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_rapid_subscribe_unsubscribe(self, running_server, ws_url):
        """Test rapid subscribe/unsubscribe operations."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Rapidly subscribe and unsubscribe
            for i in range(10):
                await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
                await websocket.recv()
                await websocket.send(json.dumps({"type": "unsubscribe", "project_id": 1}))
                await websocket.recv()

            # Connection should still be valid
            await websocket.send(json.dumps({"type": "ping"}))
            response = json.loads(await websocket.recv())
            assert response["type"] == "pong"

    @pytest.mark.asyncio
    async def test_large_project_id(self, running_server, ws_url):
        """Test with very large project IDs."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            large_id = 999999999

            # Subscribe to large project ID
            await websocket.send(json.dumps({"type": "subscribe", "project_id": large_id}))
            response = json.loads(await websocket.recv())
            assert response["project_id"] == large_id

            # Broadcast to large project ID
            await trigger_broadcast(running_server, 
                {"type": "test", "data": "test"},
                project_id=large_id
            )

            # Should receive
            data = json.loads(await websocket.recv())
            assert data["type"] == "test"

    @pytest.mark.asyncio
    async def test_zero_project_id_rejected(self, running_server, ws_url):
        """Test that project_id of 0 is rejected."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Try to subscribe to project 0
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 0}))
            response = json.loads(await websocket.recv())
            # Should receive error
            assert response["type"] == "error"
            assert "positive" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_negative_project_id_rejected(self, running_server, ws_url):
        """Test that negative project IDs are rejected."""
        async with websockets.connect(f"{ws_url}/ws") as websocket:
            # Try to subscribe to negative project ID
            await websocket.send(json.dumps({"type": "subscribe", "project_id": -1}))

            # Should receive error
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"
            assert "positive" in response["error"].lower()

            # Connection should still work
            await websocket.send(json.dumps({"type": "ping"}))
            pong = json.loads(await websocket.recv())
            assert pong["type"] == "pong"
