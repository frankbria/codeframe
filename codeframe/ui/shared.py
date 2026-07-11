"""Shared state and utilities for FastAPI server.

This module contains shared state that multiple routers need access to,
preventing circular import issues.
"""

from typing import Dict, List, Optional, Set
from fastapi import WebSocket
import asyncio
import logging

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


class SessionChatManager:
    """Track active WebSocket connections for per-session agent chat.

    Keyed by session_id (str). Provides interrupt signalling and a token
    queue so the streaming adapter can push events to the WebSocket relay.
    """

    def __init__(self):
        self._connections: Dict[str, "WebSocket"] = {}
        self._interrupt_events: Dict[str, asyncio.Event] = {}
        self._token_queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, websocket: "WebSocket") -> bool:
        """Register websocket as the active connection for session_id.

        Returns True if registered. Returns False when another live socket
        already owns this session_id (the caller should reject with close code
        4009) — the existing connection's interrupt event and token queue are
        left untouched so it stays interruptible (#759).
        """
        async with self._lock:
            existing = self._connections.get(session_id)
            if existing is not None and existing is not websocket:
                return False
            self._connections[session_id] = websocket
            self._interrupt_events[session_id] = asyncio.Event()
            self._token_queues[session_id] = asyncio.Queue()
            return True

    async def unregister(self, session_id: str, websocket: "WebSocket" = None) -> None:
        """Remove tracking state for session_id.

        If websocket is provided, only removes state when the stored connection
        matches — preventing a late disconnect from tearing down state belonging
        to a newer connection for the same session_id.
        """
        async with self._lock:
            if websocket is not None and self._connections.get(session_id) is not websocket:
                return
            self._connections.pop(session_id, None)
            self._interrupt_events.pop(session_id, None)
            self._token_queues.pop(session_id, None)

    async def get_interrupt_event(self, session_id: str) -> Optional[asyncio.Event]:
        async with self._lock:
            return self._interrupt_events.get(session_id)

    async def get_token_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        async with self._lock:
            return self._token_queues.get(session_id)

    async def signal_interrupt(self, session_id: str) -> None:
        async with self._lock:
            event = self._interrupt_events.get(session_id)
        if event is not None:
            event.set()

    async def reset_interrupt(self, session_id: str) -> None:
        async with self._lock:
            event = self._interrupt_events.get(session_id)
        if event is not None:
            event.clear()


# Global ConnectionManager instance
manager = ConnectionManager()

# Global SessionChatManager instance
session_chat_manager = SessionChatManager()
