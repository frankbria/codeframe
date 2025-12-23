"""
Pytest configuration and fixtures for UI/WebSocket tests.

This module provides test fixtures for running WebSocket tests with a real
FastAPI server instead of TestClient's mocked WebSocket connections.
"""

import os
import signal
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest
import requests
import shutil

from codeframe.persistence.database import Database


def find_free_port() -> int:
    """Find and return a free port number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def wait_for_server(url: str, timeout: float = 10.0) -> bool:
    """Wait for server to be ready by polling root endpoint.

    Args:
        url: Base URL of server (e.g., http://localhost:8080)
        timeout: Maximum time to wait in seconds

    Returns:
        True if server is ready, False if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1.0)
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.1)

    return False


@pytest.fixture(scope="module")
def running_server():
    """Start a real FastAPI server for WebSocket testing.

    This fixture:
    - Creates temporary database and workspace directories
    - Sets up test environment variables
    - Initializes database with test user and project
    - Starts server in a subprocess using codeframe serve command
    - Waits for server to be ready
    - Yields server URL
    - Cleans up on teardown

    Yields:
        str: Server URL (e.g., "http://localhost:8080")
    """
    # Create temporary directories
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)

    # Initialize database
    db = Database(db_path)
    db.initialize()

    # Create test user (user_id=1)
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (id, email, password_hash, name, created_at)
        VALUES (1, 'test@example.com', 'hashed_password', 'Test User', ?)
        """,
        (datetime.now(timezone.utc).isoformat(),)
    )
    db.conn.commit()

    # Create test project (project_id=1)
    try:
        db.create_project(
            name="Test Project",
            description="Test project for WebSocket tests",
            workspace_path=str(workspace_root / "1"),
            user_id=1
        )
        db.conn.commit()
    except Exception:
        # Project might already exist, that's OK
        pass

    # Close the database before server starts (server will re-open it)
    db.close()

    # Find free port
    port = find_free_port()
    server_url = f"http://localhost:{port}"

    # Prepare environment for subprocess
    env = os.environ.copy()
    env["DATABASE_PATH"] = str(db_path)
    env["WORKSPACE_ROOT"] = str(workspace_root)
    env["AUTH_REQUIRED"] = "false"

    # Start server in subprocess
    process: Optional[subprocess.Popen] = None
    try:
        process = subprocess.Popen(
            ["uv", "run", "codeframe", "serve", "--port", str(port), "--no-browser"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # Create new process session for proper cleanup
            env=env,
        )

        # Wait for server to start (max 15 seconds)
        server_started = False
        for i in range(150):
            # Check if process crashed during startup
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise RuntimeError(
                    f"Server process exited with code {process.returncode}\n"
                    f"stderr: {stderr.decode() if stderr else 'N/A'}\n"
                    f"stdout: {stdout.decode() if stdout else 'N/A'}"
                )

            # Try to connect to server
            if wait_for_server(server_url, timeout=0.1):
                server_started = True
                break

            time.sleep(0.1)

        if not server_started:
            raise RuntimeError(f"Server failed to start within 15 seconds at {server_url}")

        yield server_url

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
                    ["pkill", "-9", "-f", f"uvicorn.*{port}"],
                    timeout=1,
                    capture_output=True,
                )
            except Exception:
                pass  # Best effort cleanup

        # Cleanup temporary directories
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def ws_url(running_server):
    """Convert HTTP server URL to WebSocket URL.

    Args:
        running_server: Server URL fixture (e.g., "http://localhost:8080")

    Returns:
        str: WebSocket URL (e.g., "ws://localhost:8080")
    """
    return running_server.replace("http://", "ws://")
