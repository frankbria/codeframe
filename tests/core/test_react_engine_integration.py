"""Tests for ReactAgent engine integration (issue #348).

Verifies that the --engine flag properly selects between the plan-based Agent
and the ReAct-based ReactAgent across runtime, CLI, and batch conductor.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from codeframe.core.agent import AgentState, AgentStatus
from codeframe.core.conductor import (
    BatchRun,
    BatchStatus,
    OnFailure,
    _save_batch,
    start_batch,
)
from codeframe.core.workspace import create_or_load_workspace
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace for testing."""
    workspace = create_or_load_workspace(tmp_path)
    return workspace


@pytest.fixture
def workspace_with_task(temp_workspace):
    """Create a workspace with a single READY task."""
    task = tasks.create(
        temp_workspace,
        title="Test task",
        description="A test task for engine selection",
        status=TaskStatus.READY,
    )
    return temp_workspace, task


@pytest.fixture
def workspace_with_tasks(temp_workspace):
    """Create a workspace with multiple READY tasks."""
    task1 = tasks.create(
        temp_workspace,
        title="Task 1",
        description="First task",
        status=TaskStatus.READY,
    )
    task2 = tasks.create(
        temp_workspace,
        title="Task 2",
        description="Second task",
        status=TaskStatus.READY,
    )
    return temp_workspace, [task1, task2]


class TestRuntimeEngineSelection:
    """Tests for engine selection in runtime.execute_agent()."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("codeframe.core.streaming.RunOutputLogger")
    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.agent.Agent")
    def test_default_engine_uses_plan_agent(
        self, mock_agent_cls, mock_get_provider, mock_output_logger, temp_workspace
    ):
        """Default engine ('plan') should use the existing Agent class."""
        from codeframe.core.runtime import execute_agent, start_task_run

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.run.return_value = AgentState(status=AgentStatus.COMPLETED)
        mock_agent_cls.return_value = mock_agent

        state = execute_agent(temp_workspace, run)

        mock_agent_cls.assert_called_once()
        assert state.status == AgentStatus.COMPLETED

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("codeframe.core.streaming.RunOutputLogger")
    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.agent.Agent")
    def test_plan_engine_uses_plan_agent(
        self, mock_agent_cls, mock_get_provider, mock_output_logger, temp_workspace
    ):
        """Explicit engine='plan' should use the existing Agent class."""
        from codeframe.core.runtime import execute_agent, start_task_run

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        mock_agent = MagicMock()
        mock_agent.run.return_value = AgentState(status=AgentStatus.COMPLETED)
        mock_agent_cls.return_value = mock_agent

        state = execute_agent(temp_workspace, run, engine="plan")

        mock_agent_cls.assert_called_once()
        assert state.status == AgentStatus.COMPLETED

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("codeframe.core.streaming.RunOutputLogger")
    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.react_agent.ReactAgent")
    def test_react_engine_uses_react_agent(
        self, mock_react_cls, mock_get_provider, mock_output_logger, temp_workspace
    ):
        """engine='react' should use the ReactAgent class."""
        from codeframe.core.runtime import execute_agent, start_task_run

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        mock_react = MagicMock()
        mock_react.run.return_value = AgentStatus.COMPLETED
        mock_react_cls.return_value = mock_react

        state = execute_agent(temp_workspace, run, engine="react")

        mock_react_cls.assert_called_once()
        # ReactAgent returns AgentStatus, runtime wraps it in AgentState
        assert state.status == AgentStatus.COMPLETED

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("codeframe.core.streaming.RunOutputLogger")
    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.react_agent.ReactAgent")
    def test_react_engine_wraps_failed_status(
        self, mock_react_cls, mock_get_provider, mock_output_logger, temp_workspace
    ):
        """ReactAgent returning FAILED should be wrapped in AgentState."""
        from codeframe.core.runtime import execute_agent, start_task_run

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        mock_react = MagicMock()
        mock_react.run.return_value = AgentStatus.FAILED
        mock_react_cls.return_value = mock_react

        state = execute_agent(temp_workspace, run, engine="react")

        assert state.status == AgentStatus.FAILED
        assert isinstance(state, AgentState)

    def test_invalid_engine_raises_error(self, temp_workspace):
        """Invalid engine value should raise ValueError."""
        from codeframe.core.runtime import execute_agent, start_task_run

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        with pytest.raises(ValueError, match="Invalid engine"):
            execute_agent(temp_workspace, run, engine="invalid")


class TestReactEngineConstructorArgs:
    """Test that ReactAgent receives correct constructor arguments."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("codeframe.core.streaming.RunOutputLogger")
    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.react_agent.ReactAgent")
    def test_react_agent_receives_workspace_and_provider(
        self, mock_react_cls, mock_get_provider, mock_output_logger, temp_workspace
    ):
        """ReactAgent should receive workspace and llm_provider."""
        from codeframe.core.runtime import execute_agent, start_task_run

        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        mock_react = MagicMock()
        mock_react.run.return_value = AgentStatus.COMPLETED
        mock_react_cls.return_value = mock_react

        execute_agent(temp_workspace, run, engine="react")

        # Verify ReactAgent was created with workspace and llm_provider
        kwargs = mock_react_cls.call_args
        assert kwargs.kwargs["workspace"] == temp_workspace
        assert kwargs.kwargs["llm_provider"] == mock_provider


class TestBatchRunEngineField:
    """Tests for engine field on BatchRun dataclass."""

    def test_batch_run_default_engine(self):
        """BatchRun should default to engine='plan'."""
        batch = BatchRun(
            id="test-batch",
            workspace_id="ws-1",
            task_ids=["t1"],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
        )
        assert batch.engine == "plan"

    def test_batch_run_react_engine(self):
        """BatchRun should accept engine='react'."""
        batch = BatchRun(
            id="test-batch",
            workspace_id="ws-1",
            task_ids=["t1"],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            engine="react",
        )
        assert batch.engine == "react"


class TestBatchRunEnginePersistence:
    """Tests for engine field persistence in database."""

    def test_save_and_load_batch_with_engine(self, temp_workspace):
        """Engine field should survive save/load cycle."""
        from codeframe.core.conductor import get_batch

        batch = BatchRun(
            id="test-engine-persist",
            workspace_id=temp_workspace.id,
            task_ids=["t1", "t2"],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            engine="react",
        )

        _save_batch(temp_workspace, batch)

        loaded = get_batch(temp_workspace, "test-engine-persist")
        assert loaded is not None
        assert loaded.engine == "react"

    def test_save_and_load_batch_default_engine(self, temp_workspace):
        """Default engine ('plan') should persist correctly."""
        from codeframe.core.conductor import get_batch

        batch = BatchRun(
            id="test-engine-default",
            workspace_id=temp_workspace.id,
            task_ids=["t1"],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
        )

        _save_batch(temp_workspace, batch)

        loaded = get_batch(temp_workspace, "test-engine-default")
        assert loaded is not None
        assert loaded.engine == "plan"


class TestSubprocessCommandConstruction:
    """Tests for engine flag in subprocess command construction."""

    @patch("codeframe.core.conductor.subprocess.Popen")
    def test_subprocess_includes_engine_flag(self, mock_popen, temp_workspace):
        """_execute_task_subprocess should include --engine in command."""
        from codeframe.core.conductor import _execute_task_subprocess
        from codeframe.core.runtime import RunStatus

        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Mock get_active_run to return a completed run
        with patch("codeframe.core.conductor.get_active_run") as mock_gar:
            mock_run = MagicMock()
            mock_run.status.value = RunStatus.COMPLETED.value
            mock_gar.return_value = mock_run

            _execute_task_subprocess(temp_workspace, "task-123", engine="react")

        # Verify the command includes --engine react
        cmd = mock_popen.call_args[0][0]
        assert "--engine" in cmd
        assert "react" in cmd

    @patch("codeframe.core.conductor.subprocess.Popen")
    def test_subprocess_default_engine_is_plan(self, mock_popen, temp_workspace):
        """Default engine should be 'plan' in subprocess command."""
        from codeframe.core.conductor import _execute_task_subprocess
        from codeframe.core.runtime import RunStatus

        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        with patch("codeframe.core.conductor.get_active_run") as mock_gar:
            mock_run = MagicMock()
            mock_run.status.value = RunStatus.COMPLETED.value
            mock_gar.return_value = mock_run

            _execute_task_subprocess(temp_workspace, "task-123")

        cmd = mock_popen.call_args[0][0]
        assert "--engine" in cmd
        assert "plan" in cmd


class TestStartBatchEngineParam:
    """Tests for engine parameter on start_batch()."""

    @patch("codeframe.core.conductor._execute_task_subprocess")
    def test_start_batch_passes_engine_to_subprocess(
        self, mock_subprocess, workspace_with_tasks
    ):
        """start_batch with engine='react' should pass it to subprocess calls."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        mock_subprocess.return_value = "COMPLETED"

        batch = start_batch(
            workspace=workspace,
            task_ids=task_ids,
            strategy="serial",
            engine="react",
        )

        # All subprocess calls should include engine="react"
        for c in mock_subprocess.call_args_list:
            assert c.kwargs.get("engine") == "react" or (
                len(c.args) > 2 and c.args[2] is not None  # batch_id
            )

    @patch("codeframe.core.conductor._execute_task_subprocess")
    def test_start_batch_default_engine(self, mock_subprocess, workspace_with_tasks):
        """start_batch without engine param should default to 'plan'."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        mock_subprocess.return_value = "COMPLETED"

        batch = start_batch(
            workspace=workspace,
            task_ids=task_ids,
            strategy="serial",
        )

        assert batch.engine == "plan"


class TestBackwardCompatibility:
    """Tests ensuring existing behavior is unchanged."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("codeframe.core.streaming.RunOutputLogger")
    @patch("codeframe.adapters.llm.get_provider")
    @patch("codeframe.core.agent.Agent")
    def test_execute_agent_without_engine_param(
        self, mock_agent_cls, mock_get_provider, mock_output_logger, temp_workspace
    ):
        """Calling execute_agent without engine should work (backward compatible)."""
        from codeframe.core.runtime import execute_agent, start_task_run

        task = tasks.create(temp_workspace, title="Test", status=TaskStatus.READY)
        run = start_task_run(temp_workspace, task.id)

        mock_agent = MagicMock()
        mock_agent.run.return_value = AgentState(status=AgentStatus.COMPLETED)
        mock_agent_cls.return_value = mock_agent

        # Call without engine parameter - should still work
        state = execute_agent(temp_workspace, run)

        assert state.status == AgentStatus.COMPLETED
        mock_agent_cls.assert_called_once()

    def test_batch_run_without_engine_field(self, temp_workspace):
        """BatchRun created without engine should default to 'plan'."""
        batch = BatchRun(
            id="compat-test",
            workspace_id=temp_workspace.id,
            task_ids=["t1"],
            status=BatchStatus.PENDING,
            strategy="serial",
            max_parallel=4,
            on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc),
            completed_at=None,
        )
        assert batch.engine == "plan"
