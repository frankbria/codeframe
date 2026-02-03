"""Tests for execution event models.

TDD: Tests written first to define the expected behavior of
ExecutionEvent models used for SSE/WebSocket streaming.
"""

import json
from datetime import datetime



class TestExecutionEventModels:
    """Tests for ExecutionEvent Pydantic models."""

    def test_progress_event_serialization(self):
        """ProgressEvent should serialize to JSON with all fields."""
        from codeframe.core.models import ProgressEvent

        event = ProgressEvent(
            task_id="task-123",
            phase="planning",
            step=1,
            total_steps=5,
            message="Generating implementation plan",
        )

        data = event.model_dump()
        assert data["event_type"] == "progress"
        assert data["task_id"] == "task-123"
        assert data["data"]["phase"] == "planning"
        assert data["data"]["step"] == 1
        assert data["data"]["total_steps"] == 5
        assert data["data"]["message"] == "Generating implementation plan"
        assert "timestamp" in data

    def test_output_event_serialization(self):
        """OutputEvent should serialize stdout/stderr lines."""
        from codeframe.core.models import OutputEvent

        event = OutputEvent(
            task_id="task-123",
            stream="stdout",
            line="Running pytest tests...\n",
        )

        data = event.model_dump()
        assert data["event_type"] == "output"
        assert data["task_id"] == "task-123"
        assert data["data"]["stream"] == "stdout"
        assert data["data"]["line"] == "Running pytest tests...\n"

    def test_blocker_event_serialization(self):
        """BlockerEvent should include blocker details."""
        from codeframe.core.models import BlockerEvent

        event = BlockerEvent(
            task_id="task-123",
            blocker_id=42,
            question="Which authentication method should I use?",
            context="The task requires user authentication",
        )

        data = event.model_dump()
        assert data["event_type"] == "blocker"
        assert data["task_id"] == "task-123"
        assert data["data"]["blocker_id"] == 42
        assert data["data"]["question"] == "Which authentication method should I use?"
        assert data["data"]["context"] == "The task requires user authentication"

    def test_completion_event_serialization(self):
        """CompletionEvent should include status and duration."""
        from codeframe.core.models import CompletionEvent

        event = CompletionEvent(
            task_id="task-123",
            status="completed",
            duration_seconds=125.5,
            files_modified=["src/auth.py", "tests/test_auth.py"],
        )

        data = event.model_dump()
        assert data["event_type"] == "completion"
        assert data["task_id"] == "task-123"
        assert data["data"]["status"] == "completed"
        assert data["data"]["duration_seconds"] == 125.5
        assert data["data"]["files_modified"] == ["src/auth.py", "tests/test_auth.py"]

    def test_error_event_serialization(self):
        """ErrorEvent should include error details and optional traceback."""
        from codeframe.core.models import ErrorEvent

        event = ErrorEvent(
            task_id="task-123",
            error="Failed to parse Python file",
            error_type="SyntaxError",
            traceback="  File 'test.py', line 10\n    def foo(\n         ^",
        )

        data = event.model_dump()
        assert data["event_type"] == "error"
        assert data["task_id"] == "task-123"
        assert data["data"]["error"] == "Failed to parse Python file"
        assert data["data"]["error_type"] == "SyntaxError"
        assert "traceback" in data["data"]

    def test_error_event_without_traceback(self):
        """ErrorEvent should work without optional traceback."""
        from codeframe.core.models import ErrorEvent

        event = ErrorEvent(
            task_id="task-123",
            error="Network timeout",
            error_type="ConnectionError",
        )

        data = event.model_dump()
        assert data["data"]["traceback"] is None

    def test_event_json_serialization(self):
        """Events should serialize to valid JSON for SSE."""
        from codeframe.core.models import ProgressEvent

        event = ProgressEvent(
            task_id="task-123",
            phase="execution",
            step=2,
            total_steps=5,
            message="Executing step 2",
        )

        # Should be valid JSON
        json_str = event.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "progress"

    def test_event_timestamp_is_utc(self):
        """Event timestamps should be timezone-aware UTC."""
        from codeframe.core.models import ProgressEvent

        event = ProgressEvent(
            task_id="task-123",
            phase="planning",
            step=1,
            total_steps=1,
        )

        # Timestamp should be a valid ISO format string
        data = event.model_dump()
        timestamp = datetime.fromisoformat(data["timestamp"])
        assert timestamp.tzinfo is not None

    def test_heartbeat_event_serialization(self):
        """HeartbeatEvent should be minimal for keep-alive."""
        from codeframe.core.models import HeartbeatEvent

        event = HeartbeatEvent(task_id="task-123")

        data = event.model_dump()
        assert data["event_type"] == "heartbeat"
        assert data["task_id"] == "task-123"


class TestExecutionEventTypes:
    """Tests for event type literals and validation."""

    def test_event_type_literals(self):
        """Event types should be restricted to valid values."""
        from codeframe.core.models import ExecutionEventType

        assert "progress" in ExecutionEventType.__args__
        assert "output" in ExecutionEventType.__args__
        assert "blocker" in ExecutionEventType.__args__
        assert "completion" in ExecutionEventType.__args__
        assert "error" in ExecutionEventType.__args__
        assert "heartbeat" in ExecutionEventType.__args__

    def test_event_factory_function(self):
        """create_execution_event should create the right event type."""
        from codeframe.core.models import create_execution_event

        # Progress event
        progress = create_execution_event(
            "progress",
            task_id="task-1",
            phase="planning",
            step=1,
            total_steps=3,
        )
        assert progress.event_type == "progress"

        # Output event
        output = create_execution_event(
            "output",
            task_id="task-1",
            stream="stdout",
            line="test output",
        )
        assert output.event_type == "output"

        # Error event
        error = create_execution_event(
            "error",
            task_id="task-1",
            error="Something failed",
            error_type="RuntimeError",
        )
        assert error.event_type == "error"
