"""CLI metrics commands.

This module provides commands for viewing usage metrics:
- tokens: View token usage for a project
- costs: View cost metrics for a project
- agent: View metrics for a specific agent

Usage:
    codeframe metrics tokens 1
    codeframe metrics costs 1
    codeframe metrics agent lead-agent
"""

import json
import logging

import typer
from rich.console import Console
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

metrics_app = typer.Typer(
    name="metrics",
    help="Usage and cost metrics",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


def format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


@metrics_app.command()
def tokens(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View token usage for a project.

    Shows total tokens used, broken down by input/output and agent.

    Example:

        codeframe metrics tokens 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/metrics/tokens")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Token Usage for Project {project_id}[/bold]\n")

        total = result.get("total_tokens", 0)
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)

        console.print(f"[bold]Total Tokens:[/bold] {format_number(total)}")
        console.print(f"  Input:  {format_number(input_tokens)}")
        console.print(f"  Output: {format_number(output_tokens)}")

        # By agent breakdown
        by_agent = result.get("by_agent", [])
        if by_agent:
            console.print("\n[bold]By Agent:[/bold]")
            table = Table(show_header=True)
            table.add_column("Agent", style="cyan")
            table.add_column("Tokens", justify="right")

            for agent in by_agent:
                table.add_row(
                    agent.get("agent_id", ""),
                    format_number(agent.get("tokens", 0)),
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


@metrics_app.command()
def costs(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View cost metrics for a project.

    Shows total costs in USD, broken down by input/output and daily.

    Example:

        codeframe metrics costs 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/metrics/costs")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Cost Metrics for Project {project_id}[/bold]\n")

        total = result.get("total_cost_usd", 0)
        input_cost = result.get("input_cost_usd", 0)
        output_cost = result.get("output_cost_usd", 0)

        console.print(f"[bold]Total Cost:[/bold] ${total:.2f}")
        console.print(f"  Input:  ${input_cost:.2f}")
        console.print(f"  Output: ${output_cost:.2f}")

        # By day breakdown
        by_day = result.get("by_day", [])
        if by_day:
            console.print("\n[bold]Daily Breakdown:[/bold]")
            table = Table(show_header=True)
            table.add_column("Date", style="cyan")
            table.add_column("Cost", justify="right")

            for day in by_day[-7:]:  # Last 7 days
                table.add_row(
                    day.get("date", ""),
                    f"${day.get('cost_usd', 0):.2f}",
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


@metrics_app.command()
def agent(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View metrics for a specific agent.

    Shows agent's token usage, costs, and task completion stats.

    Example:

        codeframe metrics agent lead-agent
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/agents/{agent_id}/metrics")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Metrics for Agent: {agent_id}[/bold]\n")

        total_tokens = result.get("total_tokens", 0)
        total_cost = result.get("total_cost_usd", 0)
        tasks_completed = result.get("tasks_completed", 0)
        avg_tokens = result.get("average_tokens_per_task", 0)

        console.print(f"[bold]Total Tokens:[/bold] {format_number(total_tokens)}")
        console.print(f"[bold]Total Cost:[/bold] ${total_cost:.2f}")
        console.print(f"[bold]Tasks Completed:[/bold] {tasks_completed}")
        console.print(f"[bold]Avg Tokens/Task:[/bold] {format_number(avg_tokens)}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Agent {agent_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
