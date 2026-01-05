"""CLI agents commands.

This module provides commands for agent management:
- list: List agents assigned to a project
- assign: Assign an agent to a project
- remove: Remove an agent from a project
- status: Show agent's project assignments
- role: Update an agent's role

Usage:
    codeframe agents list 1
    codeframe agents assign 1 worker-2 --role worker
    codeframe agents remove 1 worker-1 --force
    codeframe agents status lead-agent
    codeframe agents role 1 worker-1 specialist
"""

import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

agents_app = typer.Typer(
    name="agents",
    help="Agent management commands",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


@agents_app.command("list")
def list_agents(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List agents assigned to a project.

    Shows all agents working on the specified project with their roles and status.

    Examples:

        codeframe agents list 1

        codeframe agents list 1 --format json
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/agents")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        if not result:
            console.print("[yellow]No agents assigned to this project.[/yellow]")
            console.print(f"Assign one: codeframe agents assign {project_id} <agent-id>")
            return

        table = Table(title=f"Agents for Project {project_id}")
        table.add_column("Agent ID", style="cyan", no_wrap=True)
        table.add_column("Role", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Assigned")

        for agent in result:
            status_style = "green" if agent.get("status") == "active" else "yellow"
            table.add_row(
                agent.get("agent_id", ""),
                agent.get("role", ""),
                f"[{status_style}]{agent.get('status', '')}[/{status_style}]",
                agent.get("assigned_at", "")[:10] if agent.get("assigned_at") else "",
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


@agents_app.command()
def assign(
    project_id: int = typer.Argument(..., help="Project ID"),
    agent_id: str = typer.Argument(..., help="Agent ID to assign"),
    role: str = typer.Option("worker", "--role", "-r", help="Agent role: lead, worker, specialist"),
):
    """Assign an agent to a project.

    Adds an agent to work on the specified project with the given role.

    Examples:

        codeframe agents assign 1 worker-2

        codeframe agents assign 1 specialist-1 --role specialist
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(
            f"/api/projects/{project_id}/agents",
            data={"agent_id": agent_id, "role": role},
        )

        console.print(f"[green]✓ Agent assigned successfully[/green]")
        console.print(f"\n[bold]Agent ID:[/bold] {result.get('agent_id')}")
        console.print(f"[bold]Project:[/bold] {project_id}")
        console.print(f"[bold]Role:[/bold] {result.get('role')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        elif e.status_code == 409:
            console.print(f"[yellow]Agent {agent_id} is already assigned to this project.[/yellow]")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@agents_app.command()
def remove(
    project_id: int = typer.Argument(..., help="Project ID"),
    agent_id: str = typer.Argument(..., help="Agent ID to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Remove without confirmation"),
):
    """Remove an agent from a project.

    Unassigns an agent from the specified project.

    Examples:

        codeframe agents remove 1 worker-1

        codeframe agents remove 1 worker-1 --force
    """
    try:
        client = APIClient()
        require_auth(client)

        # Confirm unless --force
        if not force:
            confirmed = typer.confirm(f"Remove agent {agent_id} from project {project_id}?")
            if not confirmed:
                console.print("Cancelled.")
                raise typer.Exit(0)

        client.delete(f"/api/projects/{project_id}/agents/{agent_id}")

        console.print(f"[green]✓ Agent {agent_id} removed from project {project_id}[/green]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Agent or project not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@agents_app.command()
def status(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """Show agent's project assignments.

    Displays all projects the agent is assigned to.

    Example:

        codeframe agents status lead-agent
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/agents/{agent_id}/projects")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        console.print(f"\n[bold]Agent:[/bold] {agent_id}")

        if not result:
            console.print("[yellow]Not assigned to any projects.[/yellow]")
            return

        table = Table(title="Project Assignments")
        table.add_column("Project ID", style="cyan", no_wrap=True)
        table.add_column("Project Name", style="green")
        table.add_column("Role")
        table.add_column("Assigned")

        for proj in result:
            table.add_row(
                str(proj.get("project_id", "")),
                proj.get("project_name", ""),
                proj.get("role", ""),
                proj.get("assigned_at", "")[:10] if proj.get("assigned_at") else "",
            )

        console.print(table)

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Agent {agent_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@agents_app.command()
def role(
    project_id: int = typer.Argument(..., help="Project ID"),
    agent_id: str = typer.Argument(..., help="Agent ID"),
    new_role: str = typer.Argument(..., help="New role: lead, worker, specialist"),
):
    """Update an agent's role in a project.

    Changes the role of an agent within a specific project.

    Example:

        codeframe agents role 1 worker-1 specialist
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.put(
            f"/api/projects/{project_id}/agents/{agent_id}/role",
            data={"role": new_role},
        )

        console.print(f"[green]✓ Agent role updated[/green]")
        console.print(f"\n[bold]Agent:[/bold] {result.get('agent_id')}")
        console.print(f"[bold]New Role:[/bold] {result.get('role')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Agent or project not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
