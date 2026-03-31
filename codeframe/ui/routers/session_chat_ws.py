"""WebSocket router for per-session streaming agent chat.

Endpoint:
    WS /ws/sessions/{session_id}/chat?token=<JWT>

Client → Server message types:
    {"type": "message", "content": "..."}
    {"type": "interrupt"}
    {"type": "ping"}

Server → Client message types:
    {"type": "text_delta", "content": "..."}
    {"type": "tool_use_start", "tool_name": "...", "tool_input": {...}}
    {"type": "tool_result", "tool_name": "...", "content": "..."}
    {"type": "thinking", "content": "..."}
    {"type": "cost_update", "cost_usd": 0.003, "input_tokens": 100, "output_tokens": 50}
    {"type": "done"}
    {"type": "error", "message": "..."}
    {"type": "pong"}
"""

import asyncio
import json
import logging
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from codeframe.auth.manager import SECRET, JWT_ALGORITHM, JWT_AUDIENCE, get_async_session_maker
from codeframe.auth.models import User
from codeframe.ui.shared import session_chat_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _authenticate_websocket(websocket: WebSocket) -> Optional[int]:
    """Validate JWT from query param. Returns user_id or closes with 1008."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Authentication required: missing token")
        return None

    try:
        payload = pyjwt.decode(token, SECRET, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE)
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=1008, reason="Invalid token: missing subject")
            return None
        user_id = int(user_id_str)
    except pyjwt.ExpiredSignatureError:
        await websocket.close(code=1008, reason="Token expired")
        return None
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        logger.debug("WebSocket JWT decode error: %s", exc)
        await websocket.close(code=1008, reason="Invalid authentication token")
        return None

    try:
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                await websocket.close(code=1008, reason="User not found")
                return None
            if not user.is_active:
                await websocket.close(code=1008, reason="User is inactive")
                return None
    except Exception as exc:
        logger.error("WebSocket user lookup error: %s", exc)
        await websocket.close(code=1008, reason="Authentication failed")
        return None

    return user_id


async def _run_streaming_adapter(
    session_id: str,
    user_message: str,
    token_queue: asyncio.Queue,
    interrupt_event: asyncio.Event,
) -> None:
    """Stub for the real Anthropic streaming adapter (tracked in #503).

    Signature is the integration point — replace the body when the real adapter
    is ready. Must push dicts matching the server→client protocol into
    token_queue, and check interrupt_event.is_set() periodically.
    """
    words = user_message.split() or ["..."]
    for word in words:
        if interrupt_event.is_set():
            await token_queue.put({"type": "done"})
            return
        await token_queue.put({"type": "text_delta", "content": word + " "})
        await asyncio.sleep(0.01)

    await token_queue.put(
        {"type": "cost_update", "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
    )
    await token_queue.put({"type": "done"})


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/sessions/{session_id}/chat")
async def session_chat_ws(session_id: str, websocket: WebSocket) -> None:
    """Bidirectional WebSocket for streaming agent chat on an interactive session."""
    # --- Auth ---
    user_id = await _authenticate_websocket(websocket)
    if user_id is None:
        return

    # --- Session validation ---
    db = getattr(websocket.app.state, "db", None)
    if db is None:
        await websocket.close(code=1011, reason="Database unavailable")
        return

    session = await asyncio.to_thread(db.interactive_sessions.get, session_id)
    if session is None or session.get("state") == "ended":
        await websocket.close(code=4008, reason="Session not found or ended")
        return

    # --- Accept & register ---
    await websocket.accept()
    await asyncio.to_thread(db.interactive_sessions.update_state, session_id, "active")
    await session_chat_manager.register(session_id, websocket)

    token_queue = await session_chat_manager.get_token_queue(session_id)
    adapter_task: list[Optional[asyncio.Task]] = [None]

    # ---- Relay task: token_queue → WebSocket --------------------------------
    async def _relay() -> None:
        turn_cost = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
        while True:
            event = await token_queue.get()
            if event.get("type") == "cost_update":
                turn_cost["cost_usd"] += event.get("cost_usd", 0.0)
                turn_cost["input_tokens"] += event.get("input_tokens", 0)
                turn_cost["output_tokens"] += event.get("output_tokens", 0)
            try:
                await websocket.send_json(event)
            except Exception:
                return
            if event.get("type") == "done":
                if turn_cost["cost_usd"] or turn_cost["input_tokens"] or turn_cost["output_tokens"]:
                    await asyncio.to_thread(
                        db.interactive_sessions.update_cost,
                        session_id,
                        turn_cost["cost_usd"],
                        turn_cost["input_tokens"],
                        turn_cost["output_tokens"],
                    )
                turn_cost = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}

    # ---- Receive task: WebSocket → dispatch ---------------------------------
    async def _receive() -> None:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                raise

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                except Exception:
                    pass
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "interrupt":
                await session_chat_manager.signal_interrupt(session_id)

            elif msg_type == "message":
                content = msg.get("content", "")

                # Cancel any in-flight adapter
                if adapter_task[0] and not adapter_task[0].done():
                    adapter_task[0].cancel()
                    try:
                        await adapter_task[0]
                    except (asyncio.CancelledError, Exception):
                        pass

                # Reset interrupt and drain stale queue items
                await session_chat_manager.reset_interrupt(session_id)
                while not token_queue.empty():
                    try:
                        token_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                interrupt_event = await session_chat_manager.get_interrupt_event(session_id)
                adapter_task[0] = asyncio.create_task(
                    _run_streaming_adapter(session_id, content, token_queue, interrupt_event)
                )

    relay = asyncio.create_task(_relay())
    try:
        await _receive()
    except WebSocketDisconnect:
        logger.debug("Session chat WebSocket disconnected: session_id=%s", session_id)
    except Exception as exc:
        logger.error("Session chat WebSocket error: %s", exc, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        relay.cancel()
        try:
            await relay
        except (asyncio.CancelledError, Exception):
            pass
        if adapter_task[0] and not adapter_task[0].done():
            adapter_task[0].cancel()
            try:
                await adapter_task[0]
            except (asyncio.CancelledError, Exception):
                pass
        await session_chat_manager.unregister(session_id)
        try:
            await websocket.close()
        except Exception:
            pass
