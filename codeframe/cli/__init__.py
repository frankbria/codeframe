"""Command-line interface for CodeFRAME.

The Typer entry point lives in :mod:`codeframe.cli.app` and is exposed as the
``codeframe`` / ``cf`` console scripts (see ``pyproject.toml``):

    codeframe = "codeframe.cli.app:app"
    cf        = "codeframe.cli.app:app"

This package ``__init__`` is intentionally empty so that importing
``codeframe.cli.app`` does not drag in unrelated command modules as a side
effect.
"""
