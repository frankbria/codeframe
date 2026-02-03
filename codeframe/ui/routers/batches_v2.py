"""V2 Batches router - delegates to core/conductor module.

This module provides v2-style API endpoints for batch execution management.
Batches represent coordinated execution of multiple tasks.

Routes:
    GET  /api/v2/batches             - List batches
    GET  /api/v2/batches/{id}        - Get batch status
    POST /api/v2/batches/{id}/stop   - Stop a running batch
    POST /api/v2/batches/{id}/resume - Resume a batch
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import conductor
from codeframe.core.conductor import BatchStatus
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/batches", tags=["batches-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class BatchResponse(BaseModel):
    """Response for a single batch."""

    id: str
    workspace_id: str
    task_ids: list[str]
    status: str
    strategy: str
    max_parallel: int
    on_failure: str
    started_at: Optional[str]
    completed_at: Optional[str]
    results: dict[str, str]  # task_id -> RunStatus value


class BatchListResponse(BaseModel):
    """Response for batch list."""

    batches: list[BatchResponse]
    total: int
    by_status: dict[str, int]


class StopBatchRequest(BaseModel):
    """Request for stopping a batch."""

    force: bool = Field(False, description="Force stop by terminating running processes")


class ResumeBatchRequest(BaseModel):
    """Request for resuming a batch."""

    force: bool = Field(False, description="Re-run all tasks including completed ones")


# ============================================================================
# Helper Functions
# ============================================================================


def _batch_to_response(batch: conductor.BatchRun) -> BatchResponse:
    """Convert a BatchRun to a BatchResponse."""
    return BatchResponse(
        id=batch.id,
        workspace_id=batch.workspace_id,
        task_ids=batch.task_ids,
        status=batch.status.value,
        strategy=batch.strategy,
        max_parallel=batch.max_parallel,
        on_failure=batch.on_failure.value,
        started_at=batch.started_at.isoformat() if batch.started_at else None,
        completed_at=batch.completed_at.isoformat() if batch.completed_at else None,
        results={k: v.value if hasattr(v, 'value') else str(v) for k, v in batch.results.items()},
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=BatchListResponse)
@rate_limit_standard()
async def list_batches(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (PENDING, RUNNING, COMPLETED, PARTIAL, FAILED, CANCELLED)"),
    limit: int = Query(20, ge=1, le=100),
    workspace: Workspace = Depends(get_v2_workspace),
) -> BatchListResponse:
    """List batches in the workspace.

    Args:
        status: Optional status filter
        limit: Maximum batches to return
        workspace: v2 Workspace

    Returns:
        List of batches with counts by status
    """
    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = BatchStatus(status.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    f"Invalid status: {status}",
                    ErrorCodes.VALIDATION_ERROR,
                    f"Valid values: {[s.value for s in BatchStatus]}",
                ),
            )

    # Get batches
    batch_list = conductor.list_batches(workspace, status=status_filter, limit=limit)

    # Calculate counts by status
    all_batches = conductor.list_batches(workspace, limit=1000)
    status_counts: dict[str, int] = {}
    for batch in all_batches:
        status_val = batch.status.value
        status_counts[status_val] = status_counts.get(status_val, 0) + 1

    return BatchListResponse(
        batches=[_batch_to_response(b) for b in batch_list],
        total=len(batch_list),
        by_status=status_counts,
    )


@router.get("/{batch_id}", response_model=BatchResponse)
@rate_limit_standard()
async def get_batch(
    request: Request,
    batch_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BatchResponse:
    """Get a specific batch by ID.

    Args:
        batch_id: Batch identifier
        workspace: v2 Workspace

    Returns:
        Batch details

    Raises:
        HTTPException: 404 if batch not found
    """
    batch = conductor.get_batch(workspace, batch_id)

    if not batch:
        raise HTTPException(
            status_code=404,
            detail=api_error("Batch not found", ErrorCodes.NOT_FOUND, f"No batch with id {batch_id}"),
        )

    return _batch_to_response(batch)


@router.post("/{batch_id}/stop", response_model=BatchResponse)
@rate_limit_standard()
async def stop_batch(
    request: Request,
    batch_id: str,
    body: StopBatchRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BatchResponse:
    """Stop a running batch.

    Graceful stop (force=False):
        - Marks batch as CANCELLED
        - Running tasks finish naturally

    Force stop (force=True):
        - Sends SIGTERM to running processes
        - Immediate termination

    Args:
        request: HTTP request for rate limiting
        batch_id: Batch to stop
        body: Stop options
        workspace: v2 Workspace

    Returns:
        Updated batch

    Raises:
        HTTPException:
            - 404: Batch not found
            - 400: Batch not in stoppable state
    """
    force = body.force if body else False

    try:
        batch = conductor.stop_batch(workspace, batch_id, force=force)
        return _batch_to_response(batch)

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Batch not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        raise HTTPException(
            status_code=400,
            detail=api_error("Cannot stop batch", ErrorCodes.INVALID_STATE, error_msg),
        )


@router.post("/{batch_id}/resume", response_model=BatchResponse)
@rate_limit_standard()
async def resume_batch(
    request: Request,
    batch_id: str,
    body: ResumeBatchRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BatchResponse:
    """Resume a batch by re-running failed/blocked tasks.

    Args:
        request: HTTP request for rate limiting
        batch_id: Batch to resume
        body: Resume options
        workspace: v2 Workspace

    Returns:
        Updated batch

    Raises:
        HTTPException:
            - 404: Batch not found
            - 400: Batch not in resumable state
    """
    force = body.force if body else False

    try:
        batch = conductor.resume_batch(workspace, batch_id, force=force)
        return _batch_to_response(batch)

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Batch not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        raise HTTPException(
            status_code=400,
            detail=api_error("Cannot resume batch", ErrorCodes.INVALID_STATE, error_msg),
        )

    except Exception as e:
        logger.error(f"Failed to resume batch {batch_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Resume failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/{batch_id}/cancel", response_model=BatchResponse)
@rate_limit_standard()
async def cancel_batch(
    request: Request,
    batch_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> BatchResponse:
    """Cancel a running batch.

    Similar to stop but with explicit cancel semantics.

    Args:
        batch_id: Batch to cancel
        workspace: v2 Workspace

    Returns:
        Updated batch

    Raises:
        HTTPException:
            - 404: Batch not found
            - 400: Batch not in cancellable state
    """
    try:
        batch = conductor.cancel_batch(workspace, batch_id)
        return _batch_to_response(batch)

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Batch not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        raise HTTPException(
            status_code=400,
            detail=api_error("Cannot cancel batch", ErrorCodes.INVALID_STATE, error_msg),
        )
