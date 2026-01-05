"""CLI session commands.

This module provides commands for session management:
- get: View current session state

Usage:
    codeframe session get 1
"""

import json
import logging

import typer

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError
from codeframe.cli.helpers import console, require_auth

logger = logging.getLogger(__name__)

session_app = typer.Typer(
    name="session",
    help="Session management",
    no_args_is_help=True,
)


@session_app.callback()
def session_callback():
    """Session management commands."""
    pass


@session_app.command("get")
def get_session(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View current session state for a project.

    Shows the active session information if one exists.

    Example:

        codeframe session get 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/session")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Session for Project {project_id}[/bold]\n")

        status = result.get("status", "unknown")
        status_color = "green" if status == "active" else "yellow"

        console.print(f"[bold]Session ID:[/bold] {result.get('session_id', 'N/A')}")
        console.print(f"[bold]Status:[/bold] [{status_color}]{status}[/{status_color}]")
        console.print(f"[bold]Started:[/bold] {result.get('started_at', 'N/A')}")
        console.print(f"[bold]Last Activity:[/bold] {result.get('last_activity', 'N/A')}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[yellow]No active session for project {project_id}.[/yellow]")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
