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


@pytest.fixture
def isolated_keys(monkeypatch, tmp_path):
    """No API keys anywhere: env cleared, cwd + home have no .env files."""
    for var in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "CODEFRAME_LLM_PROVIDER",
        "CODEFRAME_LLM_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))


def _completed_agent_state():
    from types import SimpleNamespace

    from codeframe.core.agent import AgentStatus

    return SimpleNamespace(
        status=AgentStatus.COMPLETED, blocker=None, step_results=[]
    )


class TestProviderAwarePreflight:
    """Pre-flight key checks must honor the resolved provider (#768)."""

    def test_work_start_openai_provider_requires_openai_key(
        self, workspace_with_ready_task, isolated_keys
    ):
        from codeframe.cli.app import app

        workspace_path, task_id = workspace_with_ready_task
        result = runner.invoke(
            app,
            ["work", "start", task_id, "--execute",
             "--llm-provider", "openai", "-w", str(workspace_path)],
        )
        assert result.exit_code != 0
        assert "OPENAI_API_KEY" in result.output
        assert "ANTHROPIC_API_KEY" not in result.output

    def test_work_start_ollama_provider_skips_anthropic_key(
        self, workspace_with_ready_task, isolated_keys, monkeypatch
    ):
        from codeframe.cli.app import app
        from codeframe.core import runtime

        workspace_path, task_id = workspace_with_ready_task
        monkeypatch.setattr(
            runtime, "execute_agent",
            lambda *a, **kw: _completed_agent_state(),
        )
        result = runner.invoke(
            app,
            ["work", "start", task_id, "--execute",
             "--llm-provider", "ollama", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0, result.output
        assert "ANTHROPIC_API_KEY" not in result.output

    def test_batch_run_openai_provider_requires_openai_key(
        self, workspace_with_ready_task, isolated_keys
    ):
        from codeframe.cli.app import app

        workspace_path, task_id = workspace_with_ready_task
        result = runner.invoke(
            app,
            ["work", "batch", "run", task_id,
             "--llm-provider", "openai", "-w", str(workspace_path)],
        )
        assert result.exit_code != 0
        assert "OPENAI_API_KEY" in result.output

    def test_batch_run_ollama_provider_skips_anthropic_key(
        self, workspace_with_ready_task, isolated_keys, monkeypatch
    ):
        from types import SimpleNamespace

        from codeframe.cli.app import app
        from codeframe.core import conductor

        workspace_path, task_id = workspace_with_ready_task
        fake_batch = SimpleNamespace(
            id="deadbeefcafe",
            status=SimpleNamespace(value="COMPLETED"),
            results={task_id: "COMPLETED"},
        )
        monkeypatch.setattr(
            conductor, "start_batch", lambda *a, **kw: fake_batch
        )
        result = runner.invoke(
            app,
            ["work", "batch", "run", task_id,
             "--llm-provider", "ollama", "-w", str(workspace_path)],
        )
        assert result.exit_code == 0, result.output
        assert "ANTHROPIC_API_KEY" not in result.output

    def test_work_retry_non_anthropic_provider_skips_anthropic_key(
        self, workspace_with_ready_task, isolated_keys, monkeypatch
    ):
        from codeframe.cli.app import app
        from codeframe.core import runtime

        workspace_path, task_id = workspace_with_ready_task
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")
        monkeypatch.setattr(
            runtime, "execute_agent",
            lambda *a, **kw: _completed_agent_state(),
        )
        result = runner.invoke(
            app, ["work", "retry", task_id, "-w", str(workspace_path)]
        )
        assert result.exit_code == 0, result.output
        assert "ANTHROPIC_API_KEY" not in result.output

    def test_work_retry_default_provider_still_requires_anthropic_key(
        self, workspace_with_ready_task, isolated_keys
    ):
        from codeframe.cli.app import app

        workspace_path, task_id = workspace_with_ready_task
        result = runner.invoke(
            app, ["work", "retry", task_id, "-w", str(workspace_path)]
        )
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output


class TestThinkPhaseProviderResolution:
    """prd stress-test and tasks generate must honor the provider chain (#768)."""

    def test_stress_test_default_provider_requires_anthropic_key(
        self, workspace_with_prd, isolated_keys
    ):
        from codeframe.cli.app import app

        result = runner.invoke(
            app, ["prd", "stress-test", "-w", str(workspace_with_prd)]
        )
        assert result.exit_code != 0
        assert "ANTHROPIC_API_KEY" in result.output

    def test_stress_test_ollama_provider_skips_anthropic_key(
        self, workspace_with_prd, isolated_keys, monkeypatch
    ):
        from types import SimpleNamespace

        from codeframe.adapters.llm import OpenAIProvider
        from codeframe.cli.app import app
        from codeframe.core import prd_stress_test

        seen_providers = []

        def fake_stress_test(content, provider, max_depth=3):
            seen_providers.append(provider)
            return SimpleNamespace(
                ambiguities=[], tree=[], tech_spec_markdown="# Spec"
            )

        monkeypatch.setattr(
            prd_stress_test, "stress_test_prd", fake_stress_test
        )
        result = runner.invoke(
            app,
            ["prd", "stress-test", "--llm-provider", "ollama",
             "-w", str(workspace_with_prd)],
        )
        assert result.exit_code == 0, result.output
        assert "ANTHROPIC_API_KEY" not in result.output
        assert len(seen_providers) == 1
        assert isinstance(seen_providers[0], OpenAIProvider)

    def test_tasks_generate_openai_provider_requires_openai_key(
        self, workspace_with_prd, isolated_keys
    ):
        from codeframe.cli.app import app

        result = runner.invoke(
            app,
            ["tasks", "generate", "--llm-provider", "openai",
             "-w", str(workspace_with_prd)],
        )
        assert result.exit_code != 0
        assert "OPENAI_API_KEY" in result.output

    def test_tasks_generate_ollama_provider_skips_anthropic_key(
        self, workspace_with_prd, isolated_keys, monkeypatch
    ):
        from codeframe.cli.app import app
        from codeframe.core import tasks as tasks_module

        monkeypatch.setattr(
            tasks_module,
            "_generate_tasks_with_llm",
            lambda *a, **kw: [{"title": "Task A", "description": "do a"}],
        )
        result = runner.invoke(
            app,
            ["tasks", "generate", "--llm-provider", "ollama",
             "-w", str(workspace_with_prd)],
        )
        assert result.exit_code == 0, result.output
        assert "ANTHROPIC_API_KEY" not in result.output


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
