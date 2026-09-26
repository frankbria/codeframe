"""CLI workspace lifecycle hooks management.

Usage:
    codeframe hooks show              # Display configured hooks
    codeframe hooks run <hook_name>   # Manually trigger a hook
    codeframe hooks set <name> <cmd>  # Set a hook command
    codeframe hooks clear <name>      # Remove a hook
    codeframe hooks trust             # Approve repo-supplied hooks (#905)
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.markup import escape

if TYPE_CHECKING:  # pragma: no cover
    from codeframe.core.config import HooksConfig

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
            table.add_row(hook_name, escape(command), "[green]configured[/green]")
        else:
            table.add_row(hook_name, "-", "[dim]not set[/dim]")

    table.add_row("", "", "")
    table.add_row("hook_timeout", f"{config.hooks.hook_timeout}s", "[dim]default[/dim]")

    console.print(table)

    from codeframe.core.hook_trust import describe_hooks, is_trusted
    if describe_hooks(config.hooks):
        if is_trusted(path, config.hooks):
            console.print("[green]Trusted[/green] — these hooks may run.")
        else:
            console.print(
                "[yellow]Not trusted[/yellow] — these hooks will NOT run. "
                "Approve with 'codeframe hooks trust'."
            )


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
        console.print(f"[red]Error:[/red] Invalid hook name '{escape(hook_name)}'")
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
        console.print(f"[yellow]Hook '{escape(hook_name)}' is not configured.[/yellow]")
        return

    if result.success:
        console.print(f"[green]Hook '{escape(hook_name)}' succeeded[/green] ({result.duration_ms}ms)")
    else:
        console.print(f"[red]Hook '{escape(hook_name)}' failed[/red] ({result.duration_ms}ms)")
        if result.timed_out:
            console.print("  [yellow]Timed out[/yellow]")

    if result.stdout.strip():
        console.print(f"  stdout: {escape(result.stdout.strip()[:500])}")
    if result.stderr.strip():
        console.print(f"  stderr: {escape(result.stderr.strip()[:500])}")

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
        console.print(f"[red]Error:[/red] Invalid hook name '{escape(hook_name)}'")
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
    was_trusted = _hooks_trusted(path, config.hooks)

    setattr(config.hooks, hook_name, command)
    save_environment_config(path, config)
    console.print(f"[green]Hook '{escape(hook_name)}' set to:[/green] {escape(command)}")
    _carry_trust_forward(path, config.hooks, was_trusted)


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
        console.print(f"[red]Error:[/red] Invalid hook name '{escape(hook_name)}'")
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

    was_trusted = _hooks_trusted(path, config.hooks)

    setattr(config.hooks, hook_name, None)
    save_environment_config(path, config)
    console.print(f"[green]Hook '{escape(hook_name)}' cleared.[/green]")
    _carry_trust_forward(path, config.hooks, was_trusted)


def _hooks_trusted(path: Path, hooks: "HooksConfig") -> bool:
    """Whether the hooks as they stand *before* an edit are approved.

    No hooks at all counts as approved: after the edit the only command is the
    operator's own.
    """
    from codeframe.core.hook_trust import describe_hooks, is_trusted

    return not describe_hooks(hooks) or is_trusted(path, hooks)


def _carry_trust_forward(path: Path, hooks: "HooksConfig", was_trusted: bool) -> None:
    """Re-approve an operator's edit to hooks that were already approved.

    Trust is keyed on the exact commands (#905), so any edit revokes it. It is
    re-recorded only when it existed before the edit: recording it otherwise
    would approve every *other* hook the repo committed (#1263).
    """
    from codeframe.core.hook_trust import describe_hooks, record_trust

    if was_trusted:
        record_trust(path, hooks)
    elif describe_hooks(hooks):
        console.print(
            "[yellow]These hooks are not trusted and will NOT run.[/yellow] "
            "Review and approve them with 'cf hooks trust'."
        )


@hooks_app.command("trust")
def hooks_trust(
    workspace_path: Optional[Path] = typer.Option(
        None, "--workspace", "-w",
        help="Workspace path (defaults to current directory)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt"),
) -> None:
    """Approve this workspace's hook commands so they are allowed to run.

    Hooks come from files a repository can commit, so cloning an untrusted repo
    would otherwise be enough to get its shell commands executed (#905). The
    decision is recorded outside the repository tree and keyed to these exact
    commands, so editing a hook requires approving it again.
    """
    from codeframe.core.config import load_environment_config
    from codeframe.core.hook_trust import describe_hooks, record_trust
    from codeframe.core.workspace import get_workspace

    path = (workspace_path or Path.cwd()).resolve()
    try:
        path = get_workspace(path).repo_path
    except (FileNotFoundError, ValueError):
        pass  # Workspace not initialized; fall back to raw path

    config = load_environment_config(path)
    described = describe_hooks(config.hooks) if config else ""
    if not described:
        console.print("[yellow]No hooks configured — nothing to trust.[/yellow]")
        raise typer.Exit(1)

    # Always show the exact commands before approval: they run as you.
    console.print("[bold]These commands will run on this workspace's lifecycle events:[/bold]")
    console.print(escape(described))
    if not yes and not typer.confirm("Trust these hooks?", default=False):
        console.print("[yellow]Not trusted.[/yellow]")
        raise typer.Exit(1)

    record_trust(path, config.hooks)
    console.print(f"[green]Hooks trusted for {escape(str(path))}[/green]")
