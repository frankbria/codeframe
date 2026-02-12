"""CLI validation helpers for pre-command checks."""

import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

console = Console()


def require_anthropic_api_key() -> str:
    """Ensure ANTHROPIC_API_KEY is available, loading from .env if needed.

    Checks os.environ first. If not found, attempts to load from .env files
    (~/.env as base, then cwd/.env with override). If found after loading,
    sets in os.environ so subprocesses inherit it.

    Returns:
        The API key string.

    Raises:
        typer.Exit: If the key cannot be found anywhere.
    """
    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        return key

    # Try loading from .env files (same priority as app.py)
    cwd_env = Path.cwd() / ".env"
    home_env = Path.home() / ".env"

    if home_env.exists():
        load_dotenv(home_env)
    if cwd_env.exists():
        load_dotenv(cwd_env, override=True)

    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
        return key

    console.print(
        "[red]Error:[/red] ANTHROPIC_API_KEY is not set. "
        "Set it in your environment or add it to a .env file."
    )
    raise typer.Exit(1)
