"""Shared state and utilities for FastAPI server.

This module contains shared state that multiple routers need access to,
preventing circular import issues.
"""

from typing import Dict, List, Optional, Any
from fastapi import WebSocket
import asyncio

from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database
from codeframe.agents.lead_agent import LeadAgent


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._connections_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._connections_lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._connections_lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        # Get snapshot of connections to avoid holding lock during I/O
        async with self._connections_lock:
            connections = self.active_connections.copy()

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Client disconnected, remove from active list
                await self.disconnect(connection)


class SharedState:
    """Thread-safe shared state for concurrent access across routers.

    This class provides async locks to prevent race conditions when
    multiple concurrent requests access mutable state dictionaries.
    """

    def __init__(self):
        self._running_agents: Dict[int, LeadAgent] = {}
        self._review_cache: Dict[int, dict] = {}
        self._agents_lock = asyncio.Lock()
        self._review_lock = asyncio.Lock()

    async def get_running_agent(self, project_id: int) -> Optional[LeadAgent]:
        """Get running agent for a project (thread-safe)."""
        async with self._agents_lock:
            return self._running_agents.get(project_id)

    async def set_running_agent(self, project_id: int, agent: LeadAgent) -> None:
        """Set running agent for a project (thread-safe)."""
        async with self._agents_lock:
            self._running_agents[project_id] = agent

    async def remove_running_agent(self, project_id: int) -> Optional[LeadAgent]:
        """Remove and return running agent for a project (thread-safe)."""
        async with self._agents_lock:
            return self._running_agents.pop(project_id, None)

    async def get_all_running_agents(self) -> Dict[int, LeadAgent]:
        """Get copy of all running agents (thread-safe)."""
        async with self._agents_lock:
            return self._running_agents.copy()

    async def get_cached_review(self, task_id: int) -> Optional[dict]:
        """Get cached review for a task (thread-safe)."""
        async with self._review_lock:
            return self._review_cache.get(task_id)

    async def set_cached_review(self, task_id: int, review_data: dict) -> None:
        """Cache review for a task (thread-safe)."""
        async with self._review_lock:
            self._review_cache[task_id] = review_data

    async def remove_cached_review(self, task_id: int) -> None:
        """Remove cached review for a task (thread-safe)."""
        async with self._review_lock:
            self._review_cache.pop(task_id, None)

    async def clear_review_cache(self) -> None:
        """Clear all cached reviews (thread-safe)."""
        async with self._review_lock:
            self._review_cache.clear()


# Global ConnectionManager instance
manager = ConnectionManager()

# Global SharedState instance (thread-safe)
shared_state = SharedState()

# DEPRECATED: Direct dictionary access (kept for backward compatibility)
# New code should use shared_state methods for thread safety
running_agents: Dict[int, LeadAgent] = {}
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
