"""Extended tests for engine registry: check_requirements, config engine field, CLI commands."""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.engine_registry import check_requirements, _get_adapter_class

pytestmark = pytest.mark.v2


class TestCheckRequirements:
    def test_react_checks_anthropic_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            reqs = check_requirements("react")
            assert reqs["ANTHROPIC_API_KEY"] is True

    def test_react_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            reqs = check_requirements("react")
            assert reqs["ANTHROPIC_API_KEY"] is False

    def test_plan_checks_anthropic_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            reqs = check_requirements("plan")
            assert reqs["ANTHROPIC_API_KEY"] is True

    def test_built_in_alias_resolves_to_react(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            reqs = check_requirements("built-in")
            assert "ANTHROPIC_API_KEY" in reqs

    def test_invalid_engine_raises(self):
        with pytest.raises(ValueError, match="Invalid engine"):
            check_requirements("nonexistent")

    def test_external_engine_with_requirements(self):
        with patch("shutil.which", return_value="/usr/bin/claude"):
            reqs = check_requirements("claude-code")
            # External adapters may have their own requirements
            assert isinstance(reqs, dict)


class TestGetAdapterClass:
    def test_react_returns_class(self):
        cls = _get_adapter_class("react")
        assert cls is not None
        assert cls.__name__ == "BuiltinReactAdapter"

    def test_plan_returns_class(self):
        cls = _get_adapter_class("plan")
        assert cls is not None
        assert cls.__name__ == "BuiltinPlanAdapter"

    def test_unknown_returns_none(self):
        cls = _get_adapter_class("nonexistent")
        assert cls is None


class TestEnvironmentConfigEngine:
    def test_default_engine_is_react(self):
        from codeframe.core.config import EnvironmentConfig
        config = EnvironmentConfig()
        assert config.engine == "react"

    def test_custom_engine(self):
        from codeframe.core.config import EnvironmentConfig
        config = EnvironmentConfig(engine="plan")
        assert config.engine == "plan"

    def test_invalid_engine_fails_validation(self):
        from codeframe.core.config import EnvironmentConfig
        config = EnvironmentConfig(engine="nonexistent")
        errors = config.validate()
        assert any("Invalid engine" in e for e in errors)

    def test_valid_engines_pass_validation(self):
        from codeframe.core.config import EnvironmentConfig
        for engine in ("react", "plan", "claude-code", "opencode", "built-in"):
            config = EnvironmentConfig(engine=engine)
            errors = config.validate()
            assert not any("Invalid engine" in e for e in errors), f"Engine '{engine}' should be valid"

    def test_engine_serialization_roundtrip(self):
        from codeframe.core.config import EnvironmentConfig
        config = EnvironmentConfig(engine="claude-code")
        data = config.to_dict()
        restored = EnvironmentConfig.from_dict(data)
        assert restored.engine == "claude-code"


class TestBuiltinReactAdapterStallRetry:
    def test_stall_retry_succeeds_on_second_attempt(self):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        from codeframe.core.agent import AgentStatus
        from codeframe.core.stall_detector import StallDetectedError

        ws = MagicMock()
        ws.repo_path = Path("/tmp/test")
        provider = MagicMock()

        call_count = 0

        def mock_constructor(**kwargs):
            inst = MagicMock()

            nonlocal call_count
            call_count += 1
            if call_count == 1:
                inst.run.side_effect = StallDetectedError(
                    elapsed_s=300, iterations=10, last_tool="read_file"
                )
            else:
                inst.run.return_value = AgentStatus.COMPLETED
            return inst

        with patch("codeframe.core.react_agent.ReactAgent") as mock_cls:
            mock_cls.side_effect = mock_constructor
            adapter = BuiltinReactAdapter(ws, provider)
            result = adapter.run("task-1", "", Path("/tmp"))

        assert result.status == "completed"

    def test_stall_retry_exhausted_returns_failed(self):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        from codeframe.core.stall_detector import StallDetectedError

        ws = MagicMock()
        ws.repo_path = Path("/tmp/test")
        provider = MagicMock()

        def always_stall(**kwargs):
            inst = MagicMock()
            inst.run.side_effect = StallDetectedError(
                elapsed_s=300, iterations=10, last_tool="read_file"
            )
            return inst

        with patch("codeframe.core.react_agent.ReactAgent") as mock_cls:
            mock_cls.side_effect = always_stall
            adapter = BuiltinReactAdapter(ws, provider)
            result = adapter.run("task-1", "", Path("/tmp"))

        assert result.status == "failed"
        assert "Stall detected" in result.error


class TestBuiltinPlanAdapterRetry:
    def _make_state(self, status, blocker=None, gate_results=None, step_results=None):
        state = MagicMock()
        state.status = status
        state.blocker = blocker
        state.gate_results = gate_results or []
        state.step_results = step_results or []
        return state

    def test_completed_returns_completed(self):
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter
        from codeframe.core.agent import AgentStatus

        ws = MagicMock()
        ws.repo_path = Path("/tmp/test")
        provider = MagicMock()

        with patch("codeframe.core.agent.Agent") as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(AgentStatus.COMPLETED)
            adapter = BuiltinPlanAdapter(ws, provider)
            result = adapter.run("task-1", "", Path("/tmp"))

        assert result.status == "completed"

    def test_blocked_triggers_supervisor_unblock(self):
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter
        from codeframe.core.agent import AgentStatus

        ws = MagicMock()
        ws.repo_path = Path("/tmp/test")
        provider = MagicMock()

        with patch("codeframe.core.agent.Agent") as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(AgentStatus.BLOCKED)
            with patch("codeframe.core.conductor.get_supervisor") as mock_sup:
                mock_sup.return_value.try_resolve_blocked_task.return_value = False
                adapter = BuiltinPlanAdapter(ws, provider)
                result = adapter.run("task-1", "", Path("/tmp"))

        assert result.status == "blocked"
        mock_sup.return_value.try_resolve_blocked_task.assert_called_once_with("task-1")

    def test_supervisor_exception_returns_original_state(self):
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter
        from codeframe.core.agent import AgentStatus

        ws = MagicMock()
        ws.repo_path = Path("/tmp/test")
        provider = MagicMock()

        with patch("codeframe.core.agent.Agent") as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(AgentStatus.BLOCKED)
            with patch("codeframe.core.conductor.get_supervisor") as mock_sup:
                mock_sup.side_effect = Exception("Database error")
                adapter = BuiltinPlanAdapter(ws, provider)
                result = adapter.run("task-1", "", Path("/tmp"))

        assert result.status == "blocked"

    def test_failed_triggers_tactical_recovery(self):
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter
        from codeframe.core.agent import AgentStatus

        ws = MagicMock()
        ws.repo_path = Path("/tmp/test")
        provider = MagicMock()

        step_result = MagicMock()
        step_result.error = "modulenotfounderror: No module named 'foo'"
        step_result.output = ""

        with patch("codeframe.core.agent.Agent") as mock_cls:
            mock_cls.return_value.run.return_value = self._make_state(
                AgentStatus.FAILED, step_results=[step_result]
            )
            with patch("codeframe.core.conductor.get_supervisor") as mock_sup:
                mock_sup.side_effect = Exception("Database error")
                adapter = BuiltinPlanAdapter(ws, provider)
                result = adapter.run("task-1", "", Path("/tmp"))

        # Even with supervisor failure, the adapter returns gracefully
        assert result.status == "failed"


class TestBuiltinAdapterRequirements:
    def test_react_has_requirements(self):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        reqs = BuiltinReactAdapter.requirements()
        assert "ANTHROPIC_API_KEY" in reqs

    def test_plan_has_requirements(self):
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter
        reqs = BuiltinPlanAdapter.requirements()
        assert "ANTHROPIC_API_KEY" in reqs
