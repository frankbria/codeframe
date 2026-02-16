"""Tests for agent integration with streaming output.

These tests verify that the Agent class correctly writes verbose output
to both stdout and the run output log file for `cf work follow`.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.workspace import create_or_load_workspace, Workspace
from codeframe.core.streaming import RunOutputLogger


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    """Create a temporary workspace for testing."""
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider."""
    provider = MagicMock()
    provider.complete.return_value = MagicMock(
        content='{"steps": [], "estimated_complexity": "low"}'
    )
    provider.get_model.return_value = "claude-sonnet-4"
    return provider


class TestAgentOutputLogger:
    """Tests for Agent output logging integration."""

    def test_agent_accepts_output_logger(self, temp_workspace: Workspace, mock_llm_provider):
        """Agent should accept an optional output_logger parameter."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        # Should not raise
        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            output_logger=logger,
        )

        assert agent.output_logger is logger
        logger.close()

    def test_agent_verbose_print_writes_to_logger(
        self, temp_workspace: Workspace, mock_llm_provider
    ):
        """Agent _verbose_print should write to the output logger."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=True,
            output_logger=logger,
        )

        agent._verbose_print("Test message from agent")

        logger.close()

        # Check the log file contains the message
        content = logger.log_path.read_text()
        assert "Test message from agent" in content

    def test_agent_verbose_print_writes_both_stdout_and_file(
        self, temp_workspace: Workspace, mock_llm_provider, capsys
    ):
        """Agent _verbose_print should write to both stdout and file when verbose=True."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=True,
            output_logger=logger,
        )

        agent._verbose_print("Test output message")

        logger.close()

        # Check stdout
        captured = capsys.readouterr()
        assert "Test output message" in captured.out

        # Check file
        content = logger.log_path.read_text()
        assert "Test output message" in content

    def test_agent_writes_to_file_even_when_not_verbose(
        self, temp_workspace: Workspace, mock_llm_provider, capsys
    ):
        """Agent should write to file even when verbose=False (for follow command)."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=False,  # Not verbose to stdout
            output_logger=logger,
        )

        agent._verbose_print("Silent message")

        logger.close()

        # Should NOT be in stdout
        captured = capsys.readouterr()
        assert "Silent message" not in captured.out

        # But SHOULD be in file
        content = logger.log_path.read_text()
        assert "Silent message" in content

    def test_agent_without_logger_still_works(
        self, temp_workspace: Workspace, mock_llm_provider, capsys
    ):
        """Agent should work normally without an output logger."""
        from codeframe.core.agent import Agent

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=True,
        )

        # Should not raise
        agent._verbose_print("Test without logger")

        captured = capsys.readouterr()
        assert "Test without logger" in captured.out


class TestRuntimeCreatesLogger:
    """Tests for runtime creating output logger for runs."""

    def test_execute_agent_creates_output_logger(self, temp_workspace: Workspace):
        """Runtime execute_agent should create an output logger for the run."""
        from codeframe.core import runtime, tasks as tasks_module
        from codeframe.core.streaming import run_output_exists
        from codeframe.core.agent import AgentStatus

        # Create task and run
        task = tasks_module.create(temp_workspace, title="Test task")
        run = runtime.start_task_run(temp_workspace, task.id)

        # Mock the ReactAgent class (default engine is now "react")
        with patch("codeframe.core.react_agent.ReactAgent") as MockReact, \
             patch("codeframe.adapters.llm.get_provider"):

            mock_agent = MagicMock()
            mock_agent.run.return_value = AgentStatus.COMPLETED
            MockReact.return_value = mock_agent

            # Patch os.getenv to provide API key
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                try:
                    runtime.execute_agent(temp_workspace, run)
                except Exception:
                    pass  # May fail on other things, but logger should be created

        # Output log should exist
        assert run_output_exists(temp_workspace, run.id)

    def test_output_logger_passed_to_agent(self, temp_workspace: Workspace):
        """Runtime should pass the output logger to the ReactAgent (default engine)."""
        from codeframe.core import runtime, tasks as tasks_module
        from codeframe.core.streaming import RunOutputLogger
        from codeframe.core.agent import AgentStatus

        task = tasks_module.create(temp_workspace, title="Test task")
        run = runtime.start_task_run(temp_workspace, task.id)

        captured_logger = None

        def capture_agent(*args, **kwargs):
            nonlocal captured_logger
            captured_logger = kwargs.get("output_logger")
            mock = MagicMock()
            mock.run.return_value = AgentStatus.COMPLETED
            return mock

        with patch("codeframe.core.react_agent.ReactAgent", side_effect=capture_agent), \
             patch("codeframe.adapters.llm.get_provider"), \
             patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            try:
                runtime.execute_agent(temp_workspace, run)
            except Exception:
                pass

        # Agent should have received a logger
        assert captured_logger is not None
        assert isinstance(captured_logger, RunOutputLogger)


class TestAgentOutputContent:
    """Tests for the content written to the output log."""

    def test_agent_logs_planning_start(
        self, temp_workspace: Workspace, mock_llm_provider
    ):
        """Agent should log when planning starts."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=True,
            output_logger=logger,
        )

        # Simulate planning status change
        agent._verbose_print("[PLAN] Creating implementation plan...")

        logger.close()

        content = logger.log_path.read_text()
        assert "PLAN" in content or "plan" in content.lower()

    def test_agent_logs_step_execution(
        self, temp_workspace: Workspace, mock_llm_provider
    ):
        """Agent should log step execution."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=True,
            output_logger=logger,
        )

        agent._verbose_print("[STEP 1] Creating file: test.py")

        logger.close()

        content = logger.log_path.read_text()
        assert "STEP" in content

    def test_agent_logs_verification_attempts(
        self, temp_workspace: Workspace, mock_llm_provider
    ):
        """Agent should log verification attempts."""
        from codeframe.core.agent import Agent

        logger = RunOutputLogger(temp_workspace, "test-run-id")

        agent = Agent(
            workspace=temp_workspace,
            llm_provider=mock_llm_provider,
            verbose=True,
            output_logger=logger,
        )

        agent._verbose_print("[VERIFY] Attempt 1/3")

        logger.close()

        content = logger.log_path.read_text()
        assert "VERIFY" in content
