"""The session terminal runs a real shell on a PTY (#1291).

bash ran on pipes, so it never treated xterm.js's Enter (``\\r``) as end of
line: commands typed in the web terminal did nothing. The relay tests mocked the
subprocess, so nothing noticed. These drive the real router and a real shell —
nothing mocked but the session row — and assert on *computed* output, so an
echo of the typed input cannot satisfy them.
"""

import json
import shutil
import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.ui.routers.terminal_ws import router

pytestmark = [
    pytest.mark.v2,
    pytest.mark.timeout(60),
    pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash"),
]


@pytest.fixture
def terminal(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.state.db = MagicMock()
    app.state.db.interactive_sessions.get.return_value = {
        "state": "active", "workspace_path": str(tmp_path), "user_id": None,
    }
    with TestClient(app).websocket_connect("/ws/sessions/s1/terminal") as ws:
        yield ws


def _read_until(ws, needle: str, seconds: float = 20) -> str:
    out = ""
    deadline = time.monotonic() + seconds
    while needle not in out:
        assert time.monotonic() < deadline, f"never saw {needle!r} in {out[-500:]!r}"
        out += ws.receive_bytes().decode(errors="replace")
    return out


def test_enter_as_xterm_sends_it_runs_the_command(terminal):
    terminal.send_text("echo HELLO_$((6*7))\r")
    _read_until(terminal, "HELLO_42")


def test_a_resize_reaches_the_shell(terminal):
    terminal.send_text(json.dumps({"type": "resize", "cols": 100, "rows": 30}))
    terminal.send_text("stty size\r")
    _read_until(terminal, "30 100")


@pytest.mark.skipif(shutil.which("setsid") is None, reason="controlling tty needs util-linux setsid")
def test_ctrl_c_interrupts_the_foreground_command(terminal):
    """Only a controlling tty turns ^C into SIGINT for the foreground job."""
    terminal.send_text("sleep 30\r")
    time.sleep(0.5)
    terminal.send_text("\x03")
    start = time.monotonic()
    terminal.send_text("echo AFTER_$((1+1))\r")
    _read_until(terminal, "AFTER_2", seconds=10)
    assert time.monotonic() - start < 10


def test_closing_the_terminal_releases_the_users_slot(tmp_path, monkeypatch):
    """Teardown awaited the shell before releasing the per-user slot, so a
    cancelled handler leaked it: three closed terminals locked the user out."""
    from codeframe.ui.routers import terminal_ws

    terminal_ws._user_terminal_counts.clear()
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.state.db = MagicMock()
    app.state.db.interactive_sessions.get.return_value = {
        "state": "active", "workspace_path": str(tmp_path), "user_id": None,
    }

    for _ in range(terminal_ws._MAX_TERMINALS_PER_USER + 1):
        with TestClient(app).websocket_connect("/ws/sessions/s1/terminal") as ws:
            ws.send_text("echo OK_$((2+2))\r")
            _read_until(ws, "OK_4")

    assert terminal_ws._user_terminal_counts == {}



def test_a_stalled_client_pauses_the_pty_reader(terminal, monkeypatch):
    """While the socket is backed up, output must stay in the PTY (the shell
    blocks on write) rather than pile up in the server (codex review)."""
    import asyncio

    from codeframe.ui.routers import terminal_ws

    peak, overflows = 0, 0
    real_put = asyncio.Queue.put_nowait

    def tracking_put(self, item):
        nonlocal peak, overflows
        try:
            real_put(self, item)
        except asyncio.QueueFull:
            overflows += 1  # a read with nowhere to put it: dropped output
            raise
        peak = max(peak, self.qsize())

    stalled = asyncio.Event()

    async def stalled_send(self, data):
        await stalled.wait()  # never set: the client stops reading

    monkeypatch.setattr(asyncio.Queue, "put_nowait", tracking_put)
    monkeypatch.setattr("starlette.websockets.WebSocket.send_bytes", stalled_send)
    terminal.send_text("yes\r")
    time.sleep(2)

    # Capped (not unbounded), and capped by pausing the reader — a bounded
    # queue alone would just drop the output that did not fit.
    assert 0 < peak <= terminal_ws._OUTPUT_QUEUE_CHUNKS
    assert overflows == 0


def test_a_shell_that_exits_closes_the_terminal_even_with_a_background_job(terminal):
    """The job keeps the PTY slave open, so the master never reports EOF; the
    relay waited on it forever and the user's slot stayed taken (review)."""
    from starlette.websockets import WebSocketDisconnect

    terminal.send_text("sleep 120 & echo BG_$((1+1))\r")
    _read_until(terminal, "BG_2")
    terminal.send_text("exit\r")
    with pytest.raises(WebSocketDisconnect):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            terminal.receive_bytes()


@pytest.mark.parametrize("value", ["1e999", "Infinity", "-1e999"])
def test_a_nonsense_resize_is_ignored(terminal, value):
    terminal.send_text(f'{{"type": "resize", "cols": {value}, "rows": 30}}')
    terminal.send_text("echo STILL_$((3+3))\r")
    _read_until(terminal, "STILL_6")


def test_a_normal_disconnect_logs_no_unretrieved_task_exception(tmp_path, monkeypatch, caplog):
    """Raising WebSocketDisconnect inside the relay task left it unretrieved,
    so every close logged an ERROR (review)."""
    import gc
    import logging

    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.state.db = MagicMock()
    app.state.db.interactive_sessions.get.return_value = {
        "state": "active", "workspace_path": str(tmp_path), "user_id": None,
    }
    with caplog.at_level(logging.ERROR, logger="asyncio"):
        with TestClient(app).websocket_connect("/ws/sessions/s1/terminal") as ws:
            ws.send_text("echo HI_$((1+1))\r")
            _read_until(ws, "HI_2")
        gc.collect()
    assert "never retrieved" not in caplog.text


def test_output_printed_just_before_exit_reaches_a_slow_client(terminal, monkeypatch):
    """Shell exit used to tear down at once, dropping output still in the PTY
    or the queue (codex review). A slow send makes the race deterministic."""
    import asyncio

    from starlette.websockets import WebSocket, WebSocketDisconnect

    real_send = WebSocket.send_bytes

    async def slow_send(self, data):
        await asyncio.sleep(0.05)
        await real_send(self, data)

    monkeypatch.setattr(WebSocket, "send_bytes", slow_send)
    terminal.send_text("seq 1 20000; exit\r")

    out = ""
    with pytest.raises(WebSocketDisconnect):
        while True:
            out += terminal.receive_bytes().decode(errors="replace")
    assert "\n20000" in out.replace("\r", ""), out[-200:]
