"""CLI command for launching the TUI dashboard.

Provides `cf dashboard` to launch the Textual-based terminal dashboard.
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

dashboard_app = typer.Typer(
    name="dashboard",
    help="Terminal dashboard for monitoring workspace state",
    invoke_without_command=True,
)


@dashboard_app.callback(invoke_without_command=True)
def dashboard(
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
    refresh_interval: int = typer.Option(
        2,
        "--refresh-interval",
        min=1,
        max=60,
        help="Seconds between data refreshes (default: 2)",
    ),
) -> None:
    """Launch the TUI dashboard.

    Shows a live terminal dashboard with task board, event log,
    and blocker notifications. Updates automatically.

    Keyboard shortcuts:
      q         Quit
      r         Force refresh
      Tab       Switch panels
      Up/Down   Navigate rows

    Example:
        codeframe dashboard
        codeframe dashboard --refresh-interval 5
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.tui.app import DashboardApp

    workspace_path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(workspace_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("[dim]Run 'codeframe init' to create a workspace first.[/dim]")
        raise typer.Exit(1)

    app = DashboardApp(
        workspace=workspace,
        refresh_interval=refresh_interval,
    )
    app.run()
