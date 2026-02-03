"""Tests for SSE streaming router.

TDD: Tests written first to define expected behavior of
the /api/v2/tasks/{task_id}/stream SSE endpoint.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.models import (
    ProgressEvent,
    OutputEvent,
    CompletionEvent,
    HeartbeatEvent,
)


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    from codeframe.auth import User
    return User(id=1, email="test@example.com", hashed_password="!DISABLED!")


@pytest.fixture
def mock_workspace(tmp_path):
    """Create a mock workspace."""
    from codeframe.core.workspace import Workspace
    from datetime import datetime, timezone

    workspace = Workspace(
        id="test-workspace-id",
        repo_path=tmp_path,
        state_dir=tmp_path / ".codeframe",
        created_at=datetime.now(timezone.utc),
    )
    # Create state directory
    workspace.state_dir.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def app_with_streaming(mock_user, mock_workspace, monkeypatch):
    """Create a FastAPI app with the streaming router and mocked dependencies."""
    from codeframe.ui.routers.streaming_v2 import router
    from codeframe.auth.dependencies import get_current_user
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.core import tasks

    # Create a mock task
    from unittest.mock import MagicMock
    mock_task = MagicMock()
    mock_task.id = "test-task"
    mock_task.title = "Test Task"

    # Patch tasks.get to return our mock task
    monkeypatch.setattr(tasks, "get", lambda workspace, task_id: mock_task)

    app = FastAPI()
    app.include_router(router)

    # Override dependencies
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_v2_workspace] = lambda: mock_workspace

    return app


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
    """Tests for streaming router endpoint configuration."""

    def test_endpoint_exists(self, app_with_streaming):
        """The streaming endpoint should be registered."""
        client = TestClient(app_with_streaming)

        # Get the OpenAPI schema to verify endpoint exists
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema.get("paths", {})

        # Verify the stream endpoint is registered
        assert "/api/v2/tasks/{task_id}/stream" in paths
        assert "get" in paths["/api/v2/tasks/{task_id}/stream"]

    def test_endpoint_returns_streaming_response(self, app_with_streaming):
        """The endpoint should return a streaming response with SSE content type."""
        from codeframe.core.streaming import EventPublisher
        from codeframe.ui.routers import streaming_v2

        # Inject a publisher that immediately completes the task
        publisher = EventPublisher()
        streaming_v2.set_event_publisher(publisher)

        try:
            client = TestClient(app_with_streaming)

            # Use stream=True but set a short timeout via the client
            # and complete the task immediately
            import threading
            import time

            def complete_task():
                time.sleep(0.1)
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(publisher.complete_task("test-task"))
                loop.close()

            thread = threading.Thread(target=complete_task)
            thread.start()

            # The TestClient doesn't easily support streaming,
            # so we just verify the endpoint starts without error
            # Real streaming tests require async client
            with client.stream("GET", "/api/v2/tasks/test-task/stream") as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                # Read at most a small amount before breaking
                break_after = 0
                for _ in response.iter_lines():
                    break_after += 1
                    if break_after > 0:
                        break

            thread.join(timeout=2.0)
        finally:
            streaming_v2.set_event_publisher(None)


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
