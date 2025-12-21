"""WebSocket router for CodeFRAME.

This module provides the WebSocket endpoint for real-time updates to the dashboard.

Endpoints:
    - WS /ws - WebSocket connection for real-time project updates
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from codeframe.ui.shared import manager

# Module logger
logger = logging.getLogger(__name__)

# Create router for WebSocket endpoint
# No prefix since WebSocket uses /ws path directly
router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time updates.

    Handles real-time communication between the backend and frontend dashboard.
    Supports ping/pong heartbeat and project subscription messages.

    TODO: Implement authorization for WebSocket connections (Issue #132)
    WebSocket connections require token-based authentication since they cannot use
    session cookies like HTTP endpoints. Implementation approach:
    1. Accept auth token as query parameter: ws://host/ws?token=...
    2. Validate token and extract user_id on connection
    3. Store user_id with WebSocket connection in manager
    4. Check db.user_has_project_access() on subscribe/unsubscribe messages
    5. Return authorization error if user lacks project access

    Args:
        websocket: WebSocket connection instance

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
                    await websocket.send_json({
                        "type": "error",
                        "error": "Subscribe message requires project_id"
                    })
                    continue

                # Validate project_id is an integer
                if not isinstance(project_id, int):
                    logger.warning(f"Invalid project_id type: {type(project_id).__name__}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"project_id must be an integer, got {type(project_id).__name__}"
                    })
                    continue

                # Validate project_id is positive
                if project_id <= 0:
                    logger.warning(f"Invalid project_id: {project_id}")
                    await websocket.send_json({
                        "type": "error",
                        "error": "project_id must be a positive integer"
                    })
                    continue

                # Track subscription
                try:
                    await manager.subscription_manager.subscribe(websocket, project_id)
                    logger.info(f"WebSocket subscribed to project {project_id}")
                    await websocket.send_json({
                        "type": "subscribed",
                        "project_id": project_id
                    })
                except Exception as e:
                    logger.error(f"Error subscribing to project {project_id}: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": "Failed to subscribe to project"
                    })
            elif message.get("type") == "unsubscribe":
                # Unsubscribe from specific project updates
                project_id = message.get("project_id")

                # Validate project_id is present
                if project_id is None:
                    logger.warning("Unsubscribe message missing project_id")
                    await websocket.send_json({
                        "type": "error",
                        "error": "Unsubscribe message requires project_id"
                    })
                    continue

                # Validate project_id is an integer
                if not isinstance(project_id, int):
                    logger.warning(f"Invalid project_id type: {type(project_id).__name__}")
                    await websocket.send_json({
                        "type": "error",
                        "error": f"project_id must be an integer, got {type(project_id).__name__}"
                    })
                    continue

                # Validate project_id is positive
                if project_id <= 0:
                    logger.warning(f"Invalid project_id: {project_id}")
                    await websocket.send_json({
                        "type": "error",
                        "error": "project_id must be a positive integer"
                    })
                    continue

                # Remove subscription
                try:
                    await manager.subscription_manager.unsubscribe(websocket, project_id)
                    logger.info(f"WebSocket unsubscribed from project {project_id}")
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "project_id": project_id
                    })
                except Exception as e:
                    logger.error(f"Error unsubscribing from project {project_id}: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "error": "Failed to unsubscribe from project"
                    })

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
