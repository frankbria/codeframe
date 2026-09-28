"""Shared LLM provider resolution (#768).

Single source of truth for the effective-provider chain used by the CLI,
runtime, and server surfaces:

    CLI flag → CODEFRAME_LLM_PROVIDER → .codeframe/config.yaml ``llm:`` → "anthropic"

and for the provider → required-API-key-env mapping, so pre-flight checks
validate the key that actually matches the resolved provider.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codeframe.core.env_provenance import (
    ALLOW_CONFIG_BASE_URL_ENV as _ALLOW_CONFIG_BASE_URL_ENV,
    UntrustedBaseURLError as _UntrustedBaseURLError,
    base_url_opt_in_granted,
    is_loopback_url,
    is_repo_supplied,
)

logger = logging.getLogger(__name__)

# Providers that need an API key up front. Local / OpenAI-compatible
# providers (ollama, vllm, compatible) and mock need none.
REQUIRED_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


# The trust policy lives in env_provenance so the adapters can apply it too
# (llm_resolution imports the adapters, so the reverse would be a cycle).
# Re-exported here because this module is its documented home for callers.
ALLOW_CONFIG_BASE_URL_ENV = _ALLOW_CONFIG_BASE_URL_ENV
UntrustedBaseURLError = _UntrustedBaseURLError
_is_loopback_url = is_loopback_url
_config_base_url_allowed = base_url_opt_in_granted


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
    env_sourced_from_repo = False
    if not base_url:
        # The env tier is trusted because it is the *operator's* environment —
        # but `cf` loads <cwd>/.env with override=True, so a file committed in a
        # cloned repo can set these keys and beat what the operator exported.
        # When it did, the value is repo content and gets the same gate as the
        # config tier (#903).
        #
        # ANTHROPIC_BASE_URL is read here rather than left to the SDK on
        # purpose: anthropic.Anthropic falls back to os.environ["ANTHROPIC_BASE_URL"]
        # whenever base_url is None, so leaving it unset here would let a repo
        # .env redirect the *default* provider entirely behind this gate's back.
        # Resolving it explicitly means the value always passes through the
        # check and is always announced.
        env_var = (
            "OPENAI_BASE_URL"
            if provider_type in OPENAI_COMPATIBLE_PROVIDERS
            else "ANTHROPIC_BASE_URL"
            if provider_type == "anthropic"
            else None
        )
        if env_var:
            base_url = os.getenv(env_var)
            if base_url and is_repo_supplied(env_var):
                env_sourced_from_repo = True

    # A config-sourced base_url is repo-controlled input (#903). #780 closed the
    # env fallback for Anthropic, but a config file committed inside a cloned
    # repo achieves the same redirect. It is not enough to gate only
    # key-bearing providers by name: get_provider hands OPENAI_API_KEY to
    # ollama/vllm/compatible too whenever it is set, so *any* provider can carry
    # the operator's key to the named host.
    untrusted_candidate = config_base_url or (base_url if env_sourced_from_repo else None)
    if untrusted_candidate and not _is_loopback_url(untrusted_candidate):
        if not _config_base_url_allowed():
            source = (
                "its .env (which overrides your environment)"
                if env_sourced_from_repo
                else "its .codeframe/config.yaml"
            )
            raise UntrustedBaseURLError(
                f"{repo_path or 'This workspace'} sets the LLM endpoint to "
                f"{untrusted_candidate!r} via {source}. That is not this "
                "machine, so running would send your API key to that host.\n"
                f"If you trust it, re-run with {ALLOW_CONFIG_BASE_URL_ENV}=1. "
                "Otherwise remove the base_url, or pass a provider explicitly."
            )
        logger.warning(
            "Using non-default LLM endpoint %s supplied by the workspace "
            "(allowed via %s)",
            untrusted_candidate,
            ALLOW_CONFIG_BASE_URL_ENV,
        )
    elif base_url:
        # Loopback, or an endpoint the operator really did set in their own
        # environment: still announce it before the first call, so a redirect is
        # never invisible in the output.
        logger.info("Using LLM endpoint %s (provider=%s)", base_url, provider_type)

    return LLMSettings(provider_type=provider_type, model=model, base_url=base_url)


class MissingApiKeyError(ValueError):
    """The resolved provider needs a key and none was found (#1264)."""


def _is_hosted() -> bool:
    # Mirrors ui.server.is_hosted_mode, which core cannot import.
    return os.getenv("CODEFRAME_DEPLOYMENT_MODE", "").strip().lower() == "hosted"


def resolve_api_key(provider_type: str, user_id: Optional[int] = None) -> Optional[str]:
    """The API key for ``provider_type``: environment first, then the store (#1264).

    ``cf auth setup`` and Settings → API Keys write to the credential store, and
    nothing used to read it — every LLM path checked the environment only.

    ``user_id`` is the server principal; ``None`` is the CLI (machine-wide store).
    Self-hosted, a principal's own store is checked before the machine-wide one:
    the env and the machine-wide store are both the operator's. In hosted mode a
    principal gets its own stored key or nothing — the environment and the
    machine-wide store belong to the operator, and borrowing them bills every
    tenant to the operator's account.
    """
    from codeframe.core.credentials import (
        CredentialManager,
        CredentialProvider,
        CredentialStoreUnreadableError,
    )

    env_var = REQUIRED_KEY_ENV.get(provider_type)
    if env_var is None:
        return None
    provider = next(p for p in CredentialProvider if p.env_var == env_var)
    hosted_tenant = user_id is not None and _is_hosted()

    if not hosted_tenant and os.getenv(env_var):
        return os.environ[env_var]

    scopes = [user_id] if hosted_tenant else list(dict.fromkeys([user_id, None]))
    for scope in scopes:
        try:
            key = CredentialManager(user_id=scope, migrate=False).get_stored_credential(provider)
        except CredentialStoreUnreadableError as exc:
            # A store we cannot decrypt holds no usable key; the missing-key
            # error that follows is the actionable one.
            logger.warning("Ignoring unreadable credential store: %s", exc)
            continue
        if key:
            return key
    return None


def require_api_key(settings: LLMSettings, user_id: Optional[int] = None) -> Optional[str]:
    """``resolve_api_key`` for resolved settings, raising when a needed key is absent.

    Returns None for providers that need no key (local / mock).

    Raises:
        MissingApiKeyError: naming both ways to supply the key.
    """
    env_var = settings.required_key_env
    if env_var is None:
        return None
    key = resolve_api_key(settings.provider_type, user_id)
    if key:
        return key
    if user_id is not None and _is_hosted():
        raise MissingApiKeyError(
            f"No {settings.provider_type} API key is stored for your account. "
            "Add one in Settings → API Keys."
        )
    raise MissingApiKeyError(
        f"No {settings.provider_type} API key found. Set {env_var}, or store one "
        f"with `cf auth setup --provider {settings.provider_type}` "
        "(web UI: Settings → API Keys)."
    )


def create_provider(settings: LLMSettings, user_id: Optional[int] = None):
    """Build the LLM provider for resolved settings.

    The key is resolved here and passed explicitly, so a stored credential is
    used (#1264) and a hosted tenant without one is refused before the adapter
    can fall back to reading the operator's environment itself.
    """
    from codeframe.adapters.llm import get_provider

    kwargs = settings.provider_kwargs()
    key = require_api_key(settings, user_id)
    if key:
        kwargs["api_key"] = key
    return get_provider(settings.provider_type, **kwargs)
