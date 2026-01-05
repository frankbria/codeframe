"""CLI discovery commands.

This module provides commands for discovery workflow management:
- start: Start discovery process for a project
- progress: View current discovery progress
- answer: Submit answer to current discovery question
- restart: Reset discovery to start over
- generate-prd: Trigger PRD generation after discovery completes

Usage:
    codeframe discovery start 1
    codeframe discovery progress 1
    codeframe discovery answer 1 "My project builds an e-commerce platform"
    codeframe discovery restart 1 --force
    codeframe discovery generate-prd 1
"""

import json
import logging

import typer
from rich.console import Console
from rich.panel import Panel

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

discovery_app = typer.Typer(
    name="discovery",
    help="Discovery workflow management",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


@discovery_app.command()
def start(
    project_id: int = typer.Argument(..., help="Project ID"),
):
    """Start discovery process for a project.

    Initiates the discovery workflow which guides through questions
    to understand project requirements.

    Example:

        codeframe discovery start 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/projects/{project_id}/start")

        console.print(f"[green]✓ Discovery started for project {project_id}[/green]")
        if result.get("message"):
            console.print(result["message"])
        console.print(f"\n[cyan]Check progress:[/cyan] codeframe discovery progress {project_id}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 409:
            console.print("[yellow]Discovery already in progress.[/yellow]")
            console.print(f"Check status: codeframe discovery progress {project_id}")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@discovery_app.command()
def progress(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """View discovery progress for a project.

    Shows current state, progress percentage, and the current question
    if discovery is in progress.

    Examples:

        codeframe discovery progress 1

        codeframe discovery progress 1 --format json
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/discovery/progress")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        phase = result.get("phase", "unknown")
        discovery = result.get("discovery")

        console.print(f"\n[bold]Project {project_id} - Discovery Progress[/bold]\n")
        console.print(f"[bold]Phase:[/bold] {phase}")

        if discovery is None:
            # Idle state - discovery not started
            console.print("\n[yellow]Discovery not started.[/yellow]")
            console.print(f"Start with: codeframe discovery start {project_id}")
            return

        state = discovery.get("state", "unknown")
        progress_pct = discovery.get("progress_percentage", 0)
        answered = discovery.get("answered_count", 0)
        total = discovery.get("total_required", 0)

        # Show state with color
        state_color = "green" if state == "completed" else "cyan" if state == "discovering" else "yellow"
        console.print(f"[bold]State:[/bold] [{state_color}]{state}[/{state_color}]")

        # Progress bar
        console.print(f"[bold]Progress:[/bold] {progress_pct:.0f}% ({answered}/{total} questions)")
        bar_width = 30
        filled = int(bar_width * progress_pct / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        console.print(f"[{bar}]")

        if state == "discovering":
            # Show current question
            remaining = discovery.get("remaining_count", 0)
            console.print(f"[bold]Remaining:[/bold] {remaining} questions")

            current_q = discovery.get("current_question")
            if current_q:
                console.print(Panel(
                    f"[bold]{current_q.get('question', 'No question')}[/bold]",
                    title=f"Question {answered + 1} of {total}",
                    subtitle=f"Category: {current_q.get('category', 'general')}",
                ))
                console.print(f"\n[cyan]Answer:[/cyan] codeframe discovery answer {project_id} \"your answer here\"")

        elif state == "completed":
            console.print("\n[green]✓ Discovery completed![/green]")
            console.print(f"[cyan]Generate PRD:[/cyan] codeframe discovery generate-prd {project_id}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@discovery_app.command()
def answer(
    project_id: int = typer.Argument(..., help="Project ID"),
    answer_text: str = typer.Argument(..., help="Your answer to the current question"),
):
    """Submit answer to current discovery question.

    Provides your answer to the current discovery question. The system will
    then present the next question or complete discovery if this was the last one.

    Example:

        codeframe discovery answer 1 "This is an e-commerce platform for small businesses"
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(
            f"/api/projects/{project_id}/discovery/answer",
            data={"answer": answer_text},
        )

        is_complete = result.get("is_complete", False)
        progress_pct = result.get("progress_percentage", 0)
        current_idx = result.get("current_index", 0)
        total = result.get("total_questions", 0)

        console.print("[green]✓ Answer submitted[/green]")
        console.print(f"[bold]Progress:[/bold] {progress_pct:.0f}% ({current_idx}/{total})")

        if is_complete:
            console.print("\n[green]✓ Discovery completed![/green]")
            console.print("PRD generation starting automatically...")
            console.print(f"Or trigger manually: codeframe discovery generate-prd {project_id}")
        else:
            next_question = result.get("next_question")
            if next_question:
                console.print("\n[bold]Next Question:[/bold]")
                console.print(Panel(next_question))
                console.print(f"\n[cyan]Answer:[/cyan] codeframe discovery answer {project_id} \"your answer\"")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 400:
            detail = e.detail or str(e)
            if "not active" in detail.lower():
                console.print("[red]Error:[/red] Discovery is not active.")
                console.print(f"Start discovery first: codeframe discovery start {project_id}")
            else:
                console.print(f"[red]Error:[/red] {detail}")
        elif e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@discovery_app.command()
def restart(
    project_id: int = typer.Argument(..., help="Project ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Restart without confirmation"),
):
    """Restart discovery process.

    Resets discovery to the beginning, clearing all previous answers.
    Useful if discovery gets stuck or you want to start over.

    Examples:

        codeframe discovery restart 1

        codeframe discovery restart 1 --force
    """
    try:
        client = APIClient()
        require_auth(client)

        # Confirm unless --force
        if not force:
            confirmed = typer.confirm(
                "Restart discovery? This will clear all previous answers."
            )
            if not confirmed:
                console.print("Cancelled.")
                raise typer.Exit(0)

        result = client.post(f"/api/projects/{project_id}/discovery/restart")

        console.print("[green]✓ Discovery has been reset[/green]")
        if result.get("message"):
            console.print(result["message"])
        console.print(f"\n[cyan]Start again:[/cyan] codeframe discovery start {project_id}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 400:
            detail = e.detail or str(e)
            if "completed" in detail.lower():
                console.print("[yellow]Discovery is already completed.[/yellow]")
                console.print("Completed discovery cannot be restarted.")
            else:
                console.print(f"[red]Error:[/red] {detail}")
        elif e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@discovery_app.command("generate-prd")
def generate_prd(
    project_id: int = typer.Argument(..., help="Project ID"),
):
    """Trigger PRD generation after discovery completes.

    Starts the background process to generate a Product Requirements Document
    based on the discovery answers. PRD generation runs asynchronously.

    Example:

        codeframe discovery generate-prd 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(f"/api/projects/{project_id}/discovery/generate-prd")

        console.print(f"[green]✓ PRD generation started for project {project_id}[/green]")
        if result.get("message"):
            console.print(result["message"])
        console.print("\n[cyan]Watch for WebSocket updates or check project status.[/cyan]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 400:
            detail = e.detail or str(e)
            if "complete" in detail.lower():
                console.print("[yellow]Discovery must be completed first.[/yellow]")
                console.print(f"Check progress: codeframe discovery progress {project_id}")
            else:
                console.print(f"[red]Error:[/red] {detail}")
        elif e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
