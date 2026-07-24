"""Shared LLM provider resolution (#768).

Single source of truth for the effective-provider chain used by the CLI,
runtime, and server surfaces:

    CLI flag → CODEFRAME_LLM_PROVIDER → .codeframe/config.yaml ``llm:`` → "anthropic"

and for the provider → required-API-key-env mapping, so pre-flight checks
validate the key that actually matches the resolved provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Providers that need an API key up front. Local / OpenAI-compatible
# providers (ollama, vllm, compatible) and mock need none.
REQUIRED_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class LLMSettings:
    """Resolved LLM provider settings."""

    provider_type: str
    model: Optional[str] = None
    base_url: Optional[str] = None

    @property
    def required_key_env(self) -> Optional[str]:
        """Env var holding the API key this provider requires, or None."""
        return REQUIRED_KEY_ENV.get(self.provider_type)

    def provider_kwargs(self) -> dict:
        """Constructor overrides for ``get_provider`` (only set values)."""
        kwargs: dict = {}
        if self.model:
            kwargs["model"] = self.model
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs


def resolve_llm_settings(
    repo_path: Optional[Path] = None,
    provider_flag: Optional[str] = None,
    model_flag: Optional[str] = None,
) -> LLMSettings:
    """Resolve effective provider/model/base_url.

    Provider: flag → CODEFRAME_LLM_PROVIDER → config → "anthropic".
    Model: flag → CODEFRAME_LLM_MODEL → config.
    Base URL: config → OPENAI_BASE_URL (env tier applies to
    OpenAI-compatible providers only, #780).

    Args:
        repo_path: Workspace repo path for ``.codeframe/config.yaml``
            lookup; None skips the config tier.
        provider_flag: CLI ``--llm-provider`` value.
        model_flag: CLI ``--llm-model`` value.
    """
    from codeframe.core.config import load_environment_config

    llm_cfg = None
    if repo_path is not None:
        env_cfg = load_environment_config(repo_path)
        llm_cfg = env_cfg.llm if (env_cfg and env_cfg.llm) else None

    provider_type = (
        provider_flag
        or os.getenv("CODEFRAME_LLM_PROVIDER")
        or (llm_cfg.provider if llm_cfg else None)
        or "anthropic"
    )
    model = (
        model_flag
        or os.getenv("CODEFRAME_LLM_MODEL")
        or (llm_cfg.model if llm_cfg else None)
    )
    # Explicit config base_url applies to any provider (anthropic proxies
    # included, #780); the OPENAI_BASE_URL env fallback is OpenAI-compatible
    # only, so an ambient value can't redirect Anthropic traffic.
    from codeframe.adapters.llm import OPENAI_COMPATIBLE_PROVIDERS

    base_url = llm_cfg.base_url if llm_cfg else None
    if not base_url and provider_type in OPENAI_COMPATIBLE_PROVIDERS:
        base_url = os.getenv("OPENAI_BASE_URL")
    return LLMSettings(provider_type=provider_type, model=model, base_url=base_url)


def create_provider(settings: LLMSettings):
    """Build the LLM provider for resolved settings."""
    from codeframe.adapters.llm import get_provider

    return get_provider(settings.provider_type, **settings.provider_kwargs())
