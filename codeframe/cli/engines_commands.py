"""CLI engine management commands.

Usage:
    codeframe engines list           # Show available engines
    codeframe engines check <name>   # Check engine requirements
"""

import typer
from rich.console import Console
from rich.table import Table

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
