"""Integration tests for server access and lifecycle."""

import os
import signal
import subprocess
import time
from typing import Optional

import pytest
import requests


class TestServerAccess:
    """Integration tests for server lifecycle and accessibility."""

    @pytest.fixture
    def test_port(self) -> int:
        """Use a unique test port to avoid conflicts."""
        import socket

        # Find an available port dynamically
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))  # Bind to port 0 to get a random available port
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = s.getsockname()[1]
        return port

    @pytest.fixture
    def server_process(self, test_port: int):
        """Start server process for testing, clean up after."""
        process: Optional[subprocess.Popen] = None
        try:
            # Start server in subprocess with new process session
            process = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "codeframe",
                    "serve",
                    "--port",
                    str(test_port),
                    "--no-browser",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Create new process session for proper cleanup
            )

            # Wait for server to start (max 5 seconds)
            for _ in range(50):
                # Check if process crashed during startup
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    raise RuntimeError(
                        f"Server process exited with code {process.returncode}\n"
                        f"stderr: {stderr.decode() if stderr else 'N/A'}\n"
                        f"stdout: {stdout.decode() if stdout else 'N/A'}"
                    )

                try:
                    response = requests.get(f"http://localhost:{test_port}", timeout=1)
                    if response.status_code == 200:
                        break
                except requests.ConnectionError:
                    pass
                time.sleep(0.1)

            yield process

        finally:
            # Clean up: terminate entire process group (parent + all children)
            if process:
                try:
                    # Kill entire process group (parent + all children)
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)

                    # Wait for graceful shutdown
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # Force kill if graceful shutdown failed
                        os.killpg(pgid, signal.SIGKILL)
                        process.wait()

                except (ProcessLookupError, PermissionError, OSError):
                    # Process already dead or no permission
                    pass

                # Fallback: ensure no uvicorn processes remain on test port
                try:
                    subprocess.run(
                        ["pkill", "-9", "-f", f"uvicorn.*{test_port}"],
                        timeout=1,
                        capture_output=True,
                    )
                except Exception:
                    pass  # Best effort cleanup

    def test_dashboard_accessible_after_serve(
        self, server_process: subprocess.Popen, test_port: int
    ):
        """Test that server is accessible after serve command starts."""
        # Server should be running (started by fixture)
        assert server_process.poll() is None, "Server process should be running"

        # Make HTTP request to root endpoint
        response = requests.get(f"http://localhost:{test_port}", timeout=5)

        # Should get 200 OK
        assert response.status_code == 200, "Server should return 200 OK"

        # Response should be JSON (health check endpoint)
        assert "application/json" in response.headers.get(
            "content-type", ""
        ), "Should return JSON content"

        # Verify response contains expected health check fields
        data = response.json()
        assert "status" in data, "Response should contain status field"
        assert data["status"] == "online", "Server status should be online"

    def test_serve_command_lifecycle(self, server_process: subprocess.Popen, test_port: int):
        """Test complete server lifecycle: start, verify, stop."""
        # Verify server is running
        assert server_process.poll() is None, "Server should be running"

        # Verify server responds to requests
        response = requests.get(f"http://localhost:{test_port}", timeout=5)
        assert response.status_code == 200

        # Stop server (kill entire process group)
        try:
            pgid = os.getpgid(server_process.pid)
            os.killpg(pgid, signal.SIGTERM)
            server_process.wait(timeout=5)
        except (ProcessLookupError, OSError):
            pass  # Process already dead

        # Verify server stopped
        assert server_process.poll() is not None, "Server should have stopped"

        # Fallback cleanup: ensure no uvicorn processes remain
        subprocess.run(
            ["pkill", "-9", "-f", f"uvicorn.*{test_port}"], capture_output=True, timeout=1
        )

        # Verify server no longer responding (exponential backoff)
        max_attempts = 10
        backoff = 0.1
        for attempt in range(max_attempts):
            try:
                requests.get(f"http://localhost:{test_port}", timeout=0.5)
                if attempt < max_attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2  # Exponential backoff (0.1s → 0.2s → 0.4s → 0.8s → 1.6s)
                else:
                    pytest.fail("Server still responding after termination")
            except requests.ConnectionError:
                break  # Server is down, test passes
