"""V2 Projects router - delegates to core modules.

This module provides v2-style API endpoints for project/workspace management
that delegate to core modules. It uses the v2 Workspace model.

The v1 router (projects.py) remains for backwards compatibility.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import project_status
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/projects", tags=["projects-v2"])


# ============================================================================
# Response Models
# ============================================================================


class TaskCountsResponse(BaseModel):
    """Response model for task counts."""

    total: int
    backlog: int
    ready: int
    in_progress: int
    done: int
    blocked: int
    failed: int


class ProgressMetricsResponse(BaseModel):
    """Response model for progress metrics."""

    completed_count: int
    total_count: int
    progress_percentage: float
    open_blockers: int


class WorkspaceStatusResponse(BaseModel):
    """Response model for workspace status."""

    workspace_id: str
    workspace_name: str
    repo_path: str
    tech_stack: Optional[str]
    task_counts: TaskCountsResponse
    progress: ProgressMetricsResponse
    created_at: str


class SessionStateResponse(BaseModel):
    """Response model for session state."""

    has_session: bool
    last_session_summary: str
    last_session_timestamp: str
    next_actions: list[str]
    progress_pct: float
    active_blockers: list[dict]


# ============================================================================
# Project Endpoints
# ============================================================================


@router.get("/status", response_model=WorkspaceStatusResponse)
@rate_limit_standard()
async def get_workspace_status(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> WorkspaceStatusResponse:
    """Get comprehensive status for a workspace.

    Combines task counts, progress metrics, and workspace metadata.

    This is the v2 equivalent of `cf status`.

    Args:
        workspace: v2 Workspace

    Returns:
        WorkspaceStatus with all status information
    """
    try:
        status = project_status.get_workspace_status(workspace)

        return WorkspaceStatusResponse(
            workspace_id=status.workspace_id,
            workspace_name=status.workspace_name,
            repo_path=status.repo_path,
            tech_stack=status.tech_stack,
            task_counts=TaskCountsResponse(
                total=status.task_counts.total,
                backlog=status.task_counts.backlog,
                ready=status.task_counts.ready,
                in_progress=status.task_counts.in_progress,
                done=status.task_counts.done,
                blocked=status.task_counts.blocked,
                failed=status.task_counts.failed,
            ),
            progress=ProgressMetricsResponse(
                completed_count=status.progress.completed_count,
                total_count=status.progress.total_count,
                progress_percentage=status.progress.progress_percentage,
                open_blockers=status.progress.open_blockers,
            ),
            created_at=status.created_at.isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to get workspace status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/progress", response_model=ProgressMetricsResponse)
@rate_limit_standard()
async def get_progress(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ProgressMetricsResponse:
    """Get progress metrics for a workspace.

    Returns completion progress and blocker count.

    Args:
        workspace: v2 Workspace

    Returns:
        ProgressMetrics with completion progress
    """
    try:
        progress = project_status.get_progress_metrics(workspace)

        return ProgressMetricsResponse(
            completed_count=progress.completed_count,
            total_count=progress.total_count,
            progress_percentage=progress.progress_percentage,
            open_blockers=progress.open_blockers,
        )

    except Exception as e:
        logger.error(f"Failed to get progress metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task-counts", response_model=TaskCountsResponse)
@rate_limit_standard()
async def get_task_counts(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> TaskCountsResponse:
    """Get task count statistics for a workspace.

    Args:
        workspace: v2 Workspace

    Returns:
        TaskCounts with counts for each status
    """
    try:
        counts = project_status.get_task_counts(workspace)

        return TaskCountsResponse(
            total=counts.total,
            backlog=counts.backlog,
            ready=counts.ready,
            in_progress=counts.in_progress,
            done=counts.done,
            blocked=counts.blocked,
            failed=counts.failed,
        )

    except Exception as e:
        logger.error(f"Failed to get task counts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session", response_model=SessionStateResponse)
@rate_limit_standard()
async def get_session_state(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> SessionStateResponse:
    """Get current session state for a workspace.

    Loads session state from .codeframe/session_state.json.

    This is the v2 equivalent of `GET /api/projects/{id}/session`.

    Args:
        workspace: v2 Workspace

    Returns:
        SessionState with session information
    """
    try:
        session = project_status.get_session_state(workspace)

        return SessionStateResponse(
            has_session=session.has_session,
            last_session_summary=session.last_session_summary,
            last_session_timestamp=session.last_session_timestamp,
            next_actions=session.next_actions,
            progress_pct=session.progress_pct,
            active_blockers=session.active_blockers,
        )

    except Exception as e:
        logger.error(f"Failed to get session state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session")
@rate_limit_standard()
async def clear_session_state(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Clear session state for a workspace.

    Removes .codeframe/session_state.json.

    Args:
        workspace: v2 Workspace

    Returns:
        Success confirmation
    """
    try:
        project_status.clear_session_state(workspace)

        return {
            "success": True,
            "message": "Session state cleared",
        }

    except Exception as e:
        logger.error(f"Failed to clear session state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
