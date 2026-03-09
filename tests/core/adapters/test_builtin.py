"""Tests for builtin adapter shims."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent, AgentResult
from codeframe.core.adapters.builtin import BuiltinPlanAdapter, BuiltinReactAdapter
from codeframe.core.agent import AgentState, AgentStatus

# Patch targets at the source modules, since builtin.py uses lazy imports.
_REACT_AGENT_CLS = "codeframe.core.react_agent.ReactAgent"
_PLAN_AGENT_CLS = "codeframe.core.agent.Agent"


@pytest.fixture
def mock_workspace():
    ws = MagicMock()
    ws.repo_path = Path("/tmp/test-repo")
    return ws


@pytest.fixture
def mock_provider():
    return MagicMock()


# ---------------------------------------------------------------------------
# BuiltinReactAdapter
# ---------------------------------------------------------------------------


class TestBuiltinReactAdapter:
    def test_name(self, mock_workspace, mock_provider):
        adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
        assert adapter.name == "react"

    def test_conforms_to_protocol(self, mock_workspace, mock_provider):
        adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
        assert isinstance(adapter, AgentAdapter)

    @pytest.mark.parametrize(
        "agent_status, expected",
        [
            (AgentStatus.COMPLETED, "completed"),
            (AgentStatus.FAILED, "failed"),
            (AgentStatus.BLOCKED, "blocked"),
        ],
    )
    def test_status_mapping(
        self, mock_workspace, mock_provider, agent_status, expected
    ):
        with patch(_REACT_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = agent_status
            adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.status == expected

    def test_unknown_status_maps_to_failed(self, mock_workspace, mock_provider):
        with patch(_REACT_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = AgentStatus.IDLE
            adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.status == "failed"

    def test_forwards_events(self, mock_workspace, mock_provider):
        received: list[AgentEvent] = []

        def capture_constructor(**kwargs):
            cb = kwargs.get("on_event")
            if cb:
                cb("step_started", {"step": 1})
            inst = MagicMock()
            inst.run.return_value = AgentStatus.COMPLETED
            return inst

        with patch(_REACT_AGENT_CLS) as mock_cls:
            mock_cls.side_effect = capture_constructor
            adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
            adapter.run("task-1", "prompt", Path("/tmp"), on_event=received.append)

        assert len(received) == 1
        assert received[0].type == "step_started"
        assert received[0].data == {"step": 1}

    def test_no_event_callback_does_not_error(self, mock_workspace, mock_provider):
        """Calling with on_event=None should not raise."""

        def trigger_event(**kwargs):
            cb = kwargs.get("on_event")
            if cb:
                cb("some_event", {})
            inst = MagicMock()
            inst.run.return_value = AgentStatus.COMPLETED
            return inst

        with patch(_REACT_AGENT_CLS) as mock_cls:
            mock_cls.side_effect = trigger_event
            adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.status == "completed"

    def test_stall_action_forwarded(self, mock_workspace, mock_provider):
        from codeframe.core.stall_detector import StallAction

        with patch(_REACT_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = AgentStatus.COMPLETED
            adapter = BuiltinReactAdapter(
                mock_workspace, mock_provider, stall_action=StallAction.FAIL
            )
            adapter.run("task-1", "prompt", Path("/tmp"))
            _, kwargs = mock_cls.call_args
            assert kwargs["stall_action"] == StallAction.FAIL

    def test_stall_action_omitted_when_none(self, mock_workspace, mock_provider):
        with patch(_REACT_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = AgentStatus.COMPLETED
            adapter = BuiltinReactAdapter(mock_workspace, mock_provider)
            adapter.run("task-1", "prompt", Path("/tmp"))
            _, kwargs = mock_cls.call_args
            assert "stall_action" not in kwargs


# ---------------------------------------------------------------------------
# BuiltinPlanAdapter
# ---------------------------------------------------------------------------


class TestBuiltinPlanAdapter:
    def test_name(self, mock_workspace, mock_provider):
        adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
        assert adapter.name == "plan"

    def test_conforms_to_protocol(self, mock_workspace, mock_provider):
        adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
        assert isinstance(adapter, AgentAdapter)

    def _make_state(self, status, blocker=None, gate_results=None):
        state = MagicMock(spec=AgentState)
        state.status = status
        state.blocker = blocker
        state.gate_results = gate_results or []
        return state

    @pytest.mark.parametrize(
        "agent_status, expected",
        [
            (AgentStatus.COMPLETED, "completed"),
            (AgentStatus.FAILED, "failed"),
            (AgentStatus.BLOCKED, "blocked"),
        ],
    )
    def test_status_mapping(
        self, mock_workspace, mock_provider, agent_status, expected
    ):
        with patch(_PLAN_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(agent_status)
            adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.status == expected

    def test_blocked_extracts_blocker_question(self, mock_workspace, mock_provider):
        blocker = MagicMock()
        blocker.question = "Which database should I use?"
        blocker.reason = None

        with patch(_PLAN_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(
                AgentStatus.BLOCKED, blocker=blocker
            )
            adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.status == "blocked"
            assert result.blocker_question == "Which database should I use?"

    def test_blocked_falls_back_to_reason(self, mock_workspace, mock_provider):
        blocker = MagicMock()
        blocker.question = None
        blocker.reason = "Missing dependency"

        with patch(_PLAN_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(
                AgentStatus.BLOCKED, blocker=blocker
            )
            adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.blocker_question == "Missing dependency"

    def test_failed_extracts_gate_errors(self, mock_workspace, mock_provider):
        check = MagicMock()
        check.output = "ruff: E501 line too long"
        gate = MagicMock()
        gate.checks = [check]

        with patch(_PLAN_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(
                AgentStatus.FAILED, gate_results=[gate]
            )
            adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.status == "failed"
            assert "E501" in result.error

    def test_failed_limits_error_output(self, mock_workspace, mock_provider):
        checks = []
        for i in range(10):
            c = MagicMock()
            c.output = f"error {i}"
            checks.append(c)
        gate = MagicMock()
        gate.checks = checks

        with patch(_PLAN_AGENT_CLS) as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(
                AgentStatus.FAILED, gate_results=[gate]
            )
            adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
            result = adapter.run("task-1", "prompt", Path("/tmp"))
            assert result.error.count("\n") == 2  # 3 errors, 2 newlines

    def test_forwards_events(self, mock_workspace, mock_provider):
        received: list[AgentEvent] = []

        def capture_constructor(**kwargs):
            cb = kwargs.get("on_event")
            if cb:
                cb("planning", {"phase": "start"})
            inst = MagicMock()
            state = MagicMock(spec=AgentState)
            state.status = AgentStatus.COMPLETED
            state.blocker = None
            state.gate_results = []
            inst.run.return_value = state
            return inst

        with patch(_PLAN_AGENT_CLS) as mock_cls:
            mock_cls.side_effect = capture_constructor
            adapter = BuiltinPlanAdapter(mock_workspace, mock_provider)
            adapter.run("task-1", "prompt", Path("/tmp"), on_event=received.append)

        assert len(received) == 1
        assert received[0].type == "planning"
