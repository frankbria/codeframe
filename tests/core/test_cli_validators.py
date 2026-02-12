"""Tests for codeframe.cli.validators module."""

import os
from pathlib import Path

import click
import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestRequireAnthropicApiKey:
    """Tests for require_anthropic_api_key() validator."""

    def test_returns_key_when_in_environment(self, monkeypatch):
        """When ANTHROPIC_API_KEY is already set, return it directly."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-123")

        from codeframe.cli.validators import require_anthropic_api_key

        result = require_anthropic_api_key()
        assert result == "sk-ant-test-key-123"

    def test_loads_key_from_dotenv_file(self, monkeypatch, tmp_path):
        """When key is not in env but exists in .env file, load and return it."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Create a .env file with the key
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-from-dotenv-456\n")

        # Change to the tmp_path directory so load_dotenv finds .env
        monkeypatch.chdir(tmp_path)

        from codeframe.cli.validators import require_anthropic_api_key

        result = require_anthropic_api_key()
        assert result == "sk-ant-from-dotenv-456"

    def test_sets_key_in_environ_after_loading_from_dotenv(self, monkeypatch, tmp_path):
        """After loading from .env, the key should be available in os.environ."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-persist-789\n")
        monkeypatch.chdir(tmp_path)

        from codeframe.cli.validators import require_anthropic_api_key

        require_anthropic_api_key()
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-persist-789"

    def test_raises_exit_when_key_missing_everywhere(self, monkeypatch, tmp_path):
        """When key is not in env and not in any .env file, raise SystemExit."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Use a directory with no .env file and isolate Path.home() to prevent
        # loading from the real ~/.env on developer machines
        monkeypatch.chdir(tmp_path)
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

        from codeframe.cli.validators import require_anthropic_api_key

        with pytest.raises(click.exceptions.Exit):
            require_anthropic_api_key()


# ---------------------------------------------------------------------------
# Fixtures for CLI integration tests
# ---------------------------------------------------------------------------

SAMPLE_PRD = """\
# Sample PRD

## Feature: User Authentication
- Implement login endpoint
- Implement signup endpoint
"""


@pytest.fixture
def workspace_with_prd(tmp_path):
    """Initialized workspace with a PRD added."""
    from codeframe.cli.app import app
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    create_or_load_workspace(repo)

    prd_file = repo / "prd.md"
    prd_file.write_text(SAMPLE_PRD)

    result = runner.invoke(app, ["prd", "add", str(prd_file), "-w", str(repo)])
    assert result.exit_code == 0, f"prd add failed: {result.output}"
    return repo


@pytest.fixture
def workspace_with_ready_task(workspace_with_prd):
    """Workspace with a PRD, generated tasks, and one READY task."""
    from codeframe.cli.app import app

    wp = str(workspace_with_prd)

    result = runner.invoke(app, ["tasks", "generate", "--no-llm", "-w", wp])
    assert result.exit_code == 0, f"tasks generate failed: {result.output}"

    result = runner.invoke(app, ["tasks", "set", "status", "READY", "--all", "-w", wp])
    assert result.exit_code == 0, f"set ready failed: {result.output}"

    # Get first task ID
    from codeframe.core import tasks
    from codeframe.core.workspace import get_workspace

    workspace = get_workspace(workspace_with_prd)
    all_tasks = tasks.list_tasks(workspace)
    assert len(all_tasks) > 0, "No tasks generated"

    return workspace_with_prd, all_tasks[0].id


# ---------------------------------------------------------------------------
# CLI Integration: tasks generate validation
# ---------------------------------------------------------------------------


class TestTasksGenerateValidation:
    """Test that tasks generate validates API key when using LLM."""

    def test_tasks_generate_without_key_exits(self, workspace_with_prd, monkeypatch, tmp_path):
        """tasks generate (LLM mode) should fail early when API key is missing."""
        from codeframe.cli.app import app

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)  # No .env here

        result = runner.invoke(
            app, ["tasks", "generate", "-w", str(workspace_with_prd)]
        )
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output

    def test_tasks_generate_no_llm_skips_validation(self, workspace_with_prd, monkeypatch, tmp_path):
        """tasks generate --no-llm should succeed without API key."""
        from codeframe.cli.app import app

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["tasks", "generate", "--no-llm", "-w", str(workspace_with_prd)]
        )
        assert result.exit_code == 0
        assert "generated" in result.output.lower()


# ---------------------------------------------------------------------------
# CLI Integration: work start validation
# ---------------------------------------------------------------------------


class TestWorkStartValidation:
    """Test that work start --execute validates API key."""

    def test_work_start_execute_without_key_exits(self, workspace_with_ready_task, monkeypatch, tmp_path):
        """work start --execute should fail early when API key is missing."""
        from codeframe.cli.app import app

        workspace_path, task_id = workspace_with_ready_task
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["work", "start", task_id, "--execute", "-w", str(workspace_path)]
        )
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output

    def test_work_start_stub_skips_validation(self, workspace_with_ready_task, monkeypatch, tmp_path):
        """work start --stub should succeed without API key."""
        from codeframe.cli.app import app

        workspace_path, task_id = workspace_with_ready_task
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(
            app, ["work", "start", task_id, "--stub", "-w", str(workspace_path)]
        )
        assert result.exit_code == 0
