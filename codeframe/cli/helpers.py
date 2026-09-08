"""Shared CLI helper utilities.

Usage:
    from codeframe.cli.helpers import console, print_error
"""

from rich.console import Console
from rich.markup import escape

# Shared console instance for all CLI modules
console = Console()


def print_error(exc: object, prefix: str = "Error:", suffix: str = "") -> None:
    """Render an error through Rich, treating the message as data.

    Exception text is never markup, and it routinely quotes user input — a task
    title, a filename, a provider name. Rendering it raw made the `except`
    handler itself raise ``MarkupError``, so a caught error became an uncaught
    crash (#1054). Escaping here means the 91 call sites cannot get it wrong.

    ``prefix``/``suffix`` are rendered as markup, so they must be static,
    trusted strings — never user input, an exception message, or anything
    derived from either. They exist to reproduce a handful of bespoke messages
    the migration would otherwise have reworded; only ``exc`` is escaped.
    """
    console.print(f"[red]{prefix}[/red] {escape(str(exc))}{suffix}")
