"""Integration tests for server access and lifecycle."""

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
        return 9999

    @pytest.fixture
    def server_process(self, test_port: int):
        """Start server process for testing, clean up after."""
        process: Optional[subprocess.Popen] = None
        try:
            # Start server in subprocess
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
            )

            # Wait for server to start (max 5 seconds)
            for _ in range(50):
                try:
                    response = requests.get(f"http://localhost:{test_port}", timeout=1)
                    if response.status_code == 200:
                        break
                except requests.ConnectionError:
                    pass
                time.sleep(0.1)

            yield process

        finally:
            # Clean up: terminate server process and all child processes
            if process:
                # Try graceful termination first
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful termination didn't work
                    process.kill()
                    process.wait()

                # Additional cleanup: kill any remaining uvicorn processes on test port
                try:
                    subprocess.run(
                        ["pkill", "-f", f"uvicorn.*{test_port}"],
                        timeout=1,
                        capture_output=True,
                    )
                except Exception:
                    pass  # Ignore cleanup errors

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
        assert "application/json" in response.headers.get("content-type", ""), "Should return JSON content"

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

        # Stop server (send SIGTERM)
        server_process.terminate()
        server_process.wait(timeout=5)

        # Verify server stopped
        assert server_process.poll() is not None, "Server should have stopped"

        # Kill any remaining uvicorn child processes
        subprocess.run(
            ["pkill", "-f", f"uvicorn.*{test_port}"], capture_output=True, timeout=1
        )

        # Verify server no longer responding (wait up to 2 seconds for port to release)
        time.sleep(1)
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                requests.get(f"http://localhost:{test_port}", timeout=0.5)
                if attempt < max_attempts - 1:
                    time.sleep(0.2)  # Wait a bit more
                else:
                    pytest.fail("Server still responding after termination")
            except requests.ConnectionError:
                break  # Server is down, test passes
