"""Events API router for CodeFRAME v2.

Provides endpoints for fetching workspace activity/event history.
Delegates to codeframe.core.events module.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from codeframe.core.workspace import Workspace, get_workspace, workspace_exists
from codeframe.core import events
from pathlib import Path

router = APIRouter(prefix="/api/v2/events", tags=["events"])


class EventResponse(BaseModel):
    """Response model for a single event."""

    id: int
    workspace_id: str
    event_type: str
    payload: dict
    created_at: str  # ISO format


class EventListResponse(BaseModel):
    """Response model for event list."""

    events: list[EventResponse]
    total: int


def _get_workspace_from_path(workspace_path: str) -> Workspace:
    """Get workspace from path, raising appropriate HTTP errors."""
    path = Path(workspace_path).resolve()

    if not workspace_exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found at {path}. Initialize with 'cf init {path}'",
        )

    workspace = get_workspace(path)
    if not workspace:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found at {path}",
        )

    return workspace


@router.get("", response_model=EventListResponse)
async def list_events(
    workspace_path: str = Query(..., description="Path to workspace directory"),
    limit: int = Query(20, ge=1, le=100, description="Maximum events to return"),
    since_id: Optional[int] = Query(None, description="Only return events after this ID"),
):
    """List recent events for a workspace.

    Returns events in reverse chronological order (newest first).

    Args:
        workspace_path: Path to the workspace
        limit: Maximum number of events (1-100, default 20)
        since_id: Optional event ID for pagination

    Returns:
        List of events with total count
    """
    workspace = _get_workspace_from_path(workspace_path)

    event_list = events.list_recent(workspace, limit=limit, since_id=since_id)

    return EventListResponse(
        events=[
            EventResponse(
                id=e.id,
                workspace_id=e.workspace_id,
                event_type=e.event_type,
                payload=e.payload,
                created_at=e.created_at.isoformat(),
            )
            for e in event_list
        ],
        total=len(event_list),
    )
