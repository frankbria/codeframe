"""CLI workspace lifecycle hooks management.

Usage:
    codeframe hooks show              # Display configured hooks
    codeframe hooks run <hook_name>   # Manually trigger a hook
    codeframe hooks set <name> <cmd>  # Set a hook command
    codeframe hooks clear <name>      # Remove a hook
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

hooks_app = typer.Typer(
    name="hooks",
    help="Workspace lifecycle hooks management",
    no_args_is_help=True,
)

VALID_HOOK_NAMES = [
    "after_init",
    "before_task",
    "after_task_success",
    "after_task_failure",
    "before_remove",
]


@hooks_app.command("show")
def hooks_show(
    workspace_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Display configured hooks from .codeframe/config.yaml."""
    from codeframe.core.config import load_environment_config

    from codeframe.core.workspace import get_workspace
    path = workspace_path or Path.cwd()
    try:
        ws = get_workspace(path)
        path = ws.repo_path
    except (FileNotFoundError, ValueError):
        pass  # Workspace not initialized; fall back to raw path
    config = load_environment_config(path)

    if not config:
        console.print("[yellow]No workspace configuration found.[/yellow]")
        console.print("Run 'codeframe init .' first.")
        raise typer.Exit(1)

    table = Table(title="Workspace Hooks")
    table.add_column("Hook Point", style="cyan")
    table.add_column("Command", style="dim")
    table.add_column("Status")

    for hook_name in VALID_HOOK_NAMES:
        command = getattr(config.hooks, hook_name, None)
        if command:
            table.add_row(hook_name, command, "[green]configured[/green]")
        else:
            table.add_row(hook_name, "-", "[dim]not set[/dim]")

    table.add_row("", "", "")
    table.add_row("hook_timeout", f"{config.hooks.hook_timeout}s", "[dim]default[/dim]")

    console.print(table)


@hooks_app.command("run")
def hooks_run(
    hook_name: str = typer.Argument(..., help="Hook name to execute"),
    task_id: str = typer.Option("", "--task-id", help="Task ID for template rendering"),
    task_title: str = typer.Option("", "--task-title", help="Task title for template rendering"),
    workspace_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Manually trigger a named hook."""
    from codeframe.core.config import load_environment_config
    from codeframe.core.hooks import HookContext, execute_hook

    if hook_name not in VALID_HOOK_NAMES:
        console.print(f"[red]Error:[/red] Invalid hook name '{hook_name}'")
        console.print(f"Valid hooks: {', '.join(VALID_HOOK_NAMES)}")
        raise typer.Exit(1)

    from codeframe.core.workspace import get_workspace
    path = workspace_path or Path.cwd()
    try:
        ws = get_workspace(path)
        path = ws.repo_path
    except (FileNotFoundError, ValueError):
        pass  # Workspace not initialized; fall back to raw path
    config = load_environment_config(path)

    if not config:
        console.print("[yellow]No workspace configuration found.[/yellow]")
        raise typer.Exit(1)

    ctx = HookContext(
        task_id=task_id,
        task_title=task_title,
        task_status="manual",
        workspace_path=str(path),
    )

    result = execute_hook(hook_name, config, path, ctx, abort_on_failure=False)

    if result is None:
        console.print(f"[yellow]Hook '{hook_name}' is not configured.[/yellow]")
        return

    if result.success:
        console.print(f"[green]Hook '{hook_name}' succeeded[/green] ({result.duration_ms}ms)")
    else:
        console.print(f"[red]Hook '{hook_name}' failed[/red] ({result.duration_ms}ms)")
        if result.timed_out:
            console.print("  [yellow]Timed out[/yellow]")

    if result.stdout.strip():
        console.print(f"  stdout: {result.stdout.strip()[:500]}")
    if result.stderr.strip():
        console.print(f"  stderr: {result.stderr.strip()[:500]}")

    if not result.success:
        raise typer.Exit(1)


@hooks_app.command("set")
def hooks_set(
    hook_name: str = typer.Argument(..., help="Hook name to configure"),
    command: str = typer.Argument(..., help="Shell command template"),
    workspace_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Set or update a hook command."""
    from codeframe.core.config import (
        load_environment_config,
        save_environment_config,
        get_default_environment_config,
    )

    if hook_name not in VALID_HOOK_NAMES:
        console.print(f"[red]Error:[/red] Invalid hook name '{hook_name}'")
        console.print(f"Valid hooks: {', '.join(VALID_HOOK_NAMES)}")
        raise typer.Exit(1)

    from codeframe.core.workspace import get_workspace
    path = workspace_path or Path.cwd()
    try:
        ws = get_workspace(path)
        path = ws.repo_path
    except (FileNotFoundError, ValueError):
        pass  # Workspace not initialized; fall back to raw path
    config = load_environment_config(path) or get_default_environment_config()

    setattr(config.hooks, hook_name, command)
    save_environment_config(path, config)

    console.print(f"[green]Hook '{hook_name}' set to:[/green] {command}")


@hooks_app.command("clear")
def hooks_clear(
    hook_name: str = typer.Argument(..., help="Hook name to clear"),
    workspace_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
) -> None:
    """Remove a hook."""
    from codeframe.core.config import (
        load_environment_config,
        save_environment_config,
    )

    if hook_name not in VALID_HOOK_NAMES:
        console.print(f"[red]Error:[/red] Invalid hook name '{hook_name}'")
        console.print(f"Valid hooks: {', '.join(VALID_HOOK_NAMES)}")
        raise typer.Exit(1)

    from codeframe.core.workspace import get_workspace
    path = workspace_path or Path.cwd()
    try:
        ws = get_workspace(path)
        path = ws.repo_path
    except (FileNotFoundError, ValueError):
        pass  # Workspace not initialized; fall back to raw path
    config = load_environment_config(path)

    if not config:
        console.print("[yellow]No workspace configuration found.[/yellow]")
        raise typer.Exit(1)

    setattr(config.hooks, hook_name, None)
    save_environment_config(path, config)

    console.print(f"[green]Hook '{hook_name}' cleared.[/green]")
