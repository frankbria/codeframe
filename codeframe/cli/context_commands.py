"""CLI context commands.

This module provides commands for agent context management:
- get: View agent context information
- stats: View context statistics
- flash-save: Create context checkpoint
- checkpoints: List context checkpoints

Usage:
    codeframe context get lead-agent
    codeframe context stats lead-agent
    codeframe context flash-save lead-agent
    codeframe context checkpoints lead-agent
"""

import json
import logging

import typer
from rich.console import Console
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

context_app = typer.Typer(
    name="context",
    help="Agent context management",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


@context_app.command()
def get(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View agent context information.

    Shows summary of the agent's current context.

    Example:

        codeframe context get lead-agent
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/agents/{agent_id}/context")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Context for Agent: {agent_id}[/bold]\n")

        console.print(f"[bold]Total Tokens:[/bold] {result.get('total_tokens', 0):,}")
        console.print(f"[bold]Items Count:[/bold] {result.get('items_count', 0)}")

        tiers = result.get("tiers", {})
        if tiers:
            console.print(f"\n[bold]Tier Distribution:[/bold]")
            console.print(f"  🔴 Hot:  {tiers.get('hot', 0)} items")
            console.print(f"  🟠 Warm: {tiers.get('warm', 0)} items")
            console.print(f"  🔵 Cold: {tiers.get('cold', 0)} items")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Agent {agent_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@context_app.command()
def stats(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View detailed context statistics.

    Shows comprehensive stats about the agent's context tiers.

    Example:

        codeframe context stats lead-agent
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/agents/{agent_id}/context/stats")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Context Statistics for Agent: {agent_id}[/bold]\n")

        console.print(f"[bold]Total Items:[/bold] {result.get('total_items', 0)}")
        console.print(f"[bold]Total Tokens:[/bold] {result.get('total_tokens', 0):,}")

        # Tier breakdown
        console.print(f"\n[bold]Tier Breakdown:[/bold]")
        table = Table(show_header=True)
        table.add_column("Tier", style="cyan")
        table.add_column("Items", justify="right")
        table.add_column("Tokens", justify="right")

        for tier_name in ["hot", "warm", "cold"]:
            tier = result.get(f"{tier_name}_tier", {})
            table.add_row(
                tier_name.capitalize(),
                str(tier.get("count", 0)),
                f"{tier.get('tokens', 0):,}",
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


@context_app.command("flash-save")
def flash_save(
    agent_id: str = typer.Argument(..., help="Agent ID"),
):
    """Create a context checkpoint (flash save).

    Saves the current context state for later recovery.

    Example:

        codeframe context flash-save lead-agent
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/agents/{agent_id}/flash-save")

        console.print(f"[green]✓ Context checkpoint created[/green]")
        console.print(f"\n[bold]Checkpoint ID:[/bold] {result.get('checkpoint_id')}")
        console.print(f"[bold]Timestamp:[/bold] {result.get('timestamp')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Agent {agent_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@context_app.command()
def checkpoints(
    agent_id: str = typer.Argument(..., help="Agent ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List context checkpoints for an agent.

    Shows all saved context checkpoints.

    Example:

        codeframe context checkpoints lead-agent
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/agents/{agent_id}/flash-save/checkpoints")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        checkpoints_list = result.get("checkpoints", [])

        if not checkpoints_list:
            console.print("[yellow]No checkpoints found.[/yellow]")
            console.print(f"Create one: codeframe context flash-save {agent_id}")
            return

        table = Table(title=f"Context Checkpoints for {agent_id}")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Timestamp")
        table.add_column("Items", justify="right")

        for cp in checkpoints_list:
            table.add_row(
                cp.get("id", ""),
                cp.get("timestamp", "")[:19].replace("T", " "),
                str(cp.get("items_count", 0)),
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
