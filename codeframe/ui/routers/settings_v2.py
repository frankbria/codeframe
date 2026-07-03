"""V2 Settings router — agent settings + API key management + notifications.

Routes:
    GET    /api/v2/settings                       - Load agent settings (defaults if missing)
    PUT    /api/v2/settings                       - Save agent settings (merge into config)
    GET    /api/v2/settings/keys                  - List API key status for all providers
    PUT    /api/v2/settings/keys/{p}              - Store an API key for provider p
    DELETE /api/v2/settings/keys/{p}              - Delete an API key for provider p
    POST   /api/v2/settings/verify-key            - Live-verify a key against its provider
    GET    /api/v2/settings/notifications         - Load outbound webhook config
    PUT    /api/v2/settings/notifications         - Save outbound webhook config
    POST   /api/v2/settings/notifications/test    - Fire a test payload and return HTTP status

Key management is machine-wide (CredentialManager / keyring) and does not
require a workspace. Env vars take precedence at read time. Notifications
config is per-workspace and persisted under .codeframe/notifications_config.json.
"""

import ipaddress
import logging
import os
import socket

from typing import Optional, cast

from anthropic import Anthropic as _AnthropicClient
from anthropic import AuthenticationError as _AnthropicAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from codeframe.auth.api_keys import SCOPE_ADMIN
from codeframe.auth.dependencies import require_scope
from openai import AuthenticationError as _OpenAIAuthError
from openai import OpenAI as _OpenAIClient
from pydantic import BaseModel, Field

from codeframe.core.config import (
    AgentBudgetConfig,
    EnvironmentConfig,
    load_environment_config,
    save_environment_config,
)
from codeframe.core.credentials import (
    CredentialManager,
    CredentialProvider,
    CredentialSource,
    validate_credential_format,
)
from codeframe.core.notifications_config import (
    load_notifications_config,
    save_notifications_config,
)
from codeframe.core.workspace import Workspace
from codeframe.notifications.webhook import (
    WebhookNotificationService,
    format_test_payload,
)
from codeframe.lib.rate_limiter import rate_limit_ai, rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.models import (
    AGENT_TYPES,
    KEY_PROVIDERS,
    AgentSettingsResponse,
    AgentTypeModelConfig,
    KeyProvider,
    KeyStatusResponse,
    StoreKeyRequest,
    UpdateAgentSettingsRequest,
    VerifyKeyRequest,
    VerifyKeyResponse,
)
from codeframe.ui.response_models import ErrorCodes, api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/settings", tags=["settings"])


def get_credential_manager() -> CredentialManager:
    """Dependency: machine-wide CredentialManager.

    Overridden in tests to point at an isolated temp directory.
    """
    return CredentialManager()


def _config_to_response(config: EnvironmentConfig) -> AgentSettingsResponse:
    """Map an EnvironmentConfig to the flat AgentSettings response shape."""
    saved_models = config.agent_type_models or {}
    agent_models = [
        AgentTypeModelConfig(
            agent_type=agent_type,
            default_model=saved_models.get(agent_type, ""),
        )
        for agent_type in AGENT_TYPES
    ]
    # Guard against legacy YAML where agent_budget may have been removed/nulled.
    budget = config.agent_budget or AgentBudgetConfig()
    return AgentSettingsResponse(
        agent_models=agent_models,
        max_turns=budget.max_iterations,
        max_cost_usd=config.max_cost_usd,
    )


@router.get("", response_model=AgentSettingsResponse)
@rate_limit_standard()
async def get_settings(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> AgentSettingsResponse:
    """Load agent settings for the workspace.

    Returns defaults if no .codeframe/config.yaml exists.
    """
    try:
        config = load_environment_config(workspace.repo_path) or EnvironmentConfig()
        return _config_to_response(config)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to load settings", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )


@router.put("", response_model=AgentSettingsResponse)
@rate_limit_standard()
async def update_settings(
    request: Request,
    body: UpdateAgentSettingsRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> AgentSettingsResponse:
    """Save agent settings.

    Merges into existing EnvironmentConfig so unrelated fields
    (package_manager, test_framework, etc.) are preserved.
    """
    try:
        config = load_environment_config(workspace.repo_path) or EnvironmentConfig()
        if config.agent_budget is None:
            config.agent_budget = AgentBudgetConfig()

        config.agent_budget.max_iterations = body.max_turns
        config.max_cost_usd = body.max_cost_usd
        # Skip empty model strings — they're equivalent to "key not present"
        # in _config_to_response, so persisting them just adds yaml noise.
        # AgentType Literal in the model already rejects unknown agent_type values.
        config.agent_type_models = {
            entry.agent_type: entry.default_model
            for entry in body.agent_models
            if entry.default_model
        }

        save_environment_config(workspace.repo_path, config)
        return _config_to_response(config)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to save settings", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )


# ============================================================================
# API Key Management (issue #555)
#
# These endpoints are machine-wide: they do not require a workspace. Keys are
# stored via CredentialManager (platform keyring or encrypted file fallback).
# Plaintext key values are NEVER returned in any response.
# ============================================================================

# Map the public provider name to the internal CredentialProvider enum.
_PROVIDER_MAP: dict[str, CredentialProvider] = {
    "LLM_ANTHROPIC": CredentialProvider.LLM_ANTHROPIC,
    "LLM_OPENAI": CredentialProvider.LLM_OPENAI,
    "GIT_GITHUB": CredentialProvider.GIT_GITHUB,
}


def _resolve_provider(provider: str) -> CredentialProvider:
    """Resolve a provider name from path/body, raising 400 for unknown values."""
    cp = _PROVIDER_MAP.get(provider)
    if cp is None:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                f"Unknown provider: {provider}. Allowed: {', '.join(KEY_PROVIDERS)}",
                ErrorCodes.VALIDATION_ERROR,
            ),
        )
    return cp


def _last_four(value: str | None) -> str | None:
    """Return the last 4 chars of a key, or None if no value.

    For values shorter than 4 chars (which format validation should
    already reject), returns the full value.
    """
    if not value:
        return None
    return value[-4:] if len(value) >= 4 else value


def _build_status(
    provider_key: KeyProvider,
    manager: CredentialManager,
) -> KeyStatusResponse:
    cp = _PROVIDER_MAP[provider_key]
    source = manager.get_credential_source(cp)
    if source == CredentialSource.NOT_FOUND:
        return KeyStatusResponse(
            provider=provider_key, stored=False, source="none", last_four=None
        )

    value = manager.get_credential(cp)
    source_str = "environment" if source == CredentialSource.ENVIRONMENT else "stored"
    return KeyStatusResponse(
        provider=provider_key,
        stored=value is not None,
        source=source_str,
        last_four=_last_four(value),
    )


@router.get("/keys", response_model=list[KeyStatusResponse])
@rate_limit_standard()
async def list_key_status(
    request: Request,
    manager: CredentialManager = Depends(get_credential_manager),
) -> list[KeyStatusResponse]:
    """Return status of each known API key without exposing plaintext."""
    return [_build_status(p, manager) for p in KEY_PROVIDERS]


@router.put(
    "/keys/{provider}",
    response_model=KeyStatusResponse,
    dependencies=[Depends(require_scope(SCOPE_ADMIN))],  # credential storage is admin-only (#717)
)
@rate_limit_standard()
async def store_key(
    provider: str,
    body: StoreKeyRequest,
    request: Request,
    manager: CredentialManager = Depends(get_credential_manager),
) -> KeyStatusResponse:
    """Store an API key for the given provider after validating its format."""
    cp = _resolve_provider(provider)
    if not validate_credential_format(cp, body.value):
        raise HTTPException(
            status_code=400,
            detail=api_error(
                f"Invalid {provider} key format",
                ErrorCodes.VALIDATION_ERROR,
            ),
        )
    try:
        manager.set_credential(cp, body.value)
    except Exception as e:
        logger.error(f"Failed to store credential: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to store credential", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )
    # _resolve_provider validated `provider` against KEY_PROVIDERS, so the
    # cast is safe — clearer than a type: ignore.
    return _build_status(cast(KeyProvider, provider), manager)


@router.delete(
    "/keys/{provider}",
    status_code=204,
    dependencies=[Depends(require_scope(SCOPE_ADMIN))],  # credential deletion is admin-only (#717)
)
@rate_limit_standard()
async def delete_key(
    provider: str,
    request: Request,
    manager: CredentialManager = Depends(get_credential_manager),
) -> Response:
    """Delete a stored credential. Idempotent — non-existent keys are a no-op."""
    cp = _resolve_provider(provider)
    try:
        manager.delete_credential(cp)
    except Exception as e:
        # Underlying store can raise on a hard keyring error; treat absence as success.
        msg = str(e).lower()
        if "no such" in msg or "not found" in msg:
            return Response(status_code=204)
        logger.error(f"Failed to delete credential: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to delete credential", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )
    return Response(status_code=204)


# ----------------------------------------------------------------------------
# Live verification helpers
#
# These are module-level so tests can monkeypatch them without touching the
# real network. The Anthropic / OpenAI clients are sync, so we wrap their
# calls in run_in_threadpool to avoid blocking the event loop.
# ----------------------------------------------------------------------------


async def _check_github_token(token: str) -> tuple[bool, str]:
    """Validate a GitHub token via GET https://api.github.com/user.

    Exception messages are NOT echoed back to the client because aiohttp
    errors can include the request URL or headers (which carry the token).
    The detailed error is logged server-side instead.
    """
    import aiohttp

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "codeframe-key-verify",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.github.com/user", headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    login = data.get("login", "")
                    return True, f"Authenticated as {login}" if login else "Valid token"
                if resp.status == 401:
                    return False, "401 Unauthorized: invalid GitHub token"
                return False, f"GitHub API returned status {resp.status}"
    except Exception as e:
        logger.warning(f"GitHub token verification raised: {e}", exc_info=True)
        return False, "GitHub verification failed: network or server error"


def _verify_anthropic_sync(key: str) -> tuple[bool, str]:
    """Verify an Anthropic key by issuing a minimal messages.create() call.

    Uses messages.create rather than models.list because messages is the
    stable, always-present API surface across all supported SDK versions
    (>=0.18). max_tokens=1 keeps the cost trivial. Non-auth exceptions
    are logged but not echoed to the client to avoid leaking provider
    internals.
    """
    try:
        client = _AnthropicClient(api_key=key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, "Anthropic key accepted"
    except _AnthropicAuthError:
        return False, "Anthropic key rejected: authentication failed"
    except Exception as e:
        logger.warning(f"Anthropic verification raised: {e}", exc_info=True)
        return False, "Anthropic verification failed: network or server error"


def _verify_openai_sync(key: str) -> tuple[bool, str]:
    """Verify an OpenAI key via models.list (small, cheap, auth-required)."""
    try:
        client = _OpenAIClient(api_key=key)
        client.models.list()
        return True, "OpenAI key accepted"
    except _OpenAIAuthError:
        return False, "OpenAI key rejected: authentication failed"
    except Exception as e:
        logger.warning(f"OpenAI verification raised: {e}", exc_info=True)
        return False, "OpenAI verification failed: network or server error"


@router.post("/verify-key", response_model=VerifyKeyResponse)
@rate_limit_ai()
async def verify_key(
    body: VerifyKeyRequest,
    request: Request,
    manager: CredentialManager = Depends(get_credential_manager),
) -> VerifyKeyResponse:
    """Live-verify a key against its provider.

    If body.value is None, the stored or env-var key is used. Failed
    verifications return 200 with valid=false; only unexpected errors
    (programmer bugs) raise 5xx.
    """
    cp = _resolve_provider(body.provider)
    key = body.value if body.value else manager.get_credential(cp)
    if not key:
        return VerifyKeyResponse(
            provider=body.provider, valid=False, message="No key provided or stored"
        )

    if cp == CredentialProvider.LLM_ANTHROPIC:
        valid, message = await run_in_threadpool(_verify_anthropic_sync, key)
    elif cp == CredentialProvider.LLM_OPENAI:
        valid, message = await run_in_threadpool(_verify_openai_sync, key)
    elif cp == CredentialProvider.GIT_GITHUB:
        valid, message = await _check_github_token(key)
    else:  # pragma: no cover -- guarded by _resolve_provider
        valid, message = False, "Verification not supported for this provider"

    return VerifyKeyResponse(provider=body.provider, valid=valid, message=message)


# ============================================================================
# Outbound webhook notifications (issue #560)
#
# Per-workspace: stored under .codeframe/notifications_config.json. The URL is
# kept as plaintext for v1 — the workspace DB is already a local file, and the
# legacy BLOCKER_WEBHOOK_URL env var was plaintext too. Encryption-at-rest is
# tracked as future work.
# ============================================================================


class NotificationSettingsResponse(BaseModel):
    webhook_url: Optional[str] = None
    webhook_enabled: bool = False


class UpdateNotificationSettingsRequest(BaseModel):
    webhook_url: Optional[str] = Field(
        default=None,
        description="Outbound webhook URL. Empty/None clears the value.",
    )
    webhook_enabled: bool = False


class TestWebhookResponse(BaseModel):
    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None


@router.get("/notifications", response_model=NotificationSettingsResponse)
@rate_limit_standard()
async def get_notification_settings(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> NotificationSettingsResponse:
    """Load outbound webhook config for this workspace."""
    cfg = load_notifications_config(workspace)
    return NotificationSettingsResponse(
        webhook_url=cfg["webhook_url"],
        webhook_enabled=cfg["webhook_enabled"],
    )


_ALLOWED_WEBHOOK_SCHEMES = frozenset({"http", "https"})


def _allow_private_webhook_hosts() -> bool:
    """Opt-out for the SSRF host check.

    Off by default (block private/internal targets). Self-hosted operators who
    legitimately point webhooks at ``localhost`` or an internal service set
    ``CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1`` — read at request time so it can be
    toggled without a restart.
    """
    return os.getenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _assert_webhook_host_is_public(hostname: str) -> None:
    """Reject webhook hosts that resolve to internal/metadata/private IPs.

    Blocks the SSRF vector where an authenticated user points the webhook at
    ``169.254.169.254`` (cloud IMDS), ``127.0.0.1``, or an RFC1918 address —
    the ``/notifications/test`` endpoint fires the URL immediately and returns
    the HTTP status, a blind-to-semi-blind SSRF primitive. IP literals are
    checked directly; DNS names are resolved and every returned address is
    checked. A host that cannot be resolved is allowed through — it isn't
    reachable right now, and we don't want to block saving a not-yet-live URL.

    Known limitation: resolve-and-check, not a request-time pinned connector,
    so DNS rebinding (public at save, private at fire) is out of scope.
    Upgrade path: pin the resolved IP through a custom aiohttp connector in
    ``send_event``.
    """
    if _allow_private_webhook_hosts():
        return

    try:
        candidates = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            candidates = [
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(
                    hostname, None, proto=socket.IPPROTO_TCP
                )
            ]
        except socket.gaierror:
            return  # unresolvable now → not reachable now; don't block the save

    for ip in candidates:
        # ::ffff:169.254.169.254 — judge by the embedded IPv4 address.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    f"Webhook host resolves to a private/internal address "
                    f"({ip}); refusing to avoid SSRF. Set "
                    f"CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1 to allow internal targets.",
                    ErrorCodes.VALIDATION_ERROR,
                ),
            )


def _validate_webhook_url(url: Optional[str]) -> Optional[str]:
    """Normalize and validate a user-supplied webhook URL.

    Returns the trimmed URL on success, or ``None`` if empty. Raises
    ``HTTPException(400)`` for non-``http(s)`` schemes — without this guard,
    a user could enter ``file:///...`` or ``ftp://...`` and aiohttp would
    happily attempt the request (SSRF on local resources) — and for hosts that
    resolve to private/internal/metadata IPs (see ``_assert_webhook_host_is_public``).
    """
    from urllib.parse import urlparse

    trimmed = (url or "").strip()
    if not trimmed:
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme.lower() not in _ALLOWED_WEBHOOK_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                f"Webhook URL must use http or https, got: {parsed.scheme!r}",
                ErrorCodes.VALIDATION_ERROR,
            ),
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "Webhook URL must include a host",
                ErrorCodes.VALIDATION_ERROR,
            ),
        )
    if parsed.hostname:
        _assert_webhook_host_is_public(parsed.hostname)
    return trimmed


@router.put("/notifications", response_model=NotificationSettingsResponse)
@rate_limit_standard()
async def update_notification_settings(
    request: Request,
    body: UpdateNotificationSettingsRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> NotificationSettingsResponse:
    """Save outbound webhook config for this workspace.

    An empty / whitespace-only URL is normalized to ``None``. The enabled
    flag is preserved as-is so the user can toggle delivery without losing
    the saved URL. The URL is validated for ``http(s)`` scheme to avoid
    ``file://`` / ``ftp://`` SSRF on local resources.
    """
    # Off the event loop: _validate_webhook_url may do a blocking DNS lookup.
    url = await run_in_threadpool(_validate_webhook_url, body.webhook_url)
    try:
        save_notifications_config(
            workspace,
            {"webhook_url": url, "webhook_enabled": body.webhook_enabled},
        )
    except OSError as e:
        logger.error("Failed to save notifications config: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to save notifications config",
                ErrorCodes.EXECUTION_FAILED,
                str(e),
            ),
        )
    return NotificationSettingsResponse(
        webhook_url=url, webhook_enabled=body.webhook_enabled
    )


@router.post("/notifications/test", response_model=TestWebhookResponse)
@rate_limit_standard()
async def test_notification_webhook(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> TestWebhookResponse:
    """Fire a test payload against the configured webhook URL.

    Returns the HTTP status code on success, or an error message on failure.
    Returns 400 if no URL is configured or if the stored URL fails the same
    safety checks the PUT endpoint enforces — the [Test] button should be
    disabled in that case, but we guard server-side too.
    """
    try:
        cfg = load_notifications_config(workspace)
    except Exception as e:
        logger.error("Failed to load notifications config: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to load notifications config",
                ErrorCodes.EXECUTION_FAILED,
                str(e),
            ),
        )

    url = (cfg["webhook_url"] or "").strip()
    if not url:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "No webhook URL configured", ErrorCodes.VALIDATION_ERROR
            ),
        )
    # Re-validate at send time — defence-in-depth for hand-edited config files.
    # We discard the return value: ``_validate_webhook_url`` raises
    # ``HTTPException(400)`` on a bad scheme/host, which is the side-effect
    # we want here. The trimmed URL it returns is already in ``url``.
    # Off the event loop — it may do a blocking DNS lookup.
    await run_in_threadpool(_validate_webhook_url, url)

    svc = WebhookNotificationService(webhook_url=url, timeout=5)
    result = await svc.send_event(format_test_payload())
    return TestWebhookResponse(
        ok=result.ok, status_code=result.status_code, error=result.error
    )
