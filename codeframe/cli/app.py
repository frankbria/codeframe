"""CodeFRAME v2 CLI - Headless, CLI-first interface.

This is the new CLI entry point for CodeFRAME v2. All commands call
core modules directly without requiring a running FastAPI server.

Command structure: codeframe <domain> <verb> [args] [--options]

Examples:
    codeframe init ./my-repo
    codeframe prd add requirements.md
    codeframe tasks generate
    codeframe work start task-1
    codeframe blocker list
    codeframe status
"""

from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

# Load environment variables from .env files
# Priority: workspace .env > home .env
_cwd = Path.cwd()
_home_env = Path.home() / ".env"
_cwd_env = _cwd / ".env"

if _home_env.exists():
    load_dotenv(_home_env)
if _cwd_env.exists():
    load_dotenv(_cwd_env, override=True)  # workspace .env takes precedence

# Create main app
app = typer.Typer(
    name="codeframe",
    help="CodeFRAME: Autonomous coding agent orchestration (v2 CLI)",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


# =============================================================================
# Root-level commands (per GOLDEN_PATH.md)
# =============================================================================


@app.command()
def init(
    repo_path: Path = typer.Argument(
        ...,
        help="Path to the target repository",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Initialize a CodeFRAME workspace for a repository.

    Creates a .codeframe/ directory with state storage and configuration.
    This is idempotent - safe to run multiple times on the same repo.

    Example:
        codeframe init ./my-project
        codeframe init .
    """
    from codeframe.core.workspace import create_or_load_workspace, workspace_exists
    from codeframe.core.events import emit_for_workspace, EventType

    try:
        already_existed = workspace_exists(repo_path)
        workspace = create_or_load_workspace(repo_path)

        # Emit event (suppress print since we'll print our own message)
        emit_for_workspace(
            workspace, EventType.WORKSPACE_INIT, {"path": str(repo_path)}, print_event=False
        )

        if already_existed:
            console.print("[blue]Workspace already initialized[/blue]")
        else:
            console.print("[green]Workspace initialized[/green]")

        console.print(f"  Path: {repo_path}")
        console.print(f"  ID: {workspace.id}")
        console.print(f"  State: {workspace.state_dir}")
        console.print()
        console.print("Next steps:")
        console.print("  codeframe prd add <file.md>   Add a PRD")
        console.print("  codeframe status              View workspace status")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def status(
    repo_path: Optional[Path] = typer.Argument(
        None,
        help="Path to repository (defaults to current directory)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    show_events: int = typer.Option(
        5,
        "--events",
        "-e",
        help="Number of recent events to show (0 to hide)",
    ),
) -> None:
    """Show workspace status summary.

    Displays current workspace state including:
    - PRD info (if loaded)
    - Task counts by status
    - Recent events
    - Open blockers

    Example:
        codeframe status
        codeframe status ./my-project
        codeframe status --events 10
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import prd, tasks, events

    path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Workspace header
        console.print("\n[bold cyan]CodeFRAME Workspace[/bold cyan]")
        console.print(f"  Path: {workspace.repo_path}")
        console.print(f"  ID: [dim]{workspace.id}[/dim]")
        console.print(f"  Created: {workspace.created_at.strftime('%Y-%m-%d %H:%M')}")

        # PRD info
        console.print("\n[bold]PRD[/bold]")
        latest_prd = prd.get_latest(workspace)
        if latest_prd:
            console.print(f"  Title: [green]{latest_prd.title}[/green]")
            console.print(f"  Added: {latest_prd.created_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            console.print("  [dim]No PRD loaded. Run 'codeframe prd add <file>'[/dim]")

        # Task counts
        console.print("\n[bold]Tasks[/bold]")
        counts = tasks.count_by_status(workspace)
        total = sum(counts.values())

        if total == 0:
            console.print("  [dim]No tasks. Run 'codeframe tasks generate'[/dim]")
        else:
            # Define status display order and colors
            status_display = [
                ("BACKLOG", "white"),
                ("READY", "blue"),
                ("IN_PROGRESS", "yellow"),
                ("BLOCKED", "red"),
                ("DONE", "green"),
                ("MERGED", "cyan"),
            ]
            for status_name, color in status_display:
                count = counts.get(status_name, 0)
                if count > 0:
                    console.print(f"  [{color}]{status_name}[/{color}]: {count}")

            console.print(f"  [bold]Total[/bold]: {total}")

        # Recent events
        if show_events > 0:
            console.print("\n[bold]Recent Activity[/bold]")
            recent = events.list_recent(workspace, limit=show_events)
            if recent:
                for event in recent:
                    timestamp = event.created_at.strftime("%H:%M:%S")
                    # Color code by event type
                    if "FAILED" in event.event_type or "ERROR" in event.event_type:
                        type_color = "red"
                    elif "COMPLETED" in event.event_type or "CREATED" in event.event_type:
                        type_color = "green"
                    elif "STARTED" in event.event_type or "INIT" in event.event_type:
                        type_color = "blue"
                    elif "BLOCKED" in event.event_type:
                        type_color = "yellow"
                    else:
                        type_color = "cyan"

                    console.print(
                        f"  [dim]{timestamp}[/dim] [{type_color}]{event.event_type}[/{type_color}]"
                    )
            else:
                console.print("  [dim]No recent events[/dim]")

        # Emit status viewed event (optional per spec)
        events.emit_for_workspace(
            workspace,
            events.EventType.STATUS_VIEWED,
            print_event=False,
        )

        console.print()  # Final newline for cleaner output

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        console.print("Run 'codeframe init <path>' to initialize.")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def summary(
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Print a short status report of the workspace.

    Shows PRD title, tasks by status, open blockers, and recent activity.
    More compact than 'status' - designed for quick overview.

    Example:
        codeframe summary
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import prd, tasks, blockers, events
    from codeframe.core.blockers import BlockerStatus

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # PRD
        latest_prd = prd.get_latest(workspace)
        if latest_prd:
            console.print(f"[bold]PRD:[/bold] {latest_prd.title}")
        else:
            console.print("[bold]PRD:[/bold] [dim]None[/dim]")

        # Task counts
        counts = tasks.count_by_status(workspace)
        total = sum(counts.values())

        if total > 0:
            parts = []
            for status in ["DONE", "IN_PROGRESS", "READY", "BACKLOG", "BLOCKED"]:
                if counts.get(status, 0) > 0:
                    parts.append(f"{counts[status]} {status.lower()}")
            console.print(f"[bold]Tasks:[/bold] {', '.join(parts)} ({total} total)")
        else:
            console.print("[bold]Tasks:[/bold] [dim]None[/dim]")

        # Open blockers
        open_blockers = blockers.list_all(workspace, status=BlockerStatus.OPEN)
        if open_blockers:
            console.print(f"[bold]Blockers:[/bold] [yellow]{len(open_blockers)} open[/yellow]")
            for b in open_blockers[:3]:
                q = b.question[:50] + "..." if len(b.question) > 50 else b.question
                console.print(f"  - {q}")
            if len(open_blockers) > 3:
                console.print(f"  ... and {len(open_blockers) - 3} more")
        else:
            console.print("[bold]Blockers:[/bold] [green]None[/green]")

        # Emit summary viewed event (optional)
        events.emit_for_workspace(
            workspace,
            events.EventType.SUMMARY_VIEWED,
            print_event=False,
        )

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@app.command()
def review(
    gates_to_run: Optional[list[str]] = typer.Option(
        None,
        "--gate",
        "-g",
        help="Specific gate to run (can be repeated)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full output from gates",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Run verification gates (tests, lint).

    Automatically detects available gates and runs them.
    Use --gate to run specific gates only.

    Available gates: pytest, ruff, mypy, npm-test, npm-lint

    Example:
        codeframe review
        codeframe review --verbose
        codeframe review --gate pytest --gate ruff
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import gates
    from codeframe.core.gates import GateStatus

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        console.print("\n[bold]Running verification gates...[/bold]\n")

        result = gates.run(workspace, gates=gates_to_run, verbose=verbose)

        # Display results
        for check in result.checks:
            if check.status == GateStatus.PASSED:
                status_str = "[green]PASSED[/green]"
            elif check.status == GateStatus.FAILED:
                status_str = "[red]FAILED[/red]"
            elif check.status == GateStatus.SKIPPED:
                status_str = "[dim]SKIPPED[/dim]"
            else:
                status_str = "[yellow]ERROR[/yellow]"

            duration_str = f" ({check.duration_ms}ms)" if check.duration_ms else ""
            console.print(f"  {check.name}: {status_str}{duration_str}")

            # Show output for failures or verbose mode
            if check.output and (check.status == GateStatus.FAILED or verbose):
                console.print(f"    [dim]{check.output}[/dim]")

        # Summary
        console.print()
        if result.passed:
            console.print(f"[bold green]All gates passed[/bold green] ({result.summary})")
        else:
            console.print(f"[bold red]Gates failed[/bold red] ({result.summary})")
            raise typer.Exit(1)

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        console.print("Run 'codeframe init' to initialize a workspace first.")
        raise typer.Exit(1)


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to run server on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
) -> None:
    """Start the optional FastAPI server (wraps core).

    The server is NOT required for Golden Path commands.
    It provides an HTTP API that wraps the same core functions.
    """
    console.print("[yellow]Server adapter not yet implemented.[/yellow]")
    console.print("Golden Path commands work without a server.")


# =============================================================================
# Domain sub-applications (Typer sub-apps)
# =============================================================================

# PRD commands
prd_app = typer.Typer(
    name="prd",
    help="PRD (Product Requirements Document) management",
    no_args_is_help=True,
)


@prd_app.command("add")
def prd_add(
    file_path: Path = typer.Argument(
        ...,
        help="Path to PRD markdown file",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Store a PRD file in the workspace.

    Example:
        codeframe prd add requirements.md
        codeframe prd add ../specs/prd.md -w ./my-project
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import prd
    from codeframe.core.events import emit_for_workspace, EventType

    workspace_path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(workspace_path)

        # Load and store PRD
        content = prd.load_file(file_path)
        record = prd.store(workspace, content, source_path=file_path)

        # Emit event
        emit_for_workspace(
            workspace,
            EventType.PRD_ADDED,
            {"prd_id": record.id, "title": record.title, "source": str(file_path)},
            print_event=False,
        )

        console.print("[green]PRD added[/green]")
        console.print(f"  Title: {record.title}")
        console.print(f"  ID: {record.id}")
        console.print(f"  Source: {file_path}")
        console.print()
        console.print("Next: codeframe tasks generate")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@prd_app.command("show")
def prd_show(
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
    full: bool = typer.Option(False, "--full", "-f", help="Show full PRD content"),
) -> None:
    """Display the current PRD."""
    from codeframe.core.workspace import get_workspace
    from codeframe.core import prd

    workspace_path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(workspace_path)
        record = prd.get_latest(workspace)

        if not record:
            console.print("[yellow]No PRD found.[/yellow]")
            console.print("Add one with: codeframe prd add <file.md>")
            return

        console.print(f"\n[bold]PRD:[/bold] {record.title}")
        console.print(f"[dim]ID: {record.id}[/dim]")
        console.print(f"[dim]Added: {record.created_at}[/dim]")

        if full:
            console.print("\n" + "-" * 40 + "\n")
            console.print(record.content)
        else:
            # Show first 500 chars as preview
            preview = record.content[:500]
            if len(record.content) > 500:
                preview += "\n\n[dim]... (use --full to see complete PRD)[/dim]"
            console.print("\n" + preview)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Tasks commands
tasks_app = typer.Typer(
    name="tasks",
    help="Task generation and management",
    no_args_is_help=True,
)


@tasks_app.command("generate")
def tasks_generate(
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Use simple extraction instead of LLM",
    ),
) -> None:
    """Generate tasks from the PRD.

    Uses LLM to decompose the PRD into actionable tasks.
    Tasks are stored in state with BACKLOG status.
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import prd, tasks
    from codeframe.core.events import emit_for_workspace, EventType

    workspace_path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(workspace_path)

        # Get latest PRD
        prd_record = prd.get_latest(workspace)
        if not prd_record:
            console.print("[red]Error:[/red] No PRD found.")
            console.print("Add one first: codeframe prd add <file.md>")
            raise typer.Exit(1)

        console.print(f"Generating tasks from PRD: [bold]{prd_record.title}[/bold]")

        if no_llm:
            console.print("[dim]Using simple extraction (--no-llm)[/dim]")
        else:
            console.print("[dim]Using LLM for task generation...[/dim]")

        # Generate tasks
        created = tasks.generate_from_prd(workspace, prd_record, use_llm=not no_llm)

        # Emit event
        emit_for_workspace(
            workspace,
            EventType.TASKS_GENERATED,
            {"prd_id": prd_record.id, "count": len(created)},
            print_event=False,
        )

        console.print(f"\n[green]Generated {len(created)} tasks[/green]\n")

        for i, task in enumerate(created, 1):
            console.print(f"  {i}. {task.title}")
            if task.description:
                # Show first line of description
                desc_preview = task.description.split("\n")[0][:60]
                console.print(f"     [dim]{desc_preview}[/dim]")

        console.print()
        console.print("Next steps:")
        console.print("  codeframe tasks list              View all tasks")
        console.print("  codeframe tasks set status READY <id>   Mark task ready")
        console.print("  codeframe tasks set status READY --all  Mark all tasks ready")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@tasks_app.command("list")
def tasks_list(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """List tasks in the workspace."""
    from rich.table import Table
    from codeframe.core.workspace import get_workspace
    from codeframe.core import tasks
    from codeframe.core.state_machine import parse_status, TaskStatus

    workspace_path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(workspace_path)

        # Parse status filter if provided
        status_filter = None
        if status:
            status_filter = parse_status(status)

        task_list = tasks.list_tasks(workspace, status=status_filter)

        if not task_list:
            if status_filter:
                console.print(f"[yellow]No tasks with status {status_filter.value}[/yellow]")
            else:
                console.print("[yellow]No tasks found.[/yellow]")
                console.print("Generate tasks with: codeframe tasks generate")
            return

        # Build table
        table = Table(title="Tasks")
        table.add_column("ID", style="dim", max_width=8)
        table.add_column("Status", style="cyan")
        table.add_column("Pri", justify="center")
        table.add_column("Title", style="white")

        status_colors = {
            TaskStatus.BACKLOG: "dim",
            TaskStatus.READY: "blue",
            TaskStatus.IN_PROGRESS: "yellow",
            TaskStatus.BLOCKED: "red",
            TaskStatus.DONE: "green",
            TaskStatus.MERGED: "green dim",
        }

        for task in task_list:
            status_style = status_colors.get(task.status, "white")
            table.add_row(
                task.id[:8],
                f"[{status_style}]{task.status.value}[/{status_style}]",
                str(task.priority),
                task.title[:60] + ("..." if len(task.title) > 60 else ""),
            )

        console.print(table)

        # Show counts
        counts = tasks.count_by_status(workspace)
        count_parts = [f"{s}: {c}" for s, c in counts.items()]
        console.print(f"\n[dim]Total: {len(task_list)} | {' | '.join(count_parts)}[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@tasks_app.command("set")
def tasks_set(
    attribute: str = typer.Argument(..., help="Attribute to set (e.g., 'status')"),
    value: str = typer.Argument(..., help="New value"),
    task_id: Optional[str] = typer.Argument(None, help="Task ID (can be partial, omit with --all)"),
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
    all_tasks_flag: bool = typer.Option(
        False,
        "--all",
        help="Apply to all tasks (or filtered by --from)",
    ),
    from_status: Optional[str] = typer.Option(
        None,
        "--from",
        help="Only update tasks with this status (use with --all)",
    ),
) -> None:
    """Set a task attribute.

    Example:
        codeframe tasks set status READY abc123
        codeframe tasks set status READY --all
        codeframe tasks set status READY --all --from BACKLOG
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import tasks
    from codeframe.core.state_machine import parse_status
    from codeframe.core.events import emit_for_workspace, EventType

    workspace_path = repo_path or Path.cwd()

    try:
        workspace = get_workspace(workspace_path)

        if attribute.lower() != "status":
            console.print(f"[red]Error:[/red] Unknown attribute '{attribute}'")
            console.print("Supported attributes: status")
            raise typer.Exit(1)

        new_status = parse_status(value)
        all_workspace_tasks = tasks.list_tasks(workspace)

        # Determine which tasks to update
        if all_tasks_flag:
            # Bulk update mode
            if from_status:
                filter_status = parse_status(from_status)
                matching = [t for t in all_workspace_tasks if t.status == filter_status]
                if not matching:
                    console.print(f"[yellow]No tasks with status {filter_status.value}[/yellow]")
                    raise typer.Exit(0)
            else:
                matching = all_workspace_tasks
                if not matching:
                    console.print("[yellow]No tasks in workspace[/yellow]")
                    raise typer.Exit(0)
        elif task_id:
            # Single task mode
            matching = [t for t in all_workspace_tasks if t.id.startswith(task_id)]
            if not matching:
                console.print(f"[red]Error:[/red] No task found matching '{task_id}'")
                raise typer.Exit(1)
            if len(matching) > 1:
                console.print(f"[red]Error:[/red] Multiple tasks match '{task_id}':")
                for t in matching:
                    console.print(f"  {t.id}: {t.title[:40]}")
                console.print("Please provide a more specific ID.")
                raise typer.Exit(1)
        else:
            console.print("[red]Error:[/red] Specify a task ID or use --all")
            raise typer.Exit(1)

        # Update tasks
        updated_count = 0
        skipped_count = 0
        for task in matching:
            if task.status == new_status:
                skipped_count += 1
                continue

            old_status = task.status
            tasks.update_status(workspace, task.id, new_status)

            emit_for_workspace(
                workspace,
                EventType.TASK_STATUS_CHANGED,
                {
                    "task_id": task.id,
                    "old_status": old_status.value,
                    "new_status": new_status.value,
                },
                print_event=False,
            )
            updated_count += 1

        # Report results
        if len(matching) == 1:
            task = matching[0]
            if updated_count:
                console.print("[green]Task updated[/green]")
                console.print(f"  {task.title[:50]}")
                console.print(f"  Status: {task.status.value} -> {new_status.value}")
            else:
                console.print(f"[yellow]Task already {new_status.value}[/yellow]")
        else:
            console.print(f"[green]Updated {updated_count} tasks to {new_status.value}[/green]")
            if skipped_count:
                console.print(f"[dim]Skipped {skipped_count} (already {new_status.value})[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Work commands
work_app = typer.Typer(
    name="work",
    help="Task execution and agent orchestration",
    no_args_is_help=True,
)


@work_app.command("start")
def work_start(
    task_id: str = typer.Argument(..., help="Task ID to start (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        "-x",
        help="Run the agent to execute the task (requires ANTHROPIC_API_KEY)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview changes without applying them (use with --execute)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Write detailed debug log to .codeframe_debug_<timestamp>.log in repo",
    ),
    stub: bool = typer.Option(
        False,
        "--stub",
        help="Run stub agent (for testing, does nothing real)",
    ),
) -> None:
    """Start working on a task.

    Transitions task to IN_PROGRESS and creates a run record.
    Use --execute to run the AI agent, or --stub for testing.

    Example:
        codeframe work start abc123
        codeframe work start abc123 --execute
        codeframe work start abc123 --execute --dry-run
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import tasks as tasks_module, runtime
    from codeframe.core.state_machine import InvalidTransitionError

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Find task by partial ID
        all_tasks = tasks_module.list_tasks(workspace)
        matching = [t for t in all_tasks if t.id.startswith(task_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No task found matching '{task_id}'")
            raise typer.Exit(1)

        if len(matching) > 1:
            console.print(f"[red]Error:[/red] Multiple tasks match '{task_id}':")
            for t in matching[:5]:
                console.print(f"  {t.id[:8]} - {t.title}")
            raise typer.Exit(1)

        task = matching[0]

        # Start the run
        run = runtime.start_task_run(workspace, task.id)

        console.print("\n[bold green]Run started[/bold green]")
        console.print(f"  Task: {task.title}")
        console.print(f"  Run ID: [dim]{run.id}[/dim]")
        console.print("  Status: [yellow]RUNNING[/yellow]")

        # Execute agent if requested
        if execute:
            from codeframe.core.agent import AgentStatus

            mode = "[dim](dry run)[/dim]" if dry_run else ""
            debug_mode = " [dim](debug logging enabled)[/dim]" if debug else ""
            console.print(f"\n[bold]Executing agent...{mode}{debug_mode}[/bold]")

            try:
                state = runtime.execute_agent(workspace, run, dry_run=dry_run, debug=debug)

                if state.status == AgentStatus.COMPLETED:
                    console.print("[bold green]Task completed successfully![/bold green]")
                elif state.status == AgentStatus.BLOCKED:
                    console.print("[yellow]Task blocked - human input needed[/yellow]")
                    if state.blocker:
                        console.print(f"  Question: {state.blocker.question}")
                    console.print("  Use 'codeframe blocker list' to see blockers")
                elif state.status == AgentStatus.FAILED:
                    console.print("[red]Task execution failed[/red]")
                    if state.step_results:
                        last_result = state.step_results[-1]
                        if last_result.error:
                            console.print(f"  Error: {last_result.error[:200]}")

                # Show debug log location if debugging was enabled
                if debug:
                    # Find the most recent debug log in the repo
                    debug_logs = list(workspace.repo_path.glob(".codeframe_debug_*.log"))
                    if debug_logs:
                        latest_log = max(debug_logs, key=lambda p: p.stat().st_mtime)
                        console.print(f"\n[dim]Debug log written to: {latest_log}[/dim]")

            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1)

        elif stub:
            console.print("\n[dim]Executing stub agent...[/dim]")
            runtime.execute_stub(workspace, run)
            runtime.complete_run(workspace, run.id)
            console.print("[green]Run completed (stub)[/green]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except InvalidTransitionError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@work_app.command("resume")
def work_resume(
    task_id: str = typer.Argument(..., help="Task ID to resume (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Resume work on a blocked task.

    Example:
        codeframe work resume abc123
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import tasks as tasks_module, runtime

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Find task by partial ID
        all_tasks = tasks_module.list_tasks(workspace)
        matching = [t for t in all_tasks if t.id.startswith(task_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No task found matching '{task_id}'")
            raise typer.Exit(1)

        if len(matching) > 1:
            console.print(f"[red]Error:[/red] Multiple tasks match '{task_id}':")
            for t in matching[:5]:
                console.print(f"  {t.id[:8]} - {t.title}")
            raise typer.Exit(1)

        task = matching[0]

        # Resume the run
        run = runtime.resume_run(workspace, task.id)

        console.print("\n[bold green]Run resumed[/bold green]")
        console.print(f"  Task: {task.title}")
        console.print(f"  Run ID: [dim]{run.id}[/dim]")
        console.print("  Status: [yellow]RUNNING[/yellow]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@work_app.command("stop")
def work_stop(
    task_id: str = typer.Argument(..., help="Task ID to stop (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Stop work on a task (graceful).

    Marks the run as stopped and returns the task to READY status.

    Example:
        codeframe work stop abc123
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import tasks as tasks_module, runtime

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Find task by partial ID
        all_tasks = tasks_module.list_tasks(workspace)
        matching = [t for t in all_tasks if t.id.startswith(task_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No task found matching '{task_id}'")
            raise typer.Exit(1)

        if len(matching) > 1:
            console.print(f"[red]Error:[/red] Multiple tasks match '{task_id}':")
            for t in matching[:5]:
                console.print(f"  {t.id[:8]} - {t.title}")
            raise typer.Exit(1)

        task = matching[0]

        # Stop the run
        run = runtime.stop_run(workspace, task.id)

        console.print("\n[bold yellow]Run stopped[/bold yellow]")
        console.print(f"  Task: {task.title}")
        console.print(f"  Run ID: [dim]{run.id}[/dim]")
        console.print("  Task returned to: [blue]READY[/blue]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@work_app.command("status")
def work_status(
    task_id: Optional[str] = typer.Argument(
        None, help="Task ID to check (shows all active runs if omitted)"
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Show status of running tasks.

    Example:
        codeframe work status           # Show all active runs
        codeframe work status abc123    # Show run for specific task
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import runtime
    from codeframe.core.runtime import RunStatus

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        if task_id:
            # Show run for specific task
            run = runtime.get_active_run(workspace, task_id)
            if run:
                console.print("\n[bold]Run Status[/bold]")
                console.print(f"  Run ID: {run.id}")
                console.print(f"  Task ID: {run.task_id}")
                console.print(f"  Status: {run.status.value}")
                console.print(f"  Started: {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                console.print(f"[dim]No active run for task {task_id}[/dim]")
        else:
            # Show all active runs
            running = runtime.list_runs(workspace, status=RunStatus.RUNNING)
            blocked = runtime.list_runs(workspace, status=RunStatus.BLOCKED)
            active = running + blocked

            if active:
                console.print(f"\n[bold]Active Runs[/bold] ({len(active)})\n")
                for run in active:
                    status_color = "yellow" if run.status == RunStatus.RUNNING else "red"
                    console.print(
                        f"  [{status_color}]{run.status.value}[/{status_color}] "
                        f"{run.task_id[:8]} (run: {run.id[:8]})"
                    )
            else:
                console.print("[dim]No active runs[/dim]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


# =============================================================================
# Batch execution commands (subcommand group: cf work batch <cmd>)
# =============================================================================

batch_app = typer.Typer(
    name="batch",
    help="Batch task execution",
    no_args_is_help=True,
)


@batch_app.command("run")
def batch_run(
    task_ids: Optional[list[str]] = typer.Argument(
        None, help="Task IDs to execute (space-separated)"
    ),
    all_ready: bool = typer.Option(
        False,
        "--all-ready",
        help="Execute all tasks with READY status",
    ),
    strategy: str = typer.Option(
        "serial",
        "--strategy",
        "-s",
        help="Execution strategy: serial, parallel, or auto (LLM-inferred dependencies)",
    ),
    max_parallel: int = typer.Option(
        4,
        "--max-parallel",
        "-p",
        help="Max concurrent tasks for parallel strategy",
    ),
    on_failure: str = typer.Option(
        "continue",
        "--on-failure",
        help="Behavior on task failure: continue or stop",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show execution plan without running",
    ),
    max_retries: int = typer.Option(
        0,
        "--retry",
        "-r",
        help="Max retry attempts for failed tasks (0 = no retries)",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Execute multiple tasks in batch.

    Execute a list of tasks sequentially (or in parallel in Phase 2).
    Use --all-ready to process all READY tasks, or specify task IDs.
    Use --retry N to automatically retry failed tasks up to N times.

    Example:
        codeframe work batch run task1 task2 task3
        codeframe work batch run --all-ready
        codeframe work batch run --all-ready --strategy serial
        codeframe work batch run task1 task2 --dry-run
        codeframe work batch run task1 task2 --retry 2
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import tasks as tasks_module, conductor
    from codeframe.core.state_machine import TaskStatus

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Determine which tasks to execute
        if all_ready:
            ready_tasks = tasks_module.list_tasks(workspace, status=TaskStatus.READY)
            if not ready_tasks:
                console.print("[yellow]No READY tasks found[/yellow]")
                return
            ids_to_execute = [t.id for t in ready_tasks]
            console.print(f"Found {len(ids_to_execute)} READY tasks")
        elif task_ids:
            # Resolve partial IDs
            all_tasks = tasks_module.list_tasks(workspace)
            ids_to_execute = []
            for partial_id in task_ids:
                matching = [t for t in all_tasks if t.id.startswith(partial_id)]
                if not matching:
                    console.print(f"[red]Error:[/red] No task found matching '{partial_id}'")
                    raise typer.Exit(1)
                if len(matching) > 1:
                    console.print(f"[red]Error:[/red] Multiple tasks match '{partial_id}':")
                    for t in matching[:3]:
                        console.print(f"  {t.id[:8]} - {t.title}")
                    raise typer.Exit(1)
                ids_to_execute.append(matching[0].id)
        else:
            console.print("[red]Error:[/red] Specify task IDs or use --all-ready")
            raise typer.Exit(1)

        # Show execution plan
        console.print("\n[bold]Batch Execution Plan[/bold]")
        console.print(f"  Strategy: {strategy}")
        console.print(f"  Tasks: {len(ids_to_execute)}")
        console.print(f"  On failure: {on_failure}")

        if dry_run:
            console.print("\n[dim]Dry run - showing tasks without executing:[/dim]")
            for i, tid in enumerate(ids_to_execute):
                task = tasks_module.get(workspace, tid)
                title = task.title if task else tid
                console.print(f"  [{i + 1}] {tid[:8]} - {title}")
            return

        # Execute batch
        if max_retries > 0:
            console.print(f"\n[bold cyan]Starting batch execution (with up to {max_retries} retries)...[/bold cyan]\n")
        else:
            console.print("\n[bold cyan]Starting batch execution...[/bold cyan]\n")

        batch = conductor.start_batch(
            workspace=workspace,
            task_ids=ids_to_execute,
            strategy=strategy,
            max_parallel=max_parallel,
            on_failure=on_failure,
            dry_run=False,
            max_retries=max_retries,
        )

        # Show summary
        console.print("\n[bold]Batch Summary[/bold]")
        console.print(f"  Batch ID: {batch.id[:8]}")
        console.print(f"  Status: {batch.status.value}")

        completed = sum(1 for s in batch.results.values() if s == "COMPLETED")
        failed = sum(1 for s in batch.results.values() if s == "FAILED")
        blocked = sum(1 for s in batch.results.values() if s == "BLOCKED")

        console.print(f"  Completed: {completed}/{len(ids_to_execute)}")
        if failed:
            console.print(f"  Failed: {failed}")
        if blocked:
            console.print(f"  Blocked: {blocked}")
        if max_retries > 0:
            console.print(f"  Retries: up to {max_retries}")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@batch_app.command("status")
def batch_status(
    batch_id: Optional[str] = typer.Argument(
        None, help="Batch ID to check (shows recent batches if omitted)"
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Show batch execution status.

    Example:
        codeframe work batch status           # Show recent batches
        codeframe work batch status abc123    # Show specific batch
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import conductor, tasks as tasks_module
    from rich.table import Table

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        if batch_id:
            # Show specific batch
            # Find by partial ID
            all_batches = conductor.list_batches(workspace, limit=100)
            matching = [b for b in all_batches if b.id.startswith(batch_id)]

            if not matching:
                console.print(f"[red]Error:[/red] No batch found matching '{batch_id}'")
                raise typer.Exit(1)

            batch = matching[0]

            # Status color
            status_colors = {
                "COMPLETED": "green",
                "PARTIAL": "yellow",
                "FAILED": "red",
                "CANCELLED": "red",
                "RUNNING": "cyan",
                "PENDING": "dim",
            }
            color = status_colors.get(batch.status.value, "white")

            console.print(f"\n[bold]Batch {batch.id[:8]}[/bold]")
            console.print(f"  Status: [{color}]{batch.status.value}[/{color}]")
            console.print(f"  Strategy: {batch.strategy}")
            console.print(f"  Started: {batch.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if batch.completed_at:
                duration = batch.completed_at - batch.started_at
                console.print(f"  Duration: {duration}")

            # Show task results
            console.print("\n  [bold]Tasks:[/bold]")
            for tid in batch.task_ids:
                task = tasks_module.get(workspace, tid)
                title = task.title[:40] if task else tid
                result = batch.results.get(tid, "pending")

                if result == "COMPLETED":
                    icon = "[green]✓[/green]"
                elif result == "BLOCKED":
                    icon = "[yellow]⊘[/yellow]"
                elif result == "FAILED":
                    icon = "[red]✗[/red]"
                else:
                    icon = "[dim]○[/dim]"

                console.print(f"    {icon} {tid[:8]} - {title}")

        else:
            # List recent batches
            batches = conductor.list_batches(workspace, limit=10)

            if not batches:
                console.print("[dim]No batch runs found[/dim]")
                return

            table = Table(title="Recent Batch Runs")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Status", width=10)
            table.add_column("Tasks", width=8)
            table.add_column("Completed", width=10)
            table.add_column("Started", width=18)

            for batch in batches:
                status_colors = {
                    "COMPLETED": "green",
                    "PARTIAL": "yellow",
                    "FAILED": "red",
                    "CANCELLED": "red",
                    "RUNNING": "cyan",
                    "PENDING": "dim",
                }
                color = status_colors.get(batch.status.value, "white")
                status_str = f"[{color}]{batch.status.value}[/{color}]"

                completed = sum(1 for s in batch.results.values() if s == "COMPLETED")
                completed_str = f"{completed}/{len(batch.task_ids)}"

                table.add_row(
                    batch.id[:8],
                    status_str,
                    str(len(batch.task_ids)),
                    completed_str,
                    batch.started_at.strftime("%Y-%m-%d %H:%M"),
                )

            console.print(table)

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@batch_app.command("cancel")
def batch_cancel(
    batch_id: str = typer.Argument(..., help="Batch ID to cancel (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Cancel a running batch.

    Example:
        codeframe work batch cancel abc123
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import conductor

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Find by partial ID
        all_batches = conductor.list_batches(workspace, limit=100)
        matching = [b for b in all_batches if b.id.startswith(batch_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No batch found matching '{batch_id}'")
            raise typer.Exit(1)

        batch = matching[0]

        if batch.status.value not in ("PENDING", "RUNNING"):
            console.print(f"[yellow]Batch is already {batch.status.value}[/yellow]")
            return

        batch = conductor.cancel_batch(workspace, batch.id)
        console.print(f"[green]Batch {batch.id[:8]} cancelled[/green]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@batch_app.command("resume")
def batch_resume(
    batch_id: str = typer.Argument(..., help="Batch ID to resume (can be partial)"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Re-run all tasks, including completed ones",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Resume a batch by re-running failed/blocked tasks.

    Re-executes tasks that failed or became blocked in a previous batch run.
    Use --force to re-run all tasks including completed ones.

    Example:
        codeframe work batch resume abc123           # Re-run failed/blocked only
        codeframe work batch resume abc123 --force  # Re-run all tasks
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import conductor

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        # Find by partial ID
        all_batches = conductor.list_batches(workspace, limit=100)
        matching = [b for b in all_batches if b.id.startswith(batch_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No batch found matching '{batch_id}'")
            raise typer.Exit(1)

        if len(matching) > 1:
            console.print(f"[yellow]Warning:[/yellow] Multiple batches match '{batch_id}':")
            for b in matching[:5]:
                console.print(f"  - {b.id[:8]} ({b.status.value})")
            console.print("Using the most recent match.")

        batch = matching[0]

        # Show what we're about to do
        failed_count = sum(1 for s in batch.results.values() if s in ("FAILED", "BLOCKED"))
        completed_count = sum(1 for s in batch.results.values() if s == "COMPLETED")

        if not force and failed_count == 0:
            console.print(f"[green]Batch {batch.id[:8]} has no failed/blocked tasks to resume.[/green]")
            console.print(f"  Status: {batch.status.value}")
            console.print(f"  Completed: {completed_count}/{len(batch.task_ids)}")
            return

        if force:
            console.print(f"[cyan]Resuming batch {batch.id[:8]} (force mode)[/cyan]")
            console.print(f"  Re-running all {len(batch.task_ids)} tasks")
        else:
            console.print(f"[cyan]Resuming batch {batch.id[:8]}[/cyan]")
            console.print(f"  Re-running {failed_count} failed/blocked tasks")
            console.print(f"  Keeping {completed_count} completed tasks")

        # Execute resume
        batch = conductor.resume_batch(workspace, batch.id, force=force)

        # Show final status
        if batch.status == conductor.BatchStatus.COMPLETED:
            console.print("\n[green]✓ Batch completed successfully![/green]")
        elif batch.status == conductor.BatchStatus.PARTIAL:
            final_failed = sum(1 for s in batch.results.values() if s in ("FAILED", "BLOCKED"))
            console.print(f"\n[yellow]⚠ Batch partially completed ({final_failed} still failing)[/yellow]")
        else:
            console.print(f"\n[red]✗ Batch {batch.status.value.lower()}[/red]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@batch_app.command("follow")
def batch_follow(
    batch_id: str = typer.Argument(..., help="Batch ID to follow (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
    no_progress: bool = typer.Option(
        False,
        "--no-progress",
        help="Plain event log only (no progress bar)",
    ),
) -> None:
    """Follow a batch execution in real-time.

    Streams batch events to terminal until batch completes or is cancelled.
    Shows progress bar with ETA based on task completion times.

    Example:
        codeframe work batch follow abc123
        codeframe work batch follow abc123 --no-progress
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import conductor, events
    from codeframe.core.progress import BatchProgress
    from rich.live import Live
    from rich.panel import Panel

    path = workspace_path or Path.cwd()

    # Terminal event types - stop following when these occur
    TERMINAL_EVENTS = {
        events.EventType.BATCH_COMPLETED,
        events.EventType.BATCH_PARTIAL,
        events.EventType.BATCH_FAILED,
        events.EventType.BATCH_CANCELLED,
    }

    def _get_event_color(event_type: str) -> str:
        """Get the Rich color for an event type."""
        if "ERROR" in event_type or "FAILED" in event_type:
            return "red"
        if "COMPLETED" in event_type:
            return "green"
        if "STARTED" in event_type:
            return "blue"
        if "BLOCKED" in event_type:
            return "yellow"
        if "QUEUED" in event_type:
            return "dim"
        return "cyan"

    def _print_batch_event(event: events.Event) -> None:
        """Print a batch event to console."""
        timestamp = event.created_at.strftime("%H:%M:%S")
        color = _get_event_color(event.event_type)

        # Extract key info from payload
        task_id = event.payload.get("task_id", "")
        position = event.payload.get("position", "")

        # Short event name (remove BATCH_ prefix for cleaner output)
        event_name = event.event_type.replace("BATCH_", "")

        # Format based on event type
        if "TASK" in event.event_type and task_id:
            detail = f"task={task_id[:8]}"
            if position:
                detail += f" ({position})"
        elif event.event_type in TERMINAL_EVENTS:
            # Batch completion event
            completed = event.payload.get("completed", 0)
            total = event.payload.get("total", 0)
            detail = f"{completed}/{total} completed"
        else:
            detail = ""

        console.print(
            f"[dim]{timestamp}[/dim] [{color}]{event_name}[/{color}]"
            + (f" {detail}" if detail else "")
        )

    def _generate_progress_display(progress: BatchProgress, batch_id_short: str) -> Panel:
        """Generate Rich panel showing progress."""
        # Build status line
        parts = []
        if progress.completed_tasks:
            parts.append(f"[green]{progress.completed_tasks} completed[/green]")
        if progress.failed_tasks:
            parts.append(f"[red]{progress.failed_tasks} failed[/red]")
        if progress.blocked_tasks:
            parts.append(f"[yellow]{progress.blocked_tasks} blocked[/yellow]")
        if progress.running_tasks:
            parts.append(f"[blue]{progress.running_tasks} running[/blue]")
        remaining = progress.remaining_tasks - progress.running_tasks
        if remaining > 0:
            parts.append(f"[dim]{remaining} pending[/dim]")

        status_line = " | ".join(parts) if parts else "Starting..."

        # Progress info
        percent = progress.progress_percent
        eta = progress.format_eta()
        elapsed = progress.format_elapsed()

        content = f"""{status_line}
Progress: {progress.processed_tasks}/{progress.total_tasks} ({percent:.0f}%)
ETA: {eta} | Elapsed: {elapsed}"""

        return Panel(
            content,
            title=f"[bold]Batch {batch_id_short}[/bold]",
            border_style="blue",
        )

    def _update_progress(progress: BatchProgress, event: events.Event) -> None:
        """Update progress tracker based on event."""
        task_id = event.payload.get("task_id", "")

        if event.event_type == events.EventType.BATCH_TASK_STARTED:
            progress.record_task_start(task_id)
        elif event.event_type == events.EventType.BATCH_TASK_COMPLETED:
            progress.record_task_complete(task_id)
        elif event.event_type == events.EventType.BATCH_TASK_FAILED:
            progress.record_task_failed(task_id)
        elif event.event_type == events.EventType.BATCH_TASK_BLOCKED:
            progress.record_task_blocked(task_id)

    try:
        workspace = get_workspace(path)

        # Find batch by partial ID
        all_batches = conductor.list_batches(workspace, limit=100)
        matching = [b for b in all_batches if b.id.startswith(batch_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No batch found matching '{batch_id}'")
            raise typer.Exit(1)

        batch = matching[0]
        batch_id_short = batch.id[:8]

        # Check if already in terminal state
        if batch.status in (
            conductor.BatchStatus.COMPLETED,
            conductor.BatchStatus.PARTIAL,
            conductor.BatchStatus.FAILED,
            conductor.BatchStatus.CANCELLED,
        ):
            console.print(f"[dim]Batch {batch_id_short} already {batch.status.value}[/dim]")

            # Show final summary
            completed = sum(1 for s in batch.results.values() if s == "COMPLETED")
            failed = sum(1 for s in batch.results.values() if s == "FAILED")
            blocked = sum(1 for s in batch.results.values() if s == "BLOCKED")

            console.print(f"\n  [green]{completed} completed[/green]", end="")
            if failed:
                console.print(f" | [red]{failed} failed[/red]", end="")
            if blocked:
                console.print(f" | [yellow]{blocked} blocked[/yellow]", end="")
            console.print()
            return

        # Initialize progress tracker
        completed_count = sum(1 for s in batch.results.values() if s == "COMPLETED")
        failed_count = sum(1 for s in batch.results.values() if s == "FAILED")
        blocked_count = sum(1 for s in batch.results.values() if s == "BLOCKED")

        progress = BatchProgress(
            total_tasks=len(batch.task_ids),
            completed_tasks=completed_count,
            failed_tasks=failed_count,
            blocked_tasks=blocked_count,
            started_at=batch.started_at,
        )

        # Get starting event ID (find batch's first event or latest)
        recent_events = events.list_recent(workspace, limit=100)
        batch_events = [e for e in recent_events if e.payload.get("batch_id") == batch.id]
        since_id = batch_events[-1].id - 1 if batch_events else 0

        console.print(f"[cyan]Following batch {batch_id_short}...[/cyan]")
        console.print("[dim]Press Ctrl+C to stop following[/dim]\n")

        try:
            if no_progress:
                # Simple mode: just print events
                for event in events.tail(workspace, since_id):
                    if event.payload.get("batch_id") != batch.id:
                        continue

                    _update_progress(progress, event)
                    _print_batch_event(event)

                    if event.event_type in TERMINAL_EVENTS:
                        break
            else:
                # Rich mode: live progress display
                with Live(
                    _generate_progress_display(progress, batch_id_short),
                    refresh_per_second=2,
                    console=console,
                ) as live:
                    for event in events.tail(workspace, since_id):
                        if event.payload.get("batch_id") != batch.id:
                            continue

                        _update_progress(progress, event)

                        # Print event below progress panel
                        live.console.print()  # Clear line
                        _print_batch_event(event)

                        # Update progress display
                        live.update(_generate_progress_display(progress, batch_id_short))

                        if event.event_type in TERMINAL_EVENTS:
                            break

        except KeyboardInterrupt:
            console.print("\n[yellow]Follow cancelled[/yellow]")
            return

        # Final summary
        batch = conductor.get_batch(workspace, batch.id)  # Refresh
        console.print()

        if batch.status == conductor.BatchStatus.COMPLETED:
            console.print(f"[green]✓ Batch {batch_id_short} completed successfully![/green]")
        elif batch.status == conductor.BatchStatus.PARTIAL:
            final_failed = sum(1 for s in batch.results.values() if s in ("FAILED", "BLOCKED"))
            console.print(
                f"[yellow]⚠ Batch {batch_id_short} partially completed "
                f"({final_failed} failed/blocked)[/yellow]"
            )
        elif batch.status == conductor.BatchStatus.CANCELLED:
            console.print(f"[red]✗ Batch {batch_id_short} was cancelled[/red]")
        else:
            console.print(f"[red]✗ Batch {batch_id_short} {batch.status.value.lower()}[/red]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


# Add batch subcommand group to work
work_app.add_typer(batch_app, name="batch")


# Events commands
events_app = typer.Typer(
    name="events",
    help="Event log management",
    no_args_is_help=True,
)


@events_app.command("tail")
def events_tail(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of events to show"),
) -> None:
    """Tail the event log."""
    # Stub for Phase 3
    console.print("[yellow]Not yet implemented.[/yellow] Coming in Phase 3.")


# Blocker commands
blocker_app = typer.Typer(
    name="blocker",
    help="Blocker management (human-in-the-loop)",
    no_args_is_help=True,
)


@blocker_app.command("list")
def blocker_list(
    all_blockers: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all blockers (not just open)",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """List blockers.

    By default shows only open blockers. Use --all to show all.

    Example:
        codeframe blocker list
        codeframe blocker list --all
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import blockers
    from codeframe.core.blockers import BlockerStatus
    from rich.table import Table

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)

        if all_blockers:
            blocker_list_data = blockers.list_all(workspace)
        else:
            blocker_list_data = blockers.list_open(workspace)

        if not blocker_list_data:
            if all_blockers:
                console.print("[dim]No blockers[/dim]")
            else:
                console.print("[dim]No open blockers[/dim]")
            return

        table = Table(title="Blockers" if all_blockers else "Open Blockers")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Status", width=10)
        table.add_column("Task", style="dim", width=8)
        table.add_column("Question", max_width=50)

        for b in blocker_list_data:
            # Status color
            if b.status == BlockerStatus.OPEN:
                status_str = "[yellow]OPEN[/yellow]"
            elif b.status == BlockerStatus.ANSWERED:
                status_str = "[blue]ANSWERED[/blue]"
            else:
                status_str = "[green]RESOLVED[/green]"

            task_str = b.task_id[:8] if b.task_id else "-"
            question_str = b.question[:50] + "..." if len(b.question) > 50 else b.question

            table.add_row(b.id[:8], status_str, task_str, question_str)

        console.print(table)

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@blocker_app.command("show")
def blocker_show(
    blocker_id: str = typer.Argument(..., help="Blocker ID (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Show details of a blocker.

    Example:
        codeframe blocker show abc123
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import blockers
    from codeframe.core.blockers import BlockerStatus

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        blocker = blockers.get(workspace, blocker_id)

        if not blocker:
            console.print(f"[red]Error:[/red] Blocker not found: {blocker_id}")
            raise typer.Exit(1)

        # Status color
        if blocker.status == BlockerStatus.OPEN:
            status_str = "[yellow]OPEN[/yellow]"
        elif blocker.status == BlockerStatus.ANSWERED:
            status_str = "[blue]ANSWERED[/blue]"
        else:
            status_str = "[green]RESOLVED[/green]"

        console.print(f"\n[bold]Blocker[/bold] {blocker.id[:8]}")
        console.print(f"  Status: {status_str}")
        console.print(f"  Task: {blocker.task_id[:8] if blocker.task_id else '-'}")
        console.print(f"  Created: {blocker.created_at.strftime('%Y-%m-%d %H:%M')}")

        console.print("\n[bold]Question:[/bold]")
        console.print(f"  {blocker.question}")

        if blocker.answer:
            console.print("\n[bold]Answer:[/bold]")
            console.print(f"  {blocker.answer}")
            if blocker.answered_at:
                console.print(f"  [dim]Answered: {blocker.answered_at.strftime('%Y-%m-%d %H:%M')}[/dim]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@blocker_app.command("create")
def blocker_create(
    question: str = typer.Argument(..., help="Question to ask"),
    task_id: Optional[str] = typer.Option(
        None,
        "--task",
        "-t",
        help="Associated task ID",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Create a blocker manually.

    Blockers are normally created by the agent when it gets stuck,
    but you can create them manually for testing or planning.

    Example:
        codeframe blocker create "What authentication method should we use?"
        codeframe blocker create "API rate limit?" --task abc123
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import blockers

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        blocker = blockers.create(workspace, question, task_id=task_id)

        console.print("\n[bold green]Blocker created[/bold green]")
        console.print(f"  ID: {blocker.id[:8]}")
        console.print(f"  Question: {question[:60]}{'...' if len(question) > 60 else ''}")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@blocker_app.command("answer")
def blocker_answer(
    blocker_id: str = typer.Argument(..., help="Blocker ID (can be partial)"),
    text: str = typer.Argument(..., help="Answer text"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Answer a blocker to unblock work.

    Example:
        codeframe blocker answer abc123 "Use OAuth 2.0 with JWT tokens"
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import blockers

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        blocker = blockers.answer(workspace, blocker_id, text)

        console.print("\n[bold green]Blocker answered[/bold green]")
        console.print(f"  ID: {blocker.id[:8]}")
        console.print("  Status: [blue]ANSWERED[/blue]")
        console.print(f"\nUse 'codeframe blocker resolve {blocker.id[:8]}' to mark as resolved.")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@blocker_app.command("resolve")
def blocker_resolve(
    blocker_id: str = typer.Argument(..., help="Blocker ID (can be partial)"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Mark a blocker as resolved.

    A blocker must be answered before it can be resolved.

    Example:
        codeframe blocker resolve abc123
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import blockers

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        blocker = blockers.resolve(workspace, blocker_id)

        console.print("\n[bold green]Blocker resolved[/bold green]")
        console.print(f"  ID: {blocker.id[:8]}")
        console.print("  Status: [green]RESOLVED[/green]")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Patch/commit commands
patch_app = typer.Typer(
    name="patch",
    help="Patch and diff management",
    no_args_is_help=True,
)


@patch_app.command("export")
def patch_export(
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output file path (auto-generated if not provided)",
    ),
    staged_only: bool = typer.Option(
        False,
        "--staged",
        "-s",
        help="Only include staged changes",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Export changes as a patch file.

    Creates a .patch file with all uncommitted changes.
    Patches are stored in .codeframe/patches/ by default.

    Example:
        codeframe patch export
        codeframe patch export --out changes.patch
        codeframe patch export --staged
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import artifacts

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        patch_info = artifacts.export_patch(workspace, out_path=out, staged_only=staged_only)

        console.print("\n[bold green]Patch exported[/bold green]")
        console.print(f"  Path: {patch_info.path}")
        console.print(f"  Size: {patch_info.size_bytes} bytes")
        console.print(
            f"  Changes: {patch_info.files_changed} files, "
            f"+{patch_info.insertions}/-{patch_info.deletions}"
        )

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@patch_app.command("list")
def patch_list(
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """List exported patches.

    Example:
        codeframe patch list
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import artifacts
    from rich.table import Table

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        patches = artifacts.list_patches(workspace)

        if not patches:
            console.print("[dim]No patches found[/dim]")
            return

        table = Table(title="Exported Patches")
        table.add_column("File", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Changes", justify="right")
        table.add_column("Created", style="dim")

        for p in patches:
            table.add_row(
                p.path.name,
                f"{p.size_bytes} B",
                f"{p.files_changed} files",
                p.created_at.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@patch_app.command("status")
def patch_status(
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Show git status summary.

    Example:
        codeframe patch status
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import artifacts

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        status = artifacts.get_status(workspace.repo_path)

        if status["clean"]:
            console.print("[green]Working tree clean[/green]")
            return

        if status["staged"]:
            console.print(f"\n[bold]Staged[/bold] ({len(status['staged'])} files)")
            for f in status["staged"][:10]:
                console.print(f"  [green]{f}[/green]")
            if len(status["staged"]) > 10:
                console.print(f"  ... and {len(status['staged']) - 10} more")

        if status["unstaged"]:
            console.print(f"\n[bold]Modified[/bold] ({len(status['unstaged'])} files)")
            for f in status["unstaged"][:10]:
                console.print(f"  [yellow]{f}[/yellow]")
            if len(status["unstaged"]) > 10:
                console.print(f"  ... and {len(status['unstaged']) - 10} more")

        if status["untracked"]:
            console.print(f"\n[bold]Untracked[/bold] ({len(status['untracked'])} files)")
            for f in status["untracked"][:5]:
                console.print(f"  [dim]{f}[/dim]")
            if len(status["untracked"]) > 5:
                console.print(f"  ... and {len(status['untracked']) - 5} more")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


commit_app = typer.Typer(
    name="commit",
    help="Git commit management",
    no_args_is_help=True,
)


@commit_app.command("create")
def commit_create(
    message: str = typer.Option(..., "--message", "-m", help="Commit message"),
    add_all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Stage all changes before committing",
    ),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Create a git commit for completed work.

    Example:
        codeframe commit create -m "feat: add user authentication"
        codeframe commit create -m "fix: handle edge case" --all
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import artifacts

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        commit_info = artifacts.create_commit(workspace, message, add_all=add_all)

        console.print("\n[bold green]Commit created[/bold green]")
        console.print(f"  Hash: {commit_info.hash}")
        console.print(f"  Message: {commit_info.message}")
        console.print(
            f"  Changes: {commit_info.files_changed} files, "
            f"+{commit_info.insertions}/-{commit_info.deletions}"
        )

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# Checkpoint commands
checkpoint_app = typer.Typer(
    name="checkpoint",
    help="State checkpoint management",
    no_args_is_help=True,
)


@checkpoint_app.command("create")
def checkpoint_create(
    name: str = typer.Argument(..., help="Checkpoint name"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Create a state checkpoint.

    Captures current task statuses, blockers, PRD, and git ref.

    Example:
        codeframe checkpoint create "before-refactor"
        codeframe checkpoint create "v1.0-ready"
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import checkpoints

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        checkpoint = checkpoints.create(workspace, name)

        summary = checkpoint.snapshot.get("summary", {})

        console.print("\n[bold green]Checkpoint created[/bold green]")
        console.print(f"  Name: {checkpoint.name}")
        console.print(f"  ID: [dim]{checkpoint.id[:8]}[/dim]")
        console.print(f"  Tasks: {summary.get('total_tasks', 0)}")

        git_ref = checkpoint.snapshot.get("git_ref")
        if git_ref:
            console.print(f"  Git: {git_ref[:7]}")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@checkpoint_app.command("list")
def checkpoint_list(
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """List available checkpoints.

    Example:
        codeframe checkpoint list
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import checkpoints
    from rich.table import Table

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        all_checkpoints = checkpoints.list_all(workspace)

        if not all_checkpoints:
            console.print("[dim]No checkpoints[/dim]")
            return

        table = Table(title="Checkpoints")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Name", style="cyan")
        table.add_column("Tasks", justify="right")
        table.add_column("Git", style="dim", width=7)
        table.add_column("Created", style="dim")

        for cp in all_checkpoints:
            summary = cp.snapshot.get("summary", {})
            git_ref = cp.snapshot.get("git_ref", "")[:7] if cp.snapshot.get("git_ref") else "-"

            table.add_row(
                cp.id[:8],
                cp.name,
                str(summary.get("total_tasks", 0)),
                git_ref,
                cp.created_at.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@checkpoint_app.command("show")
def checkpoint_show(
    name_or_id: str = typer.Argument(..., help="Checkpoint name or ID"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Show checkpoint details.

    Example:
        codeframe checkpoint show before-refactor
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import checkpoints

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        checkpoint = checkpoints.get(workspace, name_or_id)

        if not checkpoint:
            console.print(f"[red]Error:[/red] Checkpoint not found: {name_or_id}")
            raise typer.Exit(1)

        summary = checkpoint.snapshot.get("summary", {})
        tasks_by_status = summary.get("tasks_by_status", {})

        console.print(f"\n[bold]Checkpoint:[/bold] {checkpoint.name}")
        console.print(f"  ID: {checkpoint.id}")
        console.print(f"  Created: {checkpoint.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

        git_ref = checkpoint.snapshot.get("git_ref")
        if git_ref:
            console.print(f"  Git ref: {git_ref}")

        if checkpoint.snapshot.get("prd"):
            console.print(f"  PRD: {checkpoint.snapshot['prd'].get('title', 'Unknown')}")

        console.print("\n[bold]Task Summary:[/bold]")
        for status, count in tasks_by_status.items():
            if count > 0:
                console.print(f"  {status}: {count}")

        console.print(f"  Open blockers: {summary.get('open_blockers', 0)}")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


@checkpoint_app.command("restore")
def checkpoint_restore(
    name_or_id: str = typer.Argument(..., help="Checkpoint name or ID"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Restore state from a checkpoint.

    Restores task statuses from the checkpoint snapshot.
    Does not modify files or git state.

    Example:
        codeframe checkpoint restore before-refactor
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import checkpoints

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        checkpoint = checkpoints.restore(workspace, name_or_id)

        summary = checkpoint.snapshot.get("summary", {})

        console.print("\n[bold green]Checkpoint restored[/bold green]")
        console.print(f"  Name: {checkpoint.name}")
        console.print(f"  Tasks restored: {summary.get('total_tasks', 0)}")

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@checkpoint_app.command("delete")
def checkpoint_delete(
    name_or_id: str = typer.Argument(..., help="Checkpoint name or ID"),
    workspace_path: Optional[Path] = typer.Option(
        None,
        "--workspace",
        "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Delete a checkpoint.

    Example:
        codeframe checkpoint delete old-checkpoint
    """
    from codeframe.core.workspace import get_workspace
    from codeframe.core import checkpoints

    path = workspace_path or Path.cwd()

    try:
        workspace = get_workspace(path)
        deleted = checkpoints.delete(workspace, name_or_id)

        if deleted:
            console.print("[green]Checkpoint deleted[/green]")
        else:
            console.print(f"[red]Error:[/red] Checkpoint not found: {name_or_id}")
            raise typer.Exit(1)

    except FileNotFoundError:
        console.print(f"[red]Error:[/red] No workspace found at {path}")
        raise typer.Exit(1)


# Gates commands (alternative to root 'review')
gates_app = typer.Typer(
    name="gates",
    help="Quality gate management",
    no_args_is_help=True,
)


@gates_app.command("run")
def gates_run() -> None:
    """Run verification gates (tests, lint)."""
    # Stub for Phase 5
    console.print("[yellow]Not yet implemented.[/yellow] Coming in Phase 5.")


# =============================================================================
# Register all sub-applications
# =============================================================================

app.add_typer(prd_app, name="prd")
app.add_typer(tasks_app, name="tasks")
app.add_typer(work_app, name="work")
app.add_typer(events_app, name="events")
app.add_typer(blocker_app, name="blocker")
app.add_typer(patch_app, name="patch")
app.add_typer(commit_app, name="commit")
app.add_typer(checkpoint_app, name="checkpoint")
app.add_typer(gates_app, name="gates")


# =============================================================================
# Version command
# =============================================================================


@app.command()
def version() -> None:
    """Show CodeFRAME version."""
    from codeframe import __version__

    console.print(f"CodeFRAME version: [bold green]{__version__}[/bold green]")


if __name__ == "__main__":
    app()
