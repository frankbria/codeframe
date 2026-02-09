"""Tests for ReactAgent escalation, blocker detection, and quick fix integration.

Verifies:
- fix_tracker escalation after repeated gate failures
- Blocker creation on escalation threshold
- Quick fixes attempted before LLM correction
- Blocker detection from LLM text responses
- BLOCKED status return from run()
"""

from datetime import datetime, timezone

import pytest
from unittest.mock import patch, MagicMock

from codeframe.adapters.llm.base import ToolCall, ToolResult
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
        title="Fix authentication bug",
        description="Fix the auth module error handling",
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
    return GateResult(
        passed=True,
        checks=[GateCheck(name="ruff", status=GateStatus.PASSED)],
    )


def _gate_failed(error="test.py:1:1: F401 unused import"):
    return GateResult(
        passed=False,
        checks=[
            GateCheck(name="ruff", status=GateStatus.FAILED, output=error)
        ],
    )


# ---------------------------------------------------------------------------
# Escalation Tests
# ---------------------------------------------------------------------------


class TestEscalationAfterRepeatedFailures:
    """Tests that fix_tracker escalation triggers after threshold failures."""

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_escalate_after_repeated_gate_failures(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_blockers,
        workspace, provider, mock_context,
    ):
        """When gates fail repeatedly with the same error, agent should create
        a blocker and return BLOCKED instead of looping forever."""
        from codeframe.core.react_agent import ReactAgent

        # LLM completes the main loop
        provider.add_text_response("Implementation complete.")

        # Each retry attempt: LLM responds with text (no tool calls)
        for _ in range(10):
            provider.add_text_response("Tried to fix it.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        # Gates always fail with the same error
        mock_gates.run.return_value = _gate_failed("test.py:1:1: E501 line too long")

        # Mock blocker creation
        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-1"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            max_verification_retries=10,  # high to ensure escalation, not exhaustion
        )
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED
        # Blocker should have been created
        mock_blockers.create.assert_called_once()
        call_kwargs = mock_blockers.create.call_args
        # Question should contain context about the error
        question = call_kwargs[1].get("question", "") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else ""
        assert "task-1" in str(call_kwargs)

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_blocker_includes_attempted_fixes_context(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_blockers,
        workspace, provider, mock_context,
    ):
        """Blocker question should include what fixes were attempted."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        for _ in range(10):
            provider.add_text_response("Tried to fix.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_failed()

        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-2"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            max_verification_retries=10,
        )
        agent.run("task-1")

        # Verify blocker was created with informative question
        assert mock_blockers.create.called
        call_kwargs = mock_blockers.create.call_args
        question = call_kwargs.kwargs.get("question", "")
        # Question should mention error context
        assert len(question) > 0


# ---------------------------------------------------------------------------
# Quick Fix Tests
# ---------------------------------------------------------------------------


class TestQuickFixIntegration:
    """Tests that quick fixes are attempted before LLM correction."""

    @patch("codeframe.core.react_agent.apply_quick_fix")
    @patch("codeframe.core.react_agent.find_quick_fix")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_quick_fix_attempted_before_llm(
        self, mock_ctx_loader, mock_exec_tool, mock_gates,
        mock_find_qf, mock_apply_qf,
        workspace, provider, mock_context,
    ):
        """When gates fail, quick fix should be tried before the LLM mini-loop."""
        from codeframe.core.react_agent import ReactAgent

        # Main loop completes
        provider.add_text_response("Done.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        # First gate run fails, second passes (after quick fix)
        mock_gates.run.side_effect = [_gate_failed(), _gate_passed()]

        # Quick fix found and succeeds
        mock_fix = MagicMock()
        mock_fix.description = "Fix unused import"
        mock_find_qf.return_value = mock_fix
        mock_apply_qf.return_value = (True, "Fixed")

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        # Quick fix was attempted
        mock_find_qf.assert_called()
        mock_apply_qf.assert_called_once()
        # LLM should only have been called once (main loop), not for fixing
        assert provider.call_count == 1

    @patch("codeframe.core.react_agent.apply_quick_fix")
    @patch("codeframe.core.react_agent.find_quick_fix")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_quick_fix_failure_falls_through_to_llm(
        self, mock_ctx_loader, mock_exec_tool, mock_gates,
        mock_find_qf, mock_apply_qf,
        workspace, provider, mock_context,
    ):
        """When quick fix fails, the LLM mini-loop should still run."""
        from codeframe.core.react_agent import ReactAgent

        # Main loop completes
        provider.add_text_response("Done.")
        # LLM fix attempt in mini-loop
        provider.add_text_response("Fixed the issue.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        # Gate fails, then passes after LLM fix
        mock_gates.run.side_effect = [_gate_failed(), _gate_passed()]

        # Quick fix found but fails
        mock_fix = MagicMock()
        mock_fix.description = "Fix unused import"
        mock_find_qf.return_value = mock_fix
        mock_apply_qf.return_value = (False, "Could not fix")

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        # LLM was called twice: once for main loop, once for fix
        assert provider.call_count == 2

    @patch("codeframe.core.react_agent.find_quick_fix")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_no_quick_fix_available_proceeds_to_llm(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_find_qf,
        workspace, provider, mock_context,
    ):
        """When no quick fix is found, the LLM mini-loop runs normally."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response("Done.")
        provider.add_text_response("Fixed it.")

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.side_effect = [_gate_failed(), _gate_passed()]

        mock_find_qf.return_value = None

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED
        assert provider.call_count == 2


# ---------------------------------------------------------------------------
# Blocker Detection from Text Tests
# ---------------------------------------------------------------------------


class TestBlockerDetectionFromText:
    """Tests that blocker patterns in LLM text trigger BLOCKED status."""

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_text_with_access_denied_creates_blocker(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_blockers,
        workspace, provider, mock_context,
    ):
        """When the LLM says 'permission denied', a blocker is created."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response(
            "I cannot proceed because permission denied on the secrets file."
        )

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-access"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED
        mock_blockers.create.assert_called_once()

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_text_with_requirements_ambiguity_creates_blocker(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_blockers,
        workspace, provider, mock_context,
    ):
        """When the LLM says 'conflicting requirements', a blocker is created."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response(
            "There are conflicting requirements in the spec regarding error handling."
        )

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-req"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED
        mock_blockers.create.assert_called_once()

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_text_with_technical_error_does_not_block(
        self, mock_ctx_loader, mock_exec_tool, mock_gates,
        workspace, provider, mock_context,
    ):
        """Technical error text from LLM should NOT create a blocker."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response(
            "I fixed the file not found error and the implementation is complete."
        )

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        # Should complete normally, not blocked
        assert status == AgentStatus.COMPLETED

    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tactical_text_does_not_create_blocker(
        self, mock_ctx_loader, mock_exec_tool, mock_gates,
        workspace, provider, mock_context,
    ):
        """Tactical decision text should NOT create a blocker."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response(
            "I decided which approach to use and implemented it."
        )

        mock_ctx_loader.return_value.load.return_value = mock_context
        mock_gates.run.return_value = _gate_passed()

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.COMPLETED

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_tool_error_with_access_pattern_creates_blocker(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_blockers,
        workspace, provider, mock_context,
    ):
        """When a tool returns an error matching access patterns, agent blocks."""
        from codeframe.core.react_agent import ReactAgent

        # Tool call, then tool returns error with access pattern
        provider.add_tool_response(
            [ToolCall(id="tc1", name="run_command", input={"command": "deploy"})]
        )

        mock_ctx_loader.return_value.load.return_value = mock_context

        # Tool returns error with access pattern
        mock_exec_tool.return_value = ToolResult(
            tool_call_id="tc1",
            content="Error: unauthorized - authentication required for deployment",
            is_error=True,
        )

        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-tool"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED
        mock_blockers.create.assert_called_once()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestFullEscalationFlow:
    """End-to-end tests for the escalation flow."""

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.find_quick_fix")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_quick_fix_fails_then_llm_fails_then_escalation(
        self, mock_ctx_loader, mock_exec_tool, mock_gates,
        mock_find_qf, mock_blockers,
        workspace, provider, mock_context,
    ):
        """Full flow: gates fail → quick fix fails → LLM fixes fail →
        escalation → blocker → BLOCKED."""
        from codeframe.core.react_agent import ReactAgent

        # Main loop completes
        provider.add_text_response("Implementation complete.")

        # Many retry attempts where LLM tries to fix
        for _ in range(10):
            provider.add_text_response("Tried to fix it.")

        mock_ctx_loader.return_value.load.return_value = mock_context

        # Gates always fail
        mock_gates.run.return_value = _gate_failed()

        # No quick fix available
        mock_find_qf.return_value = None

        # Mock blocker creation
        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-esc"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(
            workspace=workspace,
            llm_provider=provider,
            max_verification_retries=10,
        )
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED
        mock_blockers.create.assert_called_once()

    @patch("codeframe.core.react_agent.events")
    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_blocked_status_emits_correct_events(
        self, mock_ctx_loader, mock_exec_tool, mock_gates,
        mock_blockers, mock_events,
        workspace, provider, mock_context,
    ):
        """When agent returns BLOCKED, it should emit AGENT_STARTED
        and appropriate failure/blocked events."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.events import EventType

        provider.add_text_response(
            "I cannot proceed because permission denied on the deployment config."
        )

        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-ev"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED

        emitted = [
            c.args[1] for c in mock_events.emit_for_workspace.call_args_list
        ]
        assert emitted[0] == EventType.AGENT_STARTED


class TestFixTrackerState:
    """Tests for fix_tracker integration within ReactAgent."""

    def test_react_agent_has_fix_tracker(self, workspace, provider):
        """ReactAgent should initialize with a FixAttemptTracker."""
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.fix_tracker import FixAttemptTracker

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert hasattr(agent, "fix_tracker")
        assert isinstance(agent.fix_tracker, FixAttemptTracker)

    def test_react_agent_blocker_id_initially_none(self, workspace, provider):
        """ReactAgent should initialize with blocker_id = None."""
        from codeframe.core.react_agent import ReactAgent

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        assert agent.blocker_id is None

    @patch("codeframe.core.react_agent.blockers")
    @patch("codeframe.core.react_agent.gates")
    @patch("codeframe.core.react_agent.execute_tool")
    @patch("codeframe.core.react_agent.ContextLoader")
    def test_blocker_id_set_after_blocked(
        self, mock_ctx_loader, mock_exec_tool, mock_gates, mock_blockers,
        workspace, provider, mock_context,
    ):
        """After returning BLOCKED, agent.blocker_id should be set."""
        from codeframe.core.react_agent import ReactAgent

        provider.add_text_response(
            "I cannot proceed because permission denied on the config."
        )
        mock_ctx_loader.return_value.load.return_value = mock_context

        mock_blocker = MagicMock()
        mock_blocker.id = "blocker-link-test"
        mock_blockers.create.return_value = mock_blocker

        agent = ReactAgent(workspace=workspace, llm_provider=provider)
        status = agent.run("task-1")

        assert status == AgentStatus.BLOCKED
        assert agent.blocker_id == "blocker-link-test"
