"""SSE streaming utilities for real-time task execution events.

This module provides shared SSE utilities (formatting, event generation,
publisher management) used by streaming consumers.

The actual SSE endpoint for tasks is in tasks_v2.py:
  GET /api/v2/tasks/{task_id}/stream (requires workspace_path only)
"""

import asyncio
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse  # noqa: F401 — re-exported

from codeframe.core.models import ExecutionEvent
from codeframe.core.streaming import EventPublisher

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


# NOTE: The SSE stream endpoint for tasks is defined in tasks_v2.py
# (GET /api/v2/tasks/{task_id}/stream) which only requires workspace_path
# and is compatible with browser EventSource (no custom auth headers needed).
# This module retains the shared utilities (format_sse_event, format_sse_comment,
# event_stream_generator, get_event_publisher) used by other streaming consumers.
