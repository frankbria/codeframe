"""`cf config` — machine-wide CodeFRAME configuration (issue #616)."""

import os

import typer
from rich.console import Console

from codeframe.core import telemetry as telemetry_core

config_app = typer.Typer(
    name="config",
    help="Manage machine-wide CodeFRAME configuration",
    no_args_is_help=True,
)

console = Console()


@config_app.command()
def telemetry(
    action: str = typer.Argument(..., help="on | off | status"),
) -> None:
    """Enable, disable, or inspect anonymous telemetry (default: off).

    See PRIVACY.md for exactly what is collected. Env overrides:
    CODEFRAME_TELEMETRY=on|off always wins; DO_NOT_TRACK disables.
    """
    action = action.strip().lower()
    if action not in ("on", "off", "status"):
        console.print(f"[red]Error:[/red] unknown action '{action}' (expected on|off|status)")
        raise typer.Exit(1)

    if action == "status":
        _print_status()
        return

    config = telemetry_core.load_config()
    config.enabled = action == "on"
    config.prompted = True
    telemetry_core.save_config(config)

    if config.enabled:
        console.print(
            "[green]Telemetry enabled.[/green] Anonymous usage events and crash "
            "reports will be sent — see PRIVACY.md for exactly what is collected."
        )
        console.print(f"Anonymous id: [dim]{config.anonymous_id}[/dim]")
    else:
        console.print("[yellow]Telemetry disabled.[/yellow] Nothing will be sent.")


def _print_status() -> None:
    # Resolve the effective state from this single config read (rather than
    # is_enabled(), which re-reads) so the displayed state and anonymous id
    # can't disagree if the file changes between two loads.
    config = telemetry_core.load_config()
    override = telemetry_core.env_override()
    dnt_active = os.environ.get("DO_NOT_TRACK", "").strip().lower() not in ("", "0", "false")
    if override is not None:
        effective = override
    elif dnt_active:
        effective = False
    else:
        effective = config.enabled
    state = "[green]enabled[/green]" if effective else "[yellow]disabled[/yellow]"
    console.print(f"Telemetry: {state}")

    if override is not None:
        console.print(
            f"  (overridden by CODEFRAME_TELEMETRY={os.environ['CODEFRAME_TELEMETRY']})"
        )
    elif dnt_active:
        console.print("  (disabled by DO_NOT_TRACK)")

    console.print(f"  Config file: {telemetry_core.config_path()}")
    console.print(f"  Endpoint: {telemetry_core.resolve_endpoint()}")
    if telemetry_core.config_path().exists():
        console.print(f"  Anonymous id: {config.anonymous_id}")
    console.print("  Details: PRIVACY.md  |  Change: cf config telemetry on|off")
