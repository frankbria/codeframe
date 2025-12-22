"""
Integration tests for end-to-end WebSocket subscription workflow.

This test suite validates the complete WebSocket subscription lifecycle including:
- Full subscription workflow (connect → subscribe → receive filtered messages → unsubscribe)
- Multi-client scenarios with independent subscriptions
- Subscribe/unsubscribe flow and message filtering
- Disconnect cleanup and subscription recovery
- Backward compatibility with unfiltered broadcasts
- Invalid message handling and error responses

The tests use FastAPI's TestClient WebSocket testing capabilities to simulate
real WebSocket connections and validate message routing correctness.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from codeframe.persistence.database import Database
from codeframe.ui.shared import ConnectionManager, WebSocketSubscriptionManager


@pytest.fixture
def test_client():
    """Create test client with temporary database and clean manager state."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"

    # Create fresh ConnectionManager for each test
    from codeframe.ui import server, shared
    from datetime import datetime, timezone

    # Replace manager with fresh instance for test isolation
    fresh_manager = ConnectionManager()
    original_manager = shared.manager
    shared.manager = fresh_manager
    server.manager = fresh_manager

    # Initialize database
    db = Database(db_path)
    db.initialize()
    server.app.state.db = db

    # Create test user (user_id=1) for WebSocket authentication
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (id, email, password_hash, name, created_at)
        VALUES (1, 'test@example.com', 'hashed_password', 'Test User', ?)
        """,
        (datetime.now(timezone.utc).isoformat(),)
    )
    db.conn.commit()

    # Create test project (project_id=1) owned by user 1
    try:
        db.create_project(
            name="Test Project",
            description="Test project for WebSocket tests",
            workspace_path=str(workspace_root / "1"),
            user_id=1
        )
    except Exception:
        # Project might already exist from previous test, that's OK
        pass

    db.conn.commit()

    from codeframe.workspace import WorkspaceManager

    server.app.state.workspace_manager = WorkspaceManager(workspace_root)

    client = TestClient(server.app)

    yield client

    # Cleanup
    db.close()
    shutil.rmtree(temp_dir, ignore_errors=True)

    # Restore original manager
    shared.manager = original_manager
    server.manager = original_manager


class TestFullSubscriptionWorkflow:
    """Test complete subscription workflow: connect → subscribe → receive → unsubscribe."""

    def test_connect_and_subscribe_single_project(self, test_client):
        """Test connecting and subscribing to a single project."""
        with test_client.websocket_connect("/ws") as websocket:
            # Send subscribe message
            websocket.send_json({"type": "subscribe", "project_id": 1})

            # Receive subscription confirmation
            data = websocket.receive_json()
            assert data["type"] == "subscribed"
            assert data["project_id"] == 1

    def test_receive_filtered_broadcast_after_subscribe(self, test_client):
        """Test that client receives broadcasts for subscribed project."""
        with test_client.websocket_connect("/ws") as websocket:
            # Subscribe to project 1
            websocket.send_json({"type": "subscribe", "project_id": 1})
            websocket.receive_json()  # subscription confirmation

            # Simulate broadcast to project 1
            from codeframe.ui.shared import manager

            import asyncio

            async def broadcast():
                await manager.broadcast(
                    {"type": "task_status_changed", "task_id": 42, "status": "completed"},
                    project_id=1,
                )

            asyncio.run(broadcast())

            # Client should receive the message
            data = websocket.receive_json()
            assert data["type"] == "task_status_changed"
            assert data["task_id"] == 42
            assert data["status"] == "completed"

    def test_unsubscribe_stops_receiving_messages(self, test_client):
        """Test that client stops receiving messages after unsubscribe."""
        with test_client.websocket_connect("/ws") as websocket:
            # Subscribe to project 1
            websocket.send_json({"type": "subscribe", "project_id": 1})
            websocket.receive_json()  # confirmation

            # Unsubscribe from project 1
            websocket.send_json({"type": "unsubscribe", "project_id": 1})
            unsubscribe_response = websocket.receive_json()
            assert unsubscribe_response["type"] == "unsubscribed"
            assert unsubscribe_response["project_id"] == 1

            # Broadcast to project 1 should NOT be received
            from codeframe.ui.shared import manager

            import asyncio

            async def broadcast():
                await manager.broadcast(
                    {"type": "task_status_changed", "task_id": 99, "status": "failed"},
                    project_id=1,
                )

            asyncio.run(broadcast())

            # Client should NOT receive this message
            # Use a timeout to verify no message arrives
            try:
                data = websocket.receive_json(timeout=0.1)
                # If we get here without timeout, the test should fail
                pytest.fail("Should not receive message after unsubscribe")
            except TimeoutError:
                # Expected: no message received
                pass

    def test_disconnect_cleanup(self, test_client):
        """Test that disconnect properly cleans up subscriptions."""
        # Create first WebSocket connection
        ws1 = test_client.websocket_connect("/ws")
        websocket1 = ws1.__enter__()

        # Subscribe to projects
        websocket1.send_json({"type": "subscribe", "project_id": 1})
        websocket1.receive_json()

        websocket1.send_json({"type": "subscribe", "project_id": 2})
        websocket1.receive_json()

        # Verify subscriptions exist
        from codeframe.ui.shared import manager

        import asyncio

        async def check_subscriptions():
            subs = await manager.subscription_manager.get_subscriptions(
                websocket1
            )
            return subs

        subs = asyncio.run(check_subscriptions())
        assert 1 in subs
        assert 2 in subs

        # Disconnect
        ws1.__exit__(None, None, None)

        # Verify subscriptions are cleaned up
        async def check_after_disconnect():
            subs = await manager.subscription_manager.get_subscriptions(
                websocket1
            )
            return subs

        subs = asyncio.run(check_after_disconnect())
        assert len(subs) == 0


class TestMultiClientScenario:
    """Test multi-client scenarios with independent subscriptions."""

    def test_three_clients_with_independent_subscriptions(self, test_client):
        """Test 3 clients with different project subscriptions."""
        # Create 3 WebSocket connections
        ws1_ctx = test_client.websocket_connect("/ws")
        ws1 = ws1_ctx.__enter__()

        ws2_ctx = test_client.websocket_connect("/ws")
        ws2 = ws2_ctx.__enter__()

        ws3_ctx = test_client.websocket_connect("/ws")
        ws3 = ws3_ctx.__enter__()

        # Client 1: subscribe to project 1
        ws1.send_json({"type": "subscribe", "project_id": 1})
        ws1.receive_json()

        # Client 2: subscribe to project 2
        ws2.send_json({"type": "subscribe", "project_id": 2})
        ws2.receive_json()

        # Client 3: subscribe to both projects
        ws3.send_json({"type": "subscribe", "project_id": 1})
        ws3.receive_json()
        ws3.send_json({"type": "subscribe", "project_id": 2})
        ws3.receive_json()

        # Broadcast to project 1
        from codeframe.ui.shared import manager
        import asyncio

        async def broadcast_p1():
            await manager.broadcast(
                {"type": "task_status_changed", "project_id": 1, "task_id": 101},
                project_id=1,
            )

        asyncio.run(broadcast_p1())

        # Client 1 should receive (subscribed to project 1)
        data1 = ws1.receive_json()
        assert data1["project_id"] == 1
        assert data1["task_id"] == 101

        # Client 3 should receive (subscribed to project 1)
        data3 = ws3.receive_json()
        assert data3["project_id"] == 1
        assert data3["task_id"] == 101

        # Broadcast to project 2
        async def broadcast_p2():
            await manager.broadcast(
                {"type": "task_status_changed", "project_id": 2, "task_id": 202},
                project_id=2,
            )

        asyncio.run(broadcast_p2())

        # Client 2 should receive (subscribed to project 2)
        data2 = ws2.receive_json()
        assert data2["project_id"] == 2
        assert data2["task_id"] == 202

        # Client 3 should receive (subscribed to project 2)
        data3 = ws3.receive_json()
        assert data3["project_id"] == 2
        assert data3["task_id"] == 202

        # Cleanup
        ws1_ctx.__exit__(None, None, None)
        ws2_ctx.__exit__(None, None, None)
        ws3_ctx.__exit__(None, None, None)

    def test_broadcast_isolation_between_projects(self, test_client):
        """Test that broadcasts to one project don't leak to other project subscribers."""
        ws1_ctx = test_client.websocket_connect("/ws")
        ws1 = ws1_ctx.__enter__()

        ws2_ctx = test_client.websocket_connect("/ws")
        ws2 = ws2_ctx.__enter__()

        # Client 1: subscribe to project 1 only
        ws1.send_json({"type": "subscribe", "project_id": 1})
        ws1.receive_json()

        # Client 2: subscribe to project 2 only
        ws2.send_json({"type": "subscribe", "project_id": 2})
        ws2.receive_json()

        # Broadcast to project 1
        from codeframe.ui.shared import manager
        import asyncio

        async def broadcast():
            await manager.broadcast(
                {"type": "test_result", "project_id": 1, "status": "passed"},
                project_id=1,
            )

        asyncio.run(broadcast())

        # Client 1 receives message
        data1 = ws1.receive_json()
        assert data1["project_id"] == 1

        # Client 2 should NOT receive anything (timeout)
        try:
            ws2.receive_json(timeout=0.1)
            pytest.fail("Client 2 should not receive project 1 broadcasts")
        except TimeoutError:
            pass

        ws1_ctx.__exit__(None, None, None)
        ws2_ctx.__exit__(None, None, None)


class TestSubscribeUnsubscribeFlow:
    """Test subscribe/unsubscribe flow and message filtering."""

    def test_subscribe_to_multiple_projects_sequentially(self, test_client):
        """Test subscribing to multiple projects one after another."""
        with test_client.websocket_connect("/ws") as websocket:
            # Subscribe to project 1
            websocket.send_json({"type": "subscribe", "project_id": 1})
            resp1 = websocket.receive_json()
            assert resp1["project_id"] == 1

            # Subscribe to project 2
            websocket.send_json({"type": "subscribe", "project_id": 2})
            resp2 = websocket.receive_json()
            assert resp2["project_id"] == 2

            # Subscribe to project 3
            websocket.send_json({"type": "subscribe", "project_id": 3})
            resp3 = websocket.receive_json()
            assert resp3["project_id"] == 3

            # Verify all subscriptions are active
            from codeframe.ui.shared import manager
            import asyncio

            async def check():
                # Try broadcasting to each project
                messages_received = []

                # This is a simplified test - in real scenario we'd verify each separately
                async def check_subs():
                    # Access the websocket's subscriptions
                    subs = await manager.subscription_manager.get_subscriptions(
                        websocket
                    )
                    return subs

                subs = await check_subs()
                return subs

            subs = asyncio.run(check())
            assert 1 in subs
            assert 2 in subs
            assert 3 in subs

    def test_resubscribe_to_same_project(self, test_client):
        """Test that resubscribing to same project doesn't cause issues."""
        with test_client.websocket_connect("/ws") as websocket:
            # Subscribe to project 1
            websocket.send_json({"type": "subscribe", "project_id": 1})
            websocket.receive_json()

            # Subscribe to same project again
            websocket.send_json({"type": "subscribe", "project_id": 1})
            websocket.receive_json()

            # Should still work - single subscription
            from codeframe.ui.shared import manager
            import asyncio

            async def check():
                subs = await manager.subscription_manager.get_subscriptions(
                    websocket
                )
                return len(subs)

            sub_count = asyncio.run(check())
            assert sub_count == 1

    def test_unsubscribe_then_resubscribe(self, test_client):
        """Test unsubscribing and then resubscribing to project."""
        with test_client.websocket_connect("/ws") as websocket:
            # Subscribe to project 1
            websocket.send_json({"type": "subscribe", "project_id": 1})
            websocket.receive_json()

            # Unsubscribe
            websocket.send_json({"type": "unsubscribe", "project_id": 1})
            websocket.receive_json()

            # Resubscribe
            websocket.send_json({"type": "subscribe", "project_id": 1})
            websocket.receive_json()

            # Verify subscription is active
            from codeframe.ui.shared import manager
            import asyncio

            async def check():
                subs = await manager.subscription_manager.get_subscriptions(
                    websocket
                )
                return 1 in subs

            is_subscribed = asyncio.run(check())
            assert is_subscribed


class TestDisconnectCleanup:
    """Test disconnect cleanup and subscription removal."""

    def test_disconnect_removes_all_subscriptions(self, test_client):
        """Test that disconnect removes all subscriptions for a client."""
        from codeframe.ui.shared import manager
        import asyncio

        # Create connection
        ws_ctx = test_client.websocket_connect("/ws")
        websocket = ws_ctx.__enter__()

        # Subscribe to multiple projects
        for project_id in [1, 2, 3]:
            websocket.send_json({"type": "subscribe", "project_id": project_id})
            websocket.receive_json()

        # Verify subscriptions before disconnect
        async def check_before():
            subs = await manager.subscription_manager.get_subscriptions(
                websocket
            )
            return len(subs)

        count_before = asyncio.run(check_before())
        assert count_before == 3

        # Disconnect
        ws_ctx.__exit__(None, None, None)

        # Verify subscriptions are gone
        async def check_after():
            subs = await manager.subscription_manager.get_subscriptions(
                websocket
            )
            return len(subs)

        count_after = asyncio.run(check_after())
        assert count_after == 0

    def test_disconnect_during_subscription_cleanup(self, test_client):
        """Test that disconnect properly cleans up even with active subscriptions."""
        from codeframe.ui.shared import manager
        import asyncio

        websocket_refs = []

        # Create multiple connections with subscriptions
        for i in range(3):
            ws_ctx = test_client.websocket_connect("/ws")
            ws = ws_ctx.__enter__()
            websocket_refs.append((ws_ctx, ws))

            # Subscribe to projects
            ws.send_json({"type": "subscribe", "project_id": 1})
            ws.receive_json()

        # Verify all subscriptions exist
        async def count_subscribers():
            subs = await manager.subscription_manager.get_subscribers(1)
            return len(subs)

        count = asyncio.run(count_subscribers())
        assert count == 3

        # Disconnect first client
        websocket_refs[0][0].__exit__(None, None, None)

        # Verify subscription count decreased
        count = asyncio.run(count_subscribers())
        assert count == 2

        # Cleanup remaining
        for ctx, _ in websocket_refs[1:]:
            ctx.__exit__(None, None, None)

        # Verify all cleaned up
        count = asyncio.run(count_subscribers())
        assert count == 0


class TestBackwardCompatibility:
    """Test backward compatibility with unfiltered broadcasts."""

    def test_broadcast_without_project_id_reaches_all_clients(self, test_client):
        """Test that broadcasts without project_id reach all connected clients."""
        ws1_ctx = test_client.websocket_connect("/ws")
        ws1 = ws1_ctx.__enter__()

        ws2_ctx = test_client.websocket_connect("/ws")
        ws2 = ws2_ctx.__enter__()

        # Don't subscribe - just connected
        from codeframe.ui.shared import manager
        import asyncio

        # Broadcast WITHOUT project_id (backward compatible)
        async def broadcast():
            await manager.broadcast(
                {"type": "agent_started", "agent_id": "lead-1"}
                # Note: no project_id parameter
            )

        asyncio.run(broadcast())

        # Both clients should receive the message
        data1 = ws1.receive_json()
        assert data1["type"] == "agent_started"

        data2 = ws2.receive_json()
        assert data2["type"] == "agent_started"

        ws1_ctx.__exit__(None, None, None)
        ws2_ctx.__exit__(None, None, None)

    def test_mixed_subscription_and_unsubscribed_clients(self, test_client):
        """Test mix of subscribed and unsubscribed clients with broadcasts."""
        # Client 1: subscribed to project 1
        ws1_ctx = test_client.websocket_connect("/ws")
        ws1 = ws1_ctx.__enter__()
        ws1.send_json({"type": "subscribe", "project_id": 1})
        ws1.receive_json()

        # Client 2: not subscribed to anything
        ws2_ctx = test_client.websocket_connect("/ws")
        ws2 = ws2_ctx.__enter__()

        from codeframe.ui.shared import manager
        import asyncio

        # Broadcast to project 1 (filtered)
        async def broadcast_filtered():
            await manager.broadcast(
                {"type": "task_status_changed", "task_id": 42},
                project_id=1,
            )

        asyncio.run(broadcast_filtered())

        # Client 1 should receive (subscribed)
        data1 = ws1.receive_json()
        assert data1["type"] == "task_status_changed"

        # Client 2 should NOT receive (not subscribed)
        try:
            ws2.receive_json(timeout=0.1)
            pytest.fail("Unsubscribed client should not receive filtered broadcasts")
        except TimeoutError:
            pass

        # Now broadcast to ALL (no project_id)
        async def broadcast_all():
            await manager.broadcast(
                {"type": "agent_status_changed", "agent_id": "worker-1"}
                # No project_id
            )

        asyncio.run(broadcast_all())

        # Both should receive unfiltered broadcast
        data1 = ws1.receive_json()
        assert data1["type"] == "agent_status_changed"

        data2 = ws2.receive_json()
        assert data2["type"] == "agent_status_changed"

        ws1_ctx.__exit__(None, None, None)
        ws2_ctx.__exit__(None, None, None)


class TestInvalidMessageHandling:
    """Test error handling for invalid subscribe messages."""

    def test_subscribe_with_invalid_project_id_string(self, test_client):
        """Test error handling when project_id is string instead of int."""
        with test_client.websocket_connect("/ws") as websocket:
            # Send subscribe with string project_id
            websocket.send_json({"type": "subscribe", "project_id": "invalid"})

            # Should receive error response
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "invalid" in response["error"].lower() or "project_id" in response["error"].lower()

    def test_subscribe_with_null_project_id(self, test_client):
        """Test error handling when project_id is null."""
        with test_client.websocket_connect("/ws") as websocket:
            # Send subscribe with null project_id
            websocket.send_json({"type": "subscribe", "project_id": None})

            # Should receive error response
            response = websocket.receive_json()
            assert response["type"] == "error"

    def test_subscribe_with_missing_project_id(self, test_client):
        """Test error handling when project_id is missing."""
        with test_client.websocket_connect("/ws") as websocket:
            # Send subscribe without project_id
            websocket.send_json({"type": "subscribe"})

            # Should receive error response
            response = websocket.receive_json()
            assert response["type"] == "error"

    def test_malformed_json_handling(self, test_client):
        """Test error handling for malformed JSON.

        Note: Malformed JSON at receive_text() level causes connection close
        rather than a recoverable error response. This is expected behavior
        as the JSON parsing happens before our error handler.
        """
        # The TestClient WebSocket will raise WebSocketDisconnect when receiving
        # malformed JSON at the receive_text() level
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with test_client.websocket_connect("/ws") as websocket:
                # Send malformed JSON - this will cause receive_text() to fail
                websocket.send("{ invalid json")
                # Try to receive - will raise WebSocketDisconnect
                websocket.receive_json()

    def test_invalid_message_type(self, test_client):
        """Test handling of unknown message types."""
        with test_client.websocket_connect("/ws") as websocket:
            # Send message with unknown type
            websocket.send_json({"type": "unknown_type", "data": "something"})

            # Should handle gracefully (either ignore or send back acknowledgment)
            # The behavior depends on implementation, but shouldn't crash
            # Try to send a valid message after - connection should still work
            websocket.send_json({"type": "ping"})
            response = websocket.receive_json()
            assert response["type"] == "pong"


class TestWebSocketSubscriptionManager:
    """Unit tests for WebSocketSubscriptionManager class."""

    @pytest.mark.asyncio
    async def test_subscribe_new_websocket(self):
        """Test subscribing a new websocket."""
        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, project_id=1)

        subs = await manager.get_subscriptions(ws)
        assert 1 in subs
        assert len(subs) == 1

    @pytest.mark.asyncio
    async def test_subscribe_multiple_projects(self):
        """Test subscribing to multiple projects."""
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
        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        await manager.subscribe(ws, 1)
        await manager.unsubscribe(ws, 1)

        subs = await manager.get_subscriptions(ws)
        assert len(subs) == 0

    @pytest.mark.asyncio
    async def test_cleanup_removes_all_subscriptions(self):
        """Test cleanup removes all subscriptions for a websocket."""
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
        manager = WebSocketSubscriptionManager()
        ws = AsyncMock()

        # Should not raise error
        await manager.cleanup(ws)

        subs = await manager.get_subscriptions(ws)
        assert len(subs) == 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_rapid_subscribe_unsubscribe(self, test_client):
        """Test rapid subscribe/unsubscribe operations."""
        with test_client.websocket_connect("/ws") as websocket:
            # Rapidly subscribe and unsubscribe
            for i in range(10):
                websocket.send_json({"type": "subscribe", "project_id": 1})
                websocket.receive_json()
                websocket.send_json({"type": "unsubscribe", "project_id": 1})
                websocket.receive_json()

            # Connection should still be valid
            websocket.send_json({"type": "ping"})
            response = websocket.receive_json()
            assert response["type"] == "pong"

    def test_large_project_id(self, test_client):
        """Test with very large project IDs."""
        with test_client.websocket_connect("/ws") as websocket:
            large_id = 999999999

            # Subscribe to large project ID
            websocket.send_json({"type": "subscribe", "project_id": large_id})
            response = websocket.receive_json()
            assert response["project_id"] == large_id

            # Broadcast to large project ID
            from codeframe.ui.shared import manager
            import asyncio

            async def broadcast():
                await manager.broadcast(
                    {"type": "test", "data": "test"},
                    project_id=large_id,
                )

            asyncio.run(broadcast())

            # Should receive
            data = websocket.receive_json()
            assert data["type"] == "test"

    def test_zero_project_id_rejected(self, test_client):
        """Test that project_id of 0 is rejected."""
        with test_client.websocket_connect("/ws") as websocket:
            # Try to subscribe to project 0
            websocket.send_json({"type": "subscribe", "project_id": 0})
            response = websocket.receive_json()
            # Should receive error
            assert response["type"] == "error"
            assert "positive" in response["error"].lower()

    def test_negative_project_id_rejected(self, test_client):
        """Test that negative project IDs are rejected."""
        with test_client.websocket_connect("/ws") as websocket:
            # Try to subscribe to negative project ID
            websocket.send_json({"type": "subscribe", "project_id": -1})

            # Should receive error
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "positive" in response["error"].lower()

            # Connection should still work
            websocket.send_json({"type": "ping"})
            pong = websocket.receive_json()
            assert pong["type"] == "pong"
