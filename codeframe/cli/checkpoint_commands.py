"""CLI checkpoint commands.

This module provides commands for checkpoint management:
- list: List project checkpoints
- create: Create a new checkpoint
- get: Get checkpoint details
- delete: Delete a checkpoint
- restore: Restore project to checkpoint state
- diff: Show changes since checkpoint

Usage:
    codeframe checkpoints list 1
    codeframe checkpoints create 1 "Before refactor"
    codeframe checkpoints restore 1 5 --confirm
"""

import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError

logger = logging.getLogger(__name__)

checkpoints_app = typer.Typer(
    name="checkpoints",
    help="Checkpoint management (state recovery)",
    no_args_is_help=True,
)
console = Console()


def require_auth(client: APIClient):
    """Check if client is authenticated, exit with error if not."""
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


@checkpoints_app.command("list")
def list_checkpoints(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List checkpoints for a project.

    Shows all saved project states that can be restored.

    Examples:

        codeframe checkpoints list 1

        codeframe checkpoints list 1 --format json
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/checkpoints")
        checkpoints = result.get("checkpoints", [])

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        if not checkpoints:
            console.print("[yellow]No checkpoints found.[/yellow]")
            console.print(f"Create one: codeframe checkpoints create {project_id} \"Checkpoint name\"")
            return

        table = Table(title=f"Checkpoints ({len(checkpoints)} total)")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="green")
        table.add_column("Trigger")
        table.add_column("Commit", max_width=10)
        table.add_column("Created")

        for cp in checkpoints:
            table.add_row(
                str(cp.get("id", "")),
                cp.get("name", ""),
                cp.get("trigger", ""),
                cp.get("git_commit", "")[:7] if cp.get("git_commit") else "",
                cp.get("created_at", "")[:10] if cp.get("created_at") else "",
            )

        console.print(table)

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@checkpoints_app.command()
def create(
    project_id: int = typer.Argument(..., help="Project ID"),
    name: str = typer.Argument(..., help="Checkpoint name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Checkpoint description"),
    trigger: str = typer.Option("manual", "--trigger", "-t", help="Trigger type: manual or automatic"),
):
    """Create a new checkpoint.

    Saves the current project state (code, database, context) for later recovery.

    Examples:

        codeframe checkpoints create 1 "Before refactor"

        codeframe checkpoints create 1 "Phase complete" --description "All Phase 1 tasks done"
    """
    try:
        client = APIClient()
        require_auth(client)

        data = {
            "name": name,
            "trigger": trigger,
        }
        if description:
            data["description"] = description

        result = client.post(f"/api/projects/{project_id}/checkpoints", data=data)

        console.print(f"[green]✓ Checkpoint created successfully[/green]")
        console.print(f"\n[bold]ID:[/bold] {result.get('id')}")
        console.print(f"[bold]Name:[/bold] {result.get('name')}")
        console.print(f"[bold]Commit:[/bold] {result.get('git_commit', '')[:7]}")
        console.print(f"[bold]Created:[/bold] {result.get('created_at')}")

        console.print(f"\n[cyan]Restore:[/cyan] codeframe checkpoints restore {project_id} {result.get('id')} --confirm")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@checkpoints_app.command()
def get(
    project_id: int = typer.Argument(..., help="Project ID"),
    checkpoint_id: int = typer.Argument(..., help="Checkpoint ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Get checkpoint details.

    Shows full checkpoint information including metadata.

    Example:

        codeframe checkpoints get 1 5
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/checkpoints/{checkpoint_id}")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Checkpoint #{result.get('id')}[/bold]")
        console.print(f"[bold]Name:[/bold] {result.get('name')}")
        if result.get("description"):
            console.print(f"[bold]Description:[/bold] {result.get('description')}")
        console.print(f"[bold]Trigger:[/bold] {result.get('trigger')}")
        console.print(f"[bold]Git Commit:[/bold] {result.get('git_commit')}")
        console.print(f"[bold]Created:[/bold] {result.get('created_at')}")

        # Metadata
        metadata = result.get("metadata", {})
        if metadata:
            console.print("\n[bold]Metadata:[/bold]")
            console.print(f"  Tasks: {metadata.get('tasks_completed', 0)}/{metadata.get('tasks_total', 0)} completed")
            if metadata.get("total_cost_usd") is not None:
                console.print(f"  Cost: ${metadata.get('total_cost_usd', 0):.2f}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Checkpoint not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@checkpoints_app.command()
def delete(
    project_id: int = typer.Argument(..., help="Project ID"),
    checkpoint_id: int = typer.Argument(..., help="Checkpoint ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Delete without confirmation"),
):
    """Delete a checkpoint.

    Removes checkpoint and its backup files. This cannot be undone.

    Examples:

        codeframe checkpoints delete 1 5

        codeframe checkpoints delete 1 5 --force
    """
    try:
        client = APIClient()
        require_auth(client)

        # Confirm unless --force
        if not force:
            confirmed = typer.confirm(f"Delete checkpoint {checkpoint_id}? This cannot be undone.")
            if not confirmed:
                console.print("Cancelled.")
                raise typer.Exit(0)

        client.delete(f"/api/projects/{project_id}/checkpoints/{checkpoint_id}")

        console.print(f"[green]✓ Checkpoint {checkpoint_id} deleted[/green]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@checkpoints_app.command()
def restore(
    project_id: int = typer.Argument(..., help="Project ID"),
    checkpoint_id: int = typer.Argument(..., help="Checkpoint ID"),
    confirm: bool = typer.Option(False, "--confirm", "-c", help="Actually perform the restore"),
):
    """Restore project to checkpoint state.

    Without --confirm, shows a preview of changes. With --confirm, performs the restore.

    Examples:

        codeframe checkpoints restore 1 5         # Preview changes

        codeframe checkpoints restore 1 5 --confirm  # Perform restore
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.post(
            f"/api/projects/{project_id}/checkpoints/{checkpoint_id}/restore",
            data={"confirm_restore": confirm},
        )

        if confirm:
            # Actual restore
            console.print(f"[green]✓ Project restored to checkpoint successfully[/green]")
            console.print(f"\n[bold]Checkpoint:[/bold] {result.get('checkpoint_name')}")
            console.print(f"[bold]Git Commit:[/bold] {result.get('git_commit')}")
            if result.get("items_restored"):
                console.print(f"[bold]Items Restored:[/bold] {result.get('items_restored')}")
        else:
            # Preview
            console.print(f"[bold]Preview: Changes since checkpoint '{result.get('checkpoint_name')}'[/bold]\n")

            diff = result.get("diff", "")
            if diff:
                syntax = Syntax(diff, "diff", theme="monokai", line_numbers=True)
                console.print(syntax)
            else:
                console.print("[yellow]No changes to show.[/yellow]")

            console.print(f"\n[cyan]To restore:[/cyan] codeframe checkpoints restore {project_id} {checkpoint_id} --confirm")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@checkpoints_app.command()
def diff(
    project_id: int = typer.Argument(..., help="Project ID"),
    checkpoint_id: int = typer.Argument(..., help="Checkpoint ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Show changes since checkpoint.

    Displays git diff with statistics.

    Example:

        codeframe checkpoints diff 1 5
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/checkpoints/{checkpoint_id}/diff")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        files = result.get("files_changed", 0)
        ins = result.get("insertions", 0)
        dels = result.get("deletions", 0)

        console.print(f"\n[bold]Changes since checkpoint:[/bold]")
        console.print(f"  [cyan]{files}[/cyan] files changed")
        console.print(f"  [green]+{ins}[/green] insertions")
        console.print(f"  [red]-{dels}[/red] deletions")

        diff_content = result.get("diff", "")
        if diff_content:
            console.print("\n[bold]Diff:[/bold]")
            syntax = Syntax(diff_content, "diff", theme="monokai")
            console.print(syntax)

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
