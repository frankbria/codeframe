"""Integration test: `cf serve` really boots and serves the v2 API.

This suite spent the v2 refactor skipped with the reason "serve command is stub
in v2". That stopped being true a long time ago — `cf serve` runs uvicorn
against ``codeframe.ui.server:app`` and ``GET /`` answers with the health
payload asserted below. Nothing else in the suite spawns the server as a real
subprocess (the API lifecycle tests drive the ASGI app in-process), so this is
the only thing standing between a broken `cf serve` entrypoint and a green CI
badge. Un-skipped and rewritten against v2 in #973.
"""

import os
import signal
import socket
import subprocess
import time

import pytest
import requests

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_until_gone(url: str, timeout: float = 5.0) -> bool:
    """Poll until the server stops answering, or the timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            requests.get(url, timeout=0.5)
        except requests.ConnectionError:
            return True
        time.sleep(0.1)
    return False


def test_serve_boots_answers_and_shuts_down(tmp_path):
    """Start `cf serve`, assert the health contract, then stop it."""
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"

    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()

    env = os.environ.copy()
    env["DATABASE_PATH"] = str(tmp_path / "test.db")
    # The v2 server refuses to start with auth enforced and no workspace
    # allowlist (#655/#896) — an empty allowlist would let any authenticated
    # user open a shell in any host directory.
    env["WORKSPACE_ROOT"] = str(workspace_root)

    process = subprocess.Popen(
        ["uv", "run", "codeframe", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env=env,
    )

    try:
        response = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                pytest.fail(
                    f"`cf serve` exited with {process.returncode}\n"
                    f"stderr: {stderr.decode(errors='replace')}\n"
                    f"stdout: {stdout.decode(errors='replace')}"
                )
            try:
                response = requests.get(url, timeout=1)
                break
            except requests.ConnectionError:
                time.sleep(0.1)

        assert response is not None, "`cf serve` never answered within 30s"
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        assert response.json() == {"status": "online", "service": "CodeFRAME API"}

        # Shutting the process group down must actually stop the listener.
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        assert process.wait(timeout=10) is not None
        assert _wait_until_gone(url), "server still answering after SIGTERM"

    finally:
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        process.communicate()
