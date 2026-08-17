"""Shared WebSocket state for the FastAPI server.

Lives outside the routers so ``session_chat_ws`` can import it without a
circular import. The v1 ``ConnectionManager`` / ``WebSocketSubscriptionManager``
broadcast pair was removed in #968 — nothing ever called ``connect()``, so the
subscriber list was permanently empty and every broadcast was a no-op.
"""

from typing import Dict, Optional
from fastapi import WebSocket
import asyncio
import logging

logger = logging.getLogger(__name__)


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


# Global SessionChatManager instance
session_chat_manager = SessionChatManager()
