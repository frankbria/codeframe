"""CLI stats commands for headless token/cost tracking.

This module provides commands for viewing token usage and cost statistics
directly from the local workspace database (no server required):

- tokens: View workspace token usage summary
- costs: View cost report with optional period filtering
- export: Export usage data to CSV or JSON

Usage:
    cf stats tokens                    # Workspace token summary
    cf stats tokens --task <id>        # Per-task breakdown
    cf stats costs                     # All-time costs
    cf stats costs --period month      # Last 30 days
    cf stats export --format csv --output tokens.csv
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from codeframe.cli.helpers import console

logger = logging.getLogger(__name__)

stats_app = typer.Typer(
    name="stats",
    help="Token usage and cost statistics",
    no_args_is_help=True,
)


def _get_db():
    """Get database from current workspace.

    Looks for .codeframe/state.db relative to the current directory.

    Returns:
        Initialized Database instance.

    Raises:
        typer.Exit: If no workspace is found.
    """
    from codeframe.persistence.database import Database

    db_path = Path(".codeframe/state.db")
    if not db_path.exists():
        console.print("[red]Error:[/red] No workspace found. Run 'cf init' first.")
        raise typer.Exit(1)
    db = Database(db_path)
    db.initialize()
    return db


def _get_tracker(db):
    """Create a MetricsTracker from a database instance.

    Args:
        db: Initialized Database instance.

    Returns:
        MetricsTracker instance.
    """
    from codeframe.lib.metrics_tracker import MetricsTracker

    return MetricsTracker(db=db)


def _format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


@stats_app.command()
def tokens(
    task: Optional[int] = typer.Option(
        None, "--task", "-t", help="Filter by task ID for per-task breakdown"
    ),
):
    """Show workspace token usage summary.

    Displays total tokens used across all tasks, with input/output breakdown
    and per-model statistics. Use --task to filter to a specific task.

    Examples:
        cf stats tokens                # Workspace summary
        cf stats tokens --task 1       # Task 1 breakdown
    """
    db = _get_db()
    try:
        tracker = _get_tracker(db)

        if task is not None:
            # Per-task summary
            summary = tracker.get_task_token_summary(task)

            console.print(f"\n[bold]Token Usage for Task {task}[/bold]\n")

            table = Table(show_header=True, title=None)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right")

            table.add_row("Total Tokens", _format_number(summary["total_tokens"]))
            table.add_row("Input Tokens", _format_number(summary["total_input_tokens"]))
            table.add_row("Output Tokens", _format_number(summary["total_output_tokens"]))
            table.add_row("Total Cost", f"${summary['total_cost_usd']:.4f}")
            table.add_row("LLM Calls", str(summary["call_count"]))

            console.print(table)
        else:
            # Workspace-wide summary
            records = db.get_workspace_token_usage()

            total_input = 0
            total_output = 0
            total_cost = 0.0
            model_stats: dict[str, dict] = {}

            for record in records:
                total_input += record["input_tokens"]
                total_output += record["output_tokens"]
                total_cost += record["estimated_cost_usd"]

                model = record["model_name"]
                if model not in model_stats:
                    model_stats[model] = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                        "calls": 0,
                    }
                model_stats[model]["input_tokens"] += record["input_tokens"]
                model_stats[model]["output_tokens"] += record["output_tokens"]
                model_stats[model]["cost_usd"] += record["estimated_cost_usd"]
                model_stats[model]["calls"] += 1

            total_tokens = total_input + total_output

            console.print("\n[bold]Workspace Token Usage Summary[/bold]\n")

            summary_table = Table(show_header=True)
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", justify="right")

            summary_table.add_row("Total Tokens", _format_number(total_tokens))
            summary_table.add_row("Input Tokens", _format_number(total_input))
            summary_table.add_row("Output Tokens", _format_number(total_output))
            summary_table.add_row("Total Cost", f"${total_cost:.4f}")
            summary_table.add_row("LLM Calls", str(len(records)))

            console.print(summary_table)

            if model_stats:
                console.print("\n[bold]By Model:[/bold]")
                model_table = Table(show_header=True)
                model_table.add_column("Model", style="cyan")
                model_table.add_column("Tokens", justify="right")
                model_table.add_column("Cost", justify="right")
                model_table.add_column("Calls", justify="right")

                for model_name, stats in model_stats.items():
                    model_table.add_row(
                        model_name,
                        _format_number(stats["input_tokens"] + stats["output_tokens"]),
                        f"${stats['cost_usd']:.4f}",
                        str(stats["calls"]),
                    )

                console.print(model_table)
    finally:
        db.close()


@stats_app.command()
def costs(
    period: Optional[str] = typer.Option(
        None,
        "--period",
        "-p",
        help="Time period: 'day' (24h), 'week' (7d), 'month' (30d)",
    ),
):
    """Show cost report.

    Displays total costs and per-model breakdown. Use --period to filter
    to a recent time window.

    Examples:
        cf stats costs                 # All-time costs
        cf stats costs --period month  # Last 30 days
        cf stats costs --period week   # Last 7 days
        cf stats costs --period day    # Last 24 hours
    """
    db = _get_db()
    try:
        tracker = _get_tracker(db)

        # Calculate date range from period
        start_date = None
        end_date = None
        now = datetime.now(timezone.utc)

        if period == "day":
            start_date = now - timedelta(days=1)
        elif period == "week":
            start_date = now - timedelta(weeks=1)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period is not None:
            console.print(
                f"[red]Error:[/red] Unknown period '{period}'. Use 'day', 'week', or 'month'."
            )
            raise typer.Exit(1)

        cost_data = tracker.get_workspace_costs(start_date=start_date, end_date=end_date)

        period_label = f" ({period})" if period else " (all time)"
        console.print(f"\n[bold]Cost Report{period_label}[/bold]\n")

        table = Table(show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total Cost", f"${cost_data['total_cost_usd']:.4f}")
        table.add_row("Total Tokens", _format_number(cost_data["total_tokens"]))
        table.add_row("LLM Calls", str(cost_data["total_calls"]))

        console.print(table)

        # Show per-model breakdown from raw records
        records = db.get_workspace_token_usage(start_date=start_date, end_date=end_date)
        model_costs: dict[str, dict] = {}
        for record in records:
            model = record["model_name"]
            if model not in model_costs:
                model_costs[model] = {"cost_usd": 0.0, "tokens": 0, "calls": 0}
            model_costs[model]["cost_usd"] += record["estimated_cost_usd"]
            model_costs[model]["tokens"] += record["input_tokens"] + record["output_tokens"]
            model_costs[model]["calls"] += 1

        if model_costs:
            console.print("\n[bold]By Model:[/bold]")
            model_table = Table(show_header=True)
            model_table.add_column("Model", style="cyan")
            model_table.add_column("Cost", justify="right")
            model_table.add_column("Tokens", justify="right")
            model_table.add_column("Calls", justify="right")

            for model_name, stats in model_costs.items():
                model_table.add_row(
                    model_name,
                    f"${stats['cost_usd']:.4f}",
                    _format_number(stats["tokens"]),
                    str(stats["calls"]),
                )

            console.print(model_table)
    finally:
        db.close()


@stats_app.command("export")
def export_data(
    format: str = typer.Option(
        "csv", "--format", "-f", help="Output format: csv or json"
    ),
    output: str = typer.Option(
        ..., "--output", "-o", help="Output file path"
    ),
    task: Optional[int] = typer.Option(
        None, "--task", "-t", help="Filter by task ID"
    ),
):
    """Export usage data to CSV or JSON.

    Exports raw token usage records to a file for external analysis.
    Use --task to export records for a single task only.

    Examples:
        cf stats export --format csv --output tokens.csv
        cf stats export --format json --output tokens.json
        cf stats export --format csv --output task1.csv --task 1
    """
    from codeframe.lib.metrics_tracker import MetricsTracker

    db = _get_db()
    try:
        if task is not None:
            # Get records for specific task
            records = db.get_token_usage(project_id=None, agent_id=None)
            records = [r for r in records if r.get("task_id") == task]
        else:
            records = db.get_workspace_token_usage()

        if format == "csv":
            MetricsTracker.export_to_csv(records, output)
        elif format == "json":
            MetricsTracker.export_to_json(records, output)
        else:
            console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'csv' or 'json'.")
            raise typer.Exit(1)

        console.print(f"Exported {len(records)} records to {output}")
    finally:
        db.close()
