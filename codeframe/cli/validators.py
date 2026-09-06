"""CLI validation helpers for pre-command checks."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import typer
from codeframe.core.env_provenance import load_env_files
from rich.console import Console

if TYPE_CHECKING:  # pragma: no cover - import-time cost the CLI does not pay
    from pathlib import Path

    from codeframe.core.llm_resolution import LLMSettings

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
    load_env_files()

    key = os.getenv("ANTHROPIC_API_KEY")
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
        return key

    console.print(
        "[red]Error:[/red] ANTHROPIC_API_KEY is not set. "
        "Set it in your environment or add it to a .env file."
    )
    raise typer.Exit(1)


def require_openai_api_key() -> str:
    """Ensure OPENAI_API_KEY is available, loading from .env if needed.

    Checks os.environ first. If not found, attempts to load from .env files
    (~/.env as base, then cwd/.env with override). If found after loading,
    sets in os.environ so subprocesses inherit it.

    Returns:
        The API key string.

    Raises:
        typer.Exit: If the key cannot be found anywhere.
    """
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key

    load_env_files()

    key = os.getenv("OPENAI_API_KEY")
    if key:
        os.environ["OPENAI_API_KEY"] = key
        return key

    console.print(
        "[red]Error:[/red] OPENAI_API_KEY is not set. "
        "Set it in your environment or add it to a .env file."
    )
    raise typer.Exit(1)


def require_api_key_for_provider(provider_type: str) -> str | None:
    """Validate the API key matching the resolved LLM provider (#768).

    anthropic → ANTHROPIC_API_KEY, openai → OPENAI_API_KEY. Local /
    OpenAI-compatible providers (ollama, vllm, compatible) and mock
    require no key.

    Returns:
        The API key string, or None when the provider needs no key.

    Raises:
        typer.Exit: If a required key cannot be found anywhere.
    """
    if provider_type == "anthropic":
        return require_anthropic_api_key()
    if provider_type == "openai":
        return require_openai_api_key()
    return None


def require_e2b_api_key() -> str:
    """Ensure E2B_API_KEY is available, loading from .env if needed.

    Checks os.environ first. If not found, attempts to load from .env files
    (~/.env as base, then cwd/.env with override). If found after loading,
    sets in os.environ so subprocesses inherit it.

    Returns:
        The API key string.

    Raises:
        typer.Exit: If the key cannot be found anywhere.
    """
    key = os.getenv("E2B_API_KEY")
    if key:
        return key

    load_env_files()

    key = os.getenv("E2B_API_KEY")
    if key:
        os.environ["E2B_API_KEY"] = key
        return key

    console.print(
        "[red]Error:[/red] E2B_API_KEY is not set. "
        "Set it in your environment or add it to a .env file. "
        "Get your key at https://e2b.dev"
    )
    raise typer.Exit(1)


def require_codex_auth() -> None:
    """Ensure the codex CLI can reach a model, by either route (#1010).

    Not ``require_openai_api_key``: ``codex login`` stores ChatGPT-plan
    credentials in ``auth.json`` and writes ``"OPENAI_API_KEY": null`` in that
    same file, so gating on the environment variable refused the common case —
    ``--engine codex`` was unusable for anyone who had simply logged in, even
    though the adapter and the binary both worked.

    Raises:
        typer.Exit: If codex is authenticated by neither route.
    """
    from codeframe.core.adapters.codex import CodexAdapter

    if CodexAdapter.is_authenticated():
        return

    load_env_files()
    if CodexAdapter.is_authenticated():
        return

    console.print(
        "[red]Error:[/red] codex is not authenticated. "
        "Run [bold]codex login[/bold], or set OPENAI_API_KEY in your "
        "environment or a .env file."
    )
    raise typer.Exit(1)


def require_keys_for_engine(
    repo_path: Path,
    engine: str | None = None,
    provider_flag: str | None = None,
    model_flag: str | None = None,
) -> LLMSettings | None:
    """Validate the credentials the resolved engine/provider needs (#970).

    The single place that answers "can this run reach a model?". It used to be
    copy-pasted across `cf work start`, `cf work batch run` and `cf tasks
    generate`, so any change to key handling landed on two of the three sites.

    Args:
        repo_path: Workspace repo path, for `.codeframe/config.yaml` resolution.
        engine: Engine name, or None for commands that only ever use the
            builtin LLM path (`cf tasks generate`, `cf prd stress-test`).
        provider_flag: `--llm-provider`, if the command has one.
        model_flag: `--llm-model`, if the command has one.

    Returns:
        The resolved LLM settings when a builtin engine's LLM provider is
        involved (the caller usually feeds them straight to `create_provider`),
        or None for an external engine. An external engine still has its own
        credentials checked here — codex and cloud above — it just has no
        provider to resolve.

    Raises:
        typer.Exit: If a required key or login cannot be found.
    """
    from codeframe.core.engine_registry import is_external_engine
    from codeframe.core.llm_resolution import resolve_llm_settings

    if engine == "codex":
        # Not the OpenAI key check: `codex login` is the common way in and sets
        # no env var at all (#1010).
        require_codex_auth()
        return None
    if engine == "cloud":
        require_e2b_api_key()
        return None
    if engine is not None and is_external_engine(engine):
        return None

    # Builtin engines: validate the key matching the resolved provider
    # (flag → env → config → anthropic), #768
    settings = resolve_llm_settings(
        repo_path, provider_flag=provider_flag, model_flag=model_flag
    )
    require_api_key_for_provider(settings.provider_type)
    return settings
