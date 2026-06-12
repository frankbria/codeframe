"""Telemetry-aware CLI entry wrapper (issue #616).

Wraps the Typer app to provide: the one-time opt-in prompt, command timing,
success/failure capture, and crash reporting. Telemetry can never change the
CLI's behavior — every telemetry step is best-effort and silent on failure,
and the wrapped app's exit code / exception always propagates unchanged.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

import click
import typer
import typer.main
from rich.console import Console

from codeframe.core import telemetry

logger = logging.getLogger(__name__)

console = Console()

# Bounded wait for the fire-and-forget send at process exit. Worst case this
# adds 1s to an opted-in command; opted-out commands are unaffected.
_SEND_JOIN_SECONDS = 1.0


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def resolve_command_name(cli_app: typer.Typer, args: list[str]) -> Optional[str]:
    """Map argv tokens to a registered command path ("work batch run").

    Only names that exist in the command tree are ever returned — arbitrary
    user tokens (file paths, task ids, typos) can never leak into telemetry.
    Returns None when no command token is present (bare ``cf`` / ``--help``),
    and "unknown" when the first token matches nothing.
    """
    group = typer.main.get_command(cli_app)
    path: list[str] = []
    for token in args:
        if token.startswith("-"):
            continue
        if not isinstance(group, click.Group):
            break
        command = group.commands.get(token)
        if command is None:
            break
        path.append(token)
        group = command
    if path:
        return " ".join(path)
    has_positional = any(not t.startswith("-") for t in args)
    return "unknown" if has_positional else None


def maybe_prompt_first_run(args: list[str]) -> None:
    """One-time opt-in prompt (default No). Skipped when non-interactive, when
    an env override is active, when already prompted, and during ``cf config``."""
    try:
        if not args or args[0].startswith("-") or args[0] == "config":
            return
        if telemetry.env_override() is not None:
            return
        if os.environ.get("DO_NOT_TRACK", "").strip().lower() not in ("", "0", "false"):
            return
        if not _is_interactive():
            return
        config = telemetry.load_config()
        if config.prompted:
            return
        console.print(
            "\n[bold]Help improve CodeFRAME?[/bold] Share anonymous usage events and "
            "crash reports (command name, duration, version, OS — never code, "
            "prompts, or file paths). Details: PRIVACY.md. "
            "Change anytime: [cyan]cf config telemetry on|off[/cyan]"
        )
        answer = typer.confirm("Enable anonymous telemetry?", default=False)
        config.enabled = answer
        config.prompted = True
        telemetry.save_config(config)
        console.print()
    except (click.Abort, KeyboardInterrupt):
        raise
    except Exception:
        logger.debug("Telemetry first-run prompt failed", exc_info=True)


def _coerce_exit_code(code: object) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1


def _dispatch(
    command: Optional[str],
    start: float,
    exit_code: int,
    crash: Optional[BaseException] = None,
) -> None:
    """Build and send events for this invocation. Never raises."""
    try:
        if command is None or not telemetry.is_enabled():
            return
        config = telemetry.ensure_config()
        duration_ms = int((time.monotonic() - start) * 1000)
        events = [
            telemetry.build_command_event(
                command=command,
                duration_ms=duration_ms,
                exit_code=exit_code,
                anonymous_id=config.anonymous_id,
            )
        ]
        if crash is not None:
            events.append(telemetry.build_crash_event(crash, config.anonymous_id))
        thread = telemetry.send_events_background(events, telemetry.resolve_endpoint())
        thread.join(_SEND_JOIN_SECONDS)
    except Exception:
        logger.debug("Telemetry dispatch failed", exc_info=True)


def run(cli_app: typer.Typer) -> None:
    """Run the Typer app with telemetry instrumentation around it."""
    args = sys.argv[1:]
    maybe_prompt_first_run(args)
    command = resolve_command_name(cli_app, args)
    start = time.monotonic()
    try:
        cli_app(prog_name="codeframe")
    except SystemExit as e:
        _dispatch(command, start, _coerce_exit_code(e.code))
        raise
    except (KeyboardInterrupt, click.Abort):
        _dispatch(command, start, 130)
        raise
    except BaseException as e:
        # Unhandled crash: record it, then let it propagate so Typer's
        # excepthook still prints the traceback and the exit code is unchanged.
        _dispatch(command, start, 1, crash=e)
        raise
    else:
        # Click standalone mode normally exits via SystemExit; cover the
        # non-standalone path for completeness.
        _dispatch(command, start, 0)
