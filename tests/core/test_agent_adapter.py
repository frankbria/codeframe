"""Tests for AgentAdapter protocol and supporting types.

Tests the types added by #409 (AgentContext, AdapterTokenUsage, AgentResultStatus)
merged into the canonical protocol at codeframe.core.adapters.agent_adapter.

Validates:
- Dataclass construction with defaults and full params
- AgentResultStatus enum values
- AgentContext field completeness
- AdapterTokenUsage arithmetic
- AgentResult and AgentEvent field extensions
"""

import pytest
from datetime import datetime, timezone

pytestmark = pytest.mark.v2


class TestAgentResultStatus:
    """AgentResultStatus enum covers all terminal states."""

    def test_has_completed(self):
        from codeframe.core.adapters.agent_adapter import AgentResultStatus
        assert AgentResultStatus.COMPLETED.value == "completed"

    def test_has_failed(self):
        from codeframe.core.adapters.agent_adapter import AgentResultStatus
        assert AgentResultStatus.FAILED.value == "failed"

    def test_has_blocked(self):
        from codeframe.core.adapters.agent_adapter import AgentResultStatus
        assert AgentResultStatus.BLOCKED.value == "blocked"

    def test_has_timeout(self):
        from codeframe.core.adapters.agent_adapter import AgentResultStatus
        assert AgentResultStatus.TIMEOUT.value == "timeout"

    def test_is_str_enum(self):
        from codeframe.core.adapters.agent_adapter import AgentResultStatus
        assert isinstance(AgentResultStatus.COMPLETED, str)


class TestAdapterTokenUsage:
    """Lightweight token usage dataclass."""

    def test_minimal_construction(self):
        from codeframe.core.adapters.agent_adapter import AdapterTokenUsage
        usage = AdapterTokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.model is None
        assert usage.cost_usd is None

    def test_full_construction(self):
        from codeframe.core.adapters.agent_adapter import AdapterTokenUsage
        usage = AdapterTokenUsage(
            input_tokens=1000,
            output_tokens=500,
            model="claude-sonnet-4-20250514",
            cost_usd=0.015,
        )
        assert usage.model == "claude-sonnet-4-20250514"
        assert usage.cost_usd == 0.015

    def test_total_tokens(self):
        from codeframe.core.adapters.agent_adapter import AdapterTokenUsage
        usage = AdapterTokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150


class TestAgentContext:
    """AgentContext captures all context CodeFrame provides to engines."""

    def test_minimal_construction(self):
        from codeframe.core.adapters.agent_adapter import AgentContext
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
        from codeframe.core.adapters.agent_adapter import AgentContext
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
        from codeframe.core.adapters.agent_adapter import AgentContext
        ctx1 = AgentContext(task_id="1", task_title="A", task_description="A")
        ctx2 = AgentContext(task_id="2", task_title="B", task_description="B")
        ctx1.relevant_files.append("file.py")
        assert ctx2.relevant_files == []


class TestAgentResultExtensions:
    """Tests for #409 extensions to AgentResult (token_usage, duration_ms)."""

    def test_result_with_token_usage(self):
        from codeframe.core.adapters.agent_adapter import (
            AdapterTokenUsage, AgentResult,
        )
        result = AgentResult(
            status="completed",
            output="Done",
            token_usage=AdapterTokenUsage(input_tokens=1000, output_tokens=500),
            modified_files=["auth.py"],
            duration_ms=12000,
        )
        assert result.token_usage.total_tokens == 1500
        assert result.modified_files == ["auth.py"]
        assert result.duration_ms == 12000

    def test_result_defaults_for_new_fields(self):
        from codeframe.core.adapters.agent_adapter import AgentResult
        result = AgentResult(status="completed")
        assert result.token_usage is None
        assert result.duration_ms == 0


class TestAgentEventExtensions:
    """Tests for #409 extensions to AgentEvent (message, timestamp)."""

    def test_event_with_message(self):
        from codeframe.core.adapters.agent_adapter import AgentEvent
        event = AgentEvent(type="progress", message="Working on step 1")
        assert event.message == "Working on step 1"
        assert isinstance(event.timestamp, datetime)

    def test_event_with_explicit_timestamp(self):
        from codeframe.core.adapters.agent_adapter import AgentEvent
        ts = datetime(2026, 3, 9, tzinfo=timezone.utc)
        event = AgentEvent(
            type="file_changed",
            message="Modified auth.py",
            timestamp=ts,
            data={"file": "auth.py"},
        )
        assert event.timestamp == ts
        assert event.data["file"] == "auth.py"

    def test_event_defaults_for_new_fields(self):
        from codeframe.core.adapters.agent_adapter import AgentEvent
        event = AgentEvent(type="output")
        assert event.message == ""
        assert isinstance(event.timestamp, datetime)
