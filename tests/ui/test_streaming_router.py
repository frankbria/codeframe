"""Tests for SSE streaming router.

Tests for SSE event formatting, publisher management, and
the event_stream_generator used by /api/v2/tasks/{task_id}/stream.
"""

import json

from codeframe.core.models import (
    ProgressEvent,
    OutputEvent,
    CompletionEvent,
    HeartbeatEvent,
)


class TestSSEEventFormat:
    """Tests for SSE event formatting."""

    def test_progress_event_sse_format(self):
        """ProgressEvent should format correctly for SSE."""
        from codeframe.ui.routers.streaming_v2 import format_sse_event

        event = ProgressEvent(
            task_id="task-1",
            phase="execution",
            step=2,
            total_steps=5,
            message="Running tests",
        )

        sse_data = format_sse_event(event)

        assert sse_data.startswith("data:")
        assert sse_data.endswith("\n\n")

        # Extract JSON
        json_str = sse_data[5:-2].strip()
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "progress"
        assert parsed["task_id"] == "task-1"
        assert parsed["data"]["phase"] == "execution"
        assert parsed["data"]["step"] == 2

    def test_output_event_sse_format(self):
        """OutputEvent should include stream and line in SSE format."""
        from codeframe.ui.routers.streaming_v2 import format_sse_event

        event = OutputEvent(
            task_id="task-1",
            stream="stdout",
            line="Test output line\n",
        )

        sse_data = format_sse_event(event)
        json_str = sse_data[5:-2].strip()
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "output"
        assert parsed["data"]["stream"] == "stdout"
        assert parsed["data"]["line"] == "Test output line\n"

    def test_completion_event_sse_format(self):
        """CompletionEvent should include status and duration."""
        from codeframe.ui.routers.streaming_v2 import format_sse_event

        event = CompletionEvent(
            task_id="task-1",
            status="completed",
            duration_seconds=42.5,
            files_modified=["a.py", "b.py"],
        )

        sse_data = format_sse_event(event)
        json_str = sse_data[5:-2].strip()
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "completion"
        assert parsed["data"]["status"] == "completed"
        assert parsed["data"]["duration_seconds"] == 42.5
        assert parsed["data"]["files_modified"] == ["a.py", "b.py"]

    def test_heartbeat_event_sse_format(self):
        """HeartbeatEvent should be minimal in SSE format."""
        from codeframe.ui.routers.streaming_v2 import format_sse_event

        event = HeartbeatEvent(task_id="task-1")

        sse_data = format_sse_event(event)
        json_str = sse_data[5:-2].strip()
        parsed = json.loads(json_str)

        assert parsed["event_type"] == "heartbeat"

    def test_sse_comment_format(self):
        """SSE comments should start with colon."""
        from codeframe.ui.routers.streaming_v2 import format_sse_comment

        comment = format_sse_comment("heartbeat")

        assert comment.startswith(":")
        assert comment.endswith("\n\n")
        assert "heartbeat" in comment


class TestStreamingRouterEndpoint:
    """Tests for streaming router configuration.

    NOTE: The SSE stream endpoint (GET /api/v2/tasks/{task_id}/stream) lives
    in tasks_v2.py. It only requires workspace_path, making it compatible
    with browser EventSource which cannot send custom auth headers.
    streaming_v2.py provides shared utilities only (no endpoints).
    """

    def test_streaming_router_has_no_endpoints(self):
        """streaming_v2 router should have no endpoints (utilities only)."""
        from codeframe.ui.routers.streaming_v2 import router

        assert len(router.routes) == 0


class TestEventPublisherGlobal:
    """Tests for global EventPublisher management."""

    def test_get_event_publisher_singleton(self):
        """get_event_publisher should return the same instance."""
        from codeframe.ui.routers.streaming_v2 import (
            get_event_publisher,
            set_event_publisher,
        )

        # Reset to None first
        set_event_publisher(None)

        pub1 = get_event_publisher()
        pub2 = get_event_publisher()

        assert pub1 is pub2

        # Clean up
        set_event_publisher(None)

    def test_set_event_publisher(self):
        """set_event_publisher should override the global instance."""
        from codeframe.core.streaming import EventPublisher
        from codeframe.ui.routers.streaming_v2 import (
            get_event_publisher,
            set_event_publisher,
        )

        custom_publisher = EventPublisher()
        set_event_publisher(custom_publisher)

        assert get_event_publisher() is custom_publisher

        # Clean up
        set_event_publisher(None)
