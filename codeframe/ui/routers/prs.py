"""Pull Request management router.

This module provides API endpoints for:
- Creating pull requests via GitHub API
- Listing and getting PR details
- Merging and closing PRs

Part of Sprint 11 - GitHub PR Integration.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.config import GlobalConfig, load_environment
from codeframe.git.github_integration import GitHubIntegration, GitHubAPIError
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager
from codeframe.ui.websocket_broadcasts import (
    broadcast_pr_created,
    broadcast_pr_merged,
    broadcast_pr_closed,
)
from codeframe.auth import get_current_user, User


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/prs", tags=["pull-requests"])


def get_global_config() -> GlobalConfig:
    """Get global configuration with GitHub settings."""
    load_environment()
    return GlobalConfig()


# ============================================================================
# Request/Response Models
# ============================================================================


class CreatePRRequest(BaseModel):
    """Request to create a pull request."""

    branch: str = Field(..., description="Head branch with changes")
    title: str = Field(..., description="PR title")
    body: str = Field("", description="PR description")
    base: str = Field("main", description="Base branch to merge into")


class CreatePRResponse(BaseModel):
    """Response after creating a PR."""

    pr_id: int
    pr_number: int
    pr_url: str
    status: str


class MergePRRequest(BaseModel):
    """Request to merge a pull request."""

    method: Literal["squash", "merge", "rebase"] = Field(
        "squash", description="Merge method (squash, merge, rebase)"
    )


class MergePRResponse(BaseModel):
    """Response after merging a PR."""

    merged: bool
    merge_commit_sha: Optional[str]


class ClosePRResponse(BaseModel):
    """Response after closing a PR."""

    closed: bool


class PRListResponse(BaseModel):
    """Response containing list of PRs."""

    prs: list
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


def validate_github_config(config: GlobalConfig) -> tuple[str, str]:
    """Validate that GitHub is properly configured.

    Returns:
        Tuple of (github_token, github_repo)

    Raises:
        HTTPException: If GitHub config is missing
    """
    if not config.github_token or not config.github_repo:
        raise HTTPException(
            status_code=400,
            detail="GitHub integration not configured. Set GITHUB_TOKEN and GITHUB_REPO environment variables.",
        )
    return config.github_token, config.github_repo


async def validate_project_access(
    project_id: int,
    db: Database,
    user: User,
) -> dict:
    """Validate project exists and user has access.

    Returns:
        Project dict

    Raises:
        HTTPException: If project not found or access denied
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    if not db.user_has_project_access(user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return project


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", status_code=201, response_model=CreatePRResponse)
async def create_pull_request(
    project_id: int,
    request: CreatePRRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new pull request via GitHub API.

    Args:
        project_id: Project ID
        request: PR creation request with branch, title, body, base

    Returns:
        Created PR details

    Raises:
        HTTPException:
            - 400: GitHub not configured
            - 403: Access denied
            - 404: Project not found
            - 422: GitHub API error
    """
    # Validate access
    await validate_project_access(project_id, db, current_user)

    # Get GitHub config
    config = get_global_config()
    github_token, github_repo = validate_github_config(config)

    # Create PR via GitHub API
    gh: Optional[GitHubIntegration] = None
    try:
        gh = GitHubIntegration(token=github_token, repo=github_repo)
        pr_details = await gh.create_pull_request(
            branch=request.branch,
            title=request.title,
            body=request.body,
            base=request.base,
        )

        # Store in database
        pr_id = db.pull_requests.create_pr(
            project_id=project_id,
            issue_id=None,  # Can be linked later
            branch_name=request.branch,
            title=request.title,
            body=request.body,
            base_branch=request.base,
            head_branch=request.branch,
        )

        # Update with GitHub data
        db.pull_requests.update_pr_github_data(
            pr_id=pr_id,
            pr_number=pr_details.number,
            pr_url=pr_details.url,
            github_created_at=pr_details.created_at,
        )

        # Broadcast PR created event
        await broadcast_pr_created(
            manager=manager,
            project_id=project_id,
            pr_id=pr_id,
            pr_number=pr_details.number,
            pr_url=pr_details.url,
            title=request.title,
            branch_name=request.branch,
        )

        logger.info(f"Created PR #{pr_details.number} for project {project_id}")

        return CreatePRResponse(
            pr_id=pr_id,
            pr_number=pr_details.number,
            pr_url=pr_details.url,
            status="open",
        )

    except GitHubAPIError as e:
        logger.error(f"GitHub API error creating PR: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    finally:
        if gh is not None:
            await gh.close()


@router.get("", response_model=PRListResponse)
async def list_pull_requests(
    project_id: int,
    status: Optional[str] = None,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List pull requests for a project.

    Args:
        project_id: Project ID
        status: Optional filter by status (open, merged, closed, draft)

    Returns:
        List of PRs with total count
    """
    await validate_project_access(project_id, db, current_user)

    prs = db.pull_requests.list_prs(project_id, status=status)

    return PRListResponse(prs=prs, total=len(prs))


@router.get("/{pr_number}")
async def get_pull_request(
    project_id: int,
    pr_number: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get pull request details by PR number.

    Args:
        project_id: Project ID
        pr_number: GitHub PR number

    Returns:
        PR details

    Raises:
        HTTPException: 404 if PR not found
    """
    await validate_project_access(project_id, db, current_user)

    pr = db.pull_requests.get_pr_by_number(project_id, pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail=f"PR #{pr_number} not found")

    return pr


@router.post("/{pr_number}/merge", response_model=MergePRResponse)
async def merge_pull_request(
    project_id: int,
    pr_number: int,
    request: MergePRRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge a pull request via GitHub API.

    Args:
        project_id: Project ID
        pr_number: GitHub PR number to merge
        request: Merge request with method (squash, merge, rebase)

    Returns:
        Merge result with SHA

    Raises:
        HTTPException:
            - 404: PR not found
            - 422: GitHub API error (not mergeable, conflicts, etc.)
    """
    await validate_project_access(project_id, db, current_user)

    # Verify PR exists in our database
    pr = db.pull_requests.get_pr_by_number(project_id, pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail=f"PR #{pr_number} not found")

    # Get GitHub config
    config = get_global_config()
    github_token, github_repo = validate_github_config(config)

    # Merge via GitHub API
    gh: Optional[GitHubIntegration] = None
    try:
        gh = GitHubIntegration(token=github_token, repo=github_repo)
        result = await gh.merge_pull_request(
            pr_number=pr_number,
            method=request.method,
        )

        # Update database only if merge succeeded
        if result.merged:
            db.pull_requests.update_pr_status(
                pr_id=pr["id"],
                status="merged",
                merge_commit_sha=result.sha,
            )

            # Broadcast PR merged event
            if result.sha:
                await broadcast_pr_merged(
                    manager=manager,
                    project_id=project_id,
                    pr_number=pr_number,
                    merge_commit_sha=result.sha,
                )

            logger.info(f"Merged PR #{pr_number} for project {project_id}")
        else:
            logger.warning(f"PR #{pr_number} merge returned merged=False")

        return MergePRResponse(
            merged=result.merged,
            merge_commit_sha=result.sha,
        )

    except GitHubAPIError as e:
        logger.error(f"GitHub API error merging PR: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    finally:
        if gh is not None:
            await gh.close()


@router.post("/{pr_number}/close", response_model=ClosePRResponse)
async def close_pull_request(
    project_id: int,
    pr_number: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close a pull request without merging.

    Args:
        project_id: Project ID
        pr_number: GitHub PR number to close

    Returns:
        Close result

    Raises:
        HTTPException: 404 if PR not found
    """
    await validate_project_access(project_id, db, current_user)

    # Verify PR exists in our database
    pr = db.pull_requests.get_pr_by_number(project_id, pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail=f"PR #{pr_number} not found")

    # Get GitHub config
    config = get_global_config()
    github_token, github_repo = validate_github_config(config)

    # Close via GitHub API
    gh: Optional[GitHubIntegration] = None
    try:
        gh = GitHubIntegration(token=github_token, repo=github_repo)
        closed = await gh.close_pull_request(pr_number)

        # Update database only if close succeeded
        if closed:
            db.pull_requests.update_pr_status(
                pr_id=pr["id"],
                status="closed",
            )

            # Broadcast PR closed event
            await broadcast_pr_closed(
                manager=manager,
                project_id=project_id,
                pr_number=pr_number,
            )

            logger.info(f"Closed PR #{pr_number} for project {project_id}")
        else:
            logger.warning(f"PR #{pr_number} close returned closed=False")

        return ClosePRResponse(closed=closed)

    except GitHubAPIError as e:
        logger.error(f"GitHub API error closing PR: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    finally:
        if gh is not None:
            await gh.close()
