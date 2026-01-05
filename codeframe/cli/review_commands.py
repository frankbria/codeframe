"""CLI review commands.

This module provides commands for code review management:
- status: Get review status for a task
- stats: Get review statistics for a project
- findings: Get review findings for a task
- list: List all reviews for a project

Usage:
    codeframe review status 42
    codeframe review stats 1
    codeframe review findings 42
    codeframe review list 1
"""

import json
import logging

import typer
from rich.table import Table

from codeframe.cli.api_client import APIClient, APIError, AuthenticationError
from codeframe.cli.helpers import console, require_auth

logger = logging.getLogger(__name__)

review_app = typer.Typer(
    name="review",
    help="Code review management",
    no_args_is_help=True,
)


def severity_emoji(severity: str) -> str:
    """Get emoji for severity level."""
    mapping = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🔵",
        "info": "⚪",
    }
    return mapping.get(severity.lower(), "⚫")


@review_app.command()
def status(
    task_id: int = typer.Argument(..., help="Task ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Get review status for a task.

    Shows whether a review exists and its status.

    Example:

        codeframe review status 42
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/tasks/{task_id}/review-status")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Review Status for Task {task_id}[/bold]\n")

        has_review = result.get("has_review", False)

        if has_review:
            status_val = result.get("status", "unknown")
            score = result.get("overall_score", 0)
            findings_count = result.get("findings_count", 0)

            status_color = {
                "approved": "green",
                "changes_requested": "yellow",
                "rejected": "red",
            }.get(status_val, "white")

            console.print(f"[bold]Status:[/bold] [{status_color}]{status_val}[/{status_color}]")
            console.print(f"[bold]Score:[/bold] {score}")
            console.print(f"[bold]Findings:[/bold] {findings_count}")
        else:
            console.print("[yellow]No review exists for this task.[/yellow]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Task {task_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@review_app.command()
def stats(
    project_id: int = typer.Argument(..., help="Project ID"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """Get review statistics for a project.

    Shows aggregated review metrics across all tasks.

    Example:

        codeframe review stats 1
    """
    try:
        client = APIClient()
        require_auth(client)

        result = client.get(f"/api/projects/{project_id}/review-stats")

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Text format
        console.print(f"\n[bold]Review Statistics for Project {project_id}[/bold]\n")

        total = result.get("total_reviews", 0)
        approved = result.get("approved_count", 0)
        changes = result.get("changes_requested_count", 0)
        rejected = result.get("rejected_count", 0)
        avg_score = result.get("average_score", 0)

        console.print(f"[bold]Total Reviews:[/bold] {total}")
        console.print(f"[bold]Average Score:[/bold] {avg_score}")
        console.print("\n[bold]By Status:[/bold]")
        console.print(f"  ✅ Approved: {approved}")
        console.print(f"  🔄 Changes Requested: {changes}")
        console.print(f"  ❌ Rejected: {rejected}")

    except AuthenticationError as e:
        console.print(f"[red]Authentication error:[/red] {e}")
        raise typer.Exit(1)

    except APIError as e:
        if e.status_code == 404:
            console.print(f"[red]Error:[/red] Project {project_id} not found")
        else:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@review_app.command()
def findings(
    task_id: int = typer.Argument(..., help="Task ID"),
    severity: str = typer.Option(None, "--severity", "-s", help="Filter by severity"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """Get review findings for a task.

    Shows all code review findings with severity and category.

    Example:

        codeframe review findings 42
        codeframe review findings 42 --severity critical
    """
    try:
        client = APIClient()
        require_auth(client)

        # Build URL with optional severity filter
        url = f"/api/tasks/{task_id}/reviews"
        if severity:
            url += f"?severity={severity}"

        result = client.get(url)

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        findings_list = result.get("findings", [])
        total = result.get("total_count", 0)
        severity_counts = result.get("severity_counts", {})
        has_blocking = result.get("has_blocking_findings", False)

        console.print(f"\n[bold]Review Findings for Task {task_id}[/bold]\n")

        if not findings_list:
            console.print("[green]✓ No findings found.[/green]")
            return

        # Summary
        console.print(f"[bold]Total Findings:[/bold] {total}")
        if has_blocking:
            console.print("[red]⚠ Has blocking findings (critical/high)[/red]")

        console.print("\n[bold]By Severity:[/bold]")
        for sev, count in severity_counts.items():
            if count > 0:
                console.print(f"  {severity_emoji(sev)} {sev.capitalize()}: {count}")

        # Findings table
        console.print()
        table = Table(show_header=True)
        table.add_column("Severity", style="cyan", width=10)
        table.add_column("Category", width=14)
        table.add_column("File", width=25)
        table.add_column("Message", width=40)

        for finding in findings_list:
            sev = finding.get("severity", "unknown")
            table.add_row(
                f"{severity_emoji(sev)} {sev}",
                finding.get("category", ""),
                finding.get("file_path", "")[-25:],  # Truncate long paths
                finding.get("message", "")[:40],
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


@review_app.command("list")
def list_reviews(
    project_id: int = typer.Argument(..., help="Project ID"),
    severity: str = typer.Option(None, "--severity", "-s", help="Filter by severity"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
):
    """List all code review findings for a project.

    Shows aggregated findings across all tasks in the project.

    Example:

        codeframe review list 1
        codeframe review list 1 --severity critical
    """
    try:
        client = APIClient()
        require_auth(client)

        # Build URL with optional severity filter
        url = f"/api/projects/{project_id}/code-reviews"
        if severity:
            url += f"?severity={severity}"

        result = client.get(url)

        if format == "json":
            console.print(json.dumps(result, indent=2))
            return

        # Table format
        findings_list = result.get("findings", [])
        total = result.get("total_count", 0)
        severity_counts = result.get("severity_counts", {})
        has_blocking = result.get("has_blocking_findings", False)

        console.print(f"\n[bold]Code Reviews for Project {project_id}[/bold]\n")

        if not findings_list:
            console.print("[green]✓ No findings found.[/green]")
            return

        # Summary
        console.print(f"[bold]Total Findings:[/bold] {total}")
        if has_blocking:
            console.print("[red]⚠ Has blocking findings (critical/high)[/red]")

        console.print("\n[bold]By Severity:[/bold]")
        for sev, count in severity_counts.items():
            if count > 0:
                console.print(f"  {severity_emoji(sev)} {sev.capitalize()}: {count}")

        # Findings table
        console.print()
        table = Table(show_header=True)
        table.add_column("Task", justify="right", width=6)
        table.add_column("Severity", style="cyan", width=10)
        table.add_column("Category", width=14)
        table.add_column("File", width=22)
        table.add_column("Message", width=35)

        for finding in findings_list:
            sev = finding.get("severity", "unknown")
            table.add_row(
                str(finding.get("task_id", "")),
                f"{severity_emoji(sev)} {sev}",
                finding.get("category", ""),
                finding.get("file_path", "")[-22:],  # Truncate long paths
                finding.get("message", "")[:35],
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
