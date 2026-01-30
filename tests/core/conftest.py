"""Pytest configuration for core tests.

All tests in tests/core/ are v2 (CLI-first, headless) functionality.
"""

import os
import shutil
from pathlib import Path
from typing import Generator

import pytest


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in this directory as v2."""
    for item in items:
        # Check if the test is in the core directory
        if "/tests/core/" in str(item.fspath):
            item.add_marker(pytest.mark.v2)


# =============================================================================
# Integration Test Fixtures
# =============================================================================

# Test-specific keyring service name to avoid conflicts
TEST_KEYRING_SERVICE = "codeframe-test-integration"


@pytest.fixture
def integration_storage_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide isolated storage directory for credential integration tests.

    Creates a temporary directory for credential storage that is
    automatically cleaned up after the test.
    """
    storage_dir = tmp_path / ".codeframe-test"
    storage_dir.mkdir(parents=True, exist_ok=True)
    yield storage_dir
    # Cleanup is handled by tmp_path fixture


@pytest.fixture
def integration_credential_store(integration_storage_dir: Path):
    """Provide CredentialStore for integration testing with test storage.

    Uses a dedicated test storage directory to avoid polluting the
    user's actual credential storage.
    """
    from codeframe.core.credentials import CredentialStore

    store = CredentialStore(storage_dir=integration_storage_dir)
    return store


@pytest.fixture
def cleanup_test_keyring():
    """Clean up test keyring entries after test.

    Yields the test service name, then cleans up any credentials
    stored under that service after the test completes.
    """
    from codeframe.core.credentials import (
        CredentialProvider,
        KEYRING_AVAILABLE,
    )

    yield TEST_KEYRING_SERVICE

    # Cleanup: remove any test credentials from keyring
    if KEYRING_AVAILABLE:
        try:
            import keyring
            for provider in CredentialProvider:
                try:
                    keyring.delete_password(TEST_KEYRING_SERVICE, provider.name)
                except Exception:
                    pass  # Credential may not exist
        except ImportError:
            pass


@pytest.fixture(scope="session")
def available_system_tools() -> dict[str, bool]:
    """Detect available tools on the system once per session.

    Returns a dictionary mapping tool names to availability status.
    This is cached for the session to avoid repeated subprocess calls.
    """
    tools_to_check = [
        "git", "python", "python3", "pytest", "ruff", "npm", "node",
        "cargo", "docker", "uv", "pip"
    ]

    available = {}
    for tool in tools_to_check:
        available[tool] = shutil.which(tool) is not None

    return available


@pytest.fixture
def skip_if_no_git(available_system_tools):
    """Skip test if git is not available."""
    if not available_system_tools.get("git"):
        pytest.skip("git not available on system")


@pytest.fixture
def skip_if_no_python(available_system_tools):
    """Skip test if python is not available."""
    if not available_system_tools.get("python") and not available_system_tools.get("python3"):
        pytest.skip("python not available on system")


@pytest.fixture
def real_python_project(tmp_path: Path) -> Path:
    """Create a realistic Python project structure for testing.

    Returns the path to the project directory.
    """
    project_dir = tmp_path / "test_python_project"
    project_dir.mkdir()

    # Create pyproject.toml
    (project_dir / "pyproject.toml").write_text('''[project]
name = "test-project"
version = "0.1.0"
description = "A test project"
requires-python = ">=3.8"
dependencies = [
    "pytest>=7.0.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
''')

    # Create source directory
    src_dir = project_dir / "src" / "test_project"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (src_dir / "main.py").write_text('def main(): pass\n')

    # Create tests directory
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_main.py").write_text('def test_placeholder(): pass\n')

    return project_dir


@pytest.fixture
def real_js_project(tmp_path: Path) -> Path:
    """Create a realistic JavaScript project structure for testing.

    Returns the path to the project directory.
    """
    project_dir = tmp_path / "test_js_project"
    project_dir.mkdir()

    # Create package.json
    (project_dir / "package.json").write_text('''{
  "name": "test-js-project",
  "version": "1.0.0",
  "description": "A test JavaScript project",
  "main": "index.js",
  "scripts": {
    "test": "jest",
    "lint": "eslint ."
  },
  "dependencies": {},
  "devDependencies": {
    "jest": "^29.0.0",
    "eslint": "^8.0.0"
  }
}
''')

    # Create source file
    (project_dir / "index.js").write_text('module.exports = {};\n')

    return project_dir


@pytest.fixture
def real_rust_project(tmp_path: Path) -> Path:
    """Create a realistic Rust project structure for testing.

    Returns the path to the project directory.
    """
    project_dir = tmp_path / "test_rust_project"
    project_dir.mkdir()

    # Create Cargo.toml
    (project_dir / "Cargo.toml").write_text('''[package]
name = "test-rust-project"
version = "0.1.0"
edition = "2021"

[dependencies]
''')

    # Create src directory with main.rs
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.rs").write_text('fn main() { println!("Hello!"); }\n')

    return project_dir


@pytest.fixture
def env_without_anthropic_key():
    """Temporarily remove ANTHROPIC_API_KEY from environment.

    Useful for testing credential fallback behavior.
    """
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    yield
    if original is not None:
        os.environ["ANTHROPIC_API_KEY"] = original
