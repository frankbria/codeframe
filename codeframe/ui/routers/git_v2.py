"""V2 Git router - delegates to core modules.

This module provides v2-style API endpoints for git operations
that delegate to core modules. It uses the v2 Workspace model.

The v1 router (git.py) remains for backwards compatibility.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import git
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/git", tags=["git-v2"])


# ============================================================================
# Response Models
# ============================================================================


class GitStatusResponse(BaseModel):
    """Response model for git status."""

    current_branch: str
    is_dirty: bool
    modified_files: list[str]
    untracked_files: list[str]
    staged_files: list[str]


class CommitInfoResponse(BaseModel):
    """Response model for commit information."""

    hash: str
    short_hash: str
    message: str
    author: str
    timestamp: str


class CommitListResponse(BaseModel):
    """Response model for commit listing."""

    commits: list[CommitInfoResponse]


class CommitRequest(BaseModel):
    """Request model for creating a commit."""

    files: list[str] = Field(..., min_length=1, description="Files to commit")
    message: str = Field(..., min_length=1, description="Commit message")


class CommitResultResponse(BaseModel):
    """Response model for commit result."""

    commit_hash: str
    commit_message: str
    files_changed: int


class DiffResponse(BaseModel):
    """Response model for git diff."""

    diff: str
    staged: bool


# ============================================================================
# Git Endpoints
# ============================================================================


@router.get("/status", response_model=GitStatusResponse)
@rate_limit_standard()
async def get_git_status(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> GitStatusResponse:
    """Get git working tree status.

    Returns current branch, dirty state, and file lists.

    Args:
        workspace: v2 Workspace

    Returns:
        GitStatusResponse with status information
    """
    try:
        status = git.get_status(workspace)

        return GitStatusResponse(
            current_branch=status.current_branch,
            is_dirty=status.is_dirty,
            modified_files=status.modified_files,
            untracked_files=status.untracked_files,
            staged_files=status.staged_files,
        )

    except ValueError as e:
        logger.error(f"Git status failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get git status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/commits", response_model=CommitListResponse)
@rate_limit_standard()
async def list_commits(
    request: Request,
    branch: Optional[str] = None,
    limit: int = 50,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CommitListResponse:
    """List git commits.

    Args:
        branch: Optional branch name (default: current branch)
        limit: Maximum commits to return (default: 50)
        workspace: v2 Workspace

    Returns:
        CommitListResponse with commit list
    """
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

    try:
        commits = git.list_commits(workspace, branch=branch, limit=limit)

        return CommitListResponse(
            commits=[
                CommitInfoResponse(
                    hash=c.hash,
                    short_hash=c.short_hash,
                    message=c.message,
                    author=c.author,
                    timestamp=c.timestamp,
                )
                for c in commits
            ]
        )

    except ValueError as e:
        logger.error(f"List commits failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list commits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=CommitResultResponse, status_code=201)
@rate_limit_standard()
async def create_commit(
    request: Request,
    body: CommitRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CommitResultResponse:
    """Create a git commit.

    Stages the specified files and creates a commit.

    Args:
        request: CommitRequest with files and message
        workspace: v2 Workspace

    Returns:
        CommitResultResponse with commit details
    """
    try:
        result = git.create_commit(
            workspace,
            files=body.files,
            message=body.message,
        )

        return CommitResultResponse(
            commit_hash=result.commit_hash,
            commit_message=result.commit_message,
            files_changed=result.files_changed,
        )

    except ValueError as e:
        logger.error(f"Create commit failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create commit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diff", response_model=DiffResponse)
@rate_limit_standard()
async def get_diff(
    request: Request,
    staged: bool = False,
    workspace: Workspace = Depends(get_v2_workspace),
) -> DiffResponse:
    """Get git diff.

    Args:
        staged: If True, show staged changes; if False, show unstaged
        workspace: v2 Workspace

    Returns:
        DiffResponse with diff content
    """
    try:
        diff_content = git.get_diff(workspace, staged=staged)

        return DiffResponse(
            diff=diff_content,
            staged=staged,
        )

    except ValueError as e:
        logger.error(f"Get diff failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get diff: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/branch")
@rate_limit_standard()
async def get_current_branch(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Get current branch name.

    Args:
        workspace: v2 Workspace

    Returns:
        Dict with branch name
    """
    try:
        branch = git.get_current_branch(workspace)
        return {"branch": branch}

    except ValueError as e:
        logger.error(f"Get branch failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get current branch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clean")
@rate_limit_standard()
async def check_clean(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Check if working tree is clean.

    Args:
        workspace: v2 Workspace

    Returns:
        Dict with is_clean boolean
    """
    try:
        is_clean = git.is_clean(workspace)
        return {"is_clean": is_clean}

    except ValueError as e:
        logger.error(f"Check clean failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to check if clean: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
