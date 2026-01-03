"""Shared pytest fixtures for CodeFRAME tests."""

import jwt
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator
import pytest


def create_test_jwt_token(user_id: int = 1, secret: str = None) -> str:
    """Create a JWT token for testing.

    This is a shared helper function for creating test authentication tokens.
    Can be imported by any test module.

    Args:
        user_id: User ID to include in the token (default: 1)
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


def setup_test_user(db, user_id: int = 1) -> None:
    """Create a test user in the database.

    Args:
        db: Database instance
        user_id: User ID to create (default: 1)
    """
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (?, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """,
        (user_id,),
    )
    db.conn.commit()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for testing.

    Yields:
        Path to temporary directory that will be cleaned up after test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db_path(temp_dir: Path) -> Path:
    """Provide a temporary database path.

    Args:
        temp_dir: Temporary directory fixture

    Returns:
        Path to temporary database file
    """
    return temp_dir / "test.db"


@pytest.fixture
def mock_env(monkeypatch) -> dict[str, str]:
    """Provide a clean environment for testing.

    Clears all CODEFRAME-related environment variables and provides
    a dictionary for setting test values.

    Args:
        monkeypatch: Pytest monkeypatch fixture

    Returns:
        Dictionary for setting environment variables
    """
    # Clear existing CodeFRAME environment variables
    env_vars_to_clear = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DATABASE_PATH",
        "API_HOST",
        "API_PORT",
        "LOG_LEVEL",
        "DEBUG",
    ]

    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)

    env = {}

    def set_env(key: str, value: str) -> None:
        """Set environment variable."""
        env[key] = value
        monkeypatch.setenv(key, value)

    # Provide helper method
    env["_set"] = set_env
    return env


@pytest.fixture
def sample_project_config() -> dict:
    """Provide sample project configuration data.

    Returns:
        Dictionary with valid project configuration
    """
    return {
        "project_name": "test-project",
        "project_type": "python",
        "providers": {
            "lead_agent": "claude",
            "backend_agent": "claude",
            "frontend_agent": "gpt4",
        },
        "agent_policy": {
            "require_review_below_maturity": "supporting",
            "allow_full_autonomy": False,
        },
        "interruption_mode": {
            "enabled": True,
            "sync_blockers": ["requirement", "security"],
            "async_blockers": ["technical", "external"],
        },
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset any singleton instances between tests.

    This ensures tests don't interfere with each other through
    shared state in singleton objects.
    """
    # Add singleton resets here as needed
    # For example:
    # Database._instance = None
    # Config._instance = None
    yield
    # Cleanup after test


@pytest.fixture
def anthropic_api_key(mock_env) -> str:
    """Provide a mock Anthropic API key.

    Args:
        mock_env: Mock environment fixture

    Returns:
        Test API key string
    """
    key = "sk-ant-test-key-12345"
    mock_env["_set"]("ANTHROPIC_API_KEY", key)
    return key


@pytest.fixture
def openai_api_key(mock_env) -> str:
    """Provide a mock OpenAI API key.

    Args:
        mock_env: Mock environment fixture

    Returns:
        Test API key string
    """
    key = "sk-test-key-67890"
    mock_env["_set"]("OPENAI_API_KEY", key)
    return key


# Markers for test organization
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "requires_api_key: mark test as requiring real API keys")
    config.addinivalue_line("markers", "requires_db: mark test as requiring database")


# Test collection customization
def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Auto-mark tests in integration/ directory
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Auto-mark slow tests (tests that take >5 seconds)
        if hasattr(item, "callspec"):
            if any("slow" in str(fixture) for fixture in item.callspec.params.values()):
                item.add_marker(pytest.mark.slow)


# Skip tests requiring real API keys in CI
def pytest_runtest_setup(item):
    """Run setup for each test item."""
    # Skip tests requiring API keys if not in environment
    if "requires_api_key" in [marker.name for marker in item.iter_markers()]:
        if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            pytest.skip("Requires real API key (not available in environment)")
