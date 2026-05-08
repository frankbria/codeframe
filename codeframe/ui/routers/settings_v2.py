"""V2 Settings router — agent settings + API key management.

Routes:
    GET    /api/v2/settings              - Load agent settings (defaults if missing)
    PUT    /api/v2/settings              - Save agent settings (merge into config)
    GET    /api/v2/settings/keys         - List API key status for all providers
    PUT    /api/v2/settings/keys/{p}     - Store an API key for provider p
    DELETE /api/v2/settings/keys/{p}     - Delete an API key for provider p
    POST   /api/v2/settings/verify-key   - Live-verify a key against its provider

Key management is machine-wide (CredentialManager / keyring) and does not
require a workspace. Env vars take precedence at read time.
"""

import logging

from anthropic import Anthropic as _AnthropicClient
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from openai import OpenAI as _OpenAIClient

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
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
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
    """Return the last 4 chars of a key, or None if no value."""
    if not value:
        return None
    return value[-4:]


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


@router.put("/keys/{provider}", response_model=KeyStatusResponse)
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
    # Cast str -> KeyProvider literal is safe because _resolve_provider validated it.
    return _build_status(provider, manager)  # type: ignore[arg-type]


@router.delete("/keys/{provider}", status_code=204)
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
    """Validate a GitHub token via GET https://api.github.com/user."""
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
        return False, f"GitHub verification failed: {e}"


def _verify_anthropic_sync(key: str) -> tuple[bool, str]:
    try:
        client = _AnthropicClient(api_key=key)
        client.models.list()
        return True, "Anthropic key accepted"
    except Exception as e:
        return False, f"Anthropic verification failed: {e}"


def _verify_openai_sync(key: str) -> tuple[bool, str]:
    try:
        client = _OpenAIClient(api_key=key)
        client.models.list()
        return True, "OpenAI key accepted"
    except Exception as e:
        return False, f"OpenAI verification failed: {e}"


@router.post("/verify-key", response_model=VerifyKeyResponse)
@rate_limit_standard()
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
