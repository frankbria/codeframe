"""
Pytest configuration and fixtures for UI/WebSocket tests.

This module provides test fixtures for running WebSocket tests with a real
FastAPI server instead of TestClient's mocked WebSocket connections.
"""

import jwt
import os
import secrets
import signal
import socket
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytest
import requests
import shutil

from codeframe.persistence.database import Database


def create_test_jwt_token(user_id: int = 1, secret: str = None) -> str:
    """Create a JWT token for testing.

    Args:
        user_id: User ID to include in the token
        secret: JWT secret (uses default from auth manager if not provided)

    Returns:
        JWT token string
    """
    from codeframe.auth.manager import SECRET, JWT_LIFETIME_SECONDS

    if secret is None:
        secret = SECRET

    payload = {
        "sub": str(user_id),
        "aud": ["fastapi-users:auth"],
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_LIFETIME_SECONDS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


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


def create_test_session_token(db: Database, user_id: int = 1) -> str:
    """Create a session token for WebSocket authentication.

    Args:
        db: Database instance
        user_id: User ID for the session

    Returns:
        Session token string
    """
    token = secrets.token_urlsafe(32)
    session_id = f"test-session-{secrets.token_hex(8)}"
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    db.conn.execute(
        """
        INSERT INTO sessions (id, token, user_id, expires_at)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, token, user_id, expires_at),
    )
    db.conn.commit()

    return token


@pytest.fixture(scope="module")
def running_server():
    """Start a real FastAPI server for WebSocket testing.

    This fixture:
    - Creates temporary database and workspace directories
    - Sets up test environment variables
    - Initializes database with test user, project, and session token
    - Starts server in a subprocess using codeframe serve command
    - Waits for server to be ready
    - Yields tuple of (server_url, session_token)
    - Cleans up on teardown

    Yields:
        tuple: (Server URL, Session token for WebSocket auth)
    """
    # Create temporary directories
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    workspace_root = temp_dir / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)

    # Initialize database
    db = Database(db_path)
    db.initialize()

    # Create test user (user_id=1) - FastAPI Users schema
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (1, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """
    )
    db.conn.commit()

    # Create JWT token for WebSocket authentication
    # Note: WebSocket uses JWT tokens (same as HTTP endpoints) since FastAPI Users migration
    session_token = create_test_jwt_token(user_id=1)

    # Create test projects (project_id=1, 2, 3)
    for project_id in [1, 2, 3]:
        try:
            db.create_project(
                name=f"Test Project {project_id}",
                description=f"Test project {project_id} for WebSocket tests",
                workspace_path=str(workspace_root / str(project_id)),
                user_id=1,
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

        yield (server_url, session_token)

    finally:
        # Clean up: terminate entire process group (parent + all children)
        if process:
            try:
                # Kill entire process group (parent + all children)
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)

                # Wait for graceful shutdown and drain pipes
                # IMPORTANT: communicate() drains stdout/stderr pipes to prevent
                # Python's internal reader threads from hanging
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown failed
                    os.killpg(pgid, signal.SIGKILL)
                    process.communicate()  # Still drain pipes after force kill

            except (ProcessLookupError, PermissionError, OSError):
                # Process already dead or no permission - still close pipes
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

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
    """Get the complete WebSocket URL with path and authentication token.

    Returns the full WebSocket URL ready to use for connection.

    Args:
        running_server: Tuple of (Server URL, Session token)

    Returns:
        str: Complete WebSocket URL (e.g., "ws://localhost:8080/ws?token=...")

    Example usage in tests:
        async with websockets.connect(ws_url) as websocket:
            ...
    """
    server_url, session_token = running_server
    base_ws_url = server_url.replace("http://", "ws://")
    return f"{base_ws_url}/ws?token={session_token}"


@pytest.fixture
def session_token(running_server):
    """Get the session token for authenticated requests.

    Args:
        running_server: Tuple of (Server URL, Session token)

    Returns:
        str: Session token
    """
    _, token = running_server
    return token


@pytest.fixture
def server_url(running_server):
    """Get the HTTP server URL.

    Args:
        running_server: Tuple of (Server URL, Session token)

    Returns:
        str: Server URL (e.g., "http://localhost:8080")
    """
    url, _ = running_server
    return url
