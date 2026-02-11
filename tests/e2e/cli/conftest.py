"""E2E CLI test fixtures and markers.

Tests in this directory exercise the full CLI → core → adapter pipeline
against a real project (cf-test). Tests marked with `e2e_llm` make real
API calls and should be run explicitly: `uv run pytest -m e2e_llm`.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import pytest

CF_TEST_PROJECT = Path(
    os.getenv("CF_TEST_PROJECT", Path.home() / "projects" / "cf-test")
)
CODEFRAME_ROOT = Path(
    os.getenv("CODEFRAME_ROOT", Path.home() / "projects" / "codeframe")
)


def _ensure_api_key() -> None:
    """Eagerly load ANTHROPIC_API_KEY from .env if not already set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_file = CODEFRAME_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["ANTHROPIC_API_KEY"] = key
                return


# Load API key at import time so subprocesses inherit it
_ensure_api_key()


def pytest_collection_modifyitems(config, items):
    """Auto-mark all tests in this directory as e2e."""
    for item in items:
        if "e2e/cli" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def cf_test_path() -> Path:
    """Path to the cf-test project."""
    if not CF_TEST_PROJECT.exists():
        pytest.skip(f"cf-test project not found at {CF_TEST_PROJECT}")
    return CF_TEST_PROJECT


@pytest.fixture(scope="session")
def codeframe_root() -> Path:
    """Path to the codeframe project root."""
    return CODEFRAME_ROOT


@pytest.fixture(scope="session")
def anthropic_api_key() -> str:
    """Load ANTHROPIC_API_KEY from codeframe .env or environment."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    env_file = CODEFRAME_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ["ANTHROPIC_API_KEY"] = key
                return key

    pytest.skip("ANTHROPIC_API_KEY not available")


@pytest.fixture(scope="module")
def pyproject_snapshot(cf_test_path: Path) -> dict:
    """Capture a snapshot of pyproject.toml for preservation checks."""
    toml_path = cf_test_path / "pyproject.toml"
    content = toml_path.read_text()
    return {
        "path": toml_path,
        "content": content,
        "hash": hashlib.sha256(content.encode()).hexdigest(),
    }


@pytest.fixture(scope="module")
def clean_cf_test(cf_test_path: Path) -> Path:
    """Clean the cf-test project, preserving only config and requirements.

    Removes: .codeframe/, src/task_tracker/ contents (not __init__.py),
    tests/ contents (not __init__.py), __pycache__ dirs.

    Preserves: pyproject.toml, requirements.md, .gitignore, .python-version,
    .venv/, uv.lock, README.md.
    """
    # Remove .codeframe workspace
    codeframe_dir = cf_test_path / ".codeframe"
    if codeframe_dir.exists():
        shutil.rmtree(codeframe_dir)

    # Remove generated source files (keep directory structure)
    src_dir = cf_test_path / "src" / "task_tracker"
    if src_dir.exists():
        for f in src_dir.iterdir():
            if f.name == "__pycache__":
                shutil.rmtree(f)
            elif f.name != "__init__.py" and f.is_file():
                f.unlink()
        # Reset __init__.py to empty
        init_file = src_dir / "__init__.py"
        init_file.write_text("")

    # Remove generated test files (keep directory structure)
    tests_dir = cf_test_path / "tests"
    if tests_dir.exists():
        for f in tests_dir.iterdir():
            if f.name == "__pycache__":
                shutil.rmtree(f)
            elif f.name != "__init__.py" and f.is_file():
                f.unlink()
        init_file = tests_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("")

    # Remove pytest/ruff caches
    for cache_dir in [".pytest_cache", ".ruff_cache"]:
        cache_path = cf_test_path / cache_dir
        if cache_path.exists():
            shutil.rmtree(cache_path)

    return cf_test_path
