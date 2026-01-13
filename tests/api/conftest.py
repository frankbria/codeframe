"""Shared pytest fixtures for API tests.

This conftest provides class-scoped fixtures to optimize API test performance
by reducing the number of server reloads from per-test to per-test-class.
"""

import jwt
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="class")
def class_temp_dir() -> Generator[Path, None, None]:
    """Provide a class-scoped temporary directory for testing.

    This fixture is shared across all tests in a test class to reduce setup overhead.

    Yields:
        Path to temporary directory that will be cleaned up after all tests in the class.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(scope="class")
def class_temp_db_path(class_temp_dir: Path) -> Path:
    """Provide a class-scoped temporary database path.

    Args:
        class_temp_dir: Class-scoped temporary directory fixture

    Returns:
        Path to temporary database file shared across test class
    """
    return class_temp_dir / "test.db"


def create_test_jwt_token(user_id: int = 1, secret: str = None) -> str:
    """Create a JWT token for test authentication.

    Args:
        user_id: User ID to encode in token
        secret: JWT secret (uses default if not provided)

    Returns:
        JWT token string
    """
    from codeframe.auth.manager import SECRET, JWT_LIFETIME_SECONDS

    if secret is None:
        secret = SECRET

    payload = {
        "sub": str(user_id),  # User ID as string
        "aud": ["fastapi-users:auth"],
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_LIFETIME_SECONDS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(scope="class")
def api_client(class_temp_db_path: Path) -> Generator[TestClient, None, None]:
    """Provide a class-scoped TestClient for API tests with authentication.

    This fixture sets up the environment and reloads the FastAPI server once per test class
    instead of once per test, reducing test execution time from ~10 minutes to ~1 minute.

    Performance improvement: 80-90% speedup on API test suite.

    Args:
        class_temp_db_path: Class-scoped temporary database path

    Yields:
        Configured TestClient instance with authentication headers for making API requests
    """
    # Capture original environment state for cleanup
    env_vars_to_restore = [
        "DATABASE_PATH",
        "WORKSPACE_ROOT",
        "ANTHROPIC_API_KEY",
    ]
    original_env = {}
    for var in env_vars_to_restore:
        if var in os.environ:
            original_env[var] = os.environ[var]

    # Set environment variables for this test class
    os.environ["DATABASE_PATH"] = str(class_temp_db_path)

    # Set temporary workspace root to avoid collisions
    workspace_root = class_temp_db_path.parent / "workspaces"
    os.environ["WORKSPACE_ROOT"] = str(workspace_root)

    # Set test API key for discovery endpoints
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    # Reset auth engine to pick up new DATABASE_PATH
    from codeframe.auth.manager import reset_auth_engine
    reset_auth_engine()

    # Reload server module to pick up environment changes
    # This happens ONCE per test class instead of per test
    from codeframe.ui import server
    from importlib import reload

    reload(server)

    # Create and yield TestClient
    with TestClient(server.app) as client:
        # Ensure default admin user exists (id=1) for test authentication
        db = server.app.state.db
        cursor = db.conn.cursor()

        # Insert or replace default admin user (FastAPI Users schema)
        # hashed_password uses a placeholder that cannot match any bcrypt hash
        cursor.execute(
            """
            INSERT OR REPLACE INTO users (
                id, email, name, hashed_password,
                is_active, is_superuser, is_verified, email_verified
            )
            VALUES (1, 'admin@localhost', 'Admin User', '!DISABLED!', 1, 1, 1, 1)
            """
        )
        db.conn.commit()

        # Create JWT token for test authentication
        test_token = create_test_jwt_token(user_id=1)

        # Add authentication header to all requests
        client.headers["Authorization"] = f"Bearer {test_token}"

        # Patch Database.create_project to inject user_id=1 when not provided
        original_create_project = db.create_project

        def patched_create_project(
            name: str,
            description: str,
            source_type: str = "empty",
            source_location: str = None,
            source_branch: str = "main",
            workspace_path: str = None,
            user_id: int = None,
            **kwargs,
        ) -> int:
            # Default to admin user (id=1) if no user_id provided
            if user_id is None:
                user_id = 1
            return original_create_project(
                name=name,
                description=description,
                source_type=source_type,
                source_location=source_location,
                source_branch=source_branch,
                workspace_path=workspace_path,
                user_id=user_id,
                **kwargs,
            )

        db.create_project = patched_create_project

        yield client

    # Restore original environment state
    for var in env_vars_to_restore:
        if var in original_env:
            os.environ[var] = original_env[var]
        elif var in os.environ:
            os.environ.pop(var)

    # Reset auth engine so next test class gets fresh engine with correct DB path
    reset_auth_engine()


@pytest.fixture(autouse=True)
def clean_database_between_tests(api_client: TestClient) -> Generator[None, None, None]:
    """Automatically clean the database after each test.

    This autouse fixture runs after each test and clears all database tables
    to ensure test isolation while maintaining the performance benefits of
    class-scoped fixtures.

    Args:
        api_client: Class-scoped TestClient (ensures it's set up first)

    Yields:
        None
    """
    # Let the test run first
    yield

    # Clean the database after the test completes
    # Get the app from the client
    from codeframe.ui import server
    import shutil

    # Clear all data from database after each test
    # Delete in reverse dependency order to avoid foreign key constraint violations
    if hasattr(server.app.state, "db"):
        db = server.app.state.db
        cursor = db.conn.cursor()

        # Delete all rows from tables (in reverse dependency order)
        cursor.execute("DELETE FROM code_reviews")
        cursor.execute("DELETE FROM token_usage")
        cursor.execute("DELETE FROM context_items")
        cursor.execute("DELETE FROM checkpoints")
        cursor.execute("DELETE FROM memory")
        cursor.execute("DELETE FROM blockers")
        cursor.execute("DELETE FROM changelog")  # References projects, tasks
        cursor.execute("DELETE FROM tasks")
        cursor.execute("DELETE FROM git_branches")  # Must be before issues (FK constraint)
        cursor.execute("DELETE FROM issues")
        cursor.execute("DELETE FROM project_agents")  # Multi-agent junction table
        cursor.execute("DELETE FROM agents")
        cursor.execute("DELETE FROM sessions")  # Auth sessions
        cursor.execute("DELETE FROM project_users")  # Project-user relationships
        cursor.execute("DELETE FROM projects")
        # Note: Keep users table (especially default admin user with id=1)

        db.conn.commit()

    # Clean up workspace files
    workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "/tmp/workspaces"))
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
