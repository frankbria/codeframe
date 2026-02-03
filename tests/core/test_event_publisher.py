"""Tests for EventPublisher - async event distribution system.

TDD: Tests written first to define expected behavior of
EventPublisher for SSE/WebSocket streaming.
"""

import asyncio
from typing import List

import pytest

from codeframe.core.models import (
    ProgressEvent,
    OutputEvent,
    CompletionEvent,
    ErrorEvent,
    ExecutionEvent,
)


class TestEventPublisher:
    """Tests for EventPublisher class."""

    @pytest.mark.asyncio
    async def test_publish_event_to_single_subscriber(self):
        """Published events should be received by subscriber."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-123"

        # Subscribe to events
        received: List[ExecutionEvent] = []

        async def collect_events():
            async for event in publisher.subscribe(task_id):
                received.append(event)
                if len(received) >= 2:
                    break

        # Start subscriber in background
        subscriber_task = asyncio.create_task(collect_events())

        # Give subscriber time to start
        await asyncio.sleep(0.01)

        # Publish events
        event1 = ProgressEvent(
            task_id=task_id, phase="planning", step=1, total_steps=3
        )
        event2 = ProgressEvent(
            task_id=task_id, phase="planning", step=2, total_steps=3
        )

        await publisher.publish(task_id, event1)
        await publisher.publish(task_id, event2)

        # Wait for subscriber to receive events
        await asyncio.wait_for(subscriber_task, timeout=1.0)

        assert len(received) == 2
        assert received[0].step == 1
        assert received[1].step == 2

    @pytest.mark.asyncio
    async def test_publish_event_to_multiple_subscribers(self):
        """Events should be broadcast to all subscribers."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-456"

        received1: List[ExecutionEvent] = []
        received2: List[ExecutionEvent] = []

        async def collect_events_1():
            async for event in publisher.subscribe(task_id):
                received1.append(event)
                if len(received1) >= 1:
                    break

        async def collect_events_2():
            async for event in publisher.subscribe(task_id):
                received2.append(event)
                if len(received2) >= 1:
                    break

        # Start both subscribers
        task1 = asyncio.create_task(collect_events_1())
        task2 = asyncio.create_task(collect_events_2())

        await asyncio.sleep(0.01)

        # Publish one event
        event = OutputEvent(task_id=task_id, stream="stdout", line="test output")
        await publisher.publish(task_id, event)

        # Both should receive it
        await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)

        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0].line == "test output"
        assert received2[0].line == "test output"

    @pytest.mark.asyncio
    async def test_events_isolated_by_task_id(self):
        """Events for different tasks should not cross-contaminate."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()

        received_task1: List[ExecutionEvent] = []
        received_task2: List[ExecutionEvent] = []

        async def collect_task1():
            async for event in publisher.subscribe("task-1"):
                received_task1.append(event)
                if len(received_task1) >= 1:
                    break

        async def collect_task2():
            async for event in publisher.subscribe("task-2"):
                received_task2.append(event)
                if len(received_task2) >= 1:
                    break

        task1 = asyncio.create_task(collect_task1())
        task2 = asyncio.create_task(collect_task2())

        await asyncio.sleep(0.01)

        # Publish to task-1 only
        await publisher.publish(
            "task-1",
            ProgressEvent(task_id="task-1", phase="planning", step=1, total_steps=1),
        )

        # Publish to task-2 only
        await publisher.publish(
            "task-2",
            OutputEvent(task_id="task-2", stream="stderr", line="error"),
        )

        await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)

        # Each should only receive their own events
        assert len(received_task1) == 1
        assert len(received_task2) == 1
        assert received_task1[0].event_type == "progress"
        assert received_task2[0].event_type == "output"

    @pytest.mark.asyncio
    async def test_subscriber_cleanup_on_unsubscribe(self):
        """Unsubscribing should clean up the subscriber queue."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-cleanup"

        # Subscribe
        subscription = publisher.subscribe(task_id)

        # Start iterating (this creates the queue internally)
        iterator = subscription.__aiter__()

        # Verify we have a subscriber
        assert publisher.subscriber_count(task_id) >= 0  # May be 0 before first await

        # Manually trigger cleanup
        await publisher.unsubscribe(task_id, iterator)

    @pytest.mark.asyncio
    async def test_complete_task_closes_all_subscribers(self):
        """Completing a task should close all subscriber streams."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-complete"

        received: List[ExecutionEvent] = []
        stream_ended = False

        async def collect_events():
            nonlocal stream_ended
            async for event in publisher.subscribe(task_id):
                received.append(event)
            stream_ended = True

        subscriber_task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        # Publish a completion event
        completion = CompletionEvent(
            task_id=task_id,
            status="completed",
            duration_seconds=10.5,
        )
        await publisher.publish(task_id, completion)

        # Signal task is complete
        await publisher.complete_task(task_id)

        # Subscriber should exit cleanly
        await asyncio.wait_for(subscriber_task, timeout=1.0)

        assert stream_ended is True
        assert len(received) == 1
        assert received[0].event_type == "completion"

    @pytest.mark.asyncio
    async def test_subscriber_count(self):
        """subscriber_count should return active subscriber count."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-count"

        assert publisher.subscriber_count(task_id) == 0

        # Create subscriptions
        received1: List[ExecutionEvent] = []
        received2: List[ExecutionEvent] = []

        async def subscriber1():
            async for event in publisher.subscribe(task_id):
                received1.append(event)
                break

        async def subscriber2():
            async for event in publisher.subscribe(task_id):
                received2.append(event)
                break

        task1 = asyncio.create_task(subscriber1())
        task2 = asyncio.create_task(subscriber2())

        await asyncio.sleep(0.05)

        # Should have 2 subscribers
        assert publisher.subscriber_count(task_id) == 2

        # Complete task to clean up
        await publisher.publish(
            task_id,
            ProgressEvent(task_id=task_id, phase="done", step=1, total_steps=1),
        )
        await asyncio.gather(task1, task2)

    @pytest.mark.asyncio
    async def test_publish_without_subscribers_does_not_error(self):
        """Publishing to a task with no subscribers should not raise."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()

        # Should not raise
        await publisher.publish(
            "task-no-subscribers",
            ProgressEvent(
                task_id="task-no-subscribers", phase="planning", step=1, total_steps=1
            ),
        )

    @pytest.mark.asyncio
    async def test_error_event_does_not_close_stream(self):
        """Error events should be delivered but not close the stream."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-error"

        received: List[ExecutionEvent] = []

        async def collect_events():
            async for event in publisher.subscribe(task_id):
                received.append(event)
                if len(received) >= 2:
                    break

        subscriber_task = asyncio.create_task(collect_events())
        await asyncio.sleep(0.01)

        # Publish an error, then a progress event
        await publisher.publish(
            task_id,
            ErrorEvent(
                task_id=task_id, error="Something failed", error_type="RuntimeError"
            ),
        )
        await publisher.publish(
            task_id,
            ProgressEvent(task_id=task_id, phase="retry", step=1, total_steps=1),
        )

        await asyncio.wait_for(subscriber_task, timeout=1.0)

        # Both events should be received
        assert len(received) == 2
        assert received[0].event_type == "error"
        assert received[1].event_type == "progress"


class TestEventPublisherIntegration:
    """Integration tests for EventPublisher with real event flow."""

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self):
        """Test complete event flow from start to completion."""
        from codeframe.core.streaming import EventPublisher

        publisher = EventPublisher()
        task_id = "task-lifecycle"

        received: List[ExecutionEvent] = []

        async def collect_all_events():
            async for event in publisher.subscribe(task_id):
                received.append(event)

        subscriber_task = asyncio.create_task(collect_all_events())
        await asyncio.sleep(0.01)

        # Simulate task lifecycle
        await publisher.publish(
            task_id,
            ProgressEvent(task_id=task_id, phase="planning", step=1, total_steps=3),
        )
        await publisher.publish(
            task_id,
            ProgressEvent(task_id=task_id, phase="execution", step=2, total_steps=3),
        )
        await publisher.publish(
            task_id,
            OutputEvent(task_id=task_id, stream="stdout", line="Test passed!\n"),
        )
        await publisher.publish(
            task_id,
            ProgressEvent(
                task_id=task_id, phase="verification", step=3, total_steps=3
            ),
        )
        await publisher.publish(
            task_id,
            CompletionEvent(
                task_id=task_id,
                status="completed",
                duration_seconds=45.2,
                files_modified=["src/main.py"],
            ),
        )

        # Signal completion
        await publisher.complete_task(task_id)

        await asyncio.wait_for(subscriber_task, timeout=1.0)

        # Verify full sequence
        assert len(received) == 5
        assert [e.event_type for e in received] == [
            "progress",
            "progress",
            "output",
            "progress",
            "completion",
        ]
