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
