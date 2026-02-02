"""V2 Review router - delegates to core modules.

This module provides v2-style API endpoints for code review operations
that delegate to core modules. It uses the v2 Workspace model.

The v1 router (review.py) remains for backwards compatibility.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.core import review
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


# ============================================================================
# Review Endpoints
# ============================================================================


@router.post("/files", response_model=ReviewResultResponse)
async def review_files(
    request: ReviewFilesRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ReviewResultResponse:
    """Run code review on specified files.

    Performs complexity analysis, security scanning, and OWASP pattern
    detection on the given files.

    Args:
        request: ReviewFilesRequest with file list
        workspace: v2 Workspace

    Returns:
        ReviewResultResponse with findings and score
    """
    try:
        result = review.review_files(workspace, request.files)

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
async def review_task(
    request: ReviewTaskRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ReviewResultResponse:
    """Run code review for a task's modified files.

    Convenience endpoint that wraps file review with task context.

    Args:
        request: ReviewTaskRequest with task ID and modified files
        workspace: v2 Workspace

    Returns:
        ReviewResultResponse with findings and score
    """
    try:
        result = review.review_task(
            workspace,
            task_id=request.task_id,
            files_modified=request.files_modified,
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
async def review_files_summary(
    request: ReviewFilesRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ReviewSummaryResponse:
    """Run code review and return summary only.

    Similar to review_files but returns a condensed summary without
    individual findings. Useful for quick status checks.

    Args:
        request: ReviewFilesRequest with file list
        workspace: v2 Workspace

    Returns:
        ReviewSummaryResponse with aggregated metrics
    """
    try:
        result = review.review_files(workspace, request.files)
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
