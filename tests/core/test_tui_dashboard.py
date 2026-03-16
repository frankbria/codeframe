"""Tests for TUI dashboard.

Tests the data service, app instantiation, and CLI registration.
"""

import pytest
from pathlib import Path

from codeframe.core.workspace import Workspace, create_or_load_workspace


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


# --- Data Service Tests ---


class TestDataService:
    def test_load_empty_workspace(self, workspace):
        from codeframe.tui.data_service import load_dashboard_data

        data = load_dashboard_data(workspace)
        assert data.workspace_name == workspace.repo_path.name
        assert data.tasks == []
        assert data.blockers == []
        assert data.task_counts == {}

    def test_load_with_tasks(self, workspace):
        from codeframe.tui.data_service import load_dashboard_data
        from codeframe.core import tasks as task_module

        # Create some tasks
        task_module.create(workspace, title="Task 1", description="First task")
        task_module.create(workspace, title="Task 2", description="Second task")

        data = load_dashboard_data(workspace)
        assert len(data.tasks) == 2
        assert sum(data.task_counts.values()) == 2

    def test_load_with_blockers(self, workspace):
        from codeframe.tui.data_service import load_dashboard_data
        from codeframe.core import blockers

        blockers.create(workspace, question="What should we do?")

        data = load_dashboard_data(workspace)
        assert data.blocker_count == 1
        assert len(data.blockers) == 1

    def test_load_with_events(self, workspace):
        from codeframe.tui.data_service import load_dashboard_data
        from codeframe.core.events import emit_for_workspace, EventType

        emit_for_workspace(workspace, EventType.WORKSPACE_INIT, {}, print_event=False)

        data = load_dashboard_data(workspace)
        assert len(data.events) >= 1

    def test_dashboard_data_fields(self, workspace):
        from codeframe.tui.data_service import DashboardData

        data = DashboardData()
        assert data.workspace_name == ""
        assert data.error is None


# --- App Tests ---


class TestDashboardApp:
    def test_app_instantiation(self, workspace):
        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=workspace, refresh_interval=5)
        assert app.workspace == workspace
        assert app.refresh_interval == 5

    @pytest.mark.asyncio
    async def test_app_compose(self, workspace):
        """Verify the app can compose its widget tree."""
        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=workspace)
        async with app.run_test(size=(120, 40)) as pilot:
            # App should mount successfully
            assert app.query_one("#task-table") is not None
            assert app.query_one("#event-log-content") is not None
            assert app.query_one("#blocker-log") is not None
            assert app.query_one("#status-bar") is not None

    @pytest.mark.asyncio
    async def test_app_refresh(self, workspace):
        """Verify manual refresh works."""
        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=workspace)
        async with app.run_test(size=(120, 40)) as pilot:
            # Trigger refresh via action
            await pilot.press("r")

    @pytest.mark.asyncio
    async def test_app_quit(self, workspace):
        """Verify quit shortcut works."""
        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=workspace)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("q")


# --- CLI Tests ---


class TestCLI:
    def test_dashboard_help(self):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["dashboard", "--help"])
        assert result.exit_code == 0
        assert "dashboard" in result.output.lower()
        assert "refresh" in result.output.lower()

    def test_dashboard_registered(self):
        """Dashboard command should be registered on the main app."""
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert "dashboard" in result.output.lower()
