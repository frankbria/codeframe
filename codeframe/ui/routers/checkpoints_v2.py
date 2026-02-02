"""V2 Checkpoint router - delegates to core modules.

This module provides v2-style API endpoints for checkpoint management that
delegate to core/checkpoints.py. It uses the v2 Workspace model.

The v1 router (checkpoints.py) remains for backwards compatibility.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import checkpoints
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/checkpoints", tags=["checkpoints-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateCheckpointRequest(BaseModel):
    """Request for creating a checkpoint."""

    name: str = Field(..., min_length=1, max_length=200)
    include_git_ref: bool = Field(
        default=True,
        description="Whether to capture current git HEAD",
    )


class CheckpointResponse(BaseModel):
    """Response for a single checkpoint."""

    id: str
    name: str
    created_at: str
    summary: dict[str, Any]


class CheckpointListResponse(BaseModel):
    """Response for checkpoint list."""

    checkpoints: list[CheckpointResponse]
    total: int


class TaskDiffResponse(BaseModel):
    """Response for a single task diff."""

    task_id: str
    title: str
    old_status: Optional[str]
    new_status: Optional[str]
    change_type: str


class CheckpointDiffResponse(BaseModel):
    """Response for checkpoint diff."""

    checkpoint_a: dict[str, str]
    checkpoint_b: dict[str, str]
    task_diffs: list[TaskDiffResponse]
    summary: dict[str, int]


# ============================================================================
# Checkpoint Endpoints
# ============================================================================


@router.post("", response_model=CheckpointResponse)
@rate_limit_standard()
async def create_checkpoint(
    request: Request,
    body: CreateCheckpointRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CheckpointResponse:
    """Create a new checkpoint.

    Captures current state of tasks, blockers, and optionally git ref.

    This is the v2 equivalent of `cf checkpoint create`.

    Args:
        request: Checkpoint creation request
        workspace: v2 Workspace

    Returns:
        Created checkpoint
    """
    try:
        checkpoint = checkpoints.create(
            workspace,
            name=body.name,
            include_git_ref=body.include_git_ref,
        )

        return CheckpointResponse(
            id=checkpoint.id,
            name=checkpoint.name,
            created_at=checkpoint.created_at.isoformat(),
            summary=checkpoint.snapshot.get("summary", {}),
        )

    except Exception as e:
        logger.error(f"Failed to create checkpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=CheckpointListResponse)
@rate_limit_standard()
async def list_checkpoints(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    workspace: Workspace = Depends(get_v2_workspace),
) -> CheckpointListResponse:
    """List all checkpoints.

    This is the v2 equivalent of `cf checkpoint list`.

    Args:
        limit: Maximum checkpoints to return
        workspace: v2 Workspace

    Returns:
        List of checkpoints (newest first)
    """
    checkpoint_list = checkpoints.list_all(workspace, limit=limit)

    return CheckpointListResponse(
        checkpoints=[
            CheckpointResponse(
                id=c.id,
                name=c.name,
                created_at=c.created_at.isoformat(),
                summary=c.snapshot.get("summary", {}),
            )
            for c in checkpoint_list
        ],
        total=len(checkpoint_list),
    )


@router.get("/{checkpoint_id}", response_model=CheckpointResponse)
@rate_limit_standard()
async def get_checkpoint(
    request: Request,
    checkpoint_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CheckpointResponse:
    """Get a specific checkpoint.

    Args:
        checkpoint_id: Checkpoint ID or name
        workspace: v2 Workspace

    Returns:
        Checkpoint details

    Raises:
        HTTPException: 404 if checkpoint not found
    """
    checkpoint = checkpoints.get(workspace, checkpoint_id)
    if not checkpoint:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint not found: {checkpoint_id}",
        )

    return CheckpointResponse(
        id=checkpoint.id,
        name=checkpoint.name,
        created_at=checkpoint.created_at.isoformat(),
        summary=checkpoint.snapshot.get("summary", {}),
    )


@router.post("/{checkpoint_id}/restore")
@rate_limit_standard()
async def restore_checkpoint(
    request: Request,
    checkpoint_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Restore state from a checkpoint.

    Restores task statuses from the checkpoint. Does not modify files.

    This is the v2 equivalent of `cf checkpoint restore`.

    Args:
        checkpoint_id: Checkpoint ID or name
        workspace: v2 Workspace

    Returns:
        Restore result

    Raises:
        HTTPException: 404 if checkpoint not found
    """
    try:
        checkpoint = checkpoints.restore(workspace, checkpoint_id)
        return {
            "success": True,
            "checkpoint_id": checkpoint.id,
            "checkpoint_name": checkpoint.name,
            "message": f"Restored state from checkpoint '{checkpoint.name}'",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restore checkpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{checkpoint_id}")
@rate_limit_standard()
async def delete_checkpoint(
    request: Request,
    checkpoint_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Delete a checkpoint.

    Args:
        checkpoint_id: Checkpoint ID or name
        workspace: v2 Workspace

    Returns:
        Delete result

    Raises:
        HTTPException: 404 if checkpoint not found
    """
    deleted = checkpoints.delete(workspace, checkpoint_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint not found: {checkpoint_id}",
        )

    return {
        "success": True,
        "message": f"Deleted checkpoint {checkpoint_id}",
    }


@router.get("/{checkpoint_id_a}/diff/{checkpoint_id_b}", response_model=CheckpointDiffResponse)
@rate_limit_standard()
async def diff_checkpoints(
    request: Request,
    checkpoint_id_a: str,
    checkpoint_id_b: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CheckpointDiffResponse:
    """Compare two checkpoints.

    Shows task status changes between two checkpoints.

    Args:
        checkpoint_id_a: First checkpoint ID (typically older)
        checkpoint_id_b: Second checkpoint ID (typically newer)
        workspace: v2 Workspace

    Returns:
        Diff result with task changes

    Raises:
        HTTPException: 404 if either checkpoint not found
    """
    try:
        diff_result = checkpoints.diff(workspace, checkpoint_id_a, checkpoint_id_b)

        return CheckpointDiffResponse(
            checkpoint_a={
                "id": diff_result.checkpoint_a_id,
                "name": diff_result.checkpoint_a_name,
            },
            checkpoint_b={
                "id": diff_result.checkpoint_b_id,
                "name": diff_result.checkpoint_b_name,
            },
            task_diffs=[
                TaskDiffResponse(
                    task_id=td.task_id,
                    title=td.title,
                    old_status=td.old_status,
                    new_status=td.new_status,
                    change_type=td.change_type,
                )
                for td in diff_result.task_diffs
            ],
            summary=diff_result.summary,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to diff checkpoints: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
