"""WebSocket router for interactive terminal in a session workspace.

Endpoint:
    WS /ws/sessions/{session_id}/terminal?token=<JWT>

Client → Server message types:
    Raw bytes / text: forwarded verbatim to subprocess stdin.
    {"type": "resize", "cols": 120, "rows": 40}: resize the terminal window.

Server → Client:
    Raw bytes from subprocess stdout/stderr.

Note: Uses asyncio pipes (not PTY) for simplicity. Arrow keys, colour output,
and interactive programs like vim require a PTY — that is a known limitation of
this initial implementation.
"""

import asyncio
import json
import logging
import os

import jwt as pyjwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from codeframe.auth.manager import SECRET, JWT_ALGORITHM, JWT_AUDIENCE, get_async_session_maker
from codeframe.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _authenticate_websocket(websocket: WebSocket) -> int | None:
    """Validate JWT from query param. Returns user_id or closes the socket."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Authentication required: missing token")
        return None

    try:
        payload = pyjwt.decode(token, SECRET, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE)
        user_id_str = payload.get("sub")
        if not user_id_str:
            await websocket.close(code=4001, reason="Invalid token: missing subject")
            return None
        user_id = int(user_id_str)
    except pyjwt.ExpiredSignatureError:
        await websocket.close(code=4001, reason="Token expired")
        return None
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        logger.debug("Terminal WS JWT decode error: %s", exc)
        await websocket.close(code=4001, reason="Invalid authentication token")
        return None

    try:
        async_session_maker = get_async_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                await websocket.close(code=4001, reason="User not found")
                return None
            if not user.is_active:
                await websocket.close(code=4001, reason="User is inactive")
                return None
    except Exception as exc:
        logger.error("Terminal WS user lookup error: %s", exc)
        await websocket.close(code=4001, reason="Authentication failed")
        return None

    return user_id


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/sessions/{session_id}/terminal")
async def session_terminal_ws(session_id: str, websocket: WebSocket) -> None:
    """Bidirectional WebSocket that shells bash in the session's workspace."""
    # --- Auth ---
    user_id = await _authenticate_websocket(websocket)
    if user_id is None:
        return

    # --- Session lookup ---
    db = getattr(websocket.app.state, "db", None)
    if db is None:
        await websocket.close(code=1011, reason="Database unavailable")
        return

    session = await asyncio.to_thread(db.interactive_sessions.get, session_id)
    if session is None or session.get("state") == "ended":
        await websocket.close(code=4004, reason="Session not found or ended")
        return

    # --- Ownership check ---
    session_user_id = session.get("user_id")
    if session_user_id is not None and int(session_user_id) != user_id:
        await websocket.close(code=4003, reason="Forbidden: session belongs to another user")
        return

    workspace_path = session.get("workspace_path")
    if not workspace_path:
        logger.error("session_id=%s has no workspace_path; refusing terminal spawn", session_id)
        await websocket.close(code=4008, reason="Session has no workspace configured")
        return

    await websocket.accept()

    # --- Spawn bash with a minimal, explicit environment ---
    # Do NOT use os.environ.copy() — it would expose server secrets (API keys, DB creds)
    # to the subprocess. Only pass variables required for a functional terminal.
    env = {
        "TERM": "xterm-256color",
        "HOME": os.environ.get("HOME", "/tmp"),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "SHELL": "/bin/bash",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "USER": os.environ.get("USER", ""),
    }

    process: asyncio.subprocess.Process | None = None
    ws_to_stdin_task: asyncio.Task | None = None
    stdout_to_ws_task: asyncio.Task | None = None

    try:
        process = await asyncio.create_subprocess_exec(
            "bash",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=workspace_path,
            env=env,
        )

        # --- Relay: stdout → WebSocket ---
        async def _stdout_relay() -> None:
            assert process is not None
            assert process.stdout is not None
            try:
                while True:
                    chunk = await process.stdout.read(4096)
                    if not chunk:
                        break
                    try:
                        await websocket.send_bytes(chunk)
                    except Exception:
                        break
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.debug("Terminal stdout relay error: %s", exc)

        # --- Relay: WebSocket → stdin (handles both text and binary frames) ---
        async def _stdin_relay() -> None:
            assert process is not None
            assert process.stdin is not None
            try:
                while True:
                    try:
                        msg = await websocket.receive()
                    except WebSocketDisconnect:
                        raise

                    if "text" in msg:
                        raw_text: str = msg["text"]
                        try:
                            parsed = json.loads(raw_text)
                            if isinstance(parsed, dict) and parsed.get("type") == "resize":
                                # Resize: nothing to do without a PTY
                                continue
                        except json.JSONDecodeError:
                            pass
                        process.stdin.write(raw_text.encode())
                        await process.stdin.drain()
                    elif "bytes" in msg:
                        raw_bytes: bytes = msg["bytes"]
                        try:
                            parsed = json.loads(raw_bytes)
                            if isinstance(parsed, dict) and parsed.get("type") == "resize":
                                continue
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                        process.stdin.write(raw_bytes)
                        await process.stdin.drain()

            except WebSocketDisconnect:
                raise
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.debug("Terminal stdin relay error: %s", exc)

        stdout_to_ws_task = asyncio.create_task(_stdout_relay())
        ws_to_stdin_task = asyncio.create_task(_stdin_relay())

        # Wait for either task to finish (disconnect or process exit)
        await asyncio.wait(
            [stdout_to_ws_task, ws_to_stdin_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

    except WebSocketDisconnect:
        logger.debug("Terminal WebSocket disconnected: session_id=%s", session_id)
    except Exception as exc:
        logger.error("Terminal WebSocket error: %s", exc, exc_info=True)
    finally:
        # Cancel relay tasks
        for task in [ws_to_stdin_task, stdout_to_ws_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        # Terminate subprocess
        if process is not None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    process.kill()
                except ProcessLookupError:
                    pass

        try:
            await websocket.close()
        except Exception:
            pass
