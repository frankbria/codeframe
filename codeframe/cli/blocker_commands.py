"""CLI blocker commands.

This module provides commands for human-in-the-loop blocker management:
- list: List blockers for a project
- get: Get blocker details
- resolve: Submit answer to a blocker
- metrics: View blocker analytics

Usage:
    codeframe blockers list 1
    codeframe blockers get 5
    codeframe blockers resolve 5 "Use PostgreSQL"
    codeframe blockers metrics 1
"""

import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

blockers_app = typer.Typer(
    name="blockers",
    help="Blocker management (human-in-the-loop)",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


@blockers_app.command("list")
def list_blockers(
    project_id: int = typer.Argument(..., help="Project ID"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status: PENDING, RESOLVED, EXPIRED"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List blockers for a project.

    Shows all blockers that require human input, optionally filtered by status.

    Examples:

        codeframe blockers list 1

        codeframe blockers list 1 --status PENDING

        codeframe blockers list 1 --format json
    """
    try:
        client = APIClient()
        require_auth(client)

        params = {}
        if status:
            params["status"] = status

        result = client.get(f"/api/projects/{project_id}/blockers", params=params)
        blockers = result.get("blockers", [])

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        if not blockers:
            console.print("[yellow]No blockers found.[/yellow]")
            return

        pending = result.get("pending_count", 0)
        total = result.get("total", len(blockers))

        table = Table(title=f"Blockers ({pending} pending, {total} total)")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Question", max_width=50)
        table.add_column("Status", style="yellow")
        table.add_column("Created")

        for blocker in blockers:
            status_style = "green" if blocker.get("status") == "RESOLVED" else "yellow"
            table.add_row(
                str(blocker.get("id", "")),
                blocker.get("question", "")[:50],
                f"[{status_style}]{blocker.get('status', '')}[/{status_style}]",
                blocker.get("created_at", "")[:10] if blocker.get("created_at") else "",
            )

        console.print(table)

        if pending > 0:
            console.print(f"\n[cyan]Resolve pending blockers:[/cyan] codeframe blockers resolve <id> \"your answer\"")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@blockers_app.command()
def get(
    blocker_id: int = typer.Argument(..., help="Blocker ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Get blocker details.

    Shows the full question, context, and current status.

    Example:

        codeframe blockers get 5
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/blockers/{blocker_id}")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format with panel
        status = result.get("status", "")
        status_color = "green" if status == "RESOLVED" else "yellow" if status == "PENDING" else "red"

        console.print(Panel(
            f"[bold]{result.get('question', 'No question')}[/bold]",
            title=f"Blocker #{result.get('id')}",
            subtitle=f"[{status_color}]{status}[/{status_color}]",
        ))

        console.print(f"\n[bold]Type:[/bold] {result.get('blocker_type', 'N/A')}")
        console.print(f"[bold]Agent:[/bold] {result.get('agent_id', 'N/A')}")
        console.print(f"[bold]Created:[/bold] {result.get('created_at', 'N/A')}")

        if result.get("context"):
            console.print(f"\n[bold]Context:[/bold]\n{result.get('context')}")

        if result.get("answer"):
            console.print(f"\n[bold]Answer:[/bold] {result.get('answer')}")
            console.print(f"[bold]Resolved at:[/bold] {result.get('resolved_at', 'N/A')}")

        if status == "PENDING":
            console.print(f"\n[cyan]Resolve:[/cyan] codeframe blockers resolve {blocker_id} \"your answer\"")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Blocker {blocker_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@blockers_app.command()
def resolve(
    blocker_id: int = typer.Argument(..., help="Blocker ID"),
    answer: str = typer.Argument(..., help="Your answer to the blocker"),
):
    """Resolve a blocker with your answer.

    Submits your answer to unblock the agent waiting for input.

    Example:

        codeframe blockers resolve 5 "Use PostgreSQL for the database"
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/blockers/{blocker_id}/resolve", data={"answer": answer})

        console.print(f"[green]✓ Blocker resolved successfully[/green]")
        console.print(f"\n[bold]Blocker ID:[/bold] {result.get('blocker_id')}")
        console.print(f"[bold]Status:[/bold] {result.get('status')}")
        console.print(f"[bold]Resolved at:[/bold] {result.get('resolved_at')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 409:
            console.print(f"[yellow]Blocker already resolved.[/yellow]")
            console.print("This blocker was resolved previously.")
        elif e.status_code == 404:
            console.print(f"[red]Error:[/red] Blocker {blocker_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@blockers_app.command()
def metrics(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View blocker metrics for a project.

    Shows analytics including average resolution time and expiration rates.

    Example:

        codeframe blockers metrics 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/blockers/metrics")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print("\n[bold]Blocker Metrics[/bold]\n")

        total = result.get("total_blockers", 0)
        resolved = result.get("resolved_count", 0)
        expired = result.get("expired_count", 0)
        pending = result.get("pending_count", 0)

        console.print(f"[bold]Total Blockers:[/bold] {total}")
        console.print(f"[bold]Resolved:[/bold] {resolved} [green]✓[/green]")
        console.print(f"[bold]Expired:[/bold] {expired} [red]✗[/red]")
        console.print(f"[bold]Pending:[/bold] {pending} [yellow]•[/yellow]")

        # Average resolution time
        avg_time = result.get("avg_resolution_time_seconds")
        if avg_time is not None:
            if avg_time >= 3600:
                time_str = f"{avg_time / 3600:.1f} hours"
            elif avg_time >= 60:
                time_str = f"{avg_time / 60:.0f} minutes"
            else:
                time_str = f"{avg_time:.0f} seconds"
            console.print(f"\n[bold]Avg Resolution Time:[/bold] {time_str}")

        # Expiration rate
        exp_rate = result.get("expiration_rate_percent", 0)
        rate_color = "green" if exp_rate < 5 else "yellow" if exp_rate < 20 else "red"
        console.print(f"[bold]Expiration Rate:[/bold] [{rate_color}]{exp_rate:.1f}%[/{rate_color}]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
