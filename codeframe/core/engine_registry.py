"""Engine registry for adapter lookup and resolution."""

from __future__ import annotations

import os
from typing import Any

from codeframe.core.adapters.agent_adapter import AgentAdapter


# All valid engine names
VALID_ENGINES = frozenset({
    "react",
    "plan",
    "claude-code",
    "codex",
    "opencode",
    "kilocode",
    "built-in",  # Alias for "react"
})

# External engines that use subprocess adapters (no LLM provider needed)
EXTERNAL_ENGINES = frozenset({
    "claude-code",
    "codex",
    "opencode",
    "kilocode",
})

# Builtin engines that need workspace + LLM provider
BUILTIN_ENGINES = frozenset({
    "react",
    "plan",
    "built-in",
})


def resolve_engine(cli_engine: str | None = None) -> str:
    """Resolve which engine to use.

    Priority:
    1. CLI --engine flag (explicit wins)
    2. CODEFRAME_ENGINE environment variable
    3. Default: "react"

    Args:
        cli_engine: Engine name from CLI flag, or None.

    Returns:
        Resolved engine name.

    Raises:
        ValueError: If resolved engine is not valid.
    """
    engine = cli_engine or os.environ.get("CODEFRAME_ENGINE") or "react"

    # Normalize alias
    if engine == "built-in":
        engine = "react"

    if engine not in VALID_ENGINES:
        raise ValueError(
            f"Invalid engine '{engine}'. "
            f"Must be one of: {', '.join(sorted(VALID_ENGINES))}"
        )

    return engine


def is_external_engine(engine: str) -> bool:
    """Check if an engine uses an external subprocess adapter."""
    return engine in EXTERNAL_ENGINES


def get_external_adapter(engine: str, **kwargs: Any) -> AgentAdapter:
    """Get an adapter instance for an external engine.

    Args:
        engine: Engine name (must be in EXTERNAL_ENGINES).
        **kwargs: Adapter-specific keyword arguments.

    Returns:
        AgentAdapter instance.

    Raises:
        ValueError: If engine is not an external engine.
        EnvironmentError: If the required binary is not installed.
    """
    if engine == "claude-code":
        from codeframe.core.adapters.claude_code import ClaudeCodeAdapter

        return ClaudeCodeAdapter(**kwargs)
    elif engine == "codex":
        from codeframe.core.adapters.codex import CodexAdapter

        return CodexAdapter(**kwargs)
    elif engine == "opencode":
        from codeframe.core.adapters.opencode import OpenCodeAdapter

        return OpenCodeAdapter()
    elif engine == "kilocode":
        from codeframe.core.adapters.kilocode import KilocodeAdapter

        return KilocodeAdapter(**kwargs)
    else:
        raise ValueError(
            f"Unknown external engine '{engine}'. "
            f"Valid external engines: {', '.join(sorted(EXTERNAL_ENGINES))}"
        )


def get_builtin_adapter(
    engine: str,
    workspace: Any,
    llm_provider: Any,
    **kwargs: Any,
) -> AgentAdapter:
    """Get an adapter instance for a builtin engine.

    Args:
        engine: Engine name (must be in BUILTIN_ENGINES).
        workspace: Workspace instance.
        llm_provider: LLM provider instance.
        **kwargs: Additional keyword arguments passed to the adapter.

    Returns:
        AgentAdapter instance.

    Raises:
        ValueError: If engine is not a builtin engine.
    """
    resolved = "react" if engine == "built-in" else engine

    if resolved == "react":
        from codeframe.core.adapters.builtin import BuiltinReactAdapter

        return BuiltinReactAdapter(workspace, llm_provider, **kwargs)
    elif resolved == "plan":
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter

        return BuiltinPlanAdapter(workspace, llm_provider, **kwargs)
    else:
        raise ValueError(
            f"Unknown builtin engine '{engine}'. "
            f"Valid builtin engines: {', '.join(sorted(BUILTIN_ENGINES))}"
        )


def check_requirements(engine: str) -> dict[str, bool]:
    """Check if an engine's requirements are met.

    Args:
        engine: Engine name to check.

    Returns:
        Dict of requirement-name → bool (True if satisfied).

    Raises:
        ValueError: If engine is not valid.
    """
    if engine not in VALID_ENGINES:
        raise ValueError(
            f"Invalid engine '{engine}'. "
            f"Must be one of: {', '.join(sorted(VALID_ENGINES))}"
        )

    # Resolve alias
    resolved = "react" if engine == "built-in" else engine

    # Get the adapter class and check for a requirements() classmethod
    adapter_cls = _get_adapter_class(resolved)
    if adapter_cls is None:
        return {}

    req_method = getattr(adapter_cls, "requirements", None)
    if req_method is None or not callable(req_method):
        return {}

    reqs = req_method()
    result: dict[str, bool] = {}
    for key in reqs:
        # Check environment variables for builtin engines
        result[key] = bool(os.getenv(key))

    # External adapters may also have a check_ready() classmethod
    check_ready = getattr(adapter_cls, "check_ready", None)
    if check_ready and callable(check_ready):
        result.update(check_ready())

    return result


def _get_adapter_class(engine: str) -> type | None:
    """Get the adapter class for an engine (without instantiating)."""
    if engine == "react":
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        return BuiltinReactAdapter
    elif engine == "plan":
        from codeframe.core.adapters.builtin import BuiltinPlanAdapter
        return BuiltinPlanAdapter
    elif engine == "claude-code":
        from codeframe.core.adapters.claude_code import ClaudeCodeAdapter
        return ClaudeCodeAdapter
    elif engine == "codex":
        from codeframe.core.adapters.codex import CodexAdapter
        return CodexAdapter
    elif engine == "opencode":
        from codeframe.core.adapters.opencode import OpenCodeAdapter
        return OpenCodeAdapter
    elif engine == "kilocode":
        from codeframe.core.adapters.kilocode import KilocodeAdapter
        return KilocodeAdapter
    return None


def get_adapter(
    engine: str,
    workspace: Any = None,
    llm_provider: Any = None,
    **kwargs: Any,
) -> AgentAdapter:
    """Get an adapter for any engine type.

    Unified factory that handles both external and builtin engines.

    Args:
        engine: Engine name.
        workspace: Workspace (required for builtin engines).
        llm_provider: LLM provider (required for builtin engines).
        **kwargs: Additional adapter-specific arguments.

    Returns:
        AgentAdapter instance.

    Raises:
        ValueError: If engine is invalid or builtin engine missing required args.
        EnvironmentError: If external engine binary is not installed.
    """
    if is_external_engine(engine):
        return get_external_adapter(engine, **kwargs)
    else:
        if workspace is None or llm_provider is None:
            raise ValueError(
                f"Builtin engine '{engine}' requires workspace and llm_provider"
            )
        return get_builtin_adapter(engine, workspace, llm_provider, **kwargs)
