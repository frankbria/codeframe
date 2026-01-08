"""WebSocket router for CodeFRAME.

This module provides the WebSocket endpoint for real-time updates to the dashboard.

Endpoints:
    - WS /ws - WebSocket connection for real-time project updates

Proactive Messaging:
    The WebSocket sends proactive messages to clients:
    - connection_ack: Sent after successful subscription to confirm real-time connectivity
    - project_status: Initial project state snapshot sent on subscription
    - heartbeat: Periodic messages (every 30 seconds) to keep connections alive
"""

import asyncio
import json
import logging
from datetime import datetime, UTC

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy import select

from codeframe.ui.shared import manager
from codeframe.ui.dependencies import get_db_websocket
from codeframe.persistence.database import Database
from codeframe.auth.manager import (
    SECRET,
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    get_async_session_maker,
)
from codeframe.auth.models import User

# Module logger
logger = logging.getLogger(__name__)

# Create router for WebSocket endpoint
# No prefix since WebSocket uses /ws path directly
router = APIRouter(tags=["websocket"])

# Heartbeat interval in seconds
# Heartbeats keep connections alive and verify real-time functionality
HEARTBEAT_INTERVAL_SECONDS = 30


async def send_heartbeats(websocket: WebSocket, project_id: int) -> None:
    """
    Send periodic heartbeat messages to a WebSocket client.

    This function runs in a background task and sends heartbeat messages
    every HEARTBEAT_INTERVAL_SECONDS to keep the connection alive and
    verify real-time functionality.

    Args:
        websocket: WebSocket connection to send heartbeats to
        project_id: Project ID to include in heartbeat messages
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                message = {
                    "type": "heartbeat",
                    "project_id": project_id,
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
                await websocket.send_json(message)
                logger.debug(f"Sent heartbeat for project {project_id}")
            except Exception as e:
                # Connection may have closed - exit the loop
                logger.debug(f"Heartbeat send failed (connection likely closed): {e}")
                break
    except asyncio.CancelledError:
        # Normal cancellation on disconnect
        logger.debug(f"Heartbeat task cancelled for project {project_id}")
        raise


@router.get("/ws/health")
async def websocket_health():
    """
    Health check endpoint for WebSocket server.

    Returns status indicating WebSocket server is ready to accept connections.
    Used by E2E tests and monitoring tools to verify WebSocket availability.

    Returns:
        dict: Status indicating WebSocket server is ready
    """
    return {"status": "ready"}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Database = Depends(get_db_websocket)):
    """WebSocket connection for real-time updates with authentication.

    Handles real-time communication between the backend and frontend dashboard.
    Supports ping/pong heartbeat and project subscription messages.

    Authentication:
        - Requires token as query parameter: ws://host/ws?token=YOUR_JWT_TOKEN
        - JWT token is validated and decoded on connection
        - User ID is extracted from JWT claims and stored with WebSocket connection
        - Project access is checked on subscribe/unsubscribe messages

    Args:
        websocket: WebSocket connection instance
        db: Database instance (injected)

    Message Types:
        - ping: Client heartbeat (responds with pong)
        - subscribe: Subscribe to specific project updates (requires integer project_id)
        - unsubscribe: Unsubscribe from specific project updates (requires integer project_id)

    Message Format:
        All messages must be valid JSON. Example:
        - Ping: {"type": "ping"}
        - Subscribe: {"type": "subscribe", "project_id": 1}
        - Unsubscribe: {"type": "unsubscribe", "project_id": 1}

    Error Handling:
        Invalid messages receive error responses with type "error".
        Examples of invalid messages:
        - Missing project_id in subscribe/unsubscribe
        - Non-integer project_id (e.g., string or float)
        - Non-positive project_id (≤ 0)
        - Malformed JSON

    Broadcasts:
        - agent_started: When an agent starts
        - status_update: Project status changes
        - chat_message: New chat messages
        - task_assigned: Task assignments
        - task_completed: Task completions
        - blocker_created: New blockers
    """
    # Authentication: Extract and validate JWT token from query parameters
    # Authentication is always required for WebSocket connections
    token = websocket.query_params.get("token")

    if not token:
        # No token provided - reject connection
        await websocket.close(code=1008, reason="Authentication required: missing token")
        return

    # Validate JWT token (same logic as HTTP auth in auth/dependencies.py)
    try:
        payload = pyjwt.decode(
            token,
            SECRET,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
        )
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=1008, reason="Invalid token: missing subject")
            return
        user_id = int(user_id_str)
    except pyjwt.ExpiredSignatureError:
        await websocket.close(code=1008, reason="Token expired")
        return
    except (pyjwt.InvalidTokenError, ValueError) as e:
        logger.debug(f"WebSocket JWT decode error: {e}")
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    # Verify user exists and is active
    try:
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user is None:
                await websocket.close(code=1008, reason="User not found")
                return

            if not user.is_active:
                await websocket.close(code=1008, reason="User is inactive")
                return
    except Exception as e:
        logger.error(f"WebSocket user lookup error: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return

    logger.info(f"WebSocket authenticated: user_id={user_id}")

    # Accept WebSocket connection after successful authentication
    # Note: user_id is captured in closure and used for authorization checks below
    await manager.connect(websocket)

    # Track heartbeat tasks per project to cancel on disconnect
    heartbeat_tasks: dict[int, asyncio.Task] = {}

    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()

            # Parse JSON with error handling
            try:
                message = json.loads(data)
            except json.JSONDecodeError as e:
                # Malformed JSON - log warning and send error response to client
                logger.warning(f"Malformed JSON from WebSocket client: {e}")
                try:
                    await websocket.send_json({"type": "error", "error": "Invalid JSON format"})
                except Exception:
                    # If we can't send error response, just continue
                    pass
                continue  # Skip this message and continue receiving

            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "subscribe":
                # Subscribe to specific project updates
                project_id = message.get("project_id")

                # Validate project_id is present
                if project_id is None:
                    logger.warning("Subscribe message missing project_id")
                    await websocket.send_json(
                        {"type": "error", "error": "Subscribe message requires project_id"}
                    )
                    continue

                # Validate project_id is an integer
                if not isinstance(project_id, int):
                    logger.warning(f"Invalid project_id type: {type(project_id).__name__}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": f"project_id must be an integer, got {type(project_id).__name__}",
                        }
                    )
                    continue

                # Validate project_id is positive
                if project_id <= 0:
                    logger.warning(f"Invalid project_id: {project_id}")
                    await websocket.send_json(
                        {"type": "error", "error": "project_id must be a positive integer"}
                    )
                    continue

                # Authorization check: Verify user has access to project
                if not db.user_has_project_access(user_id, project_id):
                    logger.warning(f"User {user_id} denied access to project {project_id}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": "Access denied: you do not have permission to access this project",
                        }
                    )
                    continue

                # Track subscription
                try:
                    await manager.subscription_manager.subscribe(websocket, project_id)
                    logger.info(f"WebSocket (user_id={user_id}) subscribed to project {project_id}")
                    await websocket.send_json({"type": "subscribed", "project_id": project_id})

                    # Send connection acknowledgment (proactive messaging)
                    await websocket.send_json({
                        "type": "connection_ack",
                        "project_id": project_id,
                        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        "message": "Connected to real-time updates",
                    })

                    # Send initial project status snapshot (proactive messaging)
                    try:
                        project = db.get_project(project_id)
                        if project:
                            await websocket.send_json({
                                "type": "project_status",
                                "project_id": project_id,
                                "status": project.get("status", "unknown"),
                                "phase": project.get("phase", "unknown"),
                                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                            })
                    except Exception as e:
                        # Project status is optional - don't fail subscription if unavailable
                        logger.debug(f"Could not send project status for {project_id}: {e}")

                    # Start heartbeat task for this subscription (proactive messaging)
                    if project_id not in heartbeat_tasks:
                        heartbeat_task = asyncio.create_task(
                            send_heartbeats(websocket, project_id)
                        )
                        heartbeat_tasks[project_id] = heartbeat_task
                        logger.debug(f"Started heartbeat task for project {project_id}")

                except Exception as e:
                    logger.error(f"Error subscribing to project {project_id}: {e}")
                    await websocket.send_json(
                        {"type": "error", "error": "Failed to subscribe to project"}
                    )
            elif message.get("type") == "unsubscribe":
                # Unsubscribe from specific project updates
                project_id = message.get("project_id")

                # Validate project_id is present
                if project_id is None:
                    logger.warning("Unsubscribe message missing project_id")
                    await websocket.send_json(
                        {"type": "error", "error": "Unsubscribe message requires project_id"}
                    )
                    continue

                # Validate project_id is an integer
                if not isinstance(project_id, int):
                    logger.warning(f"Invalid project_id type: {type(project_id).__name__}")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "error": f"project_id must be an integer, got {type(project_id).__name__}",
                        }
                    )
                    continue

                # Validate project_id is positive
                if project_id <= 0:
                    logger.warning(f"Invalid project_id: {project_id}")
                    await websocket.send_json(
                        {"type": "error", "error": "project_id must be a positive integer"}
                    )
                    continue

                # Remove subscription
                try:
                    await manager.subscription_manager.unsubscribe(websocket, project_id)
                    logger.info(f"WebSocket unsubscribed from project {project_id}")
                    await websocket.send_json({"type": "unsubscribed", "project_id": project_id})
                except Exception as e:
                    logger.error(f"Error unsubscribing from project {project_id}: {e}")
                    await websocket.send_json(
                        {"type": "error", "error": "Failed to unsubscribe from project"}
                    )

    except WebSocketDisconnect:
        # Normal client disconnect - no error logging needed
        logger.debug("WebSocket client disconnected normally")
    except Exception as e:
        # Log unexpected errors for debugging
        logger.error(f"WebSocket error: {type(e).__name__} - {str(e)}", exc_info=True)
    finally:
        # Cancel all heartbeat tasks
        for project_id, task in heartbeat_tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.debug(f"Cancelled heartbeat task for project {project_id}")
        heartbeat_tasks.clear()

        # Always disconnect and clean up, regardless of how we exited
        await manager.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            # Socket may already be closed - ignore errors
            pass
