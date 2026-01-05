"""CLI tasks commands.

This module provides commands for task management:
- list: List tasks for a project
- create: Create a new task
- get: Get task details
- update: Update task status/priority

Usage:
    codeframe tasks list 1
    codeframe tasks create 1 "Implement feature X"
    codeframe tasks get 5
    codeframe tasks update 5 --status completed
"""

import json
import logging
from typing import Optional

import typer
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError
from codeframe.cli.helpers import console, require_auth

logger = logging.getLogger(__name__)

tasks_app = typer.Typer(
    name="tasks",
    help="Task management commands",
    no_args_is_help=True,
)


@tasks_app.command("list")
def list_tasks(
    project_id: int = typer.Argument(..., help="Project ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status: pending, in_progress, completed"),
    priority: Optional[int] = typer.Option(None, "--priority", "-p", help="Filter by priority (0-4)"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max tasks to show"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List tasks for a project.

    Shows all tasks with optional filtering by status or priority.

    Examples:

        codeframe tasks list 1

        codeframe tasks list 1 --status pending

        codeframe tasks list 1 --priority 1
    """
    try:
        client = APIClient()
        require_auth(client)

        params = {"limit": limit}
        if status:
            params["status"] = status
        if priority is not None:
            params["priority"] = priority

        result = client.get(f"/api/projects/{project_id}/tasks", params=params)
        tasks = result.get("tasks", [])
        total = result.get("total", len(tasks))

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        if not tasks:
            console.print("[yellow]No tasks found.[/yellow]")
            console.print(f"Create one: codeframe tasks create {project_id} \"Task title\"")
            return

        table = Table(title=f"Tasks (showing {len(tasks)} of {total})")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Title", max_width=40)
        table.add_column("Status", style="yellow")
        table.add_column("Priority")

        for task in tasks:
            # Color-code status
            status_val = task.get("status", "")
            if status_val == "completed":
                status_display = f"[green]{status_val}[/green]"
            elif status_val == "in_progress":
                status_display = f"[cyan]{status_val}[/cyan]"
            else:
                status_display = f"[yellow]{status_val}[/yellow]"

            # Priority display
            pri = task.get("priority", 3)
            pri_labels = {0: "🔴 Critical", 1: "🟠 High", 2: "🟡 Medium", 3: "🟢 Normal", 4: "⚪ Low"}
            pri_display = pri_labels.get(pri, str(pri))

            table.add_row(
                str(task.get("id", "")),
                task.get("title", "")[:40],
                status_display,
                pri_display,
            )

        console.print(table)

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@tasks_app.command()
def create(
    project_id: int = typer.Argument(..., help="Project ID"),
    title: str = typer.Argument(..., help="Task title"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Task description"),
    priority: int = typer.Option(3, "--priority", "-p", help="Priority (0=critical, 4=low)"),
    status: str = typer.Option("pending", "--status", "-s", help="Initial status"),
):
    """Create a new task.

    Adds a task to the specified project.

    Examples:

        codeframe tasks create 1 "Implement user login"

        codeframe tasks create 1 "Fix bug" --priority 1 --description "Critical security issue"
    """
    try:
        client = APIClient()
        require_auth(client)

        data = {
            "project_id": project_id,
            "title": title,
            "priority": priority,
            "status": status,
        }
        if description:
            data["description"] = description

        result = client.post("/api/tasks", data=data)

        console.print("[green]✓ Task created successfully[/green]")
        console.print(f"\n[bold]ID:[/bold] {result.get('id')}")
        console.print(f"[bold]Title:[/bold] {result.get('title')}")
        console.print(f"[bold]Status:[/bold] {result.get('status')}")
        console.print(f"[bold]Priority:[/bold] {result.get('priority')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@tasks_app.command()
def get(
    task_id: int = typer.Argument(..., help="Task ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Get task details.

    Shows full information about a specific task.

    Example:

        codeframe tasks get 5
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/tasks/{task_id}")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Task #{result.get('id')}[/bold]")
        console.print(f"[bold]Title:[/bold] {result.get('title')}")
        console.print(f"[bold]Project:[/bold] {result.get('project_id')}")
        console.print(f"[bold]Status:[/bold] {result.get('status')}")
        console.print(f"[bold]Priority:[/bold] {result.get('priority')}")
        console.print(f"[bold]Created:[/bold] {result.get('created_at')}")

        if result.get("description"):
            console.print(f"\n[bold]Description:[/bold]\n{result.get('description')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Task {task_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@tasks_app.command()
def update(
    task_id: int = typer.Argument(..., help="Task ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="New status"),
    priority: Optional[int] = typer.Option(None, "--priority", "-p", help="New priority (0-4)"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="New title"),
):
    """Update task status or priority.

    Modifies an existing task's attributes.

    Examples:

        codeframe tasks update 5 --status completed

        codeframe tasks update 5 --priority 1 --status in_progress
    """
    try:
        client = APIClient()
        require_auth(client)

        # Build update data
        data = {}
        if status:
            data["status"] = status
        if priority is not None:
            data["priority"] = priority
        if title:
            data["title"] = title

        if not data:
            console.print("[yellow]No updates specified.[/yellow]")
            console.print("Use --status, --priority, or --title to update task.")
            raise typer.Exit(1)

        result = client.patch(f"/api/tasks/{task_id}", data=data)

        console.print("[green]✓ Task updated successfully[/green]")
        console.print(f"\n[bold]ID:[/bold] {result.get('id')}")
        if status:
            console.print(f"[bold]Status:[/bold] {result.get('status')}")
        if priority is not None:
            console.print(f"[bold]Priority:[/bold] {result.get('priority')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Task {task_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
