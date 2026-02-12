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
from codeframe.core.context import FileContent, TaskContext
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

        # Layer 1: base rules (updated for pre-loaded context awareness)
        assert "Read files before editing" in system_prompt

        # Layer 2: tech stack / preferences
        assert "Python with uv" in system_prompt

        # Layer 3: task info
        assert "Add hello function" in system_prompt


class TestPreloadedFileContext:
    """Tests for pre-loaded file contents in the system prompt (issue #373)."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_system_prompt_includes_loaded_files(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When loaded_files is populated, system prompt should include
        a 'Relevant Source Files' section with file contents."""
        from codeframe.core.react_agent import ReactAgent

        mock_context.loaded_files = [
            FileContent(path="src/main.py", content="def hello():\n    return 'Hello'", tokens_estimate=10),
            FileContent(path="src/utils.py", content="def add(a, b):\n    return a + b", tokens_estimate=10),
        ]

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        first_call = provider.get_call(0)
        system_prompt = first_call["system"]

        assert "## Relevant Source Files" in system_prompt
        assert "src/main.py" in system_prompt
        assert "src/utils.py" in system_prompt
        assert "def hello():" in system_prompt
        assert "def add(a, b):" in system_prompt

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_system_prompt_no_loaded_files_section_when_empty(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """When loaded_files is empty, no 'Relevant Source Files' section should appear."""
        from codeframe.core.react_agent import ReactAgent

        # mock_context.loaded_files is already empty by default
        assert mock_context.loaded_files == []

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        first_call = provider.get_call(0)
        system_prompt = first_call["system"]

        assert "## Relevant Source Files" not in system_prompt

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_rules_acknowledge_preloaded_context(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Base rules should acknowledge that pre-loaded files don't need re-reading."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        first_call = provider.get_call(0)
        system_prompt = first_call["system"]

        # Should NOT contain the old "ALWAYS read" rule
        assert "ALWAYS read a file before editing" not in system_prompt
        # Should contain updated rule that acknowledges pre-loaded context
        assert "Relevant Source Files" in system_prompt

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_initial_message_does_not_mandate_reading(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """The initial user message should not tell the agent to 'start by reading files'."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        first_call = provider.get_call(0)
        messages = first_call["messages"]
        initial_message = messages[0]["content"]

        # Should NOT mandate reading
        assert "Start by reading relevant files" not in initial_message


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
    def test_lint_errors_appended_to_edit_file_result(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """When edit_file produces lint errors, they are appended to the tool result."""
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

        # Mock run_lint_on_file to return a FAILED check with output
        mock_gates.run_lint_on_file.return_value = GateCheck(
            name="ruff",
            status=GateStatus.FAILED,
            output="bad.py:1:8: F401 `os` imported but unused",
        )
        mock_gates.GateStatus = GateStatus
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        # The second LLM call should see lint errors in the tool result
        second_call = provider.get_call(1)
        messages = second_call["messages"]

        user_msgs_with_results = [
            m for m in messages if m.get("tool_results")
        ]
        assert len(user_msgs_with_results) >= 1

        # Verify lint output was appended
        tool_content = user_msgs_with_results[0]["tool_results"][0]["content"]
        assert "LINT ERRORS" in tool_content
        assert "F401" in tool_content

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_lint_errors_appended_to_create_file_result(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """When create_file produces lint errors, they are appended to the tool result."""
        from codeframe.core.react_agent import ReactAgent

        new_file = tmp_path / "new.py"
        new_file.write_text("import os\n")

        provider.add_tool_response(
            [ToolCall(id="tc1", name="create_file", input={"path": "new.py", "content": "import os\n"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="File created.")

        mock_gates.run_lint_on_file.return_value = GateCheck(
            name="ruff",
            status=GateStatus.FAILED,
            output="new.py:1:8: F401 `os` imported but unused",
        )
        mock_gates.GateStatus = GateStatus
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        second_call = provider.get_call(1)
        messages = second_call["messages"]
        user_msgs_with_results = [m for m in messages if m.get("tool_results")]
        assert len(user_msgs_with_results) >= 1

        tool_content = user_msgs_with_results[0]["tool_results"][0]["content"]
        assert "LINT ERRORS" in tool_content

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_clean_file_no_lint_appended(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """A clean file produces no additional lint output."""
        from codeframe.core.react_agent import ReactAgent

        clean_file = tmp_path / "clean.py"
        clean_file.write_text("x = 1\n")

        provider.add_tool_response(
            [ToolCall(id="tc1", name="edit_file", input={"path": "clean.py", "edits": []})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="Edit applied.")

        mock_gates.run_lint_on_file.return_value = GateCheck(
            name="ruff", status=GateStatus.PASSED, output=""
        )
        mock_gates.GateStatus = GateStatus
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        second_call = provider.get_call(1)
        messages = second_call["messages"]
        user_msgs_with_results = [m for m in messages if m.get("tool_results")]
        assert len(user_msgs_with_results) >= 1

        tool_content = user_msgs_with_results[0]["tool_results"][0]["content"]
        assert "LINT ERRORS" not in tool_content

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_non_python_file_skips_lint(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """Non-Python files are skipped (no lint output appended)."""
        from codeframe.core.react_agent import ReactAgent

        md_file = tmp_path / "README.md"
        md_file.write_text("# Hello\n")

        provider.add_tool_response(
            [ToolCall(id="tc1", name="create_file", input={"path": "README.md", "content": "# Hello\n"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="File created.")

        mock_gates.run_lint_on_file.return_value = GateCheck(
            name="lint", status=GateStatus.SKIPPED, output="No linter configured for .md"
        )
        mock_gates.GateStatus = GateStatus
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        second_call = provider.get_call(1)
        messages = second_call["messages"]
        user_msgs_with_results = [m for m in messages if m.get("tool_results")]
        assert len(user_msgs_with_results) >= 1

        tool_content = user_msgs_with_results[0]["tool_results"][0]["content"]
        assert "LINT ERRORS" not in tool_content

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_lint_error_status_does_not_surface_as_lint_error(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """ERROR status (e.g., timeout) is not surfaced as actionable lint."""
        from codeframe.core.react_agent import ReactAgent

        py_file = tmp_path / "slow.py"
        py_file.write_text("x = 1\n")

        provider.add_tool_response(
            [ToolCall(id="tc1", name="edit_file", input={"path": "slow.py", "edits": []})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="Edit applied.")

        mock_gates.run_lint_on_file.return_value = GateCheck(
            name="ruff", status=GateStatus.ERROR, output="Timeout after 30s"
        )
        mock_gates.GateStatus = GateStatus
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        second_call = provider.get_call(1)
        messages = second_call["messages"]
        user_msgs_with_results = [m for m in messages if m.get("tool_results")]
        assert len(user_msgs_with_results) >= 1

        tool_content = user_msgs_with_results[0]["tool_results"][0]["content"]
        assert "LINT ERRORS" not in tool_content


class TestPathSafety:
    """Tests for path traversal prevention."""

    def test_ruff_on_file_rejects_path_traversal(self, workspace):
        """_run_lint_on_file should reject paths that escape the workspace."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=MockProvider())
        result = agent._run_lint_on_file("../../etc/passwd")
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

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_stream_closed_even_if_publish_fails(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_events,
        workspace, provider, mock_context,
    ):
        """complete_task_sync must be called even if publish_sync raises."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        publisher = MockEventPublisher()
        original_publish = publisher.publish_sync

        def failing_publish(task_id, event):
            from codeframe.core.models import CompletionEvent
            if isinstance(event, CompletionEvent):
                raise RuntimeError("publish failed")
            original_publish(task_id, event)

        publisher.publish_sync = failing_publish

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, event_publisher=publisher,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        # Stream must still be closed despite publish failure
        assert "task-1" in publisher.completed_tasks


# ---------------------------------------------------------------------------
# Mock helpers for runtime parameter tests
# ---------------------------------------------------------------------------


class MockOutputLogger:
    """Captures write() calls for test verification."""

    def __init__(self):
        self.lines: list[str] = []

    def write(self, message: str) -> None:
        self.lines.append(message)


# ---------------------------------------------------------------------------
# Tests for runtime parameters (issue #362)
# ---------------------------------------------------------------------------


class TestVerboseParameter:
    """Tests for the verbose parameter on ReactAgent."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_verbose_prints_to_stdout(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, capsys
    ):
        """When verbose=True, agent prints progress to stdout."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, verbose=True)
        agent.run("task-1")

        captured = capsys.readouterr()
        assert "[ReactAgent]" in captured.out

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_verbose_false_no_stdout(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, capsys
    ):
        """When verbose=False (default), no verbose output to stdout."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, verbose=False)
        agent.run("task-1")

        captured = capsys.readouterr()
        assert "[ReactAgent]" not in captured.out


class TestOutputLoggerParameter:
    """Tests for the output_logger parameter on ReactAgent."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_output_logger_always_written(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """output_logger.write() is called even when verbose=False."""
        from codeframe.core.react_agent import ReactAgent

        logger = MockOutputLogger()

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            verbose=False, output_logger=logger,
        )
        agent.run("task-1")

        assert len(logger.lines) > 0
        assert any("[ReactAgent]" in line for line in logger.lines)


class TestDebugParameter:
    """Tests for the debug parameter on ReactAgent."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_debug_creates_log_file(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """When debug=True, a .codeframe_debug_react_*.log file is created."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, debug=True)
        agent.run("task-1")

        debug_logs = list(tmp_path.glob(".codeframe_debug_react_*.log"))
        assert len(debug_logs) >= 1

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_debug_false_no_log_file(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, tmp_path
    ):
        """When debug=False (default), no debug log file is created."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, debug=False)
        agent.run("task-1")

        debug_logs = list(tmp_path.glob(".codeframe_debug_react_*.log"))
        assert len(debug_logs) == 0


class TestOnEventCallback:
    """Tests for the on_event callback parameter on ReactAgent."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_on_event_callback_invoked(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """on_event callback is called during agent run."""
        from codeframe.core.react_agent import ReactAgent

        received_events = []

        def on_event(event_type, payload):
            received_events.append((event_type, payload))

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, on_event=on_event,
        )
        agent.run("task-1")

        assert len(received_events) > 0

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_on_event_exception_does_not_crash(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """A failing on_event callback does not crash the agent."""
        from codeframe.core.react_agent import ReactAgent

        def bad_callback(event_type, payload):
            raise RuntimeError("callback boom")

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider, on_event=bad_callback,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED


class TestDryRunParameter:
    """Tests for the dry_run parameter on ReactAgent."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_dry_run_skips_write_tools(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """dry_run=True skips execute_tool for write tools (edit_file, create_file, run_command)."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="edit_file", input={"path": "test.py", "edits": []})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, dry_run=True)
        agent.run("task-1")

        # execute_tool should NOT have been called for the write tool
        mock_exec_tool.assert_not_called()

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_dry_run_allows_read_tools(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """dry_run=True still allows execute_tool for read tools (read_file, list_files, etc.)."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "main.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="file contents"
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, dry_run=True)
        agent.run("task-1")

        # execute_tool SHOULD have been called for the read tool
        mock_exec_tool.assert_called_once()


class TestFixCoordinatorParameter:
    """Tests for the fix_coordinator parameter on ReactAgent."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_fix_coordinator_accepted_as_noop(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """fix_coordinator parameter is accepted and stored without crashing."""
        from codeframe.core.react_agent import ReactAgent

        class MockFixCoordinator:
            pass

        coordinator = MockFixCoordinator()

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace, llm_provider=provider,
            fix_coordinator=coordinator,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        assert agent.fix_coordinator is coordinator


class TestDryRunUnknownTool:
    """Unknown tools should be blocked (treated as write) in dry-run mode."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_dry_run_blocks_unknown_tool(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """A hypothetical tool not in _READ_TOOLS is blocked in dry-run."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="unknown_tool", input={"arg": "val"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider, dry_run=True)
        agent.run("task-1")

        # execute_tool should NOT have been called — unknown_tool is not in _READ_TOOLS
        mock_exec_tool.assert_not_called()


class TestFailureCountIncrement:
    """_failure_count should increment on tool errors for debug log verbosity."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_failure_count_increments_on_tool_error(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """_failure_count increments when a tool returns is_error=True."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_tool_response(
            [ToolCall(id="tc1", name="read_file", input={"path": "missing.py"})]
        )
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1", content="File not found", is_error=True,
        )
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent._failure_count == 0
        agent.run("task-1")
        assert agent._failure_count >= 1


class TestAllParamsTogether:
    """Test that all new parameters work together."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_all_params_together(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context, capsys
    ):
        """All 6 new params provided together should work without errors."""
        from codeframe.core.react_agent import ReactAgent

        logger = MockOutputLogger()
        received_events = []

        def on_event(event_type, payload):
            received_events.append((event_type, payload))

        class MockFixCoordinator:
            pass

        publisher = MockEventPublisher()

        provider.add_text_response("Done.")
        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            dry_run=True,
            verbose=True,
            on_event=on_event,
            debug=True,
            output_logger=logger,
            fix_coordinator=MockFixCoordinator(),
            event_publisher=publisher,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        # Verbose output present
        captured = capsys.readouterr()
        assert "[ReactAgent]" in captured.out
        # Output logger written to
        assert len(logger.lines) > 0
        # on_event called
        assert len(received_events) > 0
