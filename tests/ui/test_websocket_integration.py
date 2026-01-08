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


async def drain_proactive_messages(websocket, expected_project_id: int = None):
    """Drain proactive messages sent after subscription.

    After subscribing, the server sends:
    1. subscribed - subscription confirmation
    2. connection_ack - proactive connection acknowledgment
    3. project_status - proactive project state snapshot

    This helper reads these messages and returns the last one received.
    Use this after calling subscribe to clear the proactive messages
    before testing broadcast message reception.

    Args:
        websocket: WebSocket connection
        expected_project_id: Optional project ID to verify in messages

    Returns:
        List of message types received during drain
    """
    proactive_types = {"subscribed", "connection_ack", "project_status"}
    drained = []

    # Read up to 3 proactive messages (subscribed, connection_ack, project_status)
    for _ in range(3):
        try:
            data = json.loads(await asyncio.wait_for(websocket.recv(), timeout=0.5))
            msg_type = data.get("type")
            drained.append(msg_type)

            if expected_project_id is not None:
                assert data.get("project_id") == expected_project_id, \
                    f"Expected project_id {expected_project_id}, got {data.get('project_id')}"

            # Stop if we get a non-proactive message (shouldn't happen normally)
            if msg_type not in proactive_types:
                break
        except asyncio.TimeoutError:
            # No more messages
            break

    return drained


class TestFullSubscriptionWorkflow:
    """Test complete subscription workflow: connect → subscribe → receive → unsubscribe."""

    @pytest.mark.asyncio
    async def test_connect_and_subscribe_single_project(self, running_server, ws_url):
        """Test connecting and subscribing to a single project."""
        async with websockets.connect(ws_url) as websocket:
            # Send subscribe message
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))

            # Receive subscription confirmation
            data = json.loads(await websocket.recv())
            assert data["type"] == "subscribed"
            assert data["project_id"] == 1

    @pytest.mark.asyncio
    async def test_receive_filtered_broadcast_after_subscribe(self, running_server, ws_url, server_url):
        """Test that client receives broadcasts for subscribed project."""
        async with websockets.connect(ws_url) as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))

            # Drain proactive messages (subscribed, connection_ack, project_status)
            drained = await drain_proactive_messages(websocket, expected_project_id=1)
            assert "subscribed" in drained

            # Trigger broadcast via test API endpoint
            await trigger_broadcast(
                server_url,
                {"type": "task_status_changed", "task_id": 42, "status": "completed"},
                project_id=1
            )

            # Client should receive the message
            data = json.loads(await websocket.recv())
            assert data["type"] == "task_status_changed"
            assert data["task_id"] == 42
            assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_receiving_messages(self, running_server, ws_url, server_url):
        """Test that client stops receiving messages after unsubscribe."""
        async with websockets.connect(ws_url) as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))

            # Drain proactive messages
            await drain_proactive_messages(websocket, expected_project_id=1)

            # Unsubscribe from project 1
            await websocket.send(json.dumps({"type": "unsubscribe", "project_id": 1}))
            unsubscribe_response = json.loads(await websocket.recv())
            assert unsubscribe_response["type"] == "unsubscribed"
            assert unsubscribe_response["project_id"] == 1

            # Broadcast to project 1 should NOT be received
            await trigger_broadcast(server_url,
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
    async def test_disconnect_cleanup(self, running_server, ws_url, server_url):
        """Test that disconnect properly cleans up subscriptions."""
        # Create first WebSocket connection
        websocket1 = await websockets.connect(ws_url)

        try:
            # Subscribe to projects
            await websocket1.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(websocket1, expected_project_id=1)

            await websocket1.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await drain_proactive_messages(websocket1, expected_project_id=2)

            # Verify subscriptions work by receiving a broadcast
            await trigger_broadcast(
                server_url,
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
            websocket2 = await websockets.connect(ws_url)
            await websocket2.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(websocket2, expected_project_id=1)

            # Trigger broadcast - only websocket2 should receive it
            await trigger_broadcast(
                server_url,
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
    async def test_three_clients_with_independent_subscriptions(self, running_server, ws_url, server_url):
        """Test 3 clients with different project subscriptions."""
        # Create 3 WebSocket connections
        ws1 = await websockets.connect(ws_url)
        ws2 = await websockets.connect(ws_url)
        ws3 = await websockets.connect(ws_url)

        try:
            # Client 1: subscribe to project 1
            await ws1.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(ws1, expected_project_id=1)

            # Client 2: subscribe to project 2
            await ws2.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await drain_proactive_messages(ws2, expected_project_id=2)

            # Client 3: subscribe to both projects
            await ws3.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(ws3, expected_project_id=1)
            await ws3.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await drain_proactive_messages(ws3, expected_project_id=2)

            # Broadcast to project 1
            await trigger_broadcast(server_url,
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
            await trigger_broadcast(server_url,
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
    async def test_broadcast_isolation_between_projects(self, running_server, ws_url, server_url):
        """Test that broadcasts to one project don't leak to other project subscribers."""
        ws1 = await websockets.connect(ws_url)
        ws2 = await websockets.connect(ws_url)

        try:
            # Client 1: subscribe to project 1 only
            await ws1.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(ws1, expected_project_id=1)

            # Client 2: subscribe to project 2 only
            await ws2.send(json.dumps({"type": "subscribe", "project_id": 2}))
            await drain_proactive_messages(ws2, expected_project_id=2)

            # Broadcast to project 1
            await trigger_broadcast(server_url,
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
    async def test_subscribe_to_multiple_projects_sequentially(self, running_server, ws_url, server_url):
        """Test subscribing to multiple projects one after another."""
        async with websockets.connect(ws_url) as websocket:
            # Subscribe to project 1 and drain proactive messages
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            drained1 = await drain_proactive_messages(websocket, expected_project_id=1)
            assert "subscribed" in drained1

            # Subscribe to project 2 and drain proactive messages
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 2}))
            drained2 = await drain_proactive_messages(websocket, expected_project_id=2)
            assert "subscribed" in drained2

            # Subscribe to project 3 and drain proactive messages
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 3}))
            drained3 = await drain_proactive_messages(websocket, expected_project_id=3)
            assert "subscribed" in drained3

            # Verify all subscriptions are active by triggering broadcasts
            # and confirming client receives messages from all projects
            await trigger_broadcast(
                server_url,
                {"type": "test_msg", "project_id": 1},
                project_id=1
            )
            msg1 = json.loads(await websocket.recv())
            assert msg1["project_id"] == 1

            await trigger_broadcast(
                server_url,
                {"type": "test_msg", "project_id": 2},
                project_id=2
            )
            msg2 = json.loads(await websocket.recv())
            assert msg2["project_id"] == 2

            await trigger_broadcast(
                server_url,
                {"type": "test_msg", "project_id": 3},
                project_id=3
            )
            msg3 = json.loads(await websocket.recv())
            assert msg3["project_id"] == 3

    @pytest.mark.asyncio
    async def test_resubscribe_to_same_project(self, running_server, ws_url, server_url):
        """Test that resubscribing to same project doesn't cause issues."""
        async with websockets.connect(ws_url) as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            drained1 = await drain_proactive_messages(websocket, expected_project_id=1)
            assert "subscribed" in drained1

            # Subscribe to same project again
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            drained2 = await drain_proactive_messages(websocket, expected_project_id=1)
            assert "subscribed" in drained2

            # Verify subscription still works by triggering a broadcast
            await trigger_broadcast(
                server_url,
                {"type": "test_msg", "data": "test"},
                project_id=1
            )
            msg = json.loads(await websocket.recv())
            assert msg["type"] == "test_msg"
            assert msg["data"] == "test"

    @pytest.mark.asyncio
    async def test_unsubscribe_then_resubscribe(self, running_server, ws_url, server_url):
        """Test unsubscribing and then resubscribing to project."""
        async with websockets.connect(ws_url) as websocket:
            # Subscribe to project 1
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(websocket, expected_project_id=1)

            # Unsubscribe
            await websocket.send(json.dumps({"type": "unsubscribe", "project_id": 1}))
            resp2 = json.loads(await websocket.recv())
            assert resp2["type"] == "unsubscribed"

            # Resubscribe
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
            drained = await drain_proactive_messages(websocket, expected_project_id=1)
            assert "subscribed" in drained

            # Verify subscription is active by triggering a broadcast
            await trigger_broadcast(
                server_url,
                {"type": "test_msg", "data": "resubscribed"},
                project_id=1
            )
            msg = json.loads(await websocket.recv())
            assert msg["type"] == "test_msg"
            assert msg["data"] == "resubscribed"


class TestDisconnectCleanup:
    """Test disconnect cleanup and subscription removal."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_all_subscriptions(self, running_server, ws_url, server_url):
        """Test that disconnect removes all subscriptions for a client."""
        # Create connection
        websocket = await websockets.connect(ws_url)

        # Subscribe to multiple projects
        for project_id in [1, 2, 3]:
            await websocket.send(json.dumps({"type": "subscribe", "project_id": project_id}))
            await drain_proactive_messages(websocket, expected_project_id=project_id)

        # Verify subscriptions work before disconnect
        await trigger_broadcast(
            server_url,
            {"type": "test_msg", "data": "before_disconnect"},
            project_id=1
        )
        msg = json.loads(await websocket.recv())
        assert msg["data"] == "before_disconnect"

        # Disconnect
        await websocket.close()
        await asyncio.sleep(0.2)  # Give server time to process disconnect

        # Create new connection (without subscribing)
        websocket2 = await websockets.connect(ws_url)
        try:
            # Trigger broadcast - new connection shouldn't receive it (not subscribed)
            await trigger_broadcast(
                server_url,
                {"type": "test_msg", "data": "after_disconnect"},
                project_id=1
            )

            # Should timeout (no message received)
            try:
                await asyncio.wait_for(websocket2.recv(), timeout=0.2)
                pytest.fail("New connection should not receive message without subscription")
            except asyncio.TimeoutError:
                pass  # Expected
        finally:
            await websocket2.close()

    @pytest.mark.asyncio
    async def test_disconnect_during_subscription_cleanup(self, running_server, ws_url, server_url):
        """Test that disconnect properly cleans up even with active subscriptions."""
        websocket_refs = []

        # Create multiple connections with subscriptions
        for i in range(3):
            ws = await websockets.connect(ws_url)
            websocket_refs.append(ws)

            # Subscribe to project 1
            await ws.send(json.dumps({"type": "subscribe", "project_id": 1}))
            await drain_proactive_messages(ws, expected_project_id=1)

        # Trigger broadcast - all 3 should receive
        await trigger_broadcast(
            server_url,
            {"type": "test_msg", "data": "all_connected"},
            project_id=1
        )

        # All 3 clients should receive the message
        for ws in websocket_refs:
            msg = json.loads(await ws.recv())
            assert msg["data"] == "all_connected"

        # Disconnect first client
        await websocket_refs[0].close()
        await asyncio.sleep(0.2)

        # Trigger broadcast - only 2 remaining should receive
        await trigger_broadcast(
            server_url,
            {"type": "test_msg", "data": "two_remaining"},
            project_id=1
        )

        # Only remaining 2 clients receive
        for ws in websocket_refs[1:]:
            msg = json.loads(await ws.recv())
            assert msg["data"] == "two_remaining"

        # Cleanup remaining
        for ws in websocket_refs[1:]:
            await ws.close()

        await asyncio.sleep(0.2)

        # Trigger broadcast - no one should receive
        await trigger_broadcast(
            server_url,
            {"type": "test_msg", "data": "all_disconnected"},
            project_id=1
        )
        # No assertions needed - just verify no errors (no receivers is OK)


class TestBackwardCompatibility:
    """Test backward compatibility with unfiltered broadcasts."""

    @pytest.mark.asyncio
    async def test_broadcast_without_project_id_reaches_all_clients(self, running_server, ws_url, server_url):
        """Test that broadcasts without project_id reach all connected clients."""
        ws1 = await websockets.connect(ws_url)
        ws2 = await websockets.connect(ws_url)

        try:
            # Don't subscribe - just connected

            # Broadcast WITHOUT project_id (backward compatible)
            await trigger_broadcast(server_url,
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
    async def test_mixed_subscription_and_unsubscribed_clients(self, running_server, ws_url, server_url):
        """Test mix of subscribed and unsubscribed clients with broadcasts."""
        # Client 1: subscribed to project 1
        ws1 = await websockets.connect(ws_url)
        await ws1.send(json.dumps({"type": "subscribe", "project_id": 1}))
        await drain_proactive_messages(ws1, expected_project_id=1)

        # Client 2: not subscribed to anything
        ws2 = await websockets.connect(ws_url)

        try:
            # Broadcast to project 1 (filtered)
            await trigger_broadcast(server_url,
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
            await trigger_broadcast(server_url,
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
        async with websockets.connect(ws_url) as websocket:
            # Send subscribe with string project_id
            await websocket.send(json.dumps({"type": "subscribe", "project_id": "invalid"}))

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"
            assert "invalid" in response["error"].lower() or "project_id" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_subscribe_with_null_project_id(self, running_server, ws_url):
        """Test error handling when project_id is null."""
        async with websockets.connect(ws_url) as websocket:
            # Send subscribe with null project_id
            await websocket.send(json.dumps({"type": "subscribe", "project_id": None}))

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"

    @pytest.mark.asyncio
    async def test_subscribe_with_missing_project_id(self, running_server, ws_url):
        """Test error handling when project_id is missing."""
        async with websockets.connect(ws_url) as websocket:
            # Send subscribe without project_id
            await websocket.send(json.dumps({"type": "subscribe"}))

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"

    @pytest.mark.asyncio
    async def test_malformed_json_handling(self, running_server, ws_url):
        """Test error handling for malformed JSON."""
        async with websockets.connect(ws_url) as websocket:
            # Send malformed JSON
            await websocket.send("{ invalid json")

            # Should receive error response
            response = json.loads(await websocket.recv())
            assert response["type"] == "error"
            assert "JSON" in response["error"] or "json" in response["error"]

    @pytest.mark.asyncio
    async def test_invalid_message_type(self, running_server, ws_url):
        """Test handling of unknown message types."""
        async with websockets.connect(ws_url) as websocket:
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
        async with websockets.connect(ws_url) as websocket:
            # Rapidly subscribe and unsubscribe
            for i in range(10):
                await websocket.send(json.dumps({"type": "subscribe", "project_id": 1}))
                # Drain proactive messages (subscribed, connection_ack, project_status)
                await drain_proactive_messages(websocket, expected_project_id=1)
                await websocket.send(json.dumps({"type": "unsubscribe", "project_id": 1}))
                resp = json.loads(await websocket.recv())
                assert resp["type"] == "unsubscribed"

            # Connection should still be valid
            await websocket.send(json.dumps({"type": "ping"}))
            response = json.loads(await websocket.recv())
            assert response["type"] == "pong"

    @pytest.mark.asyncio
    async def test_large_project_id(self, running_server, ws_url, server_url):
        """Test that subscribing to non-existent project returns access denied."""
        async with websockets.connect(ws_url) as websocket:
            large_id = 999999999

            # Subscribe to large project ID that doesn't exist
            await websocket.send(json.dumps({"type": "subscribe", "project_id": large_id}))
            response = json.loads(await websocket.recv())

            # Should get access denied error (project doesn't exist)
            assert response["type"] == "error"
            assert "access denied" in response.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_zero_project_id_rejected(self, running_server, ws_url):
        """Test that project_id of 0 is rejected."""
        async with websockets.connect(ws_url) as websocket:
            # Try to subscribe to project 0
            await websocket.send(json.dumps({"type": "subscribe", "project_id": 0}))
            response = json.loads(await websocket.recv())
            # Should receive error
            assert response["type"] == "error"
            assert "positive" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_negative_project_id_rejected(self, running_server, ws_url):
        """Test that negative project IDs are rejected."""
        async with websockets.connect(ws_url) as websocket:
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
