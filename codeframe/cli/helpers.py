"""Shared CLI helper utilities.

This module provides common utilities used across CLI command modules:
- require_auth: Authentication check for API client
- format_date: Safe date string formatting
- console: Shared Rich Console instance

Usage:
    from codeframe.cli.helpers import require_auth, format_date, console
"""

import typer
from rich.console import Console

from codeframe.cli.api_client import APIClient

# Shared console instance for all CLI modules
console = Console()


def require_auth(client: APIClient) -> None:
    """Check if client is authenticated, exit with error if not.

    Args:
        client: APIClient instance to check for authentication

    Raises:
        typer.Exit: If client is not authenticated (exit code 1)
    """
    if not client.token:
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("Please log in: codeframe auth login")
        raise typer.Exit(1)


def format_date(date_str: str | None, length: int = 10) -> str:
    """Safely extract date portion from an ISO datetime string.

    Args:
        date_str: ISO datetime string (e.g., "2024-01-15T10:30:00Z") or None
        length: Number of characters to extract (default 10 for YYYY-MM-DD)

    Returns:
        Truncated date string or empty string if input is falsy or too short

    Examples:
        >>> format_date("2024-01-15T10:30:00Z")
        '2024-01-15'
        >>> format_date(None)
        ''
        >>> format_date("short")
        ''
    """
    if not date_str or len(date_str) < length:
        return ""
    return date_str[:length]
