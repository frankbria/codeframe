"""
Shared fixtures for lifecycle tests.

These tests are EXPENSIVE — they make real LLM API calls.
They are excluded from normal pytest runs and must be invoked explicitly:

    uv run pytest tests/lifecycle/ -m lifecycle
    # or via the convenience script:
    scripts/lifecycle [--mode cli|api|web|all] [--model haiku|sonnet]
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SAMPLE_PROJECT_DIR = Path(__file__).parent / "sample_project"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "lifecycle: full end-to-end lifecycle tests (real LLM calls — run explicitly)",
    )


# ---------------------------------------------------------------------------
# Guard: skip entire suite if no API key
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(config, items):
    if not os.getenv("ANTHROPIC_API_KEY"):
        skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set — lifecycle tests require real API")
        for item in items:
            if "lifecycle" in str(item.fspath):
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_prd_path() -> Path:
    """Path to the sample project PRD."""
    return SAMPLE_PROJECT_DIR / "PRD.md"


@pytest.fixture
def target_project_dir(tmp_path) -> Path:
    """
    A fresh temporary directory with git initialized,
    ready for `cf init` and agent execution.
    """
    project = tmp_path / "csv-stats"
    project.mkdir()

    # Initialize git repo (cf init requires it)
    subprocess.run(["git", "init", str(project)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "lifecycle@test.com"],
                   cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lifecycle Test"],
                   cwd=project, check=True, capture_output=True)

    yield project

    # Optional: keep on failure for inspection (controlled by --no-cleanup flag)
    # cleanup happens automatically via tmp_path


@pytest.fixture
def cf(target_project_dir):
    """
    Helper to invoke `cf` CLI commands against the target project directory.
    Returns the completed process (stdout/stderr captured, no exception on nonzero).
    """
    def run(*args, cwd=None, timeout=60, **kwargs):
        return subprocess.run(
            ["uv", "run", "cf", *args],
            cwd=cwd or target_project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
    return run


@pytest.fixture
def initialized_workspace(target_project_dir, cf, sample_prd_path):
    """
    A workspace with:
    - cf init complete
    - PRD added
    - Tasks generated
    Ready for `cf work batch run --all-ready --execute`.
    """
    result = cf("init", str(target_project_dir), "--tech-stack", "Python with uv")
    assert result.returncode == 0, f"cf init failed:\n{result.stderr}"

    # Copy PRD into the target dir so cf prd add has a local path
    prd_dest = target_project_dir / "PRD.md"
    shutil.copy(sample_prd_path, prd_dest)

    result = cf("prd", "add", "PRD.md")
    assert result.returncode == 0, f"cf prd add failed:\n{result.stderr}"

    result = cf("tasks", "generate")
    assert result.returncode == 0, f"cf tasks generate failed:\n{result.stderr}"

    return target_project_dir
