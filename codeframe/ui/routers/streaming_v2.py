"""SSE streaming router for real-time task execution events.

This module provides Server-Sent Events (SSE) endpoints for streaming
task execution progress to web clients.

Endpoints:
- GET /api/v2/tasks/{task_id}/stream - SSE stream of execution events

This router follows the thin adapter pattern:
1. Parse HTTP request parameters
2. Subscribe to EventPublisher from core.streaming
3. Format events as SSE and stream to client
4. Handle disconnection gracefully
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from codeframe.auth import User
from codeframe.auth.dependencies import get_current_user
from codeframe.core import tasks
from codeframe.core.models import ExecutionEvent
from codeframe.core.streaming import EventPublisher
from codeframe.core.workspace import Workspace
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v2/tasks",
    tags=["streaming"],
)

# Global event publisher instance
# In production, this should be dependency-injected
_event_publisher: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    """Get or create the global EventPublisher instance.

    Returns:
        The EventPublisher singleton
    """
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher()
    return _event_publisher


def set_event_publisher(publisher: EventPublisher) -> None:
    """Set the global EventPublisher instance (for testing).

    Args:
        publisher: EventPublisher instance to use
    """
    global _event_publisher
    _event_publisher = publisher


def format_sse_event(event: ExecutionEvent) -> str:
    """Format an ExecutionEvent as an SSE data line.

    SSE format:
        data: {"event_type": "...", ...}\\n\\n

    Args:
        event: ExecutionEvent to format

    Returns:
        SSE-formatted string with data prefix and double newline
    """
    return f"data: {event.model_dump_json()}\n\n"


def format_sse_comment(message: str) -> str:
    """Format a comment line for SSE (used for heartbeats).

    SSE comments start with ':' and are ignored by EventSource clients,
    but keep the connection alive.

    Args:
        message: Comment message

    Returns:
        SSE comment string
    """
    return f": {message}\n\n"


async def event_stream_generator(
    task_id: str,
    publisher: EventPublisher,
    request: Request,
    heartbeat_interval: float = 30.0,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for a task.

    This async generator yields SSE-formatted strings as events
    are published for the given task.

    Args:
        task_id: Task ID to stream events for
        publisher: EventPublisher to subscribe to
        request: FastAPI request (for disconnect detection)
        heartbeat_interval: Seconds between heartbeat events

    Yields:
        SSE-formatted event strings
    """
    logger.info(f"Starting SSE stream for task {task_id}")

    try:
        async for event in publisher.subscribe(task_id):
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info(f"Client disconnected from task {task_id} stream")
                break

            yield format_sse_event(event)

            # If this is a completion event, we're done
            if event.event_type == "completion":
                logger.info(f"Task {task_id} completed, closing stream")
                break

    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for task {task_id}")
        raise
    except Exception as e:
        logger.error(f"Error in SSE stream for task {task_id}: {e}")
        raise
    finally:
        logger.info(f"Closing SSE stream for task {task_id}")


@router.get(
    "/{task_id}/stream",
    response_class=StreamingResponse,
    summary="Stream task execution events",
    description="""
    Stream real-time execution events for a task using Server-Sent Events (SSE).

    **Authentication required**: Pass JWT token via Authorization header or cookie.

    The stream includes:
    - **progress**: Phase transitions and step updates
    - **output**: stdout/stderr from commands
    - **blocker**: Human-in-the-loop questions
    - **completion**: Task finished (stream closes)
    - **error**: Errors during execution
    - **heartbeat**: Keep-alive (configurable, default 30s)

    The stream closes when:
    - Task completes (success or failure)
    - Client disconnects
    - Server error occurs

    Example client (JavaScript):
    ```javascript
    const eventSource = new EventSource('/api/v2/tasks/123/stream', {
        headers: { 'Authorization': 'Bearer <token>' }
    });
    eventSource.onmessage = (e) => {
        const event = JSON.parse(e.data);
        console.log(event.event_type, event.data);
    };
    ```

    Configuration (via environment variables):
    - SSE_TIMEOUT_SECONDS: Timeout for event wait (default: 30)
    - SSE_MAX_QUEUE_SIZE: Max queued events (default: 1000)
    - SSE_OUTPUT_MAX_CHARS: Max output chars per event (default: 2000)
    """,
    responses={
        200: {
            "description": "SSE event stream",
            "content": {
                "text/event-stream": {
                    "example": 'data: {"event_type":"progress","task_id":"123",...}\n\n'
                }
            },
        },
        401: {"description": "Authentication required"},
        404: {"description": "Task not found"},
    },
)
async def stream_task_events(
    task_id: str,
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream execution events for a task via SSE.

    Args:
        task_id: ID of the task to stream
        request: FastAPI request object
        workspace: User's workspace (injected by dependency)
        current_user: Authenticated user (injected by dependency)

    Returns:
        StreamingResponse with SSE content type

    Raises:
        HTTPException: 404 if task not found in workspace
    """
    # Verify task exists in user's workspace
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    publisher = get_event_publisher()

    # Log subscription without PII (use user ID instead of email)
    logger.info("User %s subscribed to task %s stream in workspace %s",
                current_user.id, task_id, workspace.id)

    return StreamingResponse(
        event_stream_generator(task_id, publisher, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
