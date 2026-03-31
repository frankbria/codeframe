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

Architecture note: This router intentionally handles session orchestration
(activation, interrupt coordination, cost aggregation) rather than delegating
to a core service. A future refactoring (TODO: extract to
core.session_chat_service) would make this a thin transport adapter. See
GitHub issue #502 for context.

Workspace scoping: This endpoint is intentionally exempt from workspace_path
query param validation. Auth is already scoped to a user via JWT and the
session_id identifies the resource — workspace scoping on a per-session WS
would be redundant. Revisit if multi-tenant workspace isolation is required.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from codeframe.auth.manager import SECRET, JWT_ALGORITHM, JWT_AUDIENCE, get_async_session_maker
from codeframe.auth.models import User
from codeframe.core.adapters.streaming_chat import StreamingChatAdapter
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
    db_repo,
    workspace_path: Path,
) -> None:
    """Drive the StreamingChatAdapter and forward ChatEvents into the token queue.

    Args:
        session_id: ID of the interactive session.
        user_message: The user's message content.
        token_queue: Queue consumed by the relay task for WebSocket forwarding.
        interrupt_event: Signals the adapter to stop mid-stream.
        db_repo: ``InteractiveSessionRepository`` for history load/persist.
        workspace_path: Absolute path to the workspace for file-system tools.
    """
    try:
        adapter = StreamingChatAdapter(
            session_id=session_id,
            db_repo=db_repo,
            workspace_path=workspace_path,
        )
        async for event in adapter.send_message(
            content=user_message,
            history=[],
            interrupt_event=interrupt_event,
        ):
            await token_queue.put(event.to_dict())
    except Exception as exc:
        logger.error("_run_streaming_adapter error: %s", exc, exc_info=True)
        await token_queue.put({"type": "error", "message": str(exc)})


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

    # --- Accept connection; everything after this point must run inside the
    #     try/finally so unregister() and close() always execute even if
    #     update_state, register, or get_token_queue raises. ---
    await websocket.accept()

    relay: Optional[asyncio.Task] = None
    adapter_task: list[Optional[asyncio.Task]] = [None]

    try:
        await asyncio.to_thread(db.interactive_sessions.update_state, session_id, "active")
        await session_chat_manager.register(session_id, websocket)

        token_queue = await session_chat_manager.get_token_queue(session_id)

        # ---- Relay task: token_queue → WebSocket ----------------------------
        async def _relay() -> None:
            """Forward adapter events to the client; persist cost on 'done'."""
            turn_cost = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
            try:
                while True:
                    event = await token_queue.get()
                    event_type = event.get("type")

                    if event_type == "cost_update":
                        turn_cost["cost_usd"] += event.get("cost_usd", 0.0)
                        turn_cost["input_tokens"] += event.get("input_tokens", 0)
                        turn_cost["output_tokens"] += event.get("output_tokens", 0)
                        try:
                            await websocket.send_json(event)
                        except Exception as exc:
                            logger.warning(
                                "session_id=%s send_json(cost_update) failed: %s", session_id, exc
                            )
                            return

                    elif event_type == "done":
                        # Persist cost BEFORE sending "done" so clients that
                        # immediately fetch session stats observe accurate totals.
                        if (
                            turn_cost["cost_usd"]
                            or turn_cost["input_tokens"]
                            or turn_cost["output_tokens"]
                        ):
                            try:
                                await asyncio.to_thread(
                                    db.interactive_sessions.update_cost,
                                    session_id,
                                    turn_cost["cost_usd"],
                                    turn_cost["input_tokens"],
                                    turn_cost["output_tokens"],
                                )
                            except Exception as exc:
                                logger.error(
                                    "session_id=%s update_cost failed: %s turn_cost=%s",
                                    session_id,
                                    exc,
                                    turn_cost,
                                )
                        turn_cost = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
                        try:
                            await websocket.send_json(event)
                        except Exception as exc:
                            logger.warning(
                                "session_id=%s send_json(done) failed: %s", session_id, exc
                            )
                            return

                    else:
                        try:
                            await websocket.send_json(event)
                        except Exception as exc:
                            logger.warning(
                                "session_id=%s send_json(%s) failed: %s",
                                session_id,
                                event_type,
                                exc,
                            )
                            return
            finally:
                # Flush any cost accumulated during a cancelled/aborted turn
                if (
                    turn_cost["cost_usd"]
                    or turn_cost["input_tokens"]
                    or turn_cost["output_tokens"]
                ):
                    try:
                        await asyncio.to_thread(
                            db.interactive_sessions.update_cost,
                            session_id,
                            turn_cost["cost_usd"],
                            turn_cost["input_tokens"],
                            turn_cost["output_tokens"],
                        )
                    except Exception as exc:
                        logger.error(
                            "session_id=%s relay finally update_cost failed: %s", session_id, exc
                        )

        # ---- Receive task: WebSocket → dispatch -----------------------------
        async def _receive() -> None:
            """Read client messages and dispatch to ping/interrupt/message handlers."""
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
                        except (asyncio.CancelledError, Exception) as exc:
                            logger.debug(
                                "session_id=%s adapter cancelled: %s", session_id, exc
                            )

                    # Reset interrupt and drain stale queue items
                    await session_chat_manager.reset_interrupt(session_id)
                    while not token_queue.empty():
                        try:
                            token_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                    interrupt_event = await session_chat_manager.get_interrupt_event(session_id)
                    raw_workspace = session.get("workspace_path")
                    if not raw_workspace:
                        logger.warning(
                            "session_id=%s has no workspace_path set; "
                            "file tools will scope to server CWD",
                            session_id,
                        )
                    workspace_path = Path(raw_workspace or ".")
                    adapter_task[0] = asyncio.create_task(
                        _run_streaming_adapter(
                            session_id,
                            content,
                            token_queue,
                            interrupt_event,
                            db.interactive_sessions,
                            workspace_path,
                        )
                    )

        relay = asyncio.create_task(_relay())
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
        if relay is not None:
            relay.cancel()
            try:
                await relay
            except (asyncio.CancelledError, Exception):
                pass
        if adapter_task[0] and not adapter_task[0].done():
            adapter_task[0].cancel()
            try:
                await adapter_task[0]
            except (asyncio.CancelledError, Exception) as exc:
                logger.debug("session_id=%s adapter cleanup: %s", session_id, exc)
        await session_chat_manager.unregister(session_id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
