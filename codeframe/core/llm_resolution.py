"""Shared LLM provider resolution (#768).

Single source of truth for the effective-provider chain used by the CLI,
runtime, and server surfaces:

    CLI flag → CODEFRAME_LLM_PROVIDER → .codeframe/config.yaml ``llm:`` → "anthropic"

and for the provider → required-API-key-env mapping, so pre-flight checks
validate the key that actually matches the resolved provider.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Providers that need an API key up front. Local / OpenAI-compatible
# providers (ollama, vllm, compatible) and mock need none.
REQUIRED_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


#: Opt-in for a config-supplied ``base_url`` that points off this machine.
#: Mirrors the other deliberate escape hatches (``CODEFRAME_ALLOW_PRIVATE_WEBHOOKS``,
#: ``CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES``).
ALLOW_CONFIG_BASE_URL_ENV = "CODEFRAME_ALLOW_CONFIG_BASE_URL"

_TRUTHY = {"1", "true", "yes", "on"}


class UntrustedBaseURLError(RuntimeError):
    """A repo-supplied ``base_url`` would send API traffic off this machine.

    ``.codeframe/config.yaml`` lives *inside the repository*, so cloning an
    untrusted repo and running any LLM command would otherwise ship the
    operator's long-lived API key to whatever host that file names — with no
    validation, no warning, and no visible difference in output (issue #903).
    """


def _is_loopback_url(url: str) -> bool:
    """Whether ``url``'s host is this machine.

    A loopback endpoint cannot exfiltrate anything to a remote attacker, and it
    is the documented local-model setup (ollama/vLLM/LM Studio), so it stays
    friction-free. Anything else is a redirect that must be chosen deliberately.
    """
    try:
        host = (urlparse(url).hostname or "").strip()
    except Exception:
        # Deliberately broad: this predicate is fail-closed, and a malformed
        # config can set base_url to any YAML type. urlparse raises different
        # exceptions per type (AttributeError for a list, TypeError for an int),
        # and getting that list wrong turns a clean refusal into an unhandled
        # crash in the security gate. "Not parseable" is simply "not this
        # machine".
        return False
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a name we cannot resolve statically is not "this machine"


def _config_base_url_allowed() -> bool:
    return os.getenv(ALLOW_CONFIG_BASE_URL_ENV, "").strip().lower() in _TRUTHY


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

    config_base_url = llm_cfg.base_url if llm_cfg else None
    base_url = config_base_url
    if not base_url and provider_type in OPENAI_COMPATIBLE_PROVIDERS:
        base_url = os.getenv("OPENAI_BASE_URL")

    # A config-sourced base_url is repo-controlled input (#903). #780 closed the
    # env fallback for Anthropic, but a config file committed inside a cloned
    # repo achieves the same redirect. It is not enough to gate only
    # key-bearing providers by name: get_provider hands OPENAI_API_KEY to
    # ollama/vllm/compatible too whenever it is set, so *any* provider can carry
    # the operator's key to the named host.
    if config_base_url and not _is_loopback_url(config_base_url):
        if not _config_base_url_allowed():
            raise UntrustedBaseURLError(
                f"{repo_path or 'This workspace'}/.codeframe/config.yaml sets "
                f"llm.base_url to {config_base_url!r}, which is not this "
                "machine. Running would send your API key to that host.\n"
                "If you trust it, re-run with "
                f"{ALLOW_CONFIG_BASE_URL_ENV}=1. Otherwise remove the "
                "base_url from the config, or pass a provider explicitly."
            )
        logger.warning(
            "Using non-default LLM endpoint %s from %s (allowed via %s)",
            config_base_url,
            "workspace config",
            ALLOW_CONFIG_BASE_URL_ENV,
        )
    elif base_url:
        # Loopback, or the OPENAI_BASE_URL env tier: still announce the
        # effective endpoint before the first call, so a redirect is never
        # invisible in the output.
        logger.info("Using LLM endpoint %s (provider=%s)", base_url, provider_type)

    return LLMSettings(provider_type=provider_type, model=model, base_url=base_url)


def create_provider(settings: LLMSettings):
    """Build the LLM provider for resolved settings."""
    from codeframe.adapters.llm import get_provider

    return get_provider(settings.provider_type, **settings.provider_kwargs())
