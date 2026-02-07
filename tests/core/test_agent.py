"""Tests for agent orchestrator."""

import pytest
import json
import inspect
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from codeframe.core.agent import (
    Agent,
    AgentState,
    AgentStatus,
    BlockerInfo,
    MAX_CONSECUTIVE_FAILURES,
)
from codeframe.core.planner import ImplementationPlan, PlanStep, StepType
from codeframe.core.executor import StepResult, ExecutionStatus
from codeframe.core.context import TaskContext
from codeframe.core.tasks import Task, TaskStatus
from codeframe.core.blockers import Blocker, BlockerStatus
from codeframe.adapters.llm import MockProvider, LLMResponse


def _utc_now():
    return datetime.now(timezone.utc)


class TestAgentState:
    """Tests for AgentState dataclass."""

    def test_default_state(self):
        """Default state is idle."""
        state = AgentState()
        assert state.status == AgentStatus.IDLE
        assert state.current_step == 0

    def test_to_dict(self):
        """Can serialize state to dict."""
        state = AgentState(
            status=AgentStatus.EXECUTING,
            task_id="task-1",
            current_step=2,
        )
        d = state.to_dict()
        assert d["status"] == "executing"
        assert d["task_id"] == "task-1"
        assert d["current_step"] == 2

    def test_to_dict_with_plan(self):
        """Can serialize state with plan."""
        plan = ImplementationPlan(
            task_id="t1",
            summary="Test",
            steps=[PlanStep(1, StepType.FILE_CREATE, "Create", "a.py")],
        )
        state = AgentState(status=AgentStatus.PLANNING, plan=plan)
        d = state.to_dict()
        assert d["plan"] is not None
        assert d["plan"]["summary"] == "Test"

    def test_to_dict_with_blocker(self):
        """Can serialize state with blocker."""
        state = AgentState(
            status=AgentStatus.BLOCKED,
            blocker=BlockerInfo(
                reason="Error",
                question="What should I do?",
                context="Step 1",
            ),
        )
        d = state.to_dict()
        assert d["blocker"]["question"] == "What should I do?"


class TestBlockerInfo:
    """Tests for BlockerInfo dataclass."""

    def test_basic_blocker(self):
        """Can create basic blocker info."""
        info = BlockerInfo(
            reason="File not found",
            question="Where is the config?",
        )
        assert info.step_index is None

    def test_blocker_with_step(self):
        """Can create blocker with step reference."""
        info = BlockerInfo(
            reason="Error",
            question="How to proceed?",
            step_index=3,
        )
        assert info.step_index == 3


class TestAgentBlockerDetection:
    """Tests for blocker detection logic."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        provider.set_response_handler(
            lambda msgs: LLMResponse(content="What is the correct path?")
        )
        return provider

    def test_should_create_blocker_consecutive_failures(self, mock_provider):
        """Creates blocker after consecutive failures ONLY after self-correction attempts."""
        from codeframe.core.agent import MAX_SELF_CORRECTION_ATTEMPTS

        workspace = MagicMock()
        workspace.repo_path = Path("/tmp")
        agent = Agent(workspace, mock_provider)

        result = StepResult(
            step=PlanStep(1, StepType.FILE_EDIT, "Edit", "a.py"),
            status=ExecutionStatus.FAILED,
            error="Something went wrong",  # Generic technical error
        )

        # Technical errors should NOT create blocker until self-correction is exhausted
        assert not agent._should_create_blocker(MAX_CONSECUTIVE_FAILURES, result, self_correction_attempts=0)
        assert not agent._should_create_blocker(1, result, self_correction_attempts=0)

        # After exhausting self-correction attempts, should create blocker
        assert agent._should_create_blocker(1, result, self_correction_attempts=MAX_SELF_CORRECTION_ATTEMPTS)

    def test_should_not_create_blocker_for_technical_errors(self, mock_provider):
        """Technical errors like 'file not found' should NOT create blockers immediately."""
        workspace = MagicMock()
        workspace.repo_path = Path("/tmp")
        agent = Agent(workspace, mock_provider)

        result = StepResult(
            step=PlanStep(1, StepType.FILE_EDIT, "Edit", "a.py"),
            status=ExecutionStatus.FAILED,
            error="File not found: config.yaml",
        )

        # Technical errors should NOT trigger blocker on first failure
        # Agent should attempt self-correction instead
        assert not agent._should_create_blocker(1, result, self_correction_attempts=0)

        # Classify the error
        assert agent._classify_error("File not found: config.yaml") == "technical"
        assert agent._classify_error("Module not found") == "technical"
        assert agent._classify_error("SyntaxError: invalid syntax") == "technical"

    def test_should_create_blocker_credentials(self, mock_provider):
        """Creates blocker for credential-related errors."""
        workspace = MagicMock()
        workspace.repo_path = Path("/tmp")
        agent = Agent(workspace, mock_provider)

        result = StepResult(
            step=PlanStep(1, StepType.SHELL_COMMAND, "Deploy", "deploy.sh"),
            status=ExecutionStatus.FAILED,
            error="API key not configured",
        )

        assert agent._should_create_blocker(1, result)


class TestAgentEventEmission:
    """Tests for event emission."""

    @pytest.fixture
    def mock_provider(self):
        return MockProvider()

    def test_emits_events(self, mock_provider):
        """Agent emits events via callback."""
        events_received = []

        def on_event(event_type, data):
            events_received.append((event_type, data))

        workspace = MagicMock()
        workspace.repo_path = Path("/tmp")
        agent = Agent(workspace, mock_provider, on_event=on_event)

        agent._emit_event("test_event", {"key": "value"})

        assert len(events_received) == 1
        assert events_received[0][0] == "test_event"
        assert events_received[0][1]["key"] == "value"


class TestAgentPlanExecution:
    """Tests for plan execution flow."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        # Response for planning
        provider.add_text_response(json.dumps({
            "summary": "Test implementation",
            "steps": [
                {"index": 1, "type": "file_create", "description": "Create", "target": "test.py", "depends_on": []},
            ],
            "files_to_create": ["test.py"],
            "files_to_modify": [],
            "estimated_complexity": "low",
            "considerations": [],
        }))
        # Response for code generation
        provider.add_text_response("# Generated test file\nprint('test')")
        return provider

    @pytest.fixture
    def mock_workspace(self, tmp_path):
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path
        return workspace

    @pytest.fixture
    def mock_context(self):
        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test task", description="",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        return TaskContext(task=task)

    def test_execute_plan_success(self, mock_provider, mock_workspace, mock_context, tmp_path):
        """Successfully executes a simple plan."""
        agent = Agent(mock_workspace, mock_provider, dry_run=True)
        agent.context = mock_context

        # Set up plan
        agent.state.plan = ImplementationPlan(
            task_id="t1",
            summary="Test",
            steps=[
                PlanStep(1, StepType.FILE_CREATE, "Create file", "test.py"),
            ],
        )

        # Execute
        agent._execute_plan()

        assert agent.state.current_step == 1
        assert len(agent.state.step_results) == 1
        assert agent.state.step_results[0].status == ExecutionStatus.SUCCESS

    def test_execute_plan_handles_failure_with_self_correction(self, mock_provider, mock_workspace, mock_context, tmp_path):
        """Handles step failure by attempting self-correction first."""
        # Add responses for self-correction attempts (these will also fail since file doesn't exist)
        mock_provider.add_text_response("# Corrected code attempt 1")
        mock_provider.add_text_response("# Corrected code attempt 2")
        # Add response for blocker question generation (after self-correction exhausted)
        mock_provider.add_text_response("What is the correct file path?")

        agent = Agent(mock_workspace, mock_provider)
        agent.context = mock_context

        # Plan with step that will fail (edit non-existent file)
        agent.state.plan = ImplementationPlan(
            task_id="t1",
            summary="Test",
            steps=[
                PlanStep(1, StepType.FILE_EDIT, "Edit missing", "nonexistent.py"),
            ],
        )

        # Mock blocker creation to avoid database access
        # Note: We no longer patch tasks.update_status since agent doesn't update task status
        # (that's handled by runtime - see state separation pattern in CLAUDE.md)
        with patch("codeframe.core.agent.blockers.create") as mock_create:
            mock_blocker = MagicMock()
            mock_blocker.id = "blocker-1"
            mock_create.return_value = mock_blocker

            # Execute - should not raise, handle failure after self-correction attempts
            agent._execute_plan()

        # Should have attempted self-correction before creating blocker
        # The step will fail, agent tries self-correction, and eventually gives up
        assert len(agent.state.step_results) >= 1
        assert agent.state.step_results[0].status == ExecutionStatus.FAILED


class TestAgentIntegration:
    """Integration tests for agent with mocked dependencies."""

    @pytest.fixture
    def mock_provider(self):
        provider = MockProvider()
        # Planning response
        provider.add_text_response(json.dumps({
            "summary": "Simple test",
            "steps": [],
            "files_to_create": [],
            "files_to_modify": [],
            "estimated_complexity": "low",
            "considerations": [],
        }))
        return provider

    def test_agent_with_existing_blocker(self, mock_provider, tmp_path):
        """Agent stops if task has existing blocker."""
        workspace = MagicMock()
        workspace.id = "ws-1"
        workspace.repo_path = tmp_path

        task = Task(
            id="t1", workspace_id="w1", prd_id=None,
            title="Test", description="",
            status=TaskStatus.BLOCKED,
            priority=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

        blocker = Blocker(
            id="b1", workspace_id="w1", task_id="t1",
            question="How to proceed?",
            answer=None,
            status=BlockerStatus.OPEN,
            created_at=_utc_now(),
            answered_at=None,
        )

        context = TaskContext(task=task, blockers=[blocker])

        agent = Agent(workspace, mock_provider)
        agent.context = context

        agent._handle_existing_blockers()

        assert agent.state.status == AgentStatus.BLOCKED
        assert agent.state.blocker is not None
        assert "How to proceed?" in agent.state.blocker.question


class TestAgentStateTransitions:
    """Tests for state machine transitions."""

    def test_idle_to_planning(self):
        """Transitions from idle to planning."""
        state = AgentState()
        assert state.status == AgentStatus.IDLE

        state.status = AgentStatus.PLANNING
        assert state.status == AgentStatus.PLANNING

    def test_planning_to_executing(self):
        """Transitions from planning to executing."""
        state = AgentState(status=AgentStatus.PLANNING)
        state.status = AgentStatus.EXECUTING
        assert state.status == AgentStatus.EXECUTING

    def test_executing_to_blocked(self):
        """Transitions from executing to blocked."""
        state = AgentState(status=AgentStatus.EXECUTING)
        state.status = AgentStatus.BLOCKED
        state.blocker = BlockerInfo(reason="Test", question="Q?")
        assert state.status == AgentStatus.BLOCKED
        assert state.blocker is not None

    def test_executing_to_verifying(self):
        """Transitions from executing to verifying."""
        state = AgentState(status=AgentStatus.EXECUTING)
        state.status = AgentStatus.VERIFYING
        assert state.status == AgentStatus.VERIFYING

    def test_verifying_to_completed(self):
        """Transitions from verifying to completed."""
        state = AgentState(status=AgentStatus.VERIFYING)
        state.status = AgentStatus.COMPLETED
        assert state.status == AgentStatus.COMPLETED


class TestVerificationRecovery:
    """Tests for verification recovery and early abort."""

    def test_max_consecutive_verification_failures_constant_exists(self):
        """New constant for verification-specific failure tracking exists."""
        from codeframe.core.agent import MAX_CONSECUTIVE_VERIFICATION_FAILURES
        assert MAX_CONSECUTIVE_VERIFICATION_FAILURES == 3

    def test_incremental_verification_tracks_failures_separately(self):
        """Verification failures tracked separately from step execution failures."""
        # The _execute_plan method must have a separate counter for verification failures
        # distinct from the existing consecutive_failures counter for step execution.
        # We verify by inspecting the source for the new variable name.
        source = inspect.getsource(Agent._execute_plan)
        assert "consecutive_verification_failures" in source

    def test_verification_failed_event_includes_details(self):
        """verification_failed events include gate name, error count, and error details."""
        # The enhanced verification_failed event should include structured gate info
        # rather than just a generic error string.
        source = inspect.getsource(Agent._execute_plan)
        assert '"gates"' in source or "'gates'" in source
        assert '"error_count"' in source or "'error_count'" in source
        assert '"error_details"' in source or "'error_details'" in source

    def test_incremental_verification_uses_verbose(self):
        """_run_incremental_verification captures full error details via verbose=True."""
        source = inspect.getsource(Agent._run_incremental_verification)
        assert "verbose=True" in source
