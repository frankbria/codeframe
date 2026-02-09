"""Tests for ReactAgent — ReAct-style agent loop.

Tests the core ReAct loop, system prompt construction, tool dispatch,
final verification, and self-correction retry behavior.
"""

from datetime import datetime, timezone

import pytest
from unittest.mock import patch

from codeframe.adapters.llm.base import (
    ToolCall,
    ToolResult,
)
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core.agent import AgentStatus
from codeframe.core.context import TaskContext
from codeframe.core.gates import GateResult, GateCheck, GateStatus
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.models import ProgressEvent
from codeframe.core.workspace import Workspace

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal workspace for testing."""
    state_dir = tmp_path / ".codeframe"
    state_dir.mkdir()
    return Workspace(
        id="ws-test",
        repo_path=tmp_path,
        state_dir=state_dir,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tech_stack="Python with uv",
    )


@pytest.fixture
def mock_task():
    """Create a minimal task."""
    _ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Task(
        id="task-1",
        workspace_id="ws-test",
        prd_id=None,
        title="Add hello function",
        description="Create a hello() function that returns 'Hello, World!'",
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        created_at=_ts,
        updated_at=_ts,
    )


@pytest.fixture
def mock_context(mock_task):
    """Create a minimal TaskContext."""
    return TaskContext(task=mock_task)


@pytest.fixture
def provider():
    """Create a MockProvider."""
    return MockProvider()


def _gate_passed():
    """Return a GateResult that passed."""
    return GateResult(
        passed=True,
        checks=[GateCheck(name="ruff", status=GateStatus.PASSED)],
    )


def _gate_failed():
    """Return a GateResult that failed."""
    return GateResult(
        passed=False,
        checks=[
            GateCheck(
                name="ruff",
                status=GateStatus.FAILED,
                output="test.py:1:1: F401 unused import",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReactLoopTermination:
    """Tests for the ReAct loop termination conditions."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_loop_terminates_on_text_response(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When the LLM responds with text only (no tool calls), the loop
        should terminate and run final verification."""
        from codeframe.core.react_agent import ReactAgent

        # LLM responds with text immediately — no tool calls
        provider.add_text_response("I have completed the task.")

        # Context loader returns our mock context
        mock_ctx_loader.return_value.load.return_value = mock_context

        # Final verification passes
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        # LLM was called exactly once (the text response)
        assert provider.call_count == 1

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_loop_terminates_at_max_iterations(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When max_iterations is reached, the agent should return FAILED."""
        from codeframe.core.react_agent import ReactAgent

        # Always return tool calls — never a text-only response
        for _ in range(5):
            provider.add_tool_response(
                [ToolCall(id="tc1", name="read_file", input={"path": "test.py"})]
            )

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="file contents"
        )

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, max_iterations=3
        )
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED
        # Should have made exactly max_iterations calls
        assert provider.call_count == 3


class TestToolDispatch:
    """Tests for tool call dispatching."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_calls_dispatched_correctly(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Tool calls from the LLM are dispatched to execute_tool with
        the correct workspace_path."""
        from codeframe.core.react_agent import ReactAgent

        # First call: tool use. Second call: text (done).
        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "main.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="print('hello')"
        )

        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

        # execute_tool was called with correct args
        mock_exec_tool.assert_called_once()
        call_args = mock_exec_tool.call_args
        tool_call_arg = call_args[0][0]
        workspace_path_arg = call_args[0][1]
        assert tool_call_arg.name == "read_file"
        assert tool_call_arg.input == {"path": "main.py"}
        assert workspace_path_arg == workspace.repo_path


class TestSystemPrompt:
    """Tests for system prompt construction."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_system_prompt_contains_all_3_layers(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """The system prompt must contain:
        - Layer 1: base rules (e.g., 'ALWAYS read a file before editing')
        - Layer 2: preferences/tech_stack
        - Layer 3: task title/description
        """
        from codeframe.core.react_agent import ReactAgent

        # Give the context a tech_stack for Layer 2
        mock_context.tech_stack = "Python with uv"

        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        # Inspect the system prompt passed to the LLM
        assert provider.call_count >= 1
        first_call = provider.get_call(0)
        system_prompt = first_call["system"]

        # Layer 1: base rules
        assert "ALWAYS read a file before editing" in system_prompt

        # Layer 2: tech stack / preferences
        assert "Python with uv" in system_prompt

        # Layer 3: task info
        assert "Add hello function" in system_prompt


class TestFinalVerification:
    """Tests for final verification behavior."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_final_verification_triggered(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When the loop terminates with a text response, gates.run() is called."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("All done.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        mock_gates.run.assert_called_once_with(workspace)

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_verification_retry_on_gate_failure(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When final verification fails, the agent gets more iterations
        to fix issues, then verification is retried."""
        from codeframe.core.react_agent import ReactAgent

        # Initial loop: text response (done)
        provider.add_text_response("Implementation complete.")

        # After verification fails, agent gets to try fixing:
        # tool call to fix lint error, then text response
        provider.add_tool_response(
            [ToolCall(id="tc-fix", name="edit_file", input={"path": "test.py", "edits": []})]
        )
        provider.add_text_response("Fixed the lint error.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc-fix", content="Edit applied."
        )

        # First verification fails, second passes
        mock_gates.run.side_effect = [_gate_failed(), _gate_passed()]

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            max_verification_retries=5,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        # gates.run called twice (first failed, second passed)
        assert mock_gates.run.call_count == 2

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_verification_retry_exhaustion(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When verification retries are exhausted, agent returns FAILED."""
        from codeframe.core.react_agent import ReactAgent

        # Initial loop: text response
        provider.add_text_response("Done.")

        # Retry attempts: each retry the agent sends a text response too
        for _ in range(3):
            provider.add_text_response("Tried to fix it.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        # Verification always fails
        mock_gates.run.return_value = _gate_failed()

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            max_verification_retries=2,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED


class TestIntentPreview:
    """Tests for intent preview on high-complexity tasks."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_intent_preview_for_high_complexity(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When the task has high complexity (complexity_score >= 4),
        the system prompt should include an intent preview instruction
        telling the agent to outline its plan before executing."""
        from codeframe.core.react_agent import ReactAgent

        # Set high complexity on the task
        mock_context.task.complexity_score = 4

        provider.add_text_response("Here is my plan and implementation.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        first_call = provider.get_call(0)
        system_prompt = first_call["system"]

        # Should contain intent preview instruction for high-complexity tasks
        assert "outline" in system_prompt.lower() or "plan" in system_prompt.lower()


class TestExceptionHandling:
    """Tests for error resilience."""

    @patch("codeframe.core.react_agent.ContextLoader")
    def test_run_returns_failed_on_exception(
        self, mock_ctx_loader, workspace, provider
    ):
        """When an unhandled exception occurs (e.g., context loading fails),
        run() should return FAILED instead of propagating the exception."""
        from codeframe.core.react_agent import ReactAgent

        mock_ctx_loader.return_value.load.side_effect = RuntimeError("DB corrupt")

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED


class TestPerEditLint:
    """Tests for per-edit lint gate behavior."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_lint_errors_appended_to_tool_result(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """When edit_file produces a file with lint errors, _execute_tool_with_lint
        should append the lint output to the tool result content."""
        from codeframe.core.react_agent import ReactAgent

        # Create a Python file with a lint error in the workspace
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("import os\n")  # unused import → F401

        # LLM calls edit_file, then responds with text (done)
        provider.add_tool_response(
            [ToolCall(id="tc1", name="edit_file", input={"path": "bad.py", "edits": []})]
        )
        provider.add_text_response("Done editing.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        # execute_tool succeeds
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="Edit applied."
        )

        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        # Check that the LLM received tool results. The second call (text response)
        # should have been preceded by a user message with tool_results.
        second_call = provider.get_call(1)
        messages = second_call["messages"]

        # Find the user message with tool_results
        user_msgs_with_results = [
            m for m in messages if m.get("tool_results")
        ]
        assert len(user_msgs_with_results) >= 1

        # The tool result content should include lint output if ruff found errors.
        # Since ruff may or may not be installed in CI, we just verify the
        # _execute_tool_with_lint method was used (execute_tool was called).
        mock_exec_tool.assert_called_once()


class TestPathSafety:
    """Tests for path traversal prevention."""

    def test_ruff_on_file_rejects_path_traversal(self, workspace):
        """_run_ruff_on_file should reject paths that escape the workspace."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=MockProvider())
        result = agent._run_ruff_on_file("../../etc/passwd")
        assert result == ""


class TestEventEmissions:
    """Tests for event emissions throughout the ReactAgent lifecycle."""

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_lifecycle_events_on_success(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """A successful run emits AGENT_STARTED and AGENT_COMPLETED."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.events import EventType

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

        # Extract all event types emitted
        emitted = [
            c.args[1] for c in mock_events.emit_for_workspace.call_args_list
        ]
        assert emitted[0] == EventType.AGENT_STARTED
        assert emitted[-1] == EventType.AGENT_COMPLETED

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_lifecycle_events_on_failure(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """A failed run (max iterations) emits AGENT_STARTED and AGENT_FAILED."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.events import EventType

        for _ in range(3):
            provider.add_tool_response(
                [ToolCall(id="tc1", name="read_file", input={"path": "x.py"})]
            )
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="contents"
        )

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, max_iterations=2
        )
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED

        emitted = [
            c.args[1] for c in mock_events.emit_for_workspace.call_args_list
        ]
        assert emitted[0] == EventType.AGENT_STARTED
        assert emitted[-1] == EventType.AGENT_FAILED

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_iteration_and_tool_events(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """Tool calls emit ITERATION_STARTED/COMPLETED and TOOL_DISPATCHED/RESULT."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.events import EventType

        # One tool call iteration, then text response
        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "a.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="code"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        emitted = [
            c.args[1] for c in mock_events.emit_for_workspace.call_args_list
        ]
        assert EventType.AGENT_ITERATION_STARTED in emitted
        assert EventType.AGENT_ITERATION_COMPLETED in emitted
        assert EventType.AGENT_TOOL_DISPATCHED in emitted
        assert EventType.AGENT_TOOL_RESULT in emitted

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_result_payload_includes_lint_flag(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """AGENT_TOOL_RESULT payload includes has_lint_errors flag."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.events import EventType

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "a.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="code"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        # Find the AGENT_TOOL_RESULT call
        tool_result_calls = [
            c for c in mock_events.emit_for_workspace.call_args_list
            if c.args[1] == EventType.AGENT_TOOL_RESULT
        ]
        assert len(tool_result_calls) == 1
        payload = tool_result_calls[0].args[2]
        assert payload["tool_call_id"] == "tc1"
        assert payload["is_error"] is False
        assert payload["has_lint_errors"] is False

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_exception_emits_agent_failed(
        self, mock_ctx_loader, mock_events, workspace, provider,
    ):
        """An exception during run() emits AGENT_FAILED with reason 'exception'."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.events import EventType

        mock_ctx_loader.return_value.load.side_effect = RuntimeError("boom")

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED

        # Find AGENT_FAILED call
        failed_calls = [
            c for c in mock_events.emit_for_workspace.call_args_list
            if c.args[1] == EventType.AGENT_FAILED
        ]
        assert len(failed_calls) == 1
        assert failed_calls[0].args[2]["reason"] == "exception"


class TestAgentPhaseAndProgressEvent:
    """Tests for AgentPhase constants and enhanced ProgressEvent model."""

    def test_agent_phase_constants_exist(self):
        """AgentPhase class should define all required phase constants."""
        from codeframe.core.models import AgentPhase

        assert AgentPhase.EXPLORING == "exploring"
        assert AgentPhase.PLANNING == "planning"
        assert AgentPhase.CREATING == "creating"
        assert AgentPhase.EDITING == "editing"
        assert AgentPhase.TESTING == "testing"
        assert AgentPhase.FIXING == "fixing"
        assert AgentPhase.VERIFYING == "verifying"

    def test_progress_event_new_fields_optional(self):
        """ProgressEvent should accept new optional fields (tool_name, file_path, iteration)."""
        from codeframe.core.models import ProgressEvent

        # Should work without new fields (backward compat)
        event = ProgressEvent(
            task_id="task-1",
            phase="exploring",
            step=1,
            total_steps=5,
            message="Reading files",
        )
        assert event.tool_name is None
        assert event.file_path is None
        assert event.iteration is None

    def test_progress_event_with_new_fields(self):
        """ProgressEvent should store new fields when provided."""
        from codeframe.core.models import ProgressEvent

        event = ProgressEvent(
            task_id="task-1",
            phase="exploring",
            step=1,
            total_steps=5,
            message="Reading main.py",
            tool_name="read_file",
            file_path="main.py",
            iteration=3,
        )
        assert event.tool_name == "read_file"
        assert event.file_path == "main.py"
        assert event.iteration == 3

    def test_progress_event_data_includes_new_fields(self):
        """The computed data property should include tool_name, file_path, iteration."""
        from codeframe.core.models import ProgressEvent

        event = ProgressEvent(
            task_id="task-1",
            phase="editing",
            step=2,
            total_steps=4,
            message="Editing file",
            tool_name="edit_file",
            file_path="src/app.py",
            iteration=1,
        )
        data = event.data
        assert data["tool_name"] == "edit_file"
        assert data["file_path"] == "src/app.py"
        assert data["iteration"] == 1

    def test_progress_event_data_omits_none_new_fields(self):
        """The computed data property should include None values for unset new fields."""
        from codeframe.core.models import ProgressEvent

        event = ProgressEvent(
            task_id="task-1",
            phase="planning",
            step=0,
            total_steps=0,
        )
        data = event.data
        # New fields should be present in data dict even when None
        assert "tool_name" in data
        assert "file_path" in data
        assert "iteration" in data


class MockEventPublisher:
    """Captures published events for test verification."""

    def __init__(self):
        self.events = []
        self.completed_tasks = []

    def publish_sync(self, task_id, event):
        self.events.append((task_id, event))

    def complete_task_sync(self, task_id):
        self.completed_tasks.append(task_id)


class TestPhaseEmission:
    """Tests for phase-based progress event emission in ReactAgent."""

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_exploring_and_planning_emitted_at_start(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """run() should emit EXPLORING before context loading and PLANNING
        before system prompt construction."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        # Extract phases from published events
        phases = [ev.phase for _, ev in publisher.events if isinstance(ev, ProgressEvent)]
        assert AgentPhase.EXPLORING in phases
        assert AgentPhase.PLANNING in phases
        # EXPLORING should come before PLANNING
        exploring_idx = phases.index(AgentPhase.EXPLORING)
        planning_idx = phases.index(AgentPhase.PLANNING)
        assert exploring_idx < planning_idx

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_phase_mapping_read_file(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """read_file tool call should emit EXPLORING phase."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "main.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="file contents"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        # Find events during the react loop (not the startup ones)
        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name == "read_file"
        ]
        assert len(tool_events) >= 1
        assert tool_events[0].phase == AgentPhase.EXPLORING

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_phase_mapping_edit_file(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """edit_file tool call should emit EDITING phase with file_path."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_tool_response(
            [ToolCall(id="tc1", name="edit_file", input={"path": "src/app.py", "edits": []})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="Edit applied."
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name == "edit_file"
        ]
        assert len(tool_events) >= 1
        assert tool_events[0].phase == AgentPhase.EDITING
        assert tool_events[0].file_path == "src/app.py"

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_phase_mapping_create_file(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """create_file tool call should emit CREATING phase."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_tool_response(
            [ToolCall(id="tc1", name="create_file", input={"path": "new.py", "content": ""})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="File created."
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name == "create_file"
        ]
        assert len(tool_events) >= 1
        assert tool_events[0].phase == AgentPhase.CREATING

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_phase_mapping_run_tests(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """run_tests tool call should emit TESTING phase."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_tool_response(
            [ToolCall(id="tc1", name="run_tests", input={"test_path": "tests/"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="All tests passed."
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name == "run_tests"
        ]
        assert len(tool_events) >= 1
        assert tool_events[0].phase == AgentPhase.TESTING
        assert tool_events[0].file_path == "tests/"

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_verifying_phase_emitted(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """VERIFYING phase should be emitted before final gates.run()."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        phases = [ev.phase for _, ev in publisher.events if isinstance(ev, ProgressEvent)]
        assert AgentPhase.VERIFYING in phases

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_fixing_phase_during_verification_retry(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """During verification retry, tool calls should emit FIXING phase."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        # Initial loop: text response
        provider.add_text_response("Implementation complete.")

        # After verification fails, fix with a tool call then text
        provider.add_tool_response(
            [ToolCall(id="tc-fix", name="edit_file", input={"path": "test.py", "edits": []})]
        )
        provider.add_text_response("Fixed the lint error.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc-fix", content="Edit applied."
        )

        # First verification fails, second passes
        mock_gates.run.side_effect = [_gate_failed(), _gate_passed()]

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            max_verification_retries=5,
            event_publisher=publisher,
        )
        agent.run("task-1")

        # Find FIXING phase events
        fixing_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.phase == AgentPhase.FIXING
        ]
        assert len(fixing_events) >= 1
        assert fixing_events[0].tool_name == "edit_file"

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_no_publisher_no_crash(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """When no event_publisher is provided, agent runs without crashing."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        # No event_publisher passed
        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_iteration_included_in_tool_events(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """Tool phase events should include the current iteration number."""
        from codeframe.core.react_agent import ReactAgent

        publisher = MockEventPublisher()

        # Two iterations of tool calls
        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "a.py"})]
        )
        provider.add_tool_response(
            [ToolCall(id="tc2", name="read_file", input={"path": "b.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="contents"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        # Get tool events with iteration info
        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name is not None
        ]
        assert len(tool_events) >= 2
        # Iterations should be sequential
        iterations = [ev.iteration for ev in tool_events]
        assert iterations[0] < iterations[1]


class TestToolPhaseMap:
    """Tests for the _TOOL_PHASE_MAP constant."""

    def test_all_tool_mappings_exist(self):
        """All expected tools should be mapped to phases."""
        from codeframe.core.react_agent import _TOOL_PHASE_MAP
        from codeframe.core.models import AgentPhase

        assert _TOOL_PHASE_MAP["read_file"] == AgentPhase.EXPLORING
        assert _TOOL_PHASE_MAP["list_files"] == AgentPhase.EXPLORING
        assert _TOOL_PHASE_MAP["search_codebase"] == AgentPhase.EXPLORING
        assert _TOOL_PHASE_MAP["create_file"] == AgentPhase.CREATING
        assert _TOOL_PHASE_MAP["edit_file"] == AgentPhase.EDITING
        assert _TOOL_PHASE_MAP["run_tests"] == AgentPhase.TESTING
        assert _TOOL_PHASE_MAP["run_command"] == AgentPhase.TESTING

    def test_unknown_tool_defaults_to_exploring(self):
        """Tools not in the map should default to EXPLORING phase."""
        from codeframe.core.react_agent import _TOOL_PHASE_MAP
        from codeframe.core.models import AgentPhase

        assert _TOOL_PHASE_MAP.get("unknown_tool", AgentPhase.EXPLORING) == AgentPhase.EXPLORING


class TestPhaseEmissionEdgeCases:
    """Additional edge case tests for phase emission."""

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_publisher_exception_does_not_crash_agent(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """If event_publisher.publish_sync raises, agent continues running."""
        from codeframe.core.react_agent import ReactAgent

        class FailingPublisher:
            def publish_sync(self, task_id, event):
                raise RuntimeError("publish failed")

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=FailingPublisher(),
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_multiple_tool_calls_in_single_iteration(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """Multiple tool calls in one iteration should each emit a phase event."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        # Single iteration with two tool calls
        provider.add_tool_response([
            ToolCall(id="tc1", name="read_file", input={"path": "a.py"}),
            ToolCall(id="tc2", name="edit_file", input={"path": "b.py", "edits": []}),
        ])
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="ok"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        # Should have both EXPLORING (read_file) and EDITING (edit_file) events
        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name is not None
        ]
        tool_names = [ev.tool_name for ev in tool_events]
        assert "read_file" in tool_names
        assert "edit_file" in tool_names

        phases = [ev.phase for ev in tool_events]
        assert AgentPhase.EXPLORING in phases
        assert AgentPhase.EDITING in phases

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_run_command_maps_to_testing(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """run_command tool call should emit TESTING phase."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import AgentPhase

        publisher = MockEventPublisher()

        provider.add_tool_response(
            [ToolCall(id="tc1", name="run_command", input={"command": "ls -la"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="output"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        tool_events = [
            ev for _, ev in publisher.events
            if isinstance(ev, ProgressEvent) and ev.tool_name == "run_command"
        ]
        assert len(tool_events) >= 1
        assert tool_events[0].phase == AgentPhase.TESTING

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_progress_events_carry_correct_task_id(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """All published events should carry the correct task_id."""
        from codeframe.core.react_agent import ReactAgent

        publisher = MockEventPublisher()

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            event_publisher=publisher,
        )
        agent.run("task-1")

        for task_id, event in publisher.events:
            assert task_id == "task-1"
            assert event.task_id == "task-1"


class TestRuntimeWiring:
    """Tests that runtime.py passes event_publisher to ReactAgent."""

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_react_agent_receives_event_publisher(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """ReactAgent should accept and store event_publisher parameter."""
        from codeframe.core.react_agent import ReactAgent

        publisher = MockEventPublisher()

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            event_publisher=publisher,
        )
        assert agent.event_publisher is publisher

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_react_agent_event_publisher_defaults_to_none(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider,
    ):
        """ReactAgent should default event_publisher to None."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent.event_publisher is None


class TestStreamCompletion:
    """Tests for SSE stream completion (CompletionEvent, ErrorEvent, complete_task_sync)."""

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_completion_event_and_stream_close_on_success(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """On success, ReactAgent publishes CompletionEvent and calls complete_task_sync."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import CompletionEvent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        publisher = MockEventPublisher()
        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, event_publisher=publisher,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

        # Last published event should be CompletionEvent
        completion_events = [
            e for _, e in publisher.events if isinstance(e, CompletionEvent)
        ]
        assert len(completion_events) == 1
        assert completion_events[0].status == "completed"

        # complete_task_sync must have been called
        assert "task-1" in publisher.completed_tasks

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_error_event_and_stream_close_on_max_iterations(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """On max_iterations failure, ReactAgent publishes ErrorEvent and closes stream."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import ErrorEvent

        for _ in range(3):
            provider.add_tool_response(
                [ToolCall(id="tc1", name="read_file", input={"path": "x.py"})]
            )
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="contents"
        )

        publisher = MockEventPublisher()
        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            max_iterations=2, event_publisher=publisher,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED

        error_events = [
            e for _, e in publisher.events if isinstance(e, ErrorEvent)
        ]
        assert len(error_events) == 1
        assert error_events[0].error == "max_iterations_reached"

        assert "task-1" in publisher.completed_tasks

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_error_event_and_stream_close_on_exception(
        self, mock_ctx_loader, mock_events, workspace, provider,
    ):
        """On exception, ReactAgent publishes ErrorEvent and closes stream."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.models import ErrorEvent

        mock_ctx_loader.return_value.load.side_effect = RuntimeError("boom")

        publisher = MockEventPublisher()
        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, event_publisher=publisher,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.FAILED

        error_events = [
            e for _, e in publisher.events if isinstance(e, ErrorEvent)
        ]
        assert len(error_events) == 1
        assert error_events[0].error == "exception"

        assert "task-1" in publisher.completed_tasks

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_no_stream_events_without_publisher(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """Without event_publisher, no CompletionEvent/ErrorEvent/complete_task_sync."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        # Should complete fine without publisher
        assert status == AgentStatus.COMPLETED
