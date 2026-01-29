"""CLI environment validation commands.

This module provides commands for:
- Checking environment health
- Running comprehensive diagnostics
- Installing missing tools
- Auto-installing all missing tools

Usage:
    codeframe env check           # Quick validation
    codeframe env doctor          # Comprehensive diagnostics
    codeframe env install-missing pytest  # Install specific tool
    codeframe env auto-install --yes      # Install all missing
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from codeframe.core.environment import (
    EnvironmentValidator,
    ToolStatus,
)
from codeframe.core.installer import ToolInstaller


console = Console()

env_app = typer.Typer(
    name="env",
    help="Environment validation and tool management",
    no_args_is_help=True,
)


@env_app.command()
def check(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project directory to validate"
    ),
):
    """Quick environment validation.

    Checks if required tools are installed and shows health score.

    Examples:

        codeframe env check

        codeframe env check --project ./my-project
    """
    # Determine project path
    if project:
        project_path = Path(project)
        if not project_path.exists():
            console.print(f"[red]Error:[/red] Project path not found: {project}")
            raise typer.Exit(1)
    else:
        project_path = Path.cwd()

    # Run validation
    validator = EnvironmentValidator()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Checking environment...", total=None)
        result = validator.validate_environment(project_path)

    # Display results
    health_pct = int(result.health_score * 100)

    if result.is_healthy:
        health_color = "green"
        health_status = "Healthy"
    elif result.health_score >= 0.5:
        health_color = "yellow"
        health_status = "Partial"
    else:
        health_color = "red"
        health_status = "Unhealthy"

    console.print()
    console.print(f"[bold]Project Type:[/bold] {result.project_type}")
    console.print(f"[bold]Health Score:[/bold] [{health_color}]{health_pct}%[/{health_color}] ({health_status})")
    console.print()

    # Show tool summary
    available_count = sum(1 for t in result.detected_tools.values() if t.is_available)
    total_count = len(result.detected_tools)
    console.print(f"[bold]Tools:[/bold] {available_count}/{total_count} available")

    if result.missing_tools:
        console.print(f"[bold]Missing (required):[/bold] [red]{', '.join(result.missing_tools)}[/red]")

    if result.optional_missing:
        console.print(f"[bold]Missing (optional):[/bold] [yellow]{', '.join(result.optional_missing)}[/yellow]")

    console.print()

    # Show quick recommendations
    if result.recommendations:
        console.print("[bold]Quick fix:[/bold]")
        for rec in result.recommendations[:3]:  # Show top 3
            console.print(f"  • {rec}")
        console.print()
        console.print("[dim]Run 'codeframe env doctor' for full diagnostics[/dim]")

    if not result.is_healthy:
        raise typer.Exit(1)


@env_app.command()
def doctor(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project directory to analyze"
    ),
):
    """Comprehensive environment health analysis.

    Provides detailed diagnostics including version compatibility,
    recommendations, and potential conflicts.

    Examples:

        codeframe env doctor

        codeframe env doctor --project ./my-project
    """
    # Determine project path
    if project:
        project_path = Path(project)
        if not project_path.exists():
            console.print(f"[red]Error:[/red] Project path not found: {project}")
            raise typer.Exit(1)
    else:
        project_path = Path.cwd()

    # Run validation
    validator = EnvironmentValidator()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running comprehensive diagnostics...", total=None)
        result = validator.validate_environment(project_path)

    # Display header
    health_pct = int(result.health_score * 100)
    console.print()
    console.print(Panel(
        f"[bold]Environment Health Report[/bold]\n"
        f"Project: {project_path.name}\n"
        f"Type: {result.project_type}\n"
        f"Score: {health_pct}%",
        title="CodeFRAME Doctor",
    ))

    # Tools table
    table = Table(title="Detected Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Version")
    table.add_column("Path", style="dim")

    for name, info in sorted(result.detected_tools.items()):
        if info.status == ToolStatus.AVAILABLE:
            status = "[green]Available[/green]"
        elif info.status == ToolStatus.NOT_FOUND:
            status = "[red]Not Found[/red]"
        elif info.status == ToolStatus.VERSION_INCOMPATIBLE:
            status = "[yellow]Incompatible[/yellow]"
        else:
            status = "[dim]Error[/dim]"

        table.add_row(
            name,
            status,
            info.version or "-",
            info.path or "-",
        )

    console.print()
    console.print(table)

    # Warnings
    if result.warnings:
        console.print()
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warning in result.warnings:
            console.print(f"  [yellow]⚠[/yellow] {warning}")

    # Conflicts
    if result.conflicts:
        console.print()
        console.print("[bold red]Conflicts:[/bold red]")
        for conflict in result.conflicts:
            console.print(f"  [red]✗[/red] {conflict}")

    # Recommendations
    if result.recommendations:
        console.print()
        console.print("[bold]Recommendations:[/bold]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")

    console.print()

    if not result.is_healthy:
        console.print("[bold]To fix issues, run:[/bold]")
        console.print("  codeframe env auto-install --yes")
        console.print()
        raise typer.Exit(1)


@env_app.command("install-missing")
def install_missing(
    tool: str = typer.Argument(..., help="Name of the tool to install"),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
):
    """Install a specific missing tool.

    Attempts to install the specified tool using the appropriate
    package manager (pip, npm, cargo, or system).

    Examples:

        codeframe env install-missing pytest

        codeframe env install-missing eslint --yes
    """
    installer = ToolInstaller()

    # Check if we can install this tool
    if not installer.can_install(tool):
        console.print(f"[red]Error:[/red] Cannot install '{tool}' - no installer available")
        console.print()
        console.print("This tool may need manual installation.")
        console.print(f"Try: [dim]{installer.get_install_command(tool) or f'Install {tool} manually'}[/dim]")
        raise typer.Exit(1)

    # Show install command
    install_cmd = installer.get_install_command(tool)
    console.print(f"[bold]Tool:[/bold] {tool}")
    console.print(f"[bold]Command:[/bold] {install_cmd}")
    console.print()

    # Confirm if needed
    if not yes:
        confirmed = typer.confirm("Proceed with installation?")
        if not confirmed:
            console.print("[yellow]Installation cancelled[/yellow]")
            raise typer.Exit(0)

    # Install
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Installing {tool}...", total=None)
        result = installer.install_tool(tool, confirm=False)

    # Report result
    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
        if result.error_output:
            console.print()
            console.print("[dim]Error output:[/dim]")
            console.print(result.error_output[:500])  # Truncate long errors
        raise typer.Exit(1)


@env_app.command("auto-install")
def auto_install(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project directory"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt"
    ),
):
    """Automatically install all missing required tools.

    Detects missing tools for the project and installs them
    using the appropriate package managers.

    Examples:

        codeframe env auto-install

        codeframe env auto-install --yes

        codeframe env auto-install --project ./my-project --yes
    """
    # Determine project path
    if project:
        project_path = Path(project)
        if not project_path.exists():
            console.print(f"[red]Error:[/red] Project path not found: {project}")
            raise typer.Exit(1)
    else:
        project_path = Path.cwd()

    # Get missing tools
    validator = EnvironmentValidator()
    validation_result = validator.validate_environment(project_path)

    if not validation_result.missing_tools:
        console.print("[green]✓[/green] All required tools are already installed!")
        console.print()
        console.print("[dim]Nothing to install.[/dim]")
        return

    # Show what will be installed
    console.print("[bold]Missing tools to install:[/bold]")
    for tool in validation_result.missing_tools:
        console.print(f"  • {tool}")
    console.print()

    # Confirm if needed
    if not yes:
        confirmed = typer.confirm(f"Install {len(validation_result.missing_tools)} tool(s)?")
        if not confirmed:
            console.print("[yellow]Installation cancelled[/yellow]")
            raise typer.Exit(0)

    # Install each tool
    installer = ToolInstaller()
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Installing tools...", total=len(validation_result.missing_tools))

        for tool in validation_result.missing_tools:
            progress.update(task, description=f"Installing {tool}...")

            if installer.can_install(tool):
                result = installer.install_tool(tool, confirm=False)
                results.append(result)
            else:
                results.append(None)

            progress.advance(task)

    console.print()

    # Report results
    success_count = sum(1 for r in results if r and r.success)
    fail_count = len(results) - success_count

    console.print("[bold]Results:[/bold]")
    for i, tool in enumerate(validation_result.missing_tools):
        result = results[i]
        if result is None:
            console.print(f"  [yellow]⚠[/yellow] {tool}: No installer available")
        elif result.success:
            console.print(f"  [green]✓[/green] {tool}: Installed")
        else:
            console.print(f"  [red]✗[/red] {tool}: {result.message}")

    console.print()
    console.print(f"[bold]Summary:[/bold] {success_count} installed, {fail_count} failed")

    if fail_count > 0:
        raise typer.Exit(1)
