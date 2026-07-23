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
import os
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
    """Get database from the enclosing workspace.

    Honors the DATABASE_PATH environment variable; otherwise walks up from
    the current directory looking for .codeframe/state.db (issue #777).

    Returns:
        Initialized Database instance.

    Raises:
        typer.Exit: If no workspace is found.
    """
    from codeframe.platform_store.database import Database

    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        db_path = Path(env_path)
        if not db_path.is_file():
            console.print(
                f"[red]Error:[/red] DATABASE_PATH does not point to a database file: {db_path}"
            )
            raise typer.Exit(1)
    else:
        cwd = Path.cwd()
        db_path = None
        for p in (cwd, *cwd.parents):
            candidate = p / ".codeframe" / "state.db"
            if candidate.is_file():
                db_path = candidate
                break
        if db_path is None:
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
    task: Optional[str] = typer.Option(
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
            # Workspace-wide summary — aggregated in SQL, then totals
            # derived from the handful of per-model rows.
            by_model = db.get_costs_by_model()

            total_input = sum(m["input_tokens"] for m in by_model)
            total_output = sum(m["output_tokens"] for m in by_model)
            total_cost = sum(m["total_cost_usd"] for m in by_model)
            total_calls = sum(m["call_count"] for m in by_model)
            total_tokens = total_input + total_output

            console.print("\n[bold]Workspace Token Usage Summary[/bold]\n")

            summary_table = Table(show_header=True)
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", justify="right")

            summary_table.add_row("Total Tokens", _format_number(total_tokens))
            summary_table.add_row("Input Tokens", _format_number(total_input))
            summary_table.add_row("Output Tokens", _format_number(total_output))
            summary_table.add_row("Total Cost", f"${total_cost:.4f}")
            summary_table.add_row("LLM Calls", str(total_calls))

            console.print(summary_table)

            if by_model:
                console.print("\n[bold]By Model:[/bold]")
                model_table = Table(show_header=True)
                model_table.add_column("Model", style="cyan")
                model_table.add_column("Tokens", justify="right")
                model_table.add_column("Cost", justify="right")
                model_table.add_column("Calls", justify="right")

                for m in by_model:
                    model_table.add_row(
                        m["model_name"],
                        _format_number(m["input_tokens"] + m["output_tokens"]),
                        f"${m['total_cost_usd']:.4f}",
                        str(m["call_count"]),
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

        # Per-model rollup aggregated in SQL; totals summed over the
        # small per-model result set.
        by_model = db.get_costs_by_model(start_date=start_date, end_date=end_date)

        total_cost = sum(m["total_cost_usd"] for m in by_model)
        total_tokens = sum(m["input_tokens"] + m["output_tokens"] for m in by_model)
        total_calls = sum(m["call_count"] for m in by_model)

        period_label = f" ({period})" if period else " (all time)"
        console.print(f"\n[bold]Cost Report{period_label}[/bold]\n")

        table = Table(show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Total Cost", f"${total_cost:.4f}")
        table.add_row("Total Tokens", _format_number(total_tokens))
        table.add_row("LLM Calls", str(total_calls))

        console.print(table)

        if by_model:
            console.print("\n[bold]By Model:[/bold]")
            model_table = Table(show_header=True)
            model_table.add_column("Model", style="cyan")
            model_table.add_column("Cost", justify="right")
            model_table.add_column("Tokens", justify="right")
            model_table.add_column("Calls", justify="right")

            for m in by_model:
                model_table.add_row(
                    m["model_name"],
                    f"${m['total_cost_usd']:.4f}",
                    _format_number(m["input_tokens"] + m["output_tokens"]),
                    str(m["call_count"]),
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
    task: Optional[str] = typer.Option(
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
        if format not in ("csv", "json"):
            console.print(f"[red]Error:[/red] Unknown format '{format}'. Use 'csv' or 'json'.")
            raise typer.Exit(1)

        if task is not None:
            records = db.get_batch_token_usage(task_ids=[task])
        else:
            # Stream the workspace table — never buffered into a list.
            records = db.get_token_usage_iter()

        if format == "csv":
            n = MetricsTracker.export_to_csv(records, output)
        else:
            n = MetricsTracker.export_to_json(records, output)

        console.print(f"Exported {n} records to {output}")
    finally:
        db.close()
