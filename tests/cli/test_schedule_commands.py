"""Tests for schedule CLI commands.

TDD tests for the scheduling-related CLI commands:
- cf schedule show - Show project schedule
- cf schedule optimize - Optimize schedule
- cf schedule predict - Predict completion date
- cf schedule bottlenecks - Identify scheduling bottlenecks
"""

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus


runner = CliRunner()


@pytest.fixture
def initialized_workspace(tmp_path):
    """Create an initialized workspace with tasks."""
    # Create workspace
    workspace_path = tmp_path / "test_project"
    workspace_path.mkdir()
    workspace = create_or_load_workspace(workspace_path)

    # Create tasks: A -> B -> C using v2 API
    task_a = tasks.create(
        workspace,
        title="Task A",
        description="First task",
        status=TaskStatus.READY,
        estimated_hours=2.0,
    )

    task_b = tasks.create(
        workspace,
        title="Task B",
        description="Second task",
        status=TaskStatus.READY,
        estimated_hours=3.0,
        depends_on=[task_a.id],
    )

    task_c = tasks.create(
        workspace,
        title="Task C",
        description="Third task",
        status=TaskStatus.READY,
        estimated_hours=1.0,
        depends_on=[task_b.id],
    )

    return {
        "workspace_path": workspace_path,
        "workspace": workspace,
        "task_ids": [task_a.id, task_b.id, task_c.id],
    }


@pytest.mark.unit
class TestScheduleShowCommand:
    """Test cf schedule show command."""

    def test_schedule_show_displays_schedule(self, initialized_workspace):
        """Test schedule show displays task schedule."""
        workspace_path = initialized_workspace["workspace_path"]

        result = runner.invoke(app, ["schedule", "show", "-w", str(workspace_path)])

        assert result.exit_code == 0
        assert "Task A" in result.output or "Schedule" in result.output

    def test_schedule_show_with_agents_option(self, initialized_workspace):
        """Test schedule show with --agents option."""
        workspace_path = initialized_workspace["workspace_path"]

        result = runner.invoke(app, ["schedule", "show", "-w", str(workspace_path), "--agents", "2"])

        assert result.exit_code == 0


@pytest.mark.unit
class TestSchedulePredictCommand:
    """Test cf schedule predict command."""

    def test_schedule_predict_shows_completion_date(self, initialized_workspace):
        """Test predict shows estimated completion date."""
        workspace_path = initialized_workspace["workspace_path"]

        result = runner.invoke(app, ["schedule", "predict", "-w", str(workspace_path)])

        assert result.exit_code == 0
        # Should show some date/time related output
        assert "predict" in result.output.lower() or "completion" in result.output.lower() or "hours" in result.output.lower()


@pytest.mark.unit
class TestScheduleBottlenecksCommand:
    """Test cf schedule bottlenecks command."""

    def test_schedule_bottlenecks_runs(self, initialized_workspace):
        """Test bottlenecks command runs without error."""
        workspace_path = initialized_workspace["workspace_path"]

        result = runner.invoke(app, ["schedule", "bottlenecks", "-w", str(workspace_path)])

        assert result.exit_code == 0


@pytest.mark.unit
class TestScheduleNoWorkspace:
    """Test schedule commands without workspace."""

    def test_schedule_show_fails_without_workspace(self, tmp_path):
        """Test schedule show fails gracefully without workspace."""
        result = runner.invoke(app, ["schedule", "show", "-w", str(tmp_path)])

        assert result.exit_code != 0
        assert "error" in result.output.lower() or "not found" in result.output.lower()
