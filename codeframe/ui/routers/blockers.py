"""Blocker management router.

This module handles blocker-related endpoints for human-in-the-loop
intervention, including listing blockers, resolving them, and getting
blocker metrics.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.ui.shared import manager
from codeframe.core.models import BlockerResolve
from codeframe.ui.models import (
    BlockerResponse,
    BlockerListResponse,
    BlockerMetricsResponse,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/blockers", tags=["blockers"])


@router.get(
    "",
    response_model=BlockerListResponse,
    summary="Get project blockers",
    description="Returns all blockers for a project with optional status filtering. "
                "Blockers are human-in-the-loop intervention points where agents need guidance. "
                "SYNC blockers pause execution; ASYNC blockers allow work to continue with workarounds.",
    responses={
        200: {"model": BlockerListResponse, "description": "List of blockers with counts"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def get_project_blockers(
    project_id: int,
    status: Optional[str] = Query(
        default=None,
        description="Filter by status: 'PENDING' (awaiting answer), 'RESOLVED' (answered), 'EXPIRED' (timed out)",
        example="PENDING"
    ),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get blockers for a project (049-human-in-loop).

    Args:
        project_id: Project ID
        status: Optional filter by status ('PENDING', 'RESOLVED', 'EXPIRED')
        db: Database instance (injected)

    Returns:
        BlockerListResponse dictionary with:
        - blockers: List of blocker dictionaries
        - total: Total number of blockers
        - pending_count: Number of pending blockers
        - sync_count: Number of SYNC blockers
        - async_count: Number of ASYNC blockers

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get blockers from database
    blockers_data = db.list_blockers(project_id, status)

    return blockers_data


@router.get(
    "/metrics",
    response_model=BlockerMetricsResponse,
    summary="Get blocker metrics",
    description="Returns analytics on blocker resolution for a project, including average resolution time, "
                "expiration rate, and counts by status/type. Useful for understanding human-in-the-loop efficiency.",
    responses={
        200: {"model": BlockerMetricsResponse, "description": "Blocker metrics"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Project not found"},
    },
)
async def get_blocker_metrics_endpoint(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get blocker metrics for a project (049-human-in-loop, Phase 10/T062).

    Provides analytics on blocker resolution times and expiration rates.

    Args:
        project_id: Project ID to get metrics for
        db: Database instance (injected)

    Returns:
        200 OK: Blocker metrics
        {
            "avg_resolution_time_seconds": float | null,
            "expiration_rate_percent": float,
            "total_blockers": int,
            "resolved_count": int,
            "expired_count": int,
            "pending_count": int,
            "sync_count": int,
            "async_count": int
        }

        404 Not Found: Project doesn't exist
        {
            "error": "Project not found",
            "project_id": int
        }

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get metrics
    metrics = db.get_blocker_metrics(project_id)
    return metrics


# Individual blocker endpoints (not scoped to project)
blocker_router = APIRouter(prefix="/api/blockers", tags=["blockers"])


@blocker_router.get(
    "/{blocker_id}",
    response_model=BlockerResponse,
    summary="Get blocker details",
    description="Returns detailed information about a specific blocker, including its type, status, "
                "description, and resolution (if any). Requires access to the blocker's parent project.",
    responses={
        200: {"model": BlockerResponse, "description": "Blocker details"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied to blocker's project"},
        404: {"model": ErrorResponse, "description": "Blocker not found"},
    },
)
async def get_blocker(
    blocker_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details of a specific blocker (049-human-in-loop).

    Args:
        blocker_id: Blocker ID
        db: Database instance (injected)

    Returns:
        Blocker dictionary

    Raises:
        HTTPException:
            - 404: Blocker not found
    """
    blocker = db.get_blocker(blocker_id)

    if not blocker:
        raise HTTPException(status_code=404, detail=f"Blocker {blocker_id} not found")

    # Authorization check - verify user has access to the blocker's project
    project_id = blocker.get("project_id")
    if project_id and not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return blocker


@blocker_router.post(
    "/{blocker_id}/resolve",
    summary="Resolve a blocker",
    description="Provides an answer to resolve a blocker, allowing the agent to continue. "
                "The answer is stored with the blocker and agents can use it to proceed. "
                "Returns 409 Conflict if the blocker was already resolved.",
    responses={
        200: {"description": "Blocker resolved successfully"},
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        404: {"model": ErrorResponse, "description": "Blocker not found"},
        409: {"description": "Blocker already resolved"},
        422: {"model": ErrorResponse, "description": "Invalid request body"},
    },
)
async def resolve_blocker_endpoint(
    blocker_id: int,
    request: BlockerResolve,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve a blocker with user's answer (049-human-in-loop, Phase 4/US2).

    Args:
        blocker_id: Blocker ID to resolve
        request: BlockerResolve containing the answer
        db: Database instance (injected)

    Returns:
        200 OK: Blocker resolution successful
        {
            "blocker_id": int,
            "status": "RESOLVED",
            "resolved_at": ISODate (RFC 3339)
        }

        409 Conflict: Blocker already resolved
        {
            "error": "Blocker already resolved",
            "blocker_id": int,
            "resolved_at": ISODate (RFC 3339)
        }

        404 Not Found: Blocker doesn't exist
        {
            "error": "Blocker not found",
            "blocker_id": int
        }

    Raises:
        HTTPException:
            - 404: Blocker not found
            - 409: Blocker already resolved (duplicate resolution)
            - 422: Invalid request (validation error)
    """

    # Check if blocker exists
    blocker = db.get_blocker(blocker_id)
    if not blocker:
        raise HTTPException(
            status_code=404, detail={"error": "Blocker not found", "blocker_id": blocker_id}
        )

    # Authorization check - verify user has access to the blocker's project
    project_id = blocker.get("project_id")
    if project_id and not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Attempt to resolve blocker (returns False if already resolved)
    success = db.resolve_blocker(blocker_id, request.answer)

    if not success:
        # Blocker already resolved - return 409 Conflict
        blocker = db.get_blocker(blocker_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "Blocker already resolved",
                "blocker_id": blocker_id,
                "resolved_at": blocker["resolved_at"],
            },
        )

    # Get updated blocker for response
    blocker = db.get_blocker(blocker_id)

    # Broadcast blocker_resolved event via WebSocket
    try:
        await manager.broadcast(
            {
                "type": "blocker_resolved",
                "blocker_id": blocker_id,
                "answer": request.answer,
                "resolved_at": blocker["resolved_at"],
            }
        )
    except Exception as e:
        # Log error but don't fail the request
        logger.error(f"Failed to broadcast blocker_resolved event: {e}")

    # Return success response
    return {"blocker_id": blocker_id, "status": "RESOLVED", "resolved_at": blocker["resolved_at"]}
