"""V2 Pull Request router - delegates to git/github_integration module.

This module provides v2-style API endpoints for GitHub PR management.
Requires GITHUB_TOKEN and GITHUB_REPO environment variables.

Routes:
    GET  /api/v2/pr             - List pull requests
    GET  /api/v2/pr/{number}    - Get PR details
    POST /api/v2/pr             - Create a new PR
    POST /api/v2/pr/{number}/merge - Merge a PR
    POST /api/v2/pr/{number}/close - Close a PR without merging
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.git.github_integration import GitHubIntegration, GitHubAPIError, PRDetails
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/pr", tags=["pr-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class PRResponse(BaseModel):
    """Response for a single pull request."""

    number: int
    url: str
    state: str
    title: str
    body: Optional[str]
    created_at: str
    merged_at: Optional[str]
    head_branch: str
    base_branch: str


class PRListResponse(BaseModel):
    """Response for PR list."""

    pull_requests: list[PRResponse]
    total: int


class CreatePRRequest(BaseModel):
    """Request for creating a pull request."""

    branch: str = Field(..., min_length=1, description="Head branch with changes")
    title: str = Field(..., min_length=1, description="PR title")
    body: str = Field("", description="PR description/body")
    base: str = Field("main", description="Target branch to merge into")


class MergePRRequest(BaseModel):
    """Request for merging a pull request."""

    method: str = Field("squash", description="Merge method: merge, squash, or rebase")


class MergeResponse(BaseModel):
    """Response for merge operation."""

    sha: Optional[str]
    merged: bool
    message: str


class CICheckResponse(BaseModel):
    """A single CI check run result."""

    name: str
    status: str
    conclusion: Optional[str]


class PRStatusResponse(BaseModel):
    """Live PR status: CI checks, review status, and merge state."""

    ci_checks: list[CICheckResponse]
    review_status: str   # "approved" | "changes_requested" | "pending"
    merge_state: str     # "open" | "merged" | "closed"
    pr_url: str
    pr_number: int


# ============================================================================
# Helper Functions
# ============================================================================


def _pr_to_response(pr: PRDetails) -> PRResponse:
    """Convert a PRDetails to a PRResponse."""
    return PRResponse(
        number=pr.number,
        url=pr.url,
        state=pr.state,
        title=pr.title,
        body=pr.body,
        created_at=pr.created_at.isoformat(),
        merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
        head_branch=pr.head_branch,
        base_branch=pr.base_branch,
    )


def _get_github_client() -> GitHubIntegration:
    """Get a GitHub integration client.

    Returns:
        GitHubIntegration instance

    Raises:
        HTTPException: If GitHub token or repo not configured
    """
    try:
        return GitHubIntegration()
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "GitHub not configured",
                ErrorCodes.INVALID_REQUEST,
                str(e),
            ),
        )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status", response_model=PRStatusResponse)
@rate_limit_standard()
async def get_pr_status(
    request: Request,
    pr_number: int = Query(..., description="PR number to poll"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRStatusResponse:
    """Get live PR status: CI checks, review status, and merge state.

    Polls the GitHub API for the given PR number and returns a snapshot
    of all three status dimensions. The frontend polls this every 30 s
    and stops when merge_state is merged or closed.

    Args:
        pr_number: PR number to inspect
        workspace: v2 Workspace (for context)

    Returns:
        PRStatusResponse with CI checks, review status, and merge state
    """
    try:
        client = _get_github_client()

        # Single call to get PR state, URL, and head SHA.
        pr_raw = await client._make_request(
            "GET",
            f"/repos/{client.owner}/{client.repo_name}/pulls/{pr_number}",
        )
        head_sha: str = pr_raw["head"]["sha"]
        pr_url: str = pr_raw["html_url"]
        merge_state: str = "merged" if pr_raw.get("merged_at") else pr_raw["state"]

        # Fetch CI checks and reviews in parallel (2 more GitHub API calls).
        ci_checks, review_status = await asyncio.gather(
            client.get_pr_ci_checks(pr_number, head_sha=head_sha),
            client.get_pr_review_status(pr_number),
        )

        return PRStatusResponse(
            ci_checks=[
                CICheckResponse(name=c.name, status=c.status, conclusion=c.conclusion)
                for c in ci_checks
            ],
            review_status=review_status,
            merge_state=merge_state,
            pr_url=pr_url,
            pr_number=pr_number,
        )

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PR #{pr_number} status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get PR status", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("", response_model=PRListResponse)
@rate_limit_standard()
async def list_pull_requests(
    request: Request,
    state: str = Query("open", description="Filter by state: open, closed, all"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRListResponse:
    """List pull requests for the repository.

    Args:
        state: Filter by PR state
        workspace: v2 Workspace (for context)

    Returns:
        List of pull requests
    """
    try:
        client = _get_github_client()
        prs = await client.list_pull_requests(state=state)

        return PRListResponse(
            pull_requests=[_pr_to_response(pr) for pr in prs],
            total=len(prs),
        )

    except GitHubAPIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list PRs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to list PRs", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/{pr_number}", response_model=PRResponse)
@rate_limit_standard()
async def get_pull_request(
    request: Request,
    pr_number: int,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRResponse:
    """Get details of a specific pull request.

    Args:
        pr_number: PR number
        workspace: v2 Workspace (for context)

    Returns:
        PR details
    """
    try:
        client = _get_github_client()
        pr = await client.get_pull_request(pr_number)

        return _pr_to_response(pr)

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("", response_model=PRResponse, status_code=201)
@rate_limit_standard()
async def create_pull_request(
    request: Request,
    body: CreatePRRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRResponse:
    """Create a new pull request.

    Args:
        request: HTTP request for rate limiting
        body: PR creation request
        workspace: v2 Workspace (for context)

    Returns:
        Created PR details
    """
    try:
        client = _get_github_client()
        pr = await client.create_pull_request(
            branch=body.branch,
            title=body.title,
            body=body.body,
            base=body.base,
        )

        return _pr_to_response(pr)

    except GitHubAPIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create PR: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to create PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/{pr_number}/merge", response_model=MergeResponse)
@rate_limit_standard()
async def merge_pull_request(
    request: Request,
    pr_number: int,
    body: MergePRRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
) -> MergeResponse:
    """Merge a pull request.

    Args:
        request: HTTP request for rate limiting
        pr_number: PR number to merge
        body: Merge options
        workspace: v2 Workspace (for context)

    Returns:
        Merge result
    """
    method = body.method if body else "squash"

    try:
        client = _get_github_client()
        result = await client.merge_pull_request(pr_number, method=method)

        return MergeResponse(
            sha=result.sha,
            merged=result.merged,
            message=result.message,
        )

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        if e.status_code == 405:
            raise HTTPException(
                status_code=400,
                detail=api_error("Cannot merge", ErrorCodes.INVALID_STATE, e.message),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to merge PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to merge PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/{pr_number}/close")
@rate_limit_standard()
async def close_pull_request(
    request: Request,
    pr_number: int,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Close a pull request without merging.

    Args:
        pr_number: PR number to close
        workspace: v2 Workspace (for context)

    Returns:
        Close confirmation
    """
    try:
        client = _get_github_client()
        closed = await client.close_pull_request(pr_number)

        return {
            "success": closed,
            "message": f"PR #{pr_number} closed" if closed else f"Failed to close PR #{pr_number}",
        }

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to close PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
