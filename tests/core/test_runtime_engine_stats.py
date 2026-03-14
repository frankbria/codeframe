"""Tests for engine stats recording in execute_agent.

Verifies that runtime.execute_agent records engine performance metrics
via engine_stats.record_run after each agent execution.
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


def _make_agent_result(status="completed", tokens=1200, duration_ms=5000):
    """Create a mock AgentResult with the given parameters."""
    from codeframe.core.adapters.agent_adapter import AdapterTokenUsage, AgentResult

    token_usage = AdapterTokenUsage(input_tokens=tokens // 2, output_tokens=tokens // 2)
    return AgentResult(
        status=status,
        output="test output",
        token_usage=token_usage,
        duration_ms=duration_ms,
    )


def _make_workspace_and_run(tmp_path):
    """Create a real workspace and a mock Run for testing."""
    from codeframe.core.workspace import create_or_load_workspace
    from codeframe.core.runtime import Run, RunStatus

    repo = tmp_path / "test_repo"
    repo.mkdir()
    workspace = create_or_load_workspace(repo)

    run = Run(
        id="run-001",
        workspace_id=workspace.id,
        task_id="task-001",
        status=RunStatus.RUNNING,
        started_at="2026-03-14T00:00:00Z",
        completed_at=None,
    )
    return workspace, run


class TestExecuteAgentRecordsEngineStats:
    """Verify that execute_agent calls engine_stats.record_run."""

    @patch("codeframe.core.engine_stats.record_run")
    def test_execute_agent_records_engine_stats(self, mock_record_run, tmp_path):
        """record_run should be called with correct args after a successful run."""
        from codeframe.core.runtime import execute_agent

        workspace, run = _make_workspace_and_run(tmp_path)
        result = _make_agent_result(status="completed", tokens=1200, duration_ms=5000)

        # Patch the adapter to return our controlled result
        with (
            patch("codeframe.core.engine_registry.get_builtin_adapter") as mock_adapter_factory,
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.runtime.fail_run"),
            patch("codeframe.core.runtime.block_run"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}),
        ):
            mock_adapter = MagicMock()
            mock_adapter.run.return_value = result
            mock_adapter_factory.return_value = mock_adapter

            execute_agent(workspace, run, engine="react")

        # Verify record_run was called
        mock_record_run.assert_called_once()
        call_kwargs = mock_record_run.call_args[1]

        assert call_kwargs["workspace"] is workspace
        assert call_kwargs["run_id"] == "run-001"
        assert call_kwargs["engine"] == "react"
        assert call_kwargs["task_id"] == "task-001"
        assert call_kwargs["status"] == "COMPLETED"
        assert call_kwargs["tokens_used"] == 1200
        assert isinstance(call_kwargs["duration_ms"], int)
        assert call_kwargs["duration_ms"] > 0

    @patch("codeframe.core.engine_stats.record_run")
    def test_execute_agent_records_stats_on_failure(self, mock_record_run, tmp_path):
        """record_run should be called even when the agent fails."""
        from codeframe.core.runtime import execute_agent

        workspace, run = _make_workspace_and_run(tmp_path)
        result = _make_agent_result(status="failed", tokens=800, duration_ms=3000)

        with (
            patch("codeframe.core.engine_registry.get_builtin_adapter") as mock_adapter_factory,
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.runtime.fail_run"),
            patch("codeframe.core.runtime.block_run"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}),
        ):
            mock_adapter = MagicMock()
            mock_adapter.run.return_value = result
            mock_adapter_factory.return_value = mock_adapter

            execute_agent(workspace, run, engine="react")

        mock_record_run.assert_called_once()
        call_kwargs = mock_record_run.call_args[1]
        assert call_kwargs["status"] == "FAILED"

    @patch("codeframe.core.engine_stats.record_run")
    def test_execute_agent_handles_no_token_usage(self, mock_record_run, tmp_path):
        """record_run should handle result with no token_usage gracefully."""
        from codeframe.core.adapters.agent_adapter import AgentResult
        from codeframe.core.runtime import execute_agent

        workspace, run = _make_workspace_and_run(tmp_path)
        result = AgentResult(status="completed", output="done", token_usage=None)

        with (
            patch("codeframe.core.engine_registry.get_builtin_adapter") as mock_adapter_factory,
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.runtime.fail_run"),
            patch("codeframe.core.runtime.block_run"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}),
        ):
            mock_adapter = MagicMock()
            mock_adapter.run.return_value = result
            mock_adapter_factory.return_value = mock_adapter

            execute_agent(workspace, run, engine="react")

        mock_record_run.assert_called_once()
        call_kwargs = mock_record_run.call_args[1]
        assert call_kwargs["tokens_used"] == 0


class TestExecuteAgentStatsFailureGraceful:
    """Verify that engine_stats failures don't crash execute_agent."""

    @patch("codeframe.core.engine_stats.record_run", side_effect=Exception("DB error"))
    def test_execute_agent_stats_failure_doesnt_crash(self, mock_record_run, tmp_path):
        """execute_agent should complete normally even if stats recording fails."""
        from codeframe.core.agent import AgentStatus
        from codeframe.core.runtime import execute_agent

        workspace, run = _make_workspace_and_run(tmp_path)
        result = _make_agent_result(status="completed", tokens=1200)

        with (
            patch("codeframe.core.engine_registry.get_builtin_adapter") as mock_adapter_factory,
            patch("codeframe.core.runtime.complete_run"),
            patch("codeframe.core.runtime.fail_run"),
            patch("codeframe.core.runtime.block_run"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}),
        ):
            mock_adapter = MagicMock()
            mock_adapter.run.return_value = result
            mock_adapter_factory.return_value = mock_adapter

            state = execute_agent(workspace, run, engine="react")

        # Should still return COMPLETED despite stats failure
        assert state.status == AgentStatus.COMPLETED
        mock_record_run.assert_called_once()
