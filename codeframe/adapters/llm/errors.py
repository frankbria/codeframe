"""Actionable messages for provider failures (#1110).

The two most likely first-run failures — a bad key and a retired model — used to
reach the user as a Python repr of the provider's JSON body:

    Error: Error code: 401 - {'type': 'error', 'error': {'type':
    'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}

That is the first thing a new user sees, at the first AI-backed command in the
README quickstart, and it says nothing about what to do.

The message is built here rather than in each CLI command's error handler, so it
reaches *every* LLM-backed surface — `prd generate`, `tasks generate`,
`work start --execute`, `prd stress-test`, the server — through the ordinary
`except ... as e: print(e)` that each already has. One place, whole surface.
"""

from __future__ import annotations

import os
from typing import Optional

from codeframe.adapters.llm.base import (
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMModelNotFoundError,
    LLMOverloadedError,
    LLMRateLimitError,
    Purpose,
)

VERBOSE_ENV = "CODEFRAME_VERBOSE"
# Same truthy set the rest of the repo uses (env_provenance, hook_trust,
# notifications_config): CODEFRAME_VERBOSE=0/false/no/off means off.
_TRUTHY = {"1", "true", "yes", "on"}


def _verbose() -> bool:
    return os.getenv(VERBOSE_ENV, "").strip().lower() in _TRUTHY

# provider -> the env var its API key is read from. Mirrors
# llm_resolution.REQUIRED_KEY_ENV, which cannot be imported here (core imports
# the adapters, so the reverse direction is a cycle).
_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
# OpenAI-compatible providers that run locally and need no credentials — they
# are constructed with api_key="not-required", so key advice would misdirect.
_LOCAL_PROVIDERS = frozenset({"ollama", "vllm", "compatible"})


# Both SDKs name their exception classes the same way, so the type is a reliable
# signal even when the status attribute is missing — which happens with a
# partially-constructed exception, and in tests that pass a stub response.
_TYPE_TO_STATUS = {
    "AuthenticationError": 401,
    "PermissionDeniedError": 403,
    "NotFoundError": 404,
    "RateLimitError": 429,
    "InternalServerError": 500,
    "APIConnectionError": None,  # genuinely has no status
    "APITimeoutError": None,
}


def _status_of(exc: Exception) -> Optional[int]:
    """HTTP status from an SDK exception, without importing either SDK."""
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    # Fall back to the exception's own type name.
    for klass in type(exc).__mro__:
        if klass.__name__ in _TYPE_TO_STATUS:
            return _TYPE_TO_STATUS[klass.__name__]
    return None


def _model_override_env(purpose: Optional[Purpose]) -> str:
    if purpose is None:
        return "CODEFRAME_EXECUTION_MODEL"
    return f"CODEFRAME_{purpose.value.upper()}_MODEL"


def _with_raw(message: str, exc: Exception) -> str:
    """Append the provider's own payload only when the user asked for it.

    The raw text is never lost regardless: it stays on ``__cause__`` because
    every raise site uses ``raise ... from exc``.
    """
    if _verbose():
        return f"{message}\n\nProvider response:\n{exc}"
    return f"{message}\n\n(set {VERBOSE_ENV}=1 to see the raw provider response)"


def map_provider_error(
    exc: Exception,
    *,
    provider: str,
    model: str,
    purpose: Optional[Purpose] = None,
) -> LLMError:
    """Translate a provider SDK exception into an actionable typed LLMError.

    Returns the error rather than raising it, so call sites read
    ``raise map_provider_error(...) from exc`` and keep the original traceback.
    """
    status = _status_of(exc)
    key_env = _KEY_ENV.get(provider)

    if status == 401 or "authentication" in str(exc).lower():
        lines = [f"The {provider} API rejected the API key."]
        if key_env:
            lines.append(f"  Key read from: ${key_env}")
        elif provider in _LOCAL_PROVIDERS:
            # get_provider hands OPENAI_API_KEY to these too when it is set, and
            # only substitutes "not-required" when it is not. So the advice has
            # to follow what was actually sent, not the provider name — telling
            # someone "needs no API key" while their key is being rejected is
            # worse than the raw dict this whole change replaces.
            if os.getenv("OPENAI_API_KEY"):
                lines.append("  Key read from: $OPENAI_API_KEY")
                lines.append(
                    "  (this provider does not require a key, but one was set, "
                    "so it was sent — unset it if the endpoint expects none)"
                )
            else:
                lines.append(
                    "  This provider runs locally and was sent no API key, so this "
                    "is usually the endpoint rejecting the request — check that "
                    "the server at your base_url is the one you expect."
                )
        lines.append(f"  Provider: {provider} (set CODEFRAME_LLM_PROVIDER or llm.provider in .codeframe/config.yaml)")
        lines.append("")
        lines.append(f"Check that ${key_env} is set to a current key, then re-run." if key_env
                     else "Check the provider credentials, then re-run.")
        lines.append("`cf env check` verifies your setup.")
        return LLMAuthError(_with_raw("\n".join(lines), exc))

    if status == 404:
        env_var = _model_override_env(purpose)
        lines = [
            f"The {provider} API does not recognise the model {model!r}.",
            "",
            f"  Override it with: ${env_var}",
            "  or set llm.model in .codeframe/config.yaml",
            "",
            "This usually means the model was retired. `cf env check` verifies your setup.",
        ]
        return LLMModelNotFoundError(_with_raw("\n".join(lines), exc))

    if status == 403:
        return LLMAuthError(
            _with_raw(
                f"The {provider} API accepted the credentials but refused this request "
                f"(HTTP 403).\n\n"
                f"The key is valid but lacks access to {model!r} — check the plan or "
                f"permissions on the account"
                + (f" whose key is in ${key_env}." if key_env else ".")
                + "\n\n`cf env check` verifies your setup.",
                exc,
            )
        )

    if status == 429:
        return LLMRateLimitError(
            _with_raw(
                f"The {provider} API rate-limited this request.\n\n"
                "Wait a moment and re-run. If it persists, your account may be at its "
                "usage limit — check the provider's console.",
                exc,
            )
        )

    if status in (500, 502, 503, 529):
        return LLMOverloadedError(
            _with_raw(
                f"The {provider} API is temporarily unavailable (HTTP {status}).\n\n"
                "This is the provider's side, not your configuration. Re-run shortly.",
                exc,
            )
        )

    return LLMConnectionError(
        _with_raw(f"The {provider} API call failed.", exc)
    )
