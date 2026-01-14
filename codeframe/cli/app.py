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
            console.print(f"[blue]Workspace already initialized[/blue]")
        else:
            console.print(f"[green]Workspace initialized[/green]")

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
        console.print(f"\n[bold cyan]CodeFRAME Workspace[/bold cyan]")
        console.print(f"  Path: {workspace.repo_path}")
        console.print(f"  ID: [dim]{workspace.id}[/dim]")
        console.print(f"  Created: {workspace.created_at.strftime('%Y-%m-%d %H:%M')}")

        # PRD info
        console.print(f"\n[bold]PRD[/bold]")
        latest_prd = prd.get_latest(workspace)
        if latest_prd:
            console.print(f"  Title: [green]{latest_prd.title}[/green]")
            console.print(f"  Added: {latest_prd.created_at.strftime('%Y-%m-%d %H:%M')}")
        else:
            console.print("  [dim]No PRD loaded. Run 'codeframe prd add <file>'[/dim]")

        # Task counts
        console.print(f"\n[bold]Tasks[/bold]")
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
            console.print(f"\n[bold]Recent Activity[/bold]")
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

        console.print(f"[green]PRD added[/green]")
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
        console.print("  codeframe tasks set status <id> READY   Mark task ready")

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
    task_id: str = typer.Argument(..., help="Task ID (can be partial)"),
    value: str = typer.Argument(..., help="New value"),
    repo_path: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Set a task attribute.

    Example:
        codeframe tasks set status abc123 READY
        codeframe tasks set status abc123 in_progress
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

        # Find task by ID (support partial match)
        all_tasks = tasks.list_tasks(workspace)
        matching = [t for t in all_tasks if t.id.startswith(task_id)]

        if not matching:
            console.print(f"[red]Error:[/red] No task found matching '{task_id}'")
            raise typer.Exit(1)

        if len(matching) > 1:
            console.print(f"[red]Error:[/red] Multiple tasks match '{task_id}':")
            for t in matching:
                console.print(f"  {t.id}: {t.title[:40]}")
            console.print("Please provide a more specific ID.")
            raise typer.Exit(1)

        task = matching[0]
        new_status = parse_status(value)

        # Update status
        old_status = task.status
        updated = tasks.update_status(workspace, task.id, new_status)

        # Emit event
        emit_for_workspace(
            workspace,
            EventType.TASK_STATUS_CHANGED,
            {"task_id": task.id, "old_status": old_status.value, "new_status": new_status.value},
            print_event=False,
        )

        console.print(f"[green]Task updated[/green]")
        console.print(f"  {task.title[:50]}")
        console.print(f"  Status: {old_status.value} -> {new_status.value}")

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

        console.print(f"\n[bold green]Run started[/bold green]")
        console.print(f"  Task: {task.title}")
        console.print(f"  Run ID: [dim]{run.id}[/dim]")
        console.print(f"  Status: [yellow]RUNNING[/yellow]")

        # Execute agent if requested
        if execute:
            from codeframe.core.agent import AgentStatus

            mode = "[dim](dry run)[/dim]" if dry_run else ""
            console.print(f"\n[bold]Executing agent...{mode}[/bold]")

            try:
                state = runtime.execute_agent(workspace, run, dry_run=dry_run)

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

        console.print(f"\n[bold green]Run resumed[/bold green]")
        console.print(f"  Task: {task.title}")
        console.print(f"  Run ID: [dim]{run.id}[/dim]")
        console.print(f"  Status: [yellow]RUNNING[/yellow]")

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

        console.print(f"\n[bold yellow]Run stopped[/bold yellow]")
        console.print(f"  Task: {task.title}")
        console.print(f"  Run ID: [dim]{run.id}[/dim]")
        console.print(f"  Task returned to: [blue]READY[/blue]")

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
                console.print(f"\n[bold]Run Status[/bold]")
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

        console.print(f"\n[bold]Question:[/bold]")
        console.print(f"  {blocker.question}")

        if blocker.answer:
            console.print(f"\n[bold]Answer:[/bold]")
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

        console.print(f"\n[bold green]Blocker created[/bold green]")
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

        console.print(f"\n[bold green]Blocker answered[/bold green]")
        console.print(f"  ID: {blocker.id[:8]}")
        console.print(f"  Status: [blue]ANSWERED[/blue]")
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

        console.print(f"\n[bold green]Blocker resolved[/bold green]")
        console.print(f"  ID: {blocker.id[:8]}")
        console.print(f"  Status: [green]RESOLVED[/green]")

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

        console.print(f"\n[bold green]Patch exported[/bold green]")
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

        console.print(f"\n[bold green]Commit created[/bold green]")
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

        console.print(f"\n[bold green]Checkpoint created[/bold green]")
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

        console.print(f"\n[bold]Task Summary:[/bold]")
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

        console.print(f"\n[bold green]Checkpoint restored[/bold green]")
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
            console.print(f"[green]Checkpoint deleted[/green]")
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
