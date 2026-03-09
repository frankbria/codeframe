"""Tests for AgentAdapter protocol and supporting types.

Validates:
- Dataclass construction with defaults and full params
- AgentResultStatus enum values
- AgentAdapter protocol compliance via @runtime_checkable
- Streaming iterator contract
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class TestAgentResultStatus:
    """AgentResultStatus enum covers all terminal states."""

    def test_has_completed(self):
        from codeframe.core.agent_adapter import AgentResultStatus
        assert AgentResultStatus.COMPLETED.value == "completed"

    def test_has_failed(self):
        from codeframe.core.agent_adapter import AgentResultStatus
        assert AgentResultStatus.FAILED.value == "failed"

    def test_has_blocked(self):
        from codeframe.core.agent_adapter import AgentResultStatus
        assert AgentResultStatus.BLOCKED.value == "blocked"

    def test_has_timeout(self):
        from codeframe.core.agent_adapter import AgentResultStatus
        assert AgentResultStatus.TIMEOUT.value == "timeout"

    def test_is_str_enum(self):
        from codeframe.core.agent_adapter import AgentResultStatus
        assert isinstance(AgentResultStatus.COMPLETED, str)


class TestAdapterTokenUsage:
    """Lightweight token usage dataclass."""

    def test_minimal_construction(self):
        from codeframe.core.agent_adapter import AdapterTokenUsage
        usage = AdapterTokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.model is None
        assert usage.cost_usd is None

    def test_full_construction(self):
        from codeframe.core.agent_adapter import AdapterTokenUsage
        usage = AdapterTokenUsage(
            input_tokens=1000,
            output_tokens=500,
            model="claude-sonnet-4-20250514",
            cost_usd=0.015,
        )
        assert usage.model == "claude-sonnet-4-20250514"
        assert usage.cost_usd == 0.015

    def test_total_tokens(self):
        from codeframe.core.agent_adapter import AdapterTokenUsage
        usage = AdapterTokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150


class TestAgentContext:
    """AgentContext captures all context CodeFrame provides to engines."""

    def test_minimal_construction(self):
        from codeframe.core.agent_adapter import AgentContext
        ctx = AgentContext(
            task_id="task-1",
            task_title="Implement feature X",
            task_description="Add X to the system",
        )
        assert ctx.task_id == "task-1"
        assert ctx.prd_content is None
        assert ctx.tech_stack is None
        assert ctx.project_preferences is None
        assert ctx.relevant_files == []
        assert ctx.file_contents == {}
        assert ctx.blocker_history == []
        assert ctx.dependency_context is None
        assert ctx.verification_gates == []
        assert ctx.attempt == 0
        assert ctx.previous_errors == []

    def test_full_construction(self):
        from codeframe.core.agent_adapter import AgentContext
        ctx = AgentContext(
            task_id="task-42",
            task_title="Fix auth bug",
            task_description="Session tokens expire too early",
            prd_content="# Auth PRD\nTokens should last 24h",
            tech_stack="Python with FastAPI",
            project_preferences="Use ruff for linting",
            relevant_files=["auth.py", "tests/test_auth.py"],
            file_contents={"auth.py": "def login(): pass"},
            blocker_history=["Previous: needed DB access"],
            dependency_context="Task-41 created the auth module",
            verification_gates=["ruff", "pytest"],
            attempt=2,
            previous_errors=["ImportError: no module named jwt"],
        )
        assert ctx.task_id == "task-42"
        assert len(ctx.relevant_files) == 2
        assert ctx.attempt == 2
        assert len(ctx.previous_errors) == 1

    def test_list_defaults_are_independent(self):
        """Ensure default_factory creates independent lists (no shared mutable state)."""
        from codeframe.core.agent_adapter import AgentContext
        ctx1 = AgentContext(task_id="1", task_title="A", task_description="A")
        ctx2 = AgentContext(task_id="2", task_title="B", task_description="B")
        ctx1.relevant_files.append("file.py")
        assert ctx2.relevant_files == []


class TestAgentResult:
    """AgentResult captures outcome from any engine."""

    def test_minimal_construction(self):
        from codeframe.core.agent_adapter import AgentResult, AgentResultStatus
        result = AgentResult(
            status=AgentResultStatus.COMPLETED,
            summary="Added feature X",
        )
        assert result.status == AgentResultStatus.COMPLETED
        assert result.files_modified == []
        assert result.files_created == []
        assert result.error is None
        assert result.blocker_question is None
        assert result.token_usage is None
        assert result.duration_ms == 0

    def test_failed_result(self):
        from codeframe.core.agent_adapter import AgentResult, AgentResultStatus
        result = AgentResult(
            status=AgentResultStatus.FAILED,
            summary="Could not implement",
            error="ImportError: missing dependency",
            duration_ms=5000,
        )
        assert result.status == AgentResultStatus.FAILED
        assert result.error is not None

    def test_blocked_result_with_question(self):
        from codeframe.core.agent_adapter import AgentResult, AgentResultStatus
        result = AgentResult(
            status=AgentResultStatus.BLOCKED,
            summary="Need clarification on auth approach",
            blocker_question="Should we use JWT or session cookies?",
        )
        assert result.blocker_question is not None

    def test_result_with_token_usage(self):
        from codeframe.core.agent_adapter import (
            AdapterTokenUsage, AgentResult, AgentResultStatus,
        )
        result = AgentResult(
            status=AgentResultStatus.COMPLETED,
            summary="Done",
            token_usage=AdapterTokenUsage(input_tokens=1000, output_tokens=500),
            files_modified=["auth.py"],
            files_created=["tests/test_auth.py"],
            duration_ms=12000,
        )
        assert result.token_usage.total_tokens == 1500
        assert result.files_modified == ["auth.py"]
        assert result.duration_ms == 12000


class TestAgentEvent:
    """AgentEvent supports progress streaming."""

    def test_minimal_construction(self):
        from codeframe.core.agent_adapter import AgentEvent
        event = AgentEvent(type="progress", message="Working on step 1")
        assert event.type == "progress"
        assert event.message == "Working on step 1"
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_with_metadata(self):
        from codeframe.core.agent_adapter import AgentEvent
        ts = datetime(2026, 3, 9, tzinfo=timezone.utc)
        event = AgentEvent(
            type="file_changed",
            message="Modified auth.py",
            timestamp=ts,
            metadata={"file": "auth.py", "lines_changed": 15},
        )
        assert event.timestamp == ts
        assert event.metadata["lines_changed"] == 15

    def test_event_types_are_strings(self):
        from codeframe.core.agent_adapter import AgentEvent
        for event_type in ("progress", "file_changed", "command_run", "error"):
            event = AgentEvent(type=event_type, message="test")
            assert event.type == event_type


class TestAgentAdapterProtocol:
    """AgentAdapter protocol compliance via @runtime_checkable."""

    def _make_compliant_class(self):
        """Create a minimal class that satisfies AgentAdapter."""
        from codeframe.core.agent_adapter import (
            AgentContext, AgentEvent, AgentResult, AgentResultStatus,
        )

        class FakeAdapter:
            def execute(
                self,
                task_prompt: str,
                workspace_path: Path,
                context: AgentContext,
                timeout_ms: int = 3_600_000,
            ) -> AgentResult:
                return AgentResult(
                    status=AgentResultStatus.COMPLETED,
                    summary="fake",
                    duration_ms=100,
                )

            def stream_events(self) -> Iterator[AgentEvent]:
                yield AgentEvent(type="progress", message="working")

            @property
            def name(self) -> str:
                return "fake"

            @property
            def requires_api_key(self) -> dict[str, str]:
                return {}

        return FakeAdapter

    def test_compliant_class_satisfies_protocol(self):
        from codeframe.core.agent_adapter import AgentAdapter
        FakeAdapter = self._make_compliant_class()
        adapter = FakeAdapter()
        assert isinstance(adapter, AgentAdapter)

    def test_non_compliant_class_fails(self):
        from codeframe.core.agent_adapter import AgentAdapter

        class NotAnAdapter:
            pass

        assert not isinstance(NotAnAdapter(), AgentAdapter)

    def test_partial_implementation_fails(self):
        from codeframe.core.agent_adapter import AgentAdapter

        class PartialAdapter:
            def execute(self, task_prompt, workspace_path, context, timeout_ms=0):
                pass
            # Missing: stream_events, name, requires_api_key

        assert not isinstance(PartialAdapter(), AgentAdapter)

    def test_execute_returns_agent_result(self):
        from codeframe.core.agent_adapter import (
            AgentContext, AgentResult, AgentResultStatus,
        )
        FakeAdapter = self._make_compliant_class()
        adapter = FakeAdapter()
        ctx = AgentContext(task_id="1", task_title="Test", task_description="Test")
        result = adapter.execute("do something", Path("/tmp"), ctx)
        assert isinstance(result, AgentResult)
        assert result.status == AgentResultStatus.COMPLETED

    def test_stream_events_yields_agent_events(self):
        from codeframe.core.agent_adapter import AgentEvent
        FakeAdapter = self._make_compliant_class()
        adapter = FakeAdapter()
        events_list = list(adapter.stream_events())
        assert len(events_list) == 1
        assert isinstance(events_list[0], AgentEvent)
