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

    Args:
        websocket: WebSocket connection instance

    Message Types:
        - ping: Client heartbeat (responds with pong)
        - subscribe: Subscribe to specific project updates

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
                    await websocket.send_json({
                        "type": "error",
                        "error": "Invalid JSON format"
                    })
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
                # TODO: Track subscriptions
                await websocket.send_json({"type": "subscribed", "project_id": project_id})

    except WebSocketDisconnect:
        # Normal client disconnect - no error logging needed
        logger.debug("WebSocket client disconnected normally")
    except Exception as e:
        # Log unexpected errors for debugging
        logger.error(f"WebSocket error: {type(e).__name__} - {str(e)}", exc_info=True)
    finally:
        # Always disconnect and clean up, regardless of how we exited
        manager.disconnect(websocket)
        try:
            await websocket.close()
        except Exception:
            # Socket may already be closed - ignore errors
            pass
