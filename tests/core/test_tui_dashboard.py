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


# --- Proof Panel Tests ---


class TestDataServiceProof:
    def test_proof_fields_default(self):
        """DashboardData has proof fields defaulting to empty."""
        from codeframe.tui.data_service import DashboardData

        data = DashboardData()
        assert data.open_requirements == []
        assert data.expiring_waivers == []
        assert data.open_obligation_count == 0

    def test_load_with_open_requirements(self, workspace):
        """Open requirements appear in dashboard data."""
        from codeframe.tui.data_service import load_dashboard_data
        from codeframe.core.proof.ledger import init_proof_tables, save_requirement
        from codeframe.core.proof.models import (
            Gate, Obligation, Requirement, RequirementScope, ReqStatus, Severity, Source,
        )
        from datetime import datetime, timezone

        init_proof_tables(workspace)
        req = Requirement(
            id="REQ-0001",
            title="Auth token not validated",
            description="Logic bug in auth",
            severity=Severity.HIGH,
            source=Source.PRODUCTION,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
            status=ReqStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        )
        save_requirement(workspace, req)

        data = load_dashboard_data(workspace)
        assert data.open_obligation_count == 1
        assert len(data.open_requirements) == 1
        assert data.open_requirements[0].id == "REQ-0001"

    def test_load_with_expiring_waiver(self, workspace):
        """Waived requirements expiring within 7 days appear in expiring_waivers."""
        from codeframe.tui.data_service import load_dashboard_data
        from codeframe.core.proof.ledger import init_proof_tables, save_requirement
        from codeframe.core.proof.models import (
            Gate, Obligation, Requirement, RequirementScope, ReqStatus, Severity, Source, Waiver,
        )
        from datetime import datetime, timezone, date, timedelta

        init_proof_tables(workspace)
        req = Requirement(
            id="REQ-0002",
            title="Expiring waiver req",
            description="Will expire soon",
            severity=Severity.LOW,
            source=Source.QA,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
            status=ReqStatus.WAIVED,
            created_at=datetime.now(timezone.utc),
            waiver=Waiver(
                reason="Short-term defer",
                expires=date.today() + timedelta(days=3),
            ),
        )
        save_requirement(workspace, req)

        data = load_dashboard_data(workspace)
        assert len(data.expiring_waivers) == 1
        assert data.expiring_waivers[0].id == "REQ-0002"

    def test_load_non_expiring_waiver_excluded(self, workspace):
        """Waived requirements expiring far in the future are NOT in expiring_waivers."""
        from codeframe.tui.data_service import load_dashboard_data
        from codeframe.core.proof.ledger import init_proof_tables, save_requirement
        from codeframe.core.proof.models import (
            Gate, Obligation, Requirement, RequirementScope, ReqStatus, Severity, Source, Waiver,
        )
        from datetime import datetime, timezone, date, timedelta

        init_proof_tables(workspace)
        req = Requirement(
            id="REQ-0003",
            title="Far future waiver",
            description="Expires in 30 days",
            severity=Severity.LOW,
            source=Source.QA,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
            status=ReqStatus.WAIVED,
            created_at=datetime.now(timezone.utc),
            waiver=Waiver(reason="Future", expires=date.today() + timedelta(days=30)),
        )
        save_requirement(workspace, req)

        data = load_dashboard_data(workspace)
        assert data.expiring_waivers == []

    def test_load_no_proof_tables_graceful(self, workspace):
        """Fresh workspace with no proof tables returns empty lists without error."""
        from codeframe.tui.data_service import load_dashboard_data

        data = load_dashboard_data(workspace)
        assert data.open_requirements == []
        assert data.expiring_waivers == []
        assert data.open_obligation_count == 0
        # No error from proof loading (tables auto-created by _ensure_tables)
        assert data.error is None or "proof" not in (data.error or "").lower()


class TestDashboardAppProof:
    @pytest.mark.asyncio
    async def test_proof_panel_mounted(self, workspace):
        """Proof log widget is present in the composed widget tree."""
        from codeframe.tui.app import DashboardApp

        app = DashboardApp(workspace=workspace)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.query_one("#proof-log") is not None

    @pytest.mark.asyncio
    async def test_proof_panel_empty_state(self, workspace):
        """Empty proof state shows 'No open obligations'."""
        from codeframe.tui.app import DashboardApp
        from textual.widgets import RichLog

        app = DashboardApp(workspace=workspace)
        async with app.run_test(size=(120, 40)) as pilot:
            log = app.query_one("#proof-log", RichLog)
            # RichLog.lines returns Strip objects; str() gives plain text
            content = "\n".join(str(line) for line in log.lines)
            assert "No open obligations" in content

    def test_status_bar_obligation_badge(self):
        """StatusBar includes obligation badge when open_obligation_count > 0."""
        from codeframe.tui.app import StatusBar
        from codeframe.tui.data_service import DashboardData

        # Capture what update() receives by mocking it
        updates: list[str] = []
        bar = StatusBar.__new__(StatusBar)
        bar.update = lambda txt: updates.append(str(txt))

        data = DashboardData(open_obligation_count=2)
        StatusBar.update_from_data(bar, data)

        assert updates, "update() was not called"
        assert any("obligation" in u.lower() for u in updates)


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
