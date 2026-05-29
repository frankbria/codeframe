"""
Integration Test Fixtures for CodeFRAME

Provides shared fixtures for integration tests that use real implementations:
- Real SQLite database (in-memory or temp file)
- Real file system operations in temp directories
- Real subprocess execution for quality gates
- Mock only external services (Anthropic, OpenAI, GitHub APIs)

Usage:
    @pytest.mark.integration
    async def test_something(real_db, test_workspace, mock_llm_api):
        # Your test using real database and workspace
        pass
"""

import json
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codeframe.persistence.database import Database


# =============================================================================
# Database Fixtures
# =============================================================================


@pytest.fixture
def real_db() -> Generator[Database, None, None]:
    """Create a real in-memory SQLite database with full schema.

    This fixture provides a real database instance for integration testing.
    The database is isolated per test and cleaned up automatically.

    Yields:
        Database: A fully initialized in-memory database instance.
    """
    db = Database(":memory:")
    db.initialize()
    yield db
    if db.conn:
        db.conn.close()


@pytest.fixture
def real_db_file(tmp_path: Path) -> Generator[Database, None, None]:
    """Create a real SQLite database file for persistence testing.

    Use this fixture when you need to test database persistence across
    multiple database connections or process restarts.

    Args:
        tmp_path: Pytest temp directory fixture

    Yields:
        Database: A file-backed database instance.
    """
    db_path = tmp_path / "test_codeframe.db"
    db = Database(str(db_path))
    db.initialize()
    yield db
    if db.conn:
        db.conn.close()


# =============================================================================
# File System Fixtures
# =============================================================================


@pytest.fixture
def test_workspace(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temp directory for file operations.

    This fixture provides an isolated workspace for each test,
    mimicking a real project workspace.

    Yields:
        Path: Path to temp workspace directory.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)

    # Create standard project structure
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()

    yield workspace

    # Cleanup (handled by pytest tmp_path automatically)


@pytest.fixture
def python_project_workspace(test_workspace: Path) -> Path:
    """Create a workspace with Python project structure.

    Creates:
    - pyproject.toml
    - src/ directory with sample module
    - tests/ directory with sample test

    Args:
        test_workspace: Base workspace fixture

    Returns:
        Path: Path to Python project workspace.
    """
    # Create pyproject.toml
    pyproject = {
        "project": {
            "name": "test-project",
            "version": "0.1.0",
            "requires-python": ">=3.11",
        },
        "tool": {
            "pytest": {"testpaths": ["tests"]},
            "ruff": {"line-length": 100},
        },
    }
    (test_workspace / "pyproject.toml").write_text(
        "[project]\nname = 'test-project'\nversion = '0.1.0'\n"
    )

    # Create sample module
    (test_workspace / "src" / "module.py").write_text(
        'def hello(name: str) -> str:\n    """Return greeting."""\n    return f"Hello, {name}!"\n'
    )

    # Create sample test
    (test_workspace / "tests" / "test_module.py").write_text(
        'from src.module import hello\n\ndef test_hello():\n    assert hello("World") == "Hello, World!"\n'
    )

    return test_workspace


@pytest.fixture
def typescript_project_workspace(test_workspace: Path) -> Path:
    """Create a workspace with TypeScript project structure.

    Creates:
    - package.json
    - tsconfig.json
    - src/ directory with sample module
    - tests/ directory with sample test

    Args:
        test_workspace: Base workspace fixture

    Returns:
        Path: Path to TypeScript project workspace.
    """
    # Create package.json
    package_json = {
        "name": "test-project",
        "version": "0.1.0",
        "scripts": {
            "test": "jest",
            "build": "tsc",
        },
        "devDependencies": {
            "typescript": "^5.0.0",
            "jest": "^29.0.0",
        },
    }
    (test_workspace / "package.json").write_text(json.dumps(package_json, indent=2))

    # Create tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "target": "ES2020",
            "module": "commonjs",
            "strict": True,
            "outDir": "./dist",
        },
        "include": ["src/**/*"],
    }
    (test_workspace / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2))

    # Create sample module
    (test_workspace / "src" / "module.ts").write_text(
        'export function hello(name: string): string {\n  return `Hello, ${name}!`;\n}\n'
    )

    return test_workspace


# =============================================================================
# External API Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_anthropic_api():
    """Mock Anthropic API for integration tests.

    This fixture provides a mock Anthropic client that returns realistic
    responses without making actual API calls.

    Use this for integration tests that need to test agent behavior
    without incurring API costs.

    Yields:
        Mock: Mock Anthropic client with configured responses.
    """
    with patch("anthropic.AsyncAnthropic") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client

        # Default successful response
        def create_response(content: str = "Task completed successfully."):
            response = Mock()
            response.content = [Mock(text=content)]
            response.usage = Mock(input_tokens=100, output_tokens=50)
            return response

        mock_client.messages.create = AsyncMock(return_value=create_response())

        yield mock_client


@pytest.fixture
def mock_llm_response_factory(mock_anthropic_api):
    """Factory fixture for creating custom LLM responses.

    Use this to configure specific responses for different test scenarios.

    Example:
        def test_something(mock_llm_response_factory):
            response = mock_llm_response_factory(
                content='{"files": [...], "explanation": "Done"}'
            )
            # mock_anthropic_api now returns this response
    """

    def factory(content: str, input_tokens: int = 100, output_tokens: int = 50):
        response = Mock()
        response.content = [Mock(text=content)]
        response.usage = Mock(input_tokens=input_tokens, output_tokens=output_tokens)
        mock_anthropic_api.messages.create.return_value = response
        return response

    return factory


# =============================================================================
# Agent Fixtures
# =============================================================================


# =============================================================================
# Environment Fixtures
# =============================================================================


@pytest.fixture
def clean_env(monkeypatch):
    """Provide a clean environment for testing.

    Clears CODEFRAME environment variables and provides helpers.

    Args:
        monkeypatch: Pytest monkeypatch fixture

    Returns:
        dict: Environment helpers.
    """
    # Clear existing environment variables
    vars_to_clear = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DATABASE_PATH",
        "API_HOST",
        "API_PORT",
    ]
    for var in vars_to_clear:
        monkeypatch.delenv(var, raising=False)

    # Set test API key
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-integration-key")

    return {"monkeypatch": monkeypatch}


# =============================================================================
# Quality Gates Fixtures
# =============================================================================


# =============================================================================
# Markers
# =============================================================================


def pytest_configure(config):
    """Add custom markers for integration tests."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "requires_subprocess: mark test as requiring subprocess execution"
    )
