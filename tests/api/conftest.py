"""Shared pytest fixtures for API tests.

This conftest provides class-scoped fixtures to optimize API test performance
by reducing the number of server reloads from per-test to per-test-class.
"""

import os
import tempfile
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


@pytest.fixture(scope="class")
def api_client(class_temp_db_path: Path) -> Generator[TestClient, None, None]:
    """Provide a class-scoped TestClient for API tests.

    This fixture sets up the environment and reloads the FastAPI server once per test class
    instead of once per test, reducing test execution time from ~10 minutes to ~1 minute.

    Performance improvement: 80-90% speedup on API test suite.

    Args:
        class_temp_db_path: Class-scoped temporary database path

    Yields:
        Configured TestClient instance for making API requests
    """
    # Capture original environment state for cleanup
    env_vars_to_restore = ["DATABASE_PATH", "WORKSPACE_ROOT", "ANTHROPIC_API_KEY"]
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

    # Reload server module to pick up environment changes
    # This happens ONCE per test class instead of per test
    from codeframe.ui import server
    from importlib import reload

    reload(server)

    # Create and yield TestClient
    with TestClient(server.app) as client:
        yield client
    
    # Restore original environment state
    for var in env_vars_to_restore:
        if var in original_env:
            os.environ[var] = original_env[var]
        elif var in os.environ:
            os.environ.pop(var)


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
        cursor.execute("DELETE FROM tasks")
        cursor.execute("DELETE FROM issues")
        cursor.execute("DELETE FROM project_agents")  # Multi-agent junction table
        cursor.execute("DELETE FROM agents")
        cursor.execute("DELETE FROM projects")

        db.conn.commit()

    # Clean up workspace files
    workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "/tmp/workspaces"))
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
        workspace_root.mkdir(parents=True, exist_ok=True)
