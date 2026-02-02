"""V2 Blockers router - delegates to core/blockers module.

This module provides v2-style API endpoints for blocker management (human-in-the-loop).
Blockers represent questions that pause task execution until answered by a human.

Routes:
    GET  /api/v2/blockers             - List blockers with optional filters
    GET  /api/v2/blockers/{id}        - Get a specific blocker
    POST /api/v2/blockers             - Create a new blocker
    POST /api/v2/blockers/{id}/answer - Answer a blocker
    POST /api/v2/blockers/{id}/resolve - Mark blocker as resolved
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.core import blockers
from codeframe.core.blockers import BlockerStatus
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/blockers", tags=["blockers-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class BlockerResponse(BaseModel):
    """Response for a single blocker."""

    id: str
    workspace_id: str
    task_id: Optional[str]
    question: str
    answer: Optional[str]
    status: str
    created_at: str
    answered_at: Optional[str]


class BlockerListResponse(BaseModel):
    """Response for blocker list."""

    blockers: list[BlockerResponse]
    total: int
    by_status: dict[str, int]


class CreateBlockerRequest(BaseModel):
    """Request for creating a blocker."""

    question: str = Field(..., min_length=1, description="The question to ask")
    task_id: Optional[str] = Field(None, description="Optional associated task ID")


class AnswerBlockerRequest(BaseModel):
    """Request for answering a blocker."""

    answer: str = Field(..., min_length=1, description="The answer text")


# ============================================================================
# Helper Functions
# ============================================================================


def _blocker_to_response(blocker: blockers.Blocker) -> BlockerResponse:
    """Convert a Blocker to a BlockerResponse."""
    return BlockerResponse(
        id=blocker.id,
        workspace_id=blocker.workspace_id,
        task_id=blocker.task_id,
        question=blocker.question,
        answer=blocker.answer,
        status=blocker.status.value,
        created_at=blocker.created_at.isoformat(),
        answered_at=blocker.answered_at.isoformat() if blocker.answered_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=BlockerListResponse)
async def list_blockers(
    status: Optional[str] = Query(None, description="Filter by status (OPEN, ANSWERED, RESOLVED)"),
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    limit: int = Query(100, ge=1, le=1000),
    workspace: Workspace = Depends(get_v2_workspace),
) -> BlockerListResponse:
    """List blockers in the workspace.

    Args:
        status: Optional status filter
        task_id: Optional task filter
        limit: Maximum blockers to return
        workspace: v2 Workspace

    Returns:
        List of blockers with counts by status
    """
    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = BlockerStatus(status.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    f"Invalid status: {status}",
                    ErrorCodes.VALIDATION_ERROR,
                    f"Valid values: {[s.value for s in BlockerStatus]}",
                ),
            )

    # Get blockers
    blocker_list = blockers.list_all(
        workspace,
        status=status_filter,
        task_id=task_id,
        limit=limit,
    )

    # Get counts by status
    status_counts = blockers.count_by_status(workspace)

    return BlockerListResponse(
        blockers=[_blocker_to_response(b) for b in blocker_list],
        total=len(blocker_list),
        by_status=status_counts,
    )


@router.get("/{blocker_id}", response_model=BlockerResponse)
async def get_blocker(
    blocker_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BlockerResponse:
    """Get a specific blocker by ID.

    Supports partial ID matching (prefix).

    Args:
        blocker_id: Blocker identifier (can be partial)
        workspace: v2 Workspace

    Returns:
        Blocker details

    Raises:
        HTTPException: 404 if blocker not found, 400 if multiple matches
    """
    try:
        blocker = blockers.get(workspace, blocker_id)
    except ValueError as e:
        # Multiple blockers match partial ID
        raise HTTPException(
            status_code=400,
            detail=api_error("Ambiguous blocker ID", ErrorCodes.VALIDATION_ERROR, str(e)),
        )

    if not blocker:
        raise HTTPException(
            status_code=404,
            detail=api_error("Blocker not found", ErrorCodes.NOT_FOUND, f"No blocker with id {blocker_id}"),
        )

    return _blocker_to_response(blocker)


@router.post("", response_model=BlockerResponse, status_code=201)
async def create_blocker(
    request: CreateBlockerRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BlockerResponse:
    """Create a new blocker.

    Args:
        request: Blocker creation request
        workspace: v2 Workspace

    Returns:
        Created blocker
    """
    try:
        blocker = blockers.create(
            workspace,
            question=request.question,
            task_id=request.task_id,
        )
        return _blocker_to_response(blocker)

    except Exception as e:
        logger.error(f"Failed to create blocker: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to create blocker", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/{blocker_id}/answer", response_model=BlockerResponse)
async def answer_blocker(
    blocker_id: str,
    request: AnswerBlockerRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BlockerResponse:
    """Answer a blocker.

    Answering a blocker also resets the associated task to READY status,
    so it can be restarted with `cf work start <task-id> --execute`.

    Args:
        blocker_id: Blocker to answer (can be partial ID)
        request: Answer request
        workspace: v2 Workspace

    Returns:
        Updated blocker

    Raises:
        HTTPException:
            - 404: Blocker not found
            - 400: Blocker already resolved or ambiguous ID
    """
    try:
        blocker = blockers.answer(workspace, blocker_id, request.answer)
        return _blocker_to_response(blocker)

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Blocker not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        elif "already resolved" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail=api_error("Cannot answer", ErrorCodes.INVALID_STATE, error_msg),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=api_error("Invalid request", ErrorCodes.VALIDATION_ERROR, error_msg),
            )


@router.post("/{blocker_id}/resolve", response_model=BlockerResponse)
async def resolve_blocker(
    blocker_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BlockerResponse:
    """Mark a blocker as resolved.

    A blocker must be answered before it can be resolved.

    Args:
        blocker_id: Blocker to resolve (can be partial ID)
        workspace: v2 Workspace

    Returns:
        Updated blocker

    Raises:
        HTTPException:
            - 404: Blocker not found
            - 400: Blocker not answered yet or already resolved
    """
    try:
        blocker = blockers.resolve(workspace, blocker_id)
        return _blocker_to_response(blocker)

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Blocker not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        elif "must be answered" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail=api_error("Cannot resolve", ErrorCodes.INVALID_STATE, error_msg),
            )
        elif "already resolved" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail=api_error("Cannot resolve", ErrorCodes.INVALID_STATE, error_msg),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=api_error("Invalid request", ErrorCodes.VALIDATION_ERROR, error_msg),
            )
