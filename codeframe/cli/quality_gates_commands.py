"""CLI quality-gates commands.

This module provides commands for quality gate management:
- get: View quality gate status for a task
- run: Trigger quality gate checks

Usage:
    codeframe quality-gates get 5
    codeframe quality-gates run 5
    codeframe quality-gates run 5 --gate tests
"""

import json
import logging
from typing import Optional

import typer
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError
from codeframe.cli.helpers import console, require_auth

logger = logging.getLogger(__name__)

quality_gates_app = typer.Typer(
    name="quality-gates",
    help="Quality gate management",
    no_args_is_help=True,
)


@quality_gates_app.command()
def get(
    task_id: int = typer.Argument(..., help="Task ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """View quality gate status for a task.

    Shows the status of all quality gates (tests, type-check, coverage, review).

    Example:

        codeframe quality-gates get 5
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/tasks/{task_id}/quality-gates")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        overall = result.get("overall_status", "unknown")
        overall_color = "green" if overall == "passed" else "yellow" if overall == "warning" else "red"

        console.print(f"\n[bold]Quality Gates for Task {task_id}[/bold]")
        console.print(f"Overall Status: [{overall_color}]{overall}[/{overall_color}]\n")

        gates = result.get("gates", [])
        if not gates:
            console.print("[yellow]No quality gates configured.[/yellow]")
            return

        table = Table()
        table.add_column("Gate", style="cyan")
        table.add_column("Status")
        table.add_column("Details")

        for gate in gates:
            status = gate.get("status", "unknown")
            if status == "passed":
                status_display = "[green]✓ passed[/green]"
            elif status == "failed":
                status_display = "[red]✗ failed[/red]"
            elif status == "warning":
                status_display = "[yellow]⚠ warning[/yellow]"
            elif status == "pending":
                status_display = "[dim]○ pending[/dim]"
            else:
                status_display = f"[dim]{status}[/dim]"

            table.add_row(
                gate.get("name", ""),
                status_display,
                gate.get("details", ""),
            )

        console.print(table)

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Task {task_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@quality_gates_app.command()
def run(
    task_id: int = typer.Argument(..., help="Task ID"),
    gate: Optional[str] = typer.Option(None, "--gate", "-g", help="Specific gate to run: tests, type_check, coverage, review"),
):
    """Trigger quality gate checks for a task.

    Runs all quality gates or a specific one if --gate is specified.

    Examples:

        codeframe quality-gates run 5

        codeframe quality-gates run 5 --gate tests
    """
    try:
        client = APIClient()
        require_auth(client)

        data = {}
        if gate:
            data["gate"] = gate

        result = client.post(f"/api/tasks/{task_id}/quality-gates", data=data)

        console.print("[green]✓ Quality gate check started[/green]")
        if result.get("message"):
            console.print(result["message"])

        console.print(f"\n[cyan]Check status:[/cyan] codeframe quality-gates get {task_id}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Task {task_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
