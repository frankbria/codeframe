"""Command-line interface for CodeFRAME.

This package provides the CLI commands for CodeFRAME, organized into
command groups for different domains (auth, projects, blockers, etc.).

The main Typer app is exported for use as the entry point:
    codeframe = "codeframe.cli:app"
    cf = "codeframe.cli:app"  # Short alias
"""

import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from codeframe.core.port_utils import check_port_availability, validate_port_range
from codeframe.core.project import Project

# Create main app with help text
app = typer.Typer(
    name="codeframe",
    help="Fully Remote Autonomous Multiagent Environment for coding",
    add_completion=False,
)
console = Console()


# =============================================================================
# Existing Commands (Preserved for backward compatibility)
# =============================================================================


@app.command()
def init(
    project_name: str = typer.Argument(..., help="Name of the project"),
    template: Optional[str] = typer.Option(None, help="Project template (future feature)"),
):
    """Initialize a new CodeFRAME project."""
    try:
        project = Project.create(project_name)
        console.print(f"✓ Initialized project: [bold green]{project_name}[/bold green]")
        console.print(f"  Location: {project.project_dir}")
        console.print("\nNext steps:")
        console.print("  1. codeframe start  - Start project execution")
        console.print("  2. codeframe status - Check project status")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def start(
    project: Optional[str] = typer.Argument(None, help="Project name or directory"),
):
    """Start project execution."""
    try:
        project_dir = Path(project) if project else Path.cwd()
        proj = Project(project_dir)
        proj.start()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def pause(
    project: Optional[str] = typer.Argument(None, help="Project name or directory"),
):
    """Pause project execution."""
    try:
        project_dir = Path(project) if project else Path.cwd()
        proj = Project(project_dir)
        proj.pause()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def resume(
    project: Optional[str] = typer.Argument(None, help="Project name or directory"),
):
    """Resume project execution from checkpoint."""
    try:
        project_dir = Path(project) if project else Path.cwd()
        proj = Project(project_dir)
        proj.resume()
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def status(
    project: Optional[str] = typer.Argument(None, help="Project name or directory"),
):
    """Show project status."""
    try:
        project_dir = Path(project) if project else Path.cwd()
        proj = Project(project_dir)
        status = proj.get_status()

        console.print(f"\n[bold]Project:[/bold] {status['name']}")
        console.print(f"[bold]Status:[/bold] {status['status']}")
        console.print(f"[bold]Progress:[/bold] {status['progress_pct']}%")
        console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def chat(
    message: str = typer.Argument(..., help="Message to Lead Agent"),
    project: Optional[str] = typer.Option(None, help="Project name or directory"),
):
    """Chat with Lead Agent."""
    try:
        project_dir = Path(project) if project else Path.cwd()
        proj = Project(project_dir)
        response = proj.chat(message)
        console.print(f"\n[bold cyan]Lead Agent:[/bold cyan] {response}\n")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def config(
    action: str = typer.Argument(..., help="Action: get or set"),
    key: Optional[str] = typer.Argument(None, help="Config key (dot notation)"),
    value: Optional[str] = typer.Argument(None, help="Config value (for set)"),
):
    """Manage project configuration."""
    try:
        proj = Project(Path.cwd())
        config = proj.config

        if action == "get":
            if not key:
                console.print("[red]Error:[/red] Key required for get")
                raise typer.Exit(1)
            val = config.get(key)
            console.print(f"{key} = {val}")

        elif action == "set":
            if not key or not value:
                console.print("[red]Error:[/red] Key and value required for set")
                raise typer.Exit(1)
            config.set(key, value)
            console.print(f"✓ Set {key} = {value}")

        else:
            console.print(f"[red]Error:[/red] Unknown action: {action}")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command(deprecated=True, hidden=True)
def checkpoint(
    action: str = typer.Argument("create", help="Action: create or list"),
    message: Optional[str] = typer.Option(None, help="Checkpoint message"),
):
    """Deprecated: Use 'codeframe checkpoints' instead."""
    console.print("[yellow]⚠ Deprecated:[/yellow] The 'checkpoint' command has been replaced.")
    console.print("Please use: [bold]codeframe checkpoints <command>[/bold]")
    console.print("\nAvailable commands:")
    console.print("  codeframe checkpoints list <project_id>")
    console.print("  codeframe checkpoints create <project_id>")
    console.print("  codeframe checkpoints restore <checkpoint_id>")


# Note: agents command group is now in agents_commands.py (Phase 2)


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to run server on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    open_browser: bool = typer.Option(
        True, "--open-browser/--no-browser", help="Auto-open browser"
    ),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development)"),
):
    """Start the CodeFRAME dashboard server.

    The server will run on the specified port and automatically open
    your browser to the dashboard. Press Ctrl+C to stop the server.

    Examples:

      codeframe serve

      codeframe serve --port 3000 --no-browser

      codeframe serve --reload
    """
    # Validate port range
    valid, msg = validate_port_range(port)
    if not valid:
        console.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(1)

    # Check port availability
    available, msg = check_port_availability(port, host)
    if not available:
        console.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(1)

    # Build uvicorn command
    cmd = [
        "uvicorn",
        "codeframe.ui.server:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    if reload:
        cmd.append("--reload")

    # Print startup message
    console.print("🌐 Starting dashboard server...")
    console.print(f"   URL: [bold cyan]http://localhost:{port}[/bold cyan]")
    console.print("   Press [bold]Ctrl+C[/bold] to stop\n")

    # Open browser in background thread (if enabled)
    if open_browser:

        def open_in_browser():
            """Open browser after delay to ensure server is ready."""
            time.sleep(1.5)
            try:
                webbrowser.open(f"http://localhost:{port}")
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Could not open browser: {e}")
                console.print(f"Please open http://localhost:{port} manually")

        browser_thread = threading.Thread(target=open_in_browser, daemon=True)
        browser_thread.start()

    # Start server (blocking call)
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n✓ Server stopped")
    except FileNotFoundError:
        console.print("[red]Error:[/red] uvicorn not found. Install with: pip install uvicorn")
        raise typer.Exit(1)
    except subprocess.CalledProcessError:
        console.print("\n[red]Server failed to start.[/red] Common issues:")
        console.print(f"  • Port {port} may be in use (try --port {port + 1})")
        console.print("  • Check the error message above for details")
        raise typer.Exit(1)


@app.command(name="clear-session")
def clear_session(
    project: Optional[str] = typer.Argument(None, help="Project name or directory"),
):
    """Clear saved session state."""
    try:
        from codeframe.core.session_manager import SessionManager

        project_dir = Path(project) if project else Path.cwd()

        # Initialize SessionManager
        session_mgr = SessionManager(str(project_dir))

        # Clear session
        session_mgr.clear_session()

        console.print("✓ Session state cleared")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def version():
    """Show CodeFRAME version."""
    from codeframe import __version__

    console.print(f"CodeFRAME version: [bold green]{__version__}[/bold green]")


# =============================================================================
# Import and register command groups (sub-applications)
# Phase 1: Core workflows - auth, projects, blockers, checkpoints, discovery
# Phase 2: Agent & task management - agents, tasks, quality-gates, metrics, session, context
# NOTE: These imports must come after app definition (E402 intentional)
# =============================================================================

# Phase 1 imports
from codeframe.cli.auth_commands import auth_app  # noqa: E402
from codeframe.cli.project_commands import projects_app  # noqa: E402
from codeframe.cli.blocker_commands import blockers_app  # noqa: E402
from codeframe.cli.checkpoint_commands import checkpoints_app  # noqa: E402
from codeframe.cli.discovery_commands import discovery_app  # noqa: E402

# Phase 2 imports
from codeframe.cli.agents_commands import agents_app  # noqa: E402
from codeframe.cli.tasks_commands import tasks_app  # noqa: E402
from codeframe.cli.quality_gates_commands import quality_gates_app  # noqa: E402
from codeframe.cli.metrics_commands import metrics_app  # noqa: E402
from codeframe.cli.session_commands import session_app  # noqa: E402
from codeframe.cli.context_commands import context_app  # noqa: E402
from codeframe.cli.review_commands import review_app  # noqa: E402

# Register Phase 1 command groups
app.add_typer(auth_app, name="auth", help="Authentication (login, logout, register)")
app.add_typer(projects_app, name="projects", help="Project management (list, create, status)")
app.add_typer(blockers_app, name="blockers", help="Blocker resolution (list, resolve, metrics)")
app.add_typer(checkpoints_app, name="checkpoints", help="Checkpoint management (create, restore)")
app.add_typer(discovery_app, name="discovery", help="Discovery workflow (start, progress, answer)")

# Register Phase 2 command groups
app.add_typer(agents_app, name="agents", help="Agent management (list, assign, remove, status)")
app.add_typer(tasks_app, name="tasks", help="Task management (list, create, get, update)")
app.add_typer(quality_gates_app, name="quality-gates", help="Quality gate checks (get, run)")
app.add_typer(metrics_app, name="metrics", help="Usage and cost metrics (tokens, costs, agent)")
app.add_typer(session_app, name="session", help="Session management (get)")
app.add_typer(context_app, name="context", help="Agent context (get, stats, flash-save, checkpoints)")
app.add_typer(review_app, name="review", help="Code review management (status, stats, findings, list)")


if __name__ == "__main__":
    app()
