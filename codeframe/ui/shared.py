"""Shared state and utilities for FastAPI server.

This module contains shared state that multiple routers need access to,
preventing circular import issues.
"""

from typing import Dict, List
from fastapi import WebSocket
import asyncio

from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database
from codeframe.agents.lead_agent import LeadAgent


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Client disconnected
                pass


# Global ConnectionManager instance
manager = ConnectionManager()

# cf-10.1: Dictionary to track running agents by project_id
running_agents: Dict[int, LeadAgent] = {}

# Sprint 9: Cache for review reports (task_id -> review report dict)
review_cache: Dict[int, dict] = {}


async def start_agent(
    project_id: int, db: Database, agents_dict: Dict[int, LeadAgent], api_key: str
) -> None:
    """Start Lead Agent for a project (cf-10.1).

    Args:
        project_id: Project ID to start agent for
        db: Database connection
        agents_dict: Dictionary to store running agents
        api_key: Anthropic API key for Lead Agent

    This function:
    - Creates LeadAgent instance
    - Updates project status to RUNNING
    - Saves greeting message to database
    - Broadcasts status updates via WebSocket
    """
    try:
        # cf-10.1: Create Lead Agent instance
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # cf-10.1: Store agent reference
        agents_dict[project_id] = agent

        # cf-10.1: Update project status to RUNNING
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # cf-10.4: Broadcast agent_started message
        try:
            await manager.broadcast(
                {
                    "type": "agent_started",
                    "project_id": project_id,
                    "agent_type": "lead",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )
        except Exception:
            # Continue even if broadcast fails
            pass

        # cf-10.4: Broadcast status_update message
        try:
            await manager.broadcast(
                {"type": "status_update", "project_id": project_id, "status": "running"}
            )
        except Exception:
            pass

        # cf-10.3: Send greeting message
        greeting = "Hi! I'm your Lead Agent. I'm here to help build your project. What would you like to create?"

        # cf-10.3: Save greeting to database
        db.create_memory(
            project_id=project_id, category="conversation", key="assistant", value=greeting
        )

        # cf-10.4: Broadcast greeting via WebSocket
        try:
            await manager.broadcast(
                {
                    "type": "chat_message",
                    "project_id": project_id,
                    "role": "assistant",
                    "content": greeting,
                }
            )
        except Exception:
            pass

    except Exception:
        # Log error but let it propagate
        raise
