"""Tests for agent adapter protocol and data types."""

from pathlib import Path

from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent, AgentResult


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_completed_result(self):
        result = AgentResult(status="completed", output="Task done")
        assert result.status == "completed"
        assert result.output == "Task done"
        assert result.modified_files == []
        assert result.error is None
        assert result.blocker_question is None

    def test_failed_result_with_error(self):
        result = AgentResult(status="failed", error="Tests failed")
        assert result.status == "failed"
        assert result.error == "Tests failed"

    def test_blocked_result_with_question(self):
        result = AgentResult(
            status="blocked",
            blocker_question="Which database should I use?",
        )
        assert result.status == "blocked"
        assert result.blocker_question == "Which database should I use?"

    def test_result_with_modified_files(self):
        result = AgentResult(
            status="completed",
            modified_files=["src/main.py", "tests/test_main.py"],
        )
        assert len(result.modified_files) == 2

    def test_default_values(self):
        result = AgentResult(status="completed")
        assert result.output == ""
        assert result.modified_files == []
        assert result.error is None
        assert result.blocker_question is None


class TestAgentEvent:
    """Tests for AgentEvent dataclass."""

    def test_event_creation(self):
        event = AgentEvent(type="progress", data={"step": 1})
        assert event.type == "progress"
        assert event.data == {"step": 1}

    def test_event_default_data(self):
        event = AgentEvent(type="output")
        assert event.data == {}


class TestAgentAdapterProtocol:
    """Tests for AgentAdapter protocol compliance."""

    def test_protocol_is_runtime_checkable(self):
        """Verify the protocol can be checked at runtime."""

        class MockAdapter:
            @property
            def name(self) -> str:
                return "mock"

            def run(self, task_id, prompt, workspace_path, on_event=None):
                return AgentResult(status="completed")

        adapter = MockAdapter()
        assert isinstance(adapter, AgentAdapter)

    def test_non_conforming_class_fails_check(self):
        """A class without the right methods should not match the protocol."""

        class NotAnAdapter:
            pass

        assert not isinstance(NotAnAdapter(), AgentAdapter)

    def test_partial_implementation_fails_check(self):
        """A class with only some methods should not match."""

        class PartialAdapter:
            @property
            def name(self) -> str:
                return "partial"

            # Missing run()

        assert not isinstance(PartialAdapter(), AgentAdapter)

    def test_adapter_can_stream_events(self):
        """Verify on_event callback works during execution."""
        events_received: list[AgentEvent] = []

        class StreamingAdapter:
            @property
            def name(self) -> str:
                return "streaming"

            def run(self, task_id, prompt, workspace_path, on_event=None):
                if on_event:
                    on_event(AgentEvent(type="progress", data={"step": 1}))
                    on_event(AgentEvent(type="output", data={"line": "hello"}))
                return AgentResult(status="completed")

        adapter = StreamingAdapter()
        adapter.run("task-1", "do stuff", Path("/tmp"), on_event=events_received.append)
        assert len(events_received) == 2
        assert events_received[0].type == "progress"
        assert events_received[1].type == "output"
