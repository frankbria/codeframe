"""CLI project commands.

This module provides commands for project management:
- list: List all projects
- create: Create a new project
- get: Get project details
- status: Get project status
- tasks: List project tasks
- activity: View activity log
- start/pause/resume: Project lifecycle control

Usage:
    codeframe projects list
    codeframe projects create "My Project"
    codeframe projects get 1
    codeframe projects status 1
    codeframe projects tasks 1 --status pending
    codeframe projects start 1
"""

import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

projects_app = typer.Typer(
    name="projects",
    help="Project management commands",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


@projects_app.command("list")
def list_projects(
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List all projects.

    Displays your projects with ID, name, status, phase, and creation date.

    Examples:

        codeframe projects list

        codeframe projects list --format json
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get("/api/projects")
        projects = result.get("projects", [])

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        if not projects:
            console.print("[yellow]No projects found.[/yellow]")
            console.print("Create one with: codeframe projects create \"My Project\"")
            return

        table = Table(title="Projects")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Phase")
        table.add_column("Created")

        for proj in projects:
            table.add_row(
                str(proj.get("id", "")),
                proj.get("name", ""),
                proj.get("status", ""),
                proj.get("phase", ""),
                proj.get("created_at", "")[:10] if proj.get("created_at") else "",
            )

        console.print(table)
        console.print(f"\n{len(projects)} project(s) total")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def create(
    name: str = typer.Argument(..., help="Project name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Project description"),
    source_type: Optional[str] = typer.Option(None, "--source-type", "-t", help="Source type: git_repo, local_path, or empty"),
    source_location: Optional[str] = typer.Option(None, "--source-location", "-l", help="Source URL or path"),
    source_branch: Optional[str] = typer.Option(None, "--source-branch", "-b", help="Git branch name"),
    no_discovery: bool = typer.Option(False, "--no-discovery", help="Skip auto-starting discovery"),
):
    """Create a new project.

    Creates a project with the given name. Discovery will start automatically
    unless --no-discovery is specified.

    Examples:

        codeframe projects create "My New App"

        codeframe projects create "Backend API" --description "REST API for mobile app"

        codeframe projects create "Open Source" --source-type git_repo --source-location https://github.com/user/repo
    """
    try:
        client = APIClient()
        require_auth(client)

        # Build request data
        data = {"name": name}
        if description:
            data["description"] = description
        if source_type:
            data["source_type"] = source_type
        if source_location:
            data["source_location"] = source_location
        if source_branch:
            data["source_branch"] = source_branch

        result = client.post("/api/projects", data=data)

        console.print("[green]✓ Project created successfully[/green]")
        console.print(f"\n[bold]ID:[/bold] {result.get('id')}")
        console.print(f"[bold]Name:[/bold] {result.get('name')}")
        console.print(f"[bold]Status:[/bold] {result.get('status')}")
        console.print(f"[bold]Phase:[/bold] {result.get('phase')}")

        if not no_discovery:
            console.print("\n[cyan]Discovery started automatically.[/cyan]")
            console.print(f"Check progress: codeframe discovery progress {result.get('id')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 409:
            console.print("[red]Error:[/red] A project with this name already exists")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def get(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Get project details.

    Displays detailed information about a specific project.

    Example:

        codeframe projects get 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Project #{result.get('id')}[/bold]")
        console.print(f"[bold]Name:[/bold] {result.get('name')}")
        console.print(f"[bold]Description:[/bold] {result.get('description', 'N/A')}")
        console.print(f"[bold]Status:[/bold] {result.get('status')}")
        console.print(f"[bold]Phase:[/bold] {result.get('phase')}")
        console.print(f"[bold]Created:[/bold] {result.get('created_at')}")
        if result.get("workspace_path"):
            console.print(f"[bold]Workspace:[/bold] {result.get('workspace_path')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def status(
    project_id: int = typer.Argument(..., help="Project ID"),
):
    """Get project status and progress.

    Shows current status, phase, and task completion metrics.

    Example:

        codeframe projects status 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/status")

        console.print(f"\n[bold]Project:[/bold] {result.get('name')}")
        console.print(f"[bold]Status:[/bold] {result.get('status')}")
        console.print(f"[bold]Phase:[/bold] {result.get('phase')}")

        progress = result.get("progress", {})
        if progress:
            total = progress.get("total_tasks", 0)
            completed = progress.get("completed_tasks", 0)
            pct = progress.get("completion_percentage", 0)

            console.print(f"\n[bold]Progress:[/bold] {pct:.0f}% ({completed}/{total} tasks)")

            # Progress bar
            bar_width = 30
            filled = int(bar_width * pct / 100)
            bar = "█" * filled + "░" * (bar_width - filled)
            console.print(f"[{bar}]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def tasks(
    project_id: int = typer.Argument(..., help="Project ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status: pending, in_progress, completed, etc."),
    limit: int = typer.Option(50, "--limit", "-l", help="Max tasks to show"),
    offset: int = typer.Option(0, "--offset", "-o", help="Skip N tasks"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List project tasks.

    Shows tasks with optional filtering by status.

    Examples:

        codeframe projects tasks 1

        codeframe projects tasks 1 --status pending

        codeframe projects tasks 1 --limit 10
    """
    try:
        client = APIClient()
        require_auth(client)

        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        result = client.get(f"/api/projects/{project_id}/tasks", params=params)
        tasks = result.get("tasks", [])
        total = result.get("total", 0)

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        if not tasks:
            console.print("[yellow]No tasks found.[/yellow]")
            return

        table = Table(title=f"Tasks (showing {len(tasks)} of {total})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title")
        table.add_column("Status", style="yellow")
        table.add_column("Priority")

        for task in tasks:
            table.add_row(
                str(task.get("id", "")),
                task.get("title", "")[:50],
                task.get("status", ""),
                str(task.get("priority", "")),
            )

        console.print(table)

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def activity(
    project_id: int = typer.Argument(..., help="Project ID"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max activities to show"),
):
    """View recent project activity.

    Shows the activity log with recent actions and events.

    Example:

        codeframe projects activity 1 --limit 10
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/activity", params={"limit": limit})
        activities = result.get("activity", [])

        if not activities:
            console.print("[yellow]No recent activity.[/yellow]")
            return

        console.print("\n[bold]Recent Activity[/bold]\n")

        for item in activities:
            timestamp = item.get("timestamp", "")[:19].replace("T", " ")
            action = item.get("action", "unknown")
            details = item.get("details", "")

            console.print(f"[dim]{timestamp}[/dim] [cyan]{action}[/cyan]")
            if details:
                console.print(f"  {details}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def start(
    project_id: int = typer.Argument(..., help="Project ID"),
):
    """Start project execution.

    Activates the project and begins agent work.

    Example:

        codeframe projects start 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/projects/{project_id}/start")

        console.print("[green]✓ Project started successfully[/green]")
        if result.get("message"):
            console.print(result["message"])

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def pause(
    project_id: int = typer.Argument(..., help="Project ID"),
):
    """Pause project execution.

    Temporarily stops agent work. Use 'resume' to continue.

    Example:

        codeframe projects pause 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/projects/{project_id}/pause")

        console.print("[green]✓ Project paused[/green]")
        if result.get("message"):
            console.print(result["message"])

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@projects_app.command()
def resume(
    project_id: int = typer.Argument(..., help="Project ID"),
):
    """Resume project execution.

    Continues work from where it was paused.

    Example:

        codeframe projects resume 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/projects/{project_id}/resume")

        console.print("[green]✓ Project resumed[/green]")
        if result.get("message"):
            console.print(result["message"])

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
