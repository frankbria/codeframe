"""Import commands for migrating projects from other tools.

Usage:
    cf import ralph [path] [--workspace PATH] [--dry-run]
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

import_app = typer.Typer(
    name="import",
    help="Import projects from other tools into CodeFRAME",
    no_args_is_help=True,
)


@import_app.command("ralph")
def import_ralph(
    path: Optional[Path] = typer.Argument(
        None,
        help="Path to the ralph project root (defaults to current directory)",
    ),
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Target CodeFRAME workspace (defaults to the ralph project root)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show the mapping report without making any changes",
    ),
) -> None:
    """Import a ralph-claude-code project (.ralph/ + .ralphrc).

    Maps .ralph/fix_plan.md to tasks (optional sections become BACKLOG),
    .ralph/PROMPT.md + specs/ to a PRD, and .ralph/AGENT.md + ALLOWED_TOOLS
    to AGENTS.md. Re-runs are idempotent.
    """
    from codeframe.core.importers.ralph import (
        RalphProjectNotFoundError,
        import_ralph_project,
    )
    from codeframe.core.state_machine import TaskStatus

    ralph_path = (path or Path.cwd()).resolve()

    try:
        report = import_ralph_project(
            ralph_path, workspace_path=workspace, dry_run=dry_run
        )
    except RalphProjectNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if dry_run:
        console.print(
            "[yellow]DRY RUN[/yellow] — mapping report only, no changes made\n"
        )

    ready = sum(
        1 for t in report.tasks_created if t["status"] == TaskStatus.READY
    )
    backlog = len(report.tasks_created) - ready
    summary = Table(title=f"Ralph import: {ralph_path}")
    summary.add_column("Source", style="cyan")
    summary.add_column("Destination")
    summary.add_row(
        ".ralph/fix_plan.md",
        f"{len(report.tasks_created)} tasks "
        f"({ready} READY, {backlog} BACKLOG), "
        f"{len(report.tasks_skipped)} skipped",
    )
    prd_label = {
        "created": "PRD created",
        "new_version": "PRD updated (new version)",
        "skipped_identical": "PRD unchanged (skipped)",
        "none": "—",
    }[report.prd_action]
    summary.add_row(".ralph/PROMPT.md + specs/", prd_label)
    agents_label = {
        "written": "AGENTS.md written",
        "skipped_exists": "AGENTS.md exists (skipped)",
        "none": "—",
    }[report.agents_md_action]
    summary.add_row(".ralph/AGENT.md + ALLOWED_TOOLS", agents_label)
    console.print(summary)

    if report.tasks_created:
        task_table = Table(title="Tasks")
        task_table.add_column("Title")
        task_table.add_column("Section", style="dim")
        task_table.add_column("Status")
        for task in report.tasks_created:
            status = task["status"].value
            color = "green" if status == "READY" else "yellow"
            task_table.add_row(
                task["title"], task["section"], f"[{color}]{status}[/{color}]"
            )
        console.print(task_table)

    if report.tasks_skipped:
        skip_table = Table(title="Skipped")
        skip_table.add_column("Title")
        skip_table.add_column("Reason", style="dim")
        for item in report.tasks_skipped:
            skip_table.add_row(item["title"], item["reason"])
        console.print(skip_table)

    if report.state_files_ignored:
        ignored = ", ".join(report.state_files_ignored)
        console.print(f"[dim]Ignored ralph state files: {ignored}[/dim]")

    if dry_run:
        console.print(
            "\nRun again without [bold]--dry-run[/bold] to perform the import."
        )
    else:
        console.print(
            f"\n[green]✓[/green] Imported into workspace at "
            f"{report.workspace_path}"
        )
