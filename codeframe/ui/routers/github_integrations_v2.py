"""V2 GitHub integrations router — repository connection via PAT (issue #563).

Routes (prefix ``/api/v2/integrations/github``):
    POST   /connect      - Validate PAT against repo, store PAT, save repo metadata
    DELETE /disconnect   - Clear stored PAT + repo metadata
    GET    /status       - Report connection status (never exposes the PAT)

The PAT is stored machine-wide via ``CredentialManager`` under
``CredentialProvider.GIT_GITHUB`` — the same slot the API Keys settings tab
(#555) uses. Repo metadata (non-secret) is persisted per-workspace under
``.codeframe/github_integration.json``. The PAT is never returned in any
response.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from codeframe.core.credentials import CredentialManager, CredentialProvider
from codeframe.core.github_connect_service import (
    GitHubConnectError,
    InsufficientScopeError,
    InvalidTokenError,
    RepoNotFoundError,
    parse_repo,
    validate_connection,
)
from codeframe.core.github_integration_config import (
    clear_github_integration_config,
    load_github_integration_config,
    save_github_integration_config,
)
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_ai, rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import ErrorCodes, api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/integrations/github", tags=["integrations"])


def get_credential_manager() -> CredentialManager:
    """Dependency: machine-wide CredentialManager.

    Overridden in tests to point at an isolated temp directory.
    """
    return CredentialManager()


class ConnectRequest(BaseModel):
    pat: str = Field(..., min_length=1, description="GitHub Personal Access Token")
    repo: str = Field(..., description="Repository in 'owner/repo' format")


class ConnectResponse(BaseModel):
    connected: bool
    repo: str
    owner_login: str
    owner_avatar_url: str


class StatusResponse(BaseModel):
    connected: bool
    repo: Optional[str] = None
    owner_login: Optional[str] = None
    owner_avatar_url: Optional[str] = None


@router.get("/status", response_model=StatusResponse)
@rate_limit_standard()
async def get_status(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> StatusResponse:
    """Report whether a GitHub repo is connected for this workspace.

    Connected means BOTH the per-workspace repo metadata exists AND the
    machine-wide GitHub PAT is present (env var or stored).
    """
    cfg = load_github_integration_config(workspace)
    has_pat = manager.get_credential(CredentialProvider.GIT_GITHUB) is not None
    if cfg is None or not has_pat:
        return StatusResponse(connected=False)
    return StatusResponse(
        connected=True,
        repo=cfg["repo"],
        owner_login=cfg["owner_login"] or None,
        owner_avatar_url=cfg["owner_avatar_url"] or None,
    )


@router.post("/connect", response_model=ConnectResponse)
@rate_limit_ai()
async def connect(
    request: Request,
    body: ConnectRequest,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> ConnectResponse:
    """Validate a PAT against the target repo, then store the PAT + repo metadata.

    The PAT is validated against the GitHub API (token validity, repo
    visibility, issues-read access) BEFORE anything is persisted. On any
    validation failure nothing is stored.
    """
    # Validate 'owner/repo' format at the boundary before any network call.
    try:
        parse_repo(body.repo)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )

    try:
        result = await validate_connection(body.pat, body.repo)
    except ValueError as e:
        # Defensive: service re-validates format too.
        raise HTTPException(
            status_code=400,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except RepoNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=api_error(str(e), ErrorCodes.NOT_FOUND),
        )
    except InsufficientScopeError as e:
        raise HTTPException(
            status_code=403,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except GitHubConnectError as e:
        raise HTTPException(
            status_code=502,
            detail=api_error(str(e), ErrorCodes.EXECUTION_FAILED),
        )

    # Validation passed — store the PAT (machine-wide) and repo metadata.
    # The GIT_GITHUB slot is shared machine-wide with the API Keys tab, so
    # capture any prior token first to restore it if the config write fails —
    # never blindly delete an unrelated, previously working credential.
    prior_pat = manager.get_credential(CredentialProvider.GIT_GITHUB)
    try:
        manager.set_credential(CredentialProvider.GIT_GITHUB, body.pat)
    except Exception as e:
        logger.error("Failed to store GitHub PAT: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to store GitHub token", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )

    try:
        saved = save_github_integration_config(
            workspace,
            {
                "repo": result["repo_full_name"],
                "owner_login": result["owner_login"],
                "owner_avatar_url": result["owner_avatar_url"],
            },
        )
    except OSError as e:
        # Roll back the credential so we don't leave a half-connected state.
        # Restore the prior token if there was one; only delete when the slot
        # was empty before this request.
        logger.error("Failed to save integration config: %s", e, exc_info=True)
        try:
            if prior_pat is not None:
                manager.set_credential(CredentialProvider.GIT_GITHUB, prior_pat)
            else:
                manager.delete_credential(CredentialProvider.GIT_GITHUB)
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to save integration config",
                ErrorCodes.EXECUTION_FAILED,
                str(e),
            ),
        )

    return ConnectResponse(
        connected=True,
        repo=saved["repo"],
        owner_login=saved["owner_login"],
        owner_avatar_url=saved["owner_avatar_url"],
    )


@router.delete("/disconnect", status_code=204)
@rate_limit_standard()
async def disconnect(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> Response:
    """Clear stored repo metadata and delete the GitHub PAT. Idempotent."""
    clear_github_integration_config(workspace)
    try:
        manager.delete_credential(CredentialProvider.GIT_GITHUB)
    except Exception as e:
        # Treat absence as success; only surface hard failures.
        msg = str(e).lower()
        if "no such" not in msg and "not found" not in msg:
            logger.warning("Failed to delete GitHub PAT on disconnect: %s", e)
    return Response(status_code=204)
