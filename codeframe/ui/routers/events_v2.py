"""Events API router for CodeFRAME v2.

Provides endpoints for fetching workspace activity/event history.
Delegates to codeframe.core.events module.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from codeframe.core.workspace import Workspace
from codeframe.core import events
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace

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


@router.get("", response_model=EventListResponse)
@rate_limit_standard()
async def list_events(
    request: Request,  # Required for rate limiting
    workspace: Workspace = Depends(get_v2_workspace),
    limit: int = Query(20, ge=1, le=100, description="Maximum events to return"),
    since_id: Optional[int] = Query(None, description="Only return events after this ID"),
):
    """List recent events for a workspace.

    Returns events in reverse chronological order (newest first).

    Args:
        request: HTTP request for rate limiting
        workspace: Resolved workspace from workspace_path query param
        limit: Maximum number of events (1-100, default 20)
        since_id: Optional event ID for pagination

    Returns:
        List of events with total count
    """
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
