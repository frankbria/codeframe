"""Chat API router for CodeFRAME.

This module provides endpoints for chatting with the Lead Agent and
retrieving conversation history.

Endpoints:
    - POST /api/projects/{project_id}/chat - Send chat message to agent
    - GET /api/projects/{project_id}/chat/history - Get chat history
"""

from datetime import datetime, UTC
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager, running_agents

# Create router for chat endpoints
router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


@router.post("")
async def chat_with_lead(
    project_id: int,
    message: Dict[str, str],
    db: Database = Depends(get_db)
):
    """Chat with Lead Agent (cf-14.1).

    Send user message to Lead Agent and get AI response.
    Broadcasts message via WebSocket for real-time updates.

    Args:
        project_id: Project ID
        message: Dict with 'message' key containing user message
        db: Database instance (injected)

    Returns:
        Dict with 'response' and 'timestamp'

    Raises:
        HTTPException:
            - 404: Project not found
            - 400: Empty message or agent not started
            - 500: Agent communication failure
    """
    # Validate input
    user_message = message.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Check if Lead Agent is running
    agent = running_agents.get(project_id)
    if not agent:
        raise HTTPException(
            status_code=400,
            detail="Lead Agent not started for this project. Start the agent first.",
        )

    try:
        # Send message to Lead Agent
        response_text = agent.chat(user_message)

        # Get current timestamp
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Broadcast assistant response via WebSocket
        try:
            await manager.broadcast(
                {
                    "type": "chat_message",
                    "project_id": project_id,
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": timestamp,
                }
            )
        except Exception:
            # Continue even if broadcast fails
            pass

        return {"response": response_text, "timestamp": timestamp}

    except Exception as e:
        # Log error and return 500
        raise HTTPException(
            status_code=500, detail=f"Error communicating with Lead Agent: {str(e)}"
        )


@router.get("/history")
async def get_chat_history(
    project_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Database = Depends(get_db)
):
    """Get conversation history for a project (cf-14.1).

    Args:
        project_id: Project ID
        limit: Maximum messages to return (default: 100)
        offset: Number of messages to skip (default: 0)
        db: Database instance (injected)

    Returns:
        Dict with 'messages' list containing conversation history

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get conversation history from database
    db_messages = db.get_conversation(project_id)

    # Apply pagination
    start = offset
    end = offset + limit
    paginated_messages = db_messages[start:end]

    # Format messages for API response
    messages = []
    for msg in paginated_messages:
        messages.append(
            {
                "role": msg["key"],  # 'user' or 'assistant'
                "content": msg["value"],
                "timestamp": msg["created_at"],
            }
        )

    return {"messages": messages}
