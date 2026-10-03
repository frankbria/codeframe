"""WebSocket router for interactive terminal in a session workspace.

Endpoint:
    WS /ws/sessions/{session_id}/terminal?ticket=<ticket>

Auth: a single-use, 60s ticket from ``POST /auth/stream-ticket`` (#745). A JWT
in the query string is not accepted. The ticket must have been minted by an
``admin``-scoped principal: a shell is the operator's power, not a user's (#1266).

Closes 4403 in hosted mode, before authenticating: the shell would run as the
server's uid, so ``<WORKSPACE_ROOT>/<user_id>`` would not contain it (#1266).

Client → Server message types:
    Raw bytes / text: written to the shell's terminal, as typed.
    {"type": "resize", "cols": 120, "rows": 40}: resize the terminal window.

Server → Client:
    Raw bytes the shell writes to its terminal.

The shell runs on a PTY that is its controlling terminal (#1291). On pipes,
bash never saw xterm.js's Enter (``\r``) as end of line, so nothing typed ran;
the PTY's line discipline maps it, and the controlling tty is what turns ^C into
SIGINT for the foreground job and applies resizes (SIGWINCH).
"""

import asyncio
import errno
import json
import logging
import os
import shutil
import struct
from typing import Optional, Tuple

try:  # POSIX only; the server must still import elsewhere
    import fcntl
    import pty
    import termios
except ImportError:  # pragma: no cover - Windows
    pty = None  # type: ignore[assignment]

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from codeframe.auth.dependencies import authenticate_websocket
from codeframe.ui.dependencies import revalidate_workspace_path

logger = logging.getLogger(__name__)

# No tags: add_api_websocket_route ignores the router-level ``tags`` kwarg,
# because WebSockets are not part of the OpenAPI schema at all (#951).
router = APIRouter()

# Per-user concurrent terminal connection counter (in-process; resets on restart).
# Key is the user_id, or None in no-auth mode (all local terminals share a bucket).
_MAX_TERMINALS_PER_USER = 3
_user_terminal_counts: dict[Optional[int], int] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _authenticate_websocket(websocket: WebSocket) -> Tuple[bool, Optional[int]]:
    """Authenticate the terminal WebSocket via the shared helper.

    Returns ``(authenticated, user_id)``; closes the socket with ``4001`` on
    failure, and ``4403`` when the ticket lacks admin scope. ``user_id`` is
    ``None`` in no-auth mode — matching REST.
    """
    return await authenticate_websocket(websocket, close_code=4001, require_admin=True)


def _resize(master_fd: int, msg: dict) -> None:
    """Apply a ``{"type": "resize"}`` message to the PTY (TIOCSWINSZ)."""
    try:
        cols = max(1, min(int(msg.get("cols", 80)), 1000))
        rows = max(1, min(int(msg.get("rows", 24)), 1000))
    except (TypeError, ValueError):
        return
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _resize_request(raw: bytes | str) -> Optional[dict]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) and parsed.get("type") == "resize" else None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/sessions/{session_id}/terminal")
async def session_terminal_ws(session_id: str, websocket: WebSocket) -> None:
    """Bidirectional WebSocket that shells bash in the session's workspace."""
    from codeframe.ui.server import is_hosted_mode

    if is_hosted_mode():
        await websocket.accept()  # so a browser sees 4403, not 1006
        await websocket.close(
            code=4403,
            reason="Terminal is disabled in hosted mode until per-tenant OS isolation exists",
        )
        return

    # --- Auth ---
    authenticated, user_id = await _authenticate_websocket(websocket)
    if not authenticated:
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
    # Skipped in no-auth mode (user_id is None): there is no identity to enforce,
    # matching REST behavior under CODEFRAME_AUTH_REQUIRED=false. When auth IS
    # enabled, fail closed — an ownerless (NULL, e.g. pre-#655 migrated) or
    # mismatched session is rejected.
    session_user_id = session.get("user_id")
    if user_id is not None and (
        session_user_id is None or int(session_user_id) != user_id
    ):
        await websocket.close(code=4003, reason="Forbidden: session belongs to another user")
        return

    workspace_path = session.get("workspace_path")
    if not workspace_path:
        logger.error("session_id=%s has no workspace_path; refusing terminal spawn", session_id)
        await websocket.close(code=4008, reason="Session has no workspace configured")
        return

    # --- Revalidate the stored path against the allowlist (TOCTOU, #704) ---
    # The path cleared the allowlist at create time, but a tenant could have
    # swapped a dir for a symlink pointing outside its root before connecting.
    # Re-resolve and re-check now; spawn with the freshly resolved path.
    revalidated = await asyncio.to_thread(
        revalidate_workspace_path, workspace_path, user_id
    )
    if revalidated is None:
        logger.error(
            "session_id=%s workspace_path no longer within allowlist; refusing terminal spawn",
            session_id,
        )
        await websocket.close(code=4008, reason="Workspace path no longer permitted")
        return
    workspace_path = str(revalidated)

    if pty is None:  # pragma: no cover - Windows
        await websocket.close(code=1011, reason="The terminal needs a POSIX host")
        return

    # --- Per-user connection cap ---
    current = _user_terminal_counts.get(user_id, 0)
    if current >= _MAX_TERMINALS_PER_USER:
        await websocket.close(code=4029, reason="Too many open terminals; close an existing session first")
        return
    _user_terminal_counts[user_id] = current + 1

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

    shell_exe = shutil.which("bash") or shutil.which("sh") or "sh"
    # util-linux `setsid --ctty` makes the PTY the shell's controlling terminal
    # (setsid + TIOCSCTTY) in C, between fork and exec. Python can only do that
    # with preexec_fn or pty.fork(), both of which run Python code in the child
    # of a multi-threaded server. Without setsid (macOS) the shell still gets the
    # PTY and its own session, so Enter works, but ^C does not signal (#1291).
    setsid_exe = shutil.which("setsid")
    argv = [setsid_exe, "--ctty", shell_exe] if setsid_exe else [shell_exe]

    process: asyncio.subprocess.Process | None = None
    ws_to_stdin_task: asyncio.Task | None = None
    stdout_to_ws_task: asyncio.Task | None = None
    master_fd: int | None = None

    try:
        # Accept inside the try so a failed handshake (client aborts) still hits
        # the finally that releases the reserved per-user slot — otherwise the
        # slot leaks and three aborts lock the user out (#756).
        await websocket.accept()

        master_fd, slave_fd = pty.openpty()
        _resize(master_fd, {"cols": 80, "rows": 24})
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=workspace_path,
                env=env,
                start_new_session=setsid_exe is None,
            )
        finally:
            os.close(slave_fd)  # the shell holds its own copies
        os.set_blocking(master_fd, False)
        loop = asyncio.get_running_loop()
        output: asyncio.Queue[bytes] = asyncio.Queue()

        def _on_readable() -> None:
            try:
                chunk = os.read(master_fd, 4096)  # type: ignore[arg-type]
            except BlockingIOError:
                return
            except OSError as exc:
                # EIO: every slave fd closed, i.e. the shell exited.
                if exc.errno != errno.EIO:
                    logger.debug("Terminal PTY read error: %s", exc)
                chunk = b""
            if not chunk:
                loop.remove_reader(master_fd)  # type: ignore[arg-type]
            output.put_nowait(chunk)

        loop.add_reader(master_fd, _on_readable)

        # --- Relay: PTY → WebSocket ---
        async def _stdout_relay() -> None:
            try:
                while chunk := await output.get():
                    try:
                        await websocket.send_bytes(chunk)
                    except Exception:
                        break
            except asyncio.CancelledError:
                pass

        async def _write(data: bytes) -> None:
            # Bounded by the 64 KiB frame cap; off the loop in case the shell is
            # not reading and the PTY buffer is full.
            assert master_fd is not None
            view = memoryview(data)
            while view:
                try:
                    written = os.write(master_fd, view)
                except BlockingIOError:
                    await asyncio.sleep(0.01)
                    continue
                view = view[written:]

        # --- Relay: WebSocket → PTY (handles both text and binary frames) ---
        async def _stdin_relay() -> None:
            assert master_fd is not None
            try:
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        raise WebSocketDisconnect(msg.get("code", 1000))
                    if "text" in msg and msg["text"] is not None:
                        raw: bytes | str = msg["text"]
                    elif "bytes" in msg and msg["bytes"] is not None:
                        raw = msg["bytes"]
                    else:
                        continue
                    if len(raw) > 65536:
                        logger.warning("session_id=%s: dropping oversized frame (%d bytes)", session_id, len(raw))
                        continue
                    resize = _resize_request(raw)
                    if resize is not None:
                        _resize(master_fd, resize)
                        continue
                    await _write(raw.encode() if isinstance(raw, str) else raw)

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
        # Synchronous steps first: the handler can be cancelled at any await
        # below, and whatever follows that await is then skipped (#1291).
        #
        # Release the per-user slot. A leaked slot outlives the connection, and
        # three of them lock the user out of terminals until restart.
        count = _user_terminal_counts.get(user_id, 0)
        if count > 1:
            _user_terminal_counts[user_id] = count - 1
        else:
            _user_terminal_counts.pop(user_id, None)

        # Closing the master hangs up the terminal: SIGHUP ends an interactive
        # bash, which ignores the SIGTERM below.
        if master_fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(master_fd)
            except Exception:
                pass
            os.close(master_fd)

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
