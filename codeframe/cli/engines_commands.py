"""CLI engine management commands.

Usage:
    codeframe engines list           # Show available engines
    codeframe engines check <name>   # Check engine requirements
    codeframe engines stats          # Show engine performance stats
    codeframe engines compare        # Compare engine performance
"""

import json as _json
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from codeframe.core import engine_stats
from codeframe.core.workspace import get_workspace

logger = logging.getLogger(__name__)

console = Console()

engines_app = typer.Typer(
    name="engines",
    help="Engine management commands",
    no_args_is_help=True,
)


@engines_app.command("list")
def engines_list() -> None:
    """List all available execution engines and their requirement status."""
    from codeframe.core.engine_registry import VALID_ENGINES, EXTERNAL_ENGINES, check_requirements

    table = Table(title="Available Engines")
    table.add_column("Engine", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Requirements", style="green")

    for engine in sorted(VALID_ENGINES):
        engine_type = "external" if engine in EXTERNAL_ENGINES else "builtin"
        if engine == "built-in":
            engine_type = "alias → react"

        try:
            reqs = check_requirements(engine)
        except ValueError:
            reqs = {}

        if not reqs:
            req_display = "[green]Ready[/green]"
        else:
            parts = []
            for key, satisfied in reqs.items():
                mark = "[green]✓[/green]" if satisfied else "[red]✗[/red]"
                parts.append(f"{mark} {key}")
            req_display = ", ".join(parts)

        table.add_row(engine, engine_type, req_display)

    console.print(table)


@engines_app.command("check")
def engines_check(
    name: str = typer.Argument(..., help="Engine name to check"),
) -> None:
    """Check if an engine's requirements are satisfied."""
    from codeframe.core.engine_registry import check_requirements

    try:
        reqs = check_requirements(name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not reqs:
        console.print(f"[green]Engine '{name}' has no additional requirements.[/green]")
        return

    all_satisfied = True
    for key, satisfied in reqs.items():
        if satisfied:
            console.print(f"  [green]✓[/green] {key}")
        else:
            console.print(f"  [red]✗[/red] {key} — not set")
            all_satisfied = False

    if all_satisfied:
        console.print(f"\n[green]Engine '{name}' is ready.[/green]")
    else:
        console.print(f"\n[red]Engine '{name}' has unmet requirements.[/red]")
        raise typer.Exit(1)


def _get_current_workspace():
    """Get workspace from current working directory.

    Returns:
        Workspace object.

    Raises:
        typer.Exit: If no workspace is found.
    """
    try:
        return get_workspace(Path.cwd())
    except (FileNotFoundError, ValueError):
        console.print("[red]Error:[/red] No workspace found. Run 'cf init' first.")
        raise typer.Exit(1)


def _compute_success_rate(metrics: dict[str, float]) -> float:
    """Compute success rate from engine metrics."""
    attempted = metrics.get("tasks_attempted", 0)
    completed = metrics.get("tasks_completed", 0)
    if attempted == 0:
        return 0.0
    return round(100.0 * completed / attempted, 1)


def _format_duration(ms: float) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.1f}s"


def _build_stats_table(stats: dict[str, dict[str, float]], title: str = "Engine Stats") -> Table:
    """Build a Rich table from engine stats."""
    table = Table(title=title)
    table.add_column("Engine", style="cyan")
    table.add_column("Tasks", justify="right")
    table.add_column("Success %", justify="right", style="green")
    table.add_column("Gate Pass %", justify="right")
    table.add_column("Avg Duration", justify="right")
    table.add_column("Total Tokens", justify="right")
    table.add_column("Avg Tokens/Task", justify="right")

    # Sort by success rate descending
    sorted_engines = sorted(
        stats.items(),
        key=lambda item: _compute_success_rate(item[1]),
        reverse=True,
    )

    for eng, metrics in sorted_engines:
        success_rate = _compute_success_rate(metrics)
        gate_rate = metrics.get("gate_pass_rate", 0.0)
        avg_dur = metrics.get("avg_duration_ms", 0.0)
        total_tok = metrics.get("total_tokens", 0.0)
        avg_tok = metrics.get("avg_tokens_per_task", 0.0)
        attempted = int(metrics.get("tasks_attempted", 0))

        table.add_row(
            eng,
            str(attempted),
            f"{success_rate}%",
            f"{gate_rate}%",
            _format_duration(avg_dur),
            f"{int(total_tok):,}",
            f"{int(avg_tok):,}",
        )

    return table


@engines_app.command("stats")
def stats(
    engine: Optional[str] = typer.Option(None, "--engine", "-e", help="Filter by engine name"),
    format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
) -> None:
    """Show engine performance statistics."""
    workspace = _get_current_workspace()
    data = engine_stats.get_engine_stats(workspace, engine=engine)

    if not data:
        console.print("[yellow]No engine stats recorded yet.[/yellow]")
        return

    if format == "json":
        console.print(_json.dumps(data, indent=2))
        return

    table = _build_stats_table(data, title="Engine Performance Stats")
    console.print(table)


@engines_app.command("compare")
def compare() -> None:
    """Compare performance across all engines."""
    workspace = _get_current_workspace()
    data = engine_stats.get_engine_stats(workspace)

    if not data:
        console.print(
            "[yellow]No engine stats recorded yet. "
            "Run tasks with different engines to see comparison.[/yellow]"
        )
        return

    table = _build_stats_table(data, title="Engine Comparison (sorted by success rate)")
    console.print(table)
