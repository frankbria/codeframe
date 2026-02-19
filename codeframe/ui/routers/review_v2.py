"""V2 Review router - delegates to core modules.

This module provides v2-style API endpoints for code review operations
that delegate to core modules. It uses the v2 Workspace model.

The v1 router (review.py) remains for backwards compatibility.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import review, git
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/review", tags=["review-v2"])


# ============================================================================
# Response Models
# ============================================================================


class ReviewFindingResponse(BaseModel):
    """Response model for a review finding."""

    category: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    message: str
    file_path: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


class ReviewResultResponse(BaseModel):
    """Response model for review result."""

    status: Literal["approved", "changes_requested", "rejected"]
    overall_score: float
    findings: list[ReviewFindingResponse]
    summary: str


class ReviewSummaryResponse(BaseModel):
    """Response model for review summary."""

    status: str
    overall_score: float
    total_findings: int
    severity_counts: dict[str, int]
    summary: str
    has_blocking_issues: bool


class ReviewFilesRequest(BaseModel):
    """Request model for reviewing files."""

    files: list[str] = Field(..., min_length=1, description="Files to review")


class ReviewTaskRequest(BaseModel):
    """Request model for reviewing a task's files."""

    task_id: str = Field(..., description="Task ID")
    files_modified: list[str] = Field(..., min_length=1, description="Modified files to review")


class FileChangeResponse(BaseModel):
    """Per-file change statistics."""

    path: str
    change_type: str
    insertions: int
    deletions: int


class DiffStatsResponse(BaseModel):
    """Response model for diff with statistics."""

    diff: str
    files_changed: int
    insertions: int
    deletions: int
    changed_files: list[FileChangeResponse]


class PatchResponse(BaseModel):
    """Response model for patch export."""

    patch: str
    filename: str


class CommitMessageResponse(BaseModel):
    """Response model for generated commit message."""

    message: str


# ============================================================================
# Review Endpoints
# ============================================================================


@router.post("/files", response_model=ReviewResultResponse)
@rate_limit_standard()
async def review_files(
    request: Request,
    body: ReviewFilesRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ReviewResultResponse:
    """Run code review on specified files.

    Performs complexity analysis, security scanning, and OWASP pattern
    detection on the given files.

    Args:
        request: HTTP request for rate limiting
        body: ReviewFilesRequest with file list
        workspace: v2 Workspace

    Returns:
        ReviewResultResponse with findings and score
    """
    try:
        result = review.review_files(workspace, body.files)

        return ReviewResultResponse(
            status=result.status,
            overall_score=result.overall_score,
            findings=[
                ReviewFindingResponse(
                    category=f.category,
                    severity=f.severity,
                    message=f.message,
                    file_path=f.file_path,
                    line_number=f.line_number,
                    suggestion=f.suggestion,
                )
                for f in result.findings
            ],
            summary=result.summary,
        )

    except Exception as e:
        logger.error(f"Failed to review files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/task", response_model=ReviewResultResponse)
@rate_limit_standard()
async def review_task(
    request: Request,
    body: ReviewTaskRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ReviewResultResponse:
    """Run code review for a task's modified files.

    Convenience endpoint that wraps file review with task context.

    Args:
        request: HTTP request for rate limiting
        body: ReviewTaskRequest with task ID and modified files
        workspace: v2 Workspace

    Returns:
        ReviewResultResponse with findings and score
    """
    try:
        result = review.review_task(
            workspace,
            task_id=body.task_id,
            files_modified=body.files_modified,
        )

        return ReviewResultResponse(
            status=result.status,
            overall_score=result.overall_score,
            findings=[
                ReviewFindingResponse(
                    category=f.category,
                    severity=f.severity,
                    message=f.message,
                    file_path=f.file_path,
                    line_number=f.line_number,
                    suggestion=f.suggestion,
                )
                for f in result.findings
            ],
            summary=result.summary,
        )

    except Exception as e:
        logger.error(f"Failed to review task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files/summary", response_model=ReviewSummaryResponse)
@rate_limit_standard()
async def review_files_summary(
    request: Request,
    body: ReviewFilesRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ReviewSummaryResponse:
    """Run code review and return summary only.

    Similar to review_files but returns a condensed summary without
    individual findings. Useful for quick status checks.

    Args:
        request: HTTP request for rate limiting
        body: ReviewFilesRequest with file list
        workspace: v2 Workspace

    Returns:
        ReviewSummaryResponse with aggregated metrics
    """
    try:
        result = review.review_files(workspace, body.files)
        summary = review.get_review_summary(result)

        return ReviewSummaryResponse(
            status=summary["status"],
            overall_score=summary["overall_score"],
            total_findings=summary["total_findings"],
            severity_counts=summary["severity_counts"],
            summary=summary["summary"],
            has_blocking_issues=summary["has_blocking_issues"],
        )

    except Exception as e:
        logger.error(f"Failed to get review summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Diff & Patch Endpoints (for Review & Commit View)
# ============================================================================


@router.get("/diff", response_model=DiffStatsResponse)
@rate_limit_standard()
async def get_review_diff(
    request: Request,
    staged: bool = False,
    workspace: Workspace = Depends(get_v2_workspace),
) -> DiffStatsResponse:
    """Get unified diff with parsed statistics.

    Returns the raw diff plus per-file change counts for display
    in the Review & Commit View.

    Args:
        request: HTTP request for rate limiting
        staged: If True, show staged changes; if False, show unstaged
        workspace: v2 Workspace

    Returns:
        DiffStatsResponse with diff text and statistics
    """
    try:
        stats = git.get_diff_stats(workspace, staged=staged)

        return DiffStatsResponse(
            diff=stats.diff,
            files_changed=stats.files_changed,
            insertions=stats.insertions,
            deletions=stats.deletions,
            changed_files=[
                FileChangeResponse(
                    path=f.path,
                    change_type=f.change_type,
                    insertions=f.insertions,
                    deletions=f.deletions,
                )
                for f in stats.changed_files
            ],
        )

    except ValueError as e:
        logger.error(f"Get review diff failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get review diff: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patch", response_model=PatchResponse)
@rate_limit_standard()
async def get_review_patch(
    request: Request,
    staged: bool = False,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PatchResponse:
    """Get patch-formatted diff for export.

    Returns the diff in patch format suitable for `git apply`.

    Args:
        request: HTTP request for rate limiting
        staged: If True, show staged changes; if False, show unstaged
        workspace: v2 Workspace

    Returns:
        PatchResponse with patch content and suggested filename
    """
    try:
        patch_content = git.get_patch(workspace, staged=staged)
        branch = git.get_current_branch(workspace)
        filename = f"{branch.replace('/', '-')}.patch"

        return PatchResponse(
            patch=patch_content,
            filename=filename,
        )

    except ValueError as e:
        logger.error(f"Get patch failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get patch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit-message", response_model=CommitMessageResponse)
@rate_limit_standard()
async def generate_commit_message(
    request: Request,
    staged: bool = False,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CommitMessageResponse:
    """Generate a commit message from the current diff.

    Analyzes changed files to suggest a conventional commit message.

    Args:
        request: HTTP request for rate limiting
        staged: If True, analyze staged changes; if False, unstaged
        workspace: v2 Workspace

    Returns:
        CommitMessageResponse with suggested message
    """
    try:
        message = git.generate_commit_message(workspace, staged=staged)

        return CommitMessageResponse(message=message)

    except ValueError as e:
        logger.error(f"Generate commit message failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate commit message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
