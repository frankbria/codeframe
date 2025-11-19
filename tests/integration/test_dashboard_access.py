"""Integration tests for dashboard server access."""

import subprocess
import time
from typing import Optional

import pytest
import requests


class TestDashboardAccess:
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
            # Clean up: terminate server process
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    def test_dashboard_accessible_after_serve(
        self, server_process: subprocess.Popen, test_port: int
    ):
        """Test that dashboard is accessible after serve command starts."""
        # Server should be running (started by fixture)
        assert server_process.poll() is None, "Server process should be running"

        # Make HTTP request to dashboard
        response = requests.get(f"http://localhost:{test_port}", timeout=5)

        # Should get 200 OK
        assert response.status_code == 200, "Dashboard should return 200 OK"

        # Response should contain HTML
        assert "text/html" in response.headers.get("content-type", ""), "Should return HTML content"

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

        # Verify server no longer responding
        time.sleep(0.5)  # Give port time to release
        with pytest.raises(requests.ConnectionError):
            requests.get(f"http://localhost:{test_port}", timeout=1)
