"""CodeFRAME TUI Dashboard — live terminal dashboard.

A Textual application showing tasks, events, and blockers
with auto-refresh and keyboard navigation.
"""

from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from codeframe.core.workspace import Workspace
from codeframe.tui.data_service import DashboardData, load_dashboard_data


# Status → color mapping for task rows
_STATUS_COLORS: dict[str, str] = {
    "DONE": "green",
    "IN_PROGRESS": "cyan",
    "READY": "yellow",
    "BACKLOG": "dim",
    "BLOCKED": "red",
    "FAILED": "red bold",
    "MERGED": "green dim",
}


class StatusBar(Static):
    """Top status bar showing task counts and workspace info."""

    def update_from_data(self, data: DashboardData) -> None:
        counts = data.task_counts
        total = sum(counts.values())
        done = counts.get("DONE", 0) + counts.get("MERGED", 0)
        active = counts.get("IN_PROGRESS", 0)
        blocked = counts.get("BLOCKED", 0) + counts.get("FAILED", 0)
        ready = counts.get("READY", 0) + counts.get("BACKLOG", 0)

        parts = [
            f"[bold]{data.workspace_name}[/bold]",
            f"Tasks: {total}",
            f"[green]{done} done[/green]",
            f"[cyan]{active} active[/cyan]",
            f"[yellow]{ready} ready[/yellow]",
        ]
        if blocked > 0:
            parts.append(f"[red]{blocked} blocked/failed[/red]")
        if data.blocker_count > 0:
            parts.append(f"[red bold]{data.blocker_count} blockers[/red bold]")

        self.update(" | ".join(parts))


class DashboardApp(App):
    """CodeFRAME TUI Dashboard."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    #main-content {
        height: 1fr;
    }
    #task-panel {
        width: 2fr;
        border: solid $primary;
    }
    #right-panel {
        width: 1fr;
    }
    #event-log {
        height: 2fr;
        border: solid $secondary;
    }
    #blocker-panel {
        height: 1fr;
        border: solid $error;
    }
    DataTable {
        height: 1fr;
    }
    RichLog {
        height: 1fr;
    }
    .panel-title {
        background: $surface;
        padding: 0 1;
        text-style: bold;
    }
    """

    TITLE = "CodeFRAME Dashboard"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("tab", "focus_next", "Next Panel"),
        Binding("shift+tab", "focus_previous", "Prev Panel"),
    ]

    workspace: Optional[Workspace] = None
    refresh_interval: int = 2
    data: reactive[Optional[DashboardData]] = reactive(None)

    def __init__(
        self,
        workspace: Workspace,
        refresh_interval: int = 2,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.workspace = workspace
        self.refresh_interval = refresh_interval

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status-bar")
        with Horizontal(id="main-content"):
            with Vertical(id="task-panel"):
                yield Static("Tasks", classes="panel-title")
                yield DataTable(id="task-table")
            with Vertical(id="right-panel"):
                with Vertical(id="event-log"):
                    yield Static("Recent Events", classes="panel-title")
                    yield RichLog(id="event-log-content", highlight=True, markup=True)
                with Vertical(id="blocker-panel"):
                    yield Static("Open Blockers", classes="panel-title")
                    yield RichLog(id="blocker-log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        # Set up task table columns
        table = self.query_one("#task-table", DataTable)
        table.add_columns("ID", "Title", "Status", "Priority")
        table.cursor_type = "row"

        # Initial data load
        self._refresh_data()

        # Auto-refresh
        self.set_interval(self.refresh_interval, self._refresh_data)

    def _refresh_data(self) -> None:
        """Load fresh data from the workspace and update all widgets."""
        if not self.workspace:
            return

        data = load_dashboard_data(self.workspace)
        self.data = data

        self._update_status_bar(data)
        self._update_task_table(data)
        self._update_event_log(data)
        self._update_blocker_panel(data)

        if data.error:
            self.notify(f"Data loading error: {data.error}", severity="warning")

    def _update_status_bar(self, data: DashboardData) -> None:
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_from_data(data)

    def _update_task_table(self, data: DashboardData) -> None:
        table = self.query_one("#task-table", DataTable)
        table.clear()

        for task in data.tasks:
            status_val = task.status.value if hasattr(task.status, "value") else str(task.status)
            color = _STATUS_COLORS.get(status_val, "white")
            table.add_row(
                task.id[:8],
                task.title[:50],
                f"[{color}]{status_val}[/{color}]",
                str(task.priority),
            )

    def _update_event_log(self, data: DashboardData) -> None:
        log = self.query_one("#event-log-content", RichLog)
        log.clear()

        for event in reversed(data.events):  # oldest first
            ts = event.created_at.strftime("%H:%M:%S") if hasattr(event.created_at, "strftime") else str(event.created_at)[:8]
            log.write(f"[dim]{ts}[/dim] {event.event_type}")

    def _update_blocker_panel(self, data: DashboardData) -> None:
        log = self.query_one("#blocker-log", RichLog)
        log.clear()

        if not data.blockers:
            log.write("[dim]No open blockers[/dim]")
            return

        for blocker in data.blockers:
            log.write(f"[red bold]{blocker.id[:8]}[/red bold]: {blocker.question[:60]}")

    def action_refresh(self) -> None:
        """Manual refresh via 'r' key."""
        self._refresh_data()
        self.notify("Refreshed")
