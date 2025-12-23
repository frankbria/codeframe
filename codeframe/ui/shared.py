"""Shared state and utilities for FastAPI server.

This module contains shared state that multiple routers need access to,
preventing circular import issues.
"""

from typing import Dict, List, Optional, Set
from fastapi import WebSocket
import asyncio
import time
import logging

from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database
from codeframe.agents.lead_agent import LeadAgent

logger = logging.getLogger(__name__)


class WebSocketSubscriptionManager:
    """Manage WebSocket subscriptions for project-filtered broadcasts.

    This manager tracks which WebSocket connections are subscribed to which
    projects, enabling filtered broadcasts that only send events to clients
    subscribed to the relevant project.

    Thread Safety:
        All methods use asyncio.Lock for thread-safe operations, consistent
        with the ConnectionManager pattern.

    Data Structure:
        subscriptions: Dict[WebSocket, Set[int]]
            Maps each websocket to a set of project_ids it's subscribed to.
            This allows a single client to subscribe to multiple projects.
    """

    def __init__(self):
        self._subscriptions: Dict[WebSocket, Set[int]] = {}
        self._subscriptions_lock = asyncio.Lock()

    async def subscribe(self, websocket: WebSocket, project_id: int) -> None:
        """Add a project subscription for a websocket.

        Args:
            websocket: WebSocket connection to subscribe
            project_id: Project ID to subscribe to
        """
        async with self._subscriptions_lock:
            if websocket not in self._subscriptions:
                self._subscriptions[websocket] = set()

            if project_id not in self._subscriptions[websocket]:
                self._subscriptions[websocket].add(project_id)
                logger.debug(f"WebSocket subscribed to project {project_id}")
            else:
                logger.debug(f"WebSocket already subscribed to project {project_id}")

    async def unsubscribe(self, websocket: WebSocket, project_id: int) -> None:
        """Remove a project subscription for a websocket.

        Args:
            websocket: WebSocket connection to unsubscribe
            project_id: Project ID to unsubscribe from
        """
        async with self._subscriptions_lock:
            if websocket in self._subscriptions:
                self._subscriptions[websocket].discard(project_id)
                logger.debug(f"WebSocket unsubscribed from project {project_id}")

                # Clean up empty subscription sets
                if not self._subscriptions[websocket]:
                    del self._subscriptions[websocket]

    async def get_subscribers(self, project_id: int) -> List[WebSocket]:
        """Get list of websockets subscribed to a project.

        Args:
            project_id: Project ID to get subscribers for

        Returns:
            List of WebSocket connections subscribed to the project
        """
        async with self._subscriptions_lock:
            subscribers = [
                ws for ws, projects in self._subscriptions.items()
                if project_id in projects
            ]
            return subscribers

    async def cleanup(self, websocket: WebSocket) -> None:
        """Remove all subscriptions for a websocket (called on disconnect).

        Args:
            websocket: WebSocket connection to clean up
        """
        async with self._subscriptions_lock:
            if websocket in self._subscriptions:
                project_count = len(self._subscriptions[websocket])
                del self._subscriptions[websocket]
                logger.debug(f"Cleaned up {project_count} subscriptions for disconnected WebSocket")

    async def get_subscriptions(self, websocket: WebSocket) -> Set[int]:
        """Get all project_ids a websocket is subscribed to.

        Args:
            websocket: WebSocket connection to check

        Returns:
            Set of project_ids the websocket is subscribed to (empty set if none)
        """
        async with self._subscriptions_lock:
            return self._subscriptions.get(websocket, set()).copy()


class ConnectionManager:
    """Manage WebSocket connections for real-time updates with project-based filtering."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._connections_lock = asyncio.Lock()
        self.subscription_manager = WebSocketSubscriptionManager()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._connections_lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        # Clean up subscriptions first
        await self.subscription_manager.cleanup(websocket)

        # Then remove from active connections
        async with self._connections_lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def _send_to_connection(self, connection: WebSocket, message: dict) -> Optional[WebSocket]:
        """Send message to a single connection, returning connection on failure.

        Args:
            connection: WebSocket connection to send to
            message: Message dict to send

        Returns:
            The connection object if sending failed (for cleanup), None on success
        """
        try:
            await connection.send_json(message)
            return None
        except Exception:
            # Return connection for cleanup
            return connection

    async def broadcast(self, message: dict, project_id: Optional[int] = None):
        """Broadcast message to connected clients concurrently.

        Args:
            message: Message dict to broadcast
            project_id: Optional project ID for filtered broadcasts.
                       If None, broadcasts to all connected clients (backward compatible).
                       If provided, only broadcasts to clients subscribed to that project.
        """
        # Determine which connections should receive the message
        if project_id is None:
            # Backward compatible: broadcast to all connections
            async with self._connections_lock:
                connections = self.active_connections.copy()
        else:
            # Filtered broadcast: only to subscribers of this project
            connections = await self.subscription_manager.get_subscribers(project_id)

        # Send to all connections concurrently (no lock held during I/O)
        tasks = [
            asyncio.create_task(self._send_to_connection(conn, message))
            for conn in connections
        ]

        # Wait for all sends to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Disconnect any connections that failed
        for result in results:
            if result is not None:
                # This was a failed connection, disconnect it
                await self.disconnect(result)


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
# WARNING: Direct access bypasses async locks and is NOT thread-safe!
# New code should use shared_state async methods for thread safety.
# These reference the same underlying storage as shared_state to prevent
# data divergence, but direct modifications are NOT synchronized.
running_agents: Dict[int, LeadAgent] = shared_state._running_agents
review_cache: Dict[int, dict] = shared_state._review_cache


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
    - Checks for existing running agent (thread-safe)
    - Creates LeadAgent instance
    - Atomically stores in both shared_state and agents_dict
    - Updates project status to RUNNING
    - Saves greeting message to database
    - Broadcasts status updates via WebSocket

    Raises:
        ValueError: If agent is already running for this project
    """
    # Acquire lock before checking/creating agent to prevent race conditions
    async with shared_state._agents_lock:
        # Check if agent already exists in shared_state
        existing_agent = shared_state._running_agents.get(project_id)
        if existing_agent is not None:
            raise ValueError(f"Agent already running for project {project_id}")

        # Create Lead Agent instance (only after checking no existing agent)
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # Atomically store agent in both shared_state and agents_dict
        # while still holding the lock
        # Note: agents_dict and shared_state._running_agents may reference
        # the same underlying dict (for backward compatibility), but we
        # store in both to handle cases where they differ
        shared_state._running_agents[project_id] = agent
        if agents_dict is not shared_state._running_agents:
            agents_dict[project_id] = agent

    # Lock released - now safe to do I/O operations
    try:
        # Update project status to RUNNING (non-blocking)
        await asyncio.to_thread(db.update_project, project_id, {"status": ProjectStatus.RUNNING})

        # Broadcast agent_started message
        try:
            await manager.broadcast(
                {
                    "type": "agent_started",
                    "project_id": project_id,
                    "agent_type": "lead",
                    "timestamp": time.time(),  # Wall-clock timestamp (seconds since epoch)
                },
                project_id=project_id
            )
        except Exception:
            # Continue even if broadcast fails
            pass

        # cf-10.4: Broadcast status_update message
        try:
            await manager.broadcast(
                {"type": "status_update", "project_id": project_id, "status": "running"},
                project_id=project_id
            )
        except Exception:
            pass

        # cf-10.3: Send greeting message
        greeting = "Hi! I'm your Lead Agent. I'm here to help build your project. What would you like to create?"

        # cf-10.3: Save greeting to database (non-blocking)
        await asyncio.to_thread(
            db.create_memory,
            project_id=project_id,
            category="conversation",
            key="assistant",
            value=greeting,
        )

        # cf-10.4: Broadcast greeting via WebSocket
        try:
            await manager.broadcast(
                {
                    "type": "chat_message",
                    "project_id": project_id,
                    "role": "assistant",
                    "content": greeting,
                },
                project_id=project_id
            )
        except Exception:
            pass

    except Exception:
        # Cleanup: Remove agent from dictionaries if initialization failed
        # This prevents inconsistent state where agent exists but isn't fully initialized
        async with shared_state._agents_lock:
            shared_state._running_agents.pop(project_id, None)
            if agents_dict is not shared_state._running_agents:
                agents_dict.pop(project_id, None)
        raise
