"""Tests for ReactAgent token usage tracking.

Verifies that the ReactAgent accumulates token records during execution,
provides aggregation methods, and handles persistence failures gracefully.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from codeframe.adapters.llm.base import (
    LLMResponse,
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReactAgentTokenAccumulation:
    """Tests for token record accumulation during agent run."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_react_agent_accumulates_token_records(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Verify tokens are collected during a run with tool calls."""
        from codeframe.core.react_agent import ReactAgent

        # First call: tool call with known token counts
        provider.add_response(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="read_file", input={"path": "a.py"})],
                stop_reason="tool_use",
                model="claude-sonnet-4-20250514",
                input_tokens=150,
                output_tokens=50,
            )
        )
        # Second call: text response (agent done)
        provider.add_response(
            LLMResponse(
                content="I have completed the task.",
                model="claude-sonnet-4-20250514",
                input_tokens=200,
                output_tokens=30,
            )
        )

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="file contents")
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

        records = agent.get_token_usage()
        assert len(records) == 2

        # First record: tool call iteration
        assert records[0]["input_tokens"] == 150
        assert records[0]["output_tokens"] == 50
        assert records[0]["model"] == "claude-sonnet-4-20250514"
        assert records[0]["call_type"] == "task_execution"
        assert records[0]["iteration"] == 1

        # Second record: text response iteration
        assert records[1]["input_tokens"] == 200
        assert records[1]["output_tokens"] == 30
        assert records[1]["iteration"] == 2

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_react_agent_accumulates_verification_tokens(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Verify tokens from verification fix loops are also recorded."""
        from codeframe.core.react_agent import ReactAgent

        # Main loop: text response (agent done quickly)
        provider.add_response(
            LLMResponse(
                content="I have completed the task.",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=20,
            )
        )

        # Verification fails first time, then LLM fixes, then passes
        failed_gate = GateResult(
            passed=False,
            checks=[GateCheck(name="ruff", status=GateStatus.FAILED, output="error")],
        )
        # First gate check fails, second passes
        mock_gates.run.side_effect = [failed_gate, _gate_passed()]

        # Fix loop LLM response (text-only, no tools needed)
        provider.add_response(
            LLMResponse(
                content="Fixed the issue.",
                model="claude-sonnet-4-20250514",
                input_tokens=300,
                output_tokens=60,
            )
        )

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="ok")

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

        records = agent.get_token_usage()
        # Should have at least the main loop call + the verification fix call
        assert len(records) >= 2

        # Check that verification fix tokens are recorded with correct call_type
        verification_records = [r for r in records if r["call_type"] == "verification_fix"]
        assert len(verification_records) >= 1
        assert verification_records[0]["input_tokens"] == 300
        assert verification_records[0]["output_tokens"] == 60


class TestReactAgentGetTotalTokens:
    """Tests for get_total_tokens() aggregation method."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_react_agent_get_total_tokens(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Verify get_total_tokens() returns correct aggregation."""
        from codeframe.core.react_agent import ReactAgent

        # Two iterations with known token counts
        provider.add_response(
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="read_file", input={"path": "a.py"})],
                stop_reason="tool_use",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=40,
            )
        )
        provider.add_response(
            LLMResponse(
                content="Done.",
                model="claude-sonnet-4-20250514",
                input_tokens=200,
                output_tokens=60,
            )
        )

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_exec_tool.return_value = ToolResult(tool_call_id="tc1", content="ok")
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        agent.run("task-1")

        totals = agent.get_total_tokens()
        assert totals["input_tokens"] == 300
        assert totals["output_tokens"] == 100
        assert totals["total_tokens"] == 400
        assert "estimated_cost_usd" in totals
        assert isinstance(totals["estimated_cost_usd"], float)
        assert totals["estimated_cost_usd"] >= 0.0

    def test_get_total_tokens_empty(self, workspace, provider):
        """get_total_tokens() returns zeros when no calls have been made."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        totals = agent.get_total_tokens()
        assert totals["input_tokens"] == 0
        assert totals["output_tokens"] == 0
        assert totals["total_tokens"] == 0
        assert totals["estimated_cost_usd"] == 0.0


class TestReactAgentTokenPersistenceFailure:
    """Tests for graceful handling of token persistence failures."""

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.TaskContextPackager")
    def test_react_agent_token_persistence_failure_doesnt_crash(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, workspace, provider, mock_context
    ):
        """Verify that a failure in _persist_token_usage does not crash the agent."""
        from codeframe.core.react_agent import ReactAgent

        # Simple text response
        provider.add_response(
            LLMResponse(
                content="I have completed the task.",
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=20,
            )
        )

        mock_ctx_loader.return_value.load_context.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)

        # Make _persist_token_usage raise an exception
        with patch.object(agent, "_persist_token_usage", side_effect=Exception("DB error")):
            status = agent.run("task-1")

        # Agent should still complete successfully despite persistence failure
        assert status == AgentStatus.COMPLETED

        # Token records should still be available in-memory
        records = agent.get_token_usage()
        assert len(records) == 1
