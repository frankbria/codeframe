"""WebSocket router for CodeFRAME.

This module provides the WebSocket endpoint for real-time updates to the dashboard.

Endpoints:
    - WS /ws - WebSocket connection for real-time project updates
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from codeframe.ui.shared import manager
from codeframe.ui.dependencies import get_db_websocket
from codeframe.persistence.database import Database

# Module logger
logger = logging.getLogger(__name__)

# Create router for WebSocket endpoint
# No prefix since WebSocket uses /ws path directly
router = APIRouter(tags=["websocket"])


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
        - Requires token as query parameter: ws://host/ws?token=YOUR_SESSION_TOKEN
        - Token is validated against sessions table on connection
        - User ID is extracted and stored with WebSocket connection
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
    # Authentication: Extract and validate token from query parameters
    # Authentication is always required for WebSocket connections
    token = websocket.query_params.get("token")

    if not token:
        # No token provided - reject connection
        await websocket.close(code=1008, reason="Authentication required: missing token")
        return

    # Validate token against sessions table
    cursor = db.conn.execute(
        """
        SELECT s.user_id, s.expires_at
        FROM sessions s
        WHERE s.token = ?
        """,
        (token,),
    )
    row = cursor.fetchone()

    if not row:
        # Invalid token
        await websocket.close(code=1008, reason="Invalid authentication token")
        return

    user_id, expires_at_str = row

    # Check if session has expired
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        # Invalid timestamp format - reject connection
        await websocket.close(code=1008, reason="Invalid session data")
        return

    if expires_at < datetime.now(timezone.utc):
        # Expired token - delete session and reject connection
        db.conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.conn.commit()
        await websocket.close(code=1008, reason="Session expired")
        return

    logger.info(f"WebSocket authenticated: user_id={user_id}")

    # Accept WebSocket connection after successful authentication
    # Note: user_id is captured in closure and used for authorization checks below
    await manager.connect(websocket)
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
        # Always disconnect and clean up, regardless of how we exited
        await manager.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            # Socket may already be closed - ignore errors
            pass
