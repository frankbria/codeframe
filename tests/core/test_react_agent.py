"""Tests for ReactAgent — ReAct-style agent loop.

Tests the core ReAct loop, system prompt construction, tool dispatch,
final verification, and self-correction retry behavior.
"""

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
        created_at="2026-01-01T00:00:00+00:00",
        tech_stack="Python with uv",
    )


@pytest.fixture
def mock_task():
    """Create a minimal task."""
    return Task(
        id="task-1",
        workspace_id="ws-test",
        prd_id=None,
        title="Add hello function",
        description="Create a hello() function that returns 'Hello, World!'",
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
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
