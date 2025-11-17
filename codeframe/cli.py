"""Command-line interface for CodeFRAME."""

from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from codeframe.core.project import Project

app = typer.Typer(
    name="codeframe",
    help="Fully Remote Autonomous Multiagent Environment for coding",
    add_completion=False,
)
console = Console()


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

        console.print(f"\n[bold]Project:[/bold] {status['project_name']}")
        console.print(f"[bold]Status:[/bold] {status['status']}")
        console.print(f"[bold]Progress:[/bold] {status['completion_percentage']}%")
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


@app.command()
def checkpoint(
    action: str = typer.Argument("create", help="Action: create or list"),
    message: Optional[str] = typer.Option(None, help="Checkpoint message"),
):
    """Manage checkpoints."""
    console.print(f"Checkpoint {action} - [yellow]Not implemented yet[/yellow]")


@app.command()
def agents(
    action: str = typer.Argument("list", help="Action: list or status"),
    agent_id: Optional[str] = typer.Argument(None, help="Agent ID"),
):
    """Manage agents."""
    console.print(f"Agents {action} - [yellow]Not implemented yet[/yellow]")


@app.command()
def version():
    """Show CodeFRAME version."""
    from codeframe import __version__

    console.print(f"CodeFRAME version: [bold green]{__version__}[/bold green]")


if __name__ == "__main__":
    app()
