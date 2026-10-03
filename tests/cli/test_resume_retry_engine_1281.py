"""#1281: `cf work resume/retry` used the wrong engine, and `--dry-run` was
silently ignored by external engines.

`work_resume` hard-defaulted `--engine react`, overriding CODEFRAME_ENGINE and
the workspace config. `work_retry` had no engine option at all. So a
claude-code user's resume or retry switched to the built-in engine partway
through a task, and failed outright with no ANTHROPIC_API_KEY. Separately,
`--dry-run` only reached the built-in engine: an external engine edited the
repo, the run completed, and auto-close could close the linked issue.

These tests record the engine that reaches the key check and the agent.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import runtime, tasks
from codeframe.core.agent import AgentState, AgentStatus
from codeframe.core.config import EnvironmentConfig, save_environment_config
from codeframe.core.engine_registry import resolve_workspace_engine
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEFRAME_ENGINE", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


@pytest.fixture
def seen(monkeypatch):
    """Record the engine passed to the key check and to the agent."""
    record: dict = {}

    def keys(repo_path, engine=None, **kwargs):
        record["keys"] = engine

    def execute(workspace, run, *args, **kwargs):
        record["agent"] = kwargs.get("engine")
        record["dry_run"] = kwargs.get("dry_run")
        runtime.complete_run(workspace, run.id)
        return AgentState(status=AgentStatus.COMPLETED)

    monkeypatch.setattr("codeframe.cli.validators.require_keys_for_engine", keys)
    monkeypatch.setattr(runtime, "execute_agent", execute)
    return record


def _blocked_task(ws):
    task = tasks.create(ws, title="t", status=TaskStatus.READY)
    run = runtime.start_task_run(ws, task.id)
    runtime.block_run(ws, run.id, "")
    return task


def _failed_task(ws):
    task = tasks.create(ws, title="t", status=TaskStatus.READY)
    run = runtime.start_task_run(ws, task.id)
    runtime.fail_run(ws, run.id)
    return task


def _cf(ws, *args):
    return CliRunner().invoke(app, [*args, "-w", str(ws.repo_path)])


# ---------------------------------------------------------------------------
# One resolver: flag > CODEFRAME_ENGINE > workspace config > react
# ---------------------------------------------------------------------------


class TestTheResolver:
    def test_default(self, ws):
        assert resolve_workspace_engine(None, ws.repo_path) == "react"

    def test_config(self, ws):
        save_environment_config(ws.repo_path, EnvironmentConfig(engine="codex"))
        assert resolve_workspace_engine(None, ws.repo_path) == "codex"

    def test_env_beats_config(self, ws, monkeypatch):
        save_environment_config(ws.repo_path, EnvironmentConfig(engine="codex"))
        monkeypatch.setenv("CODEFRAME_ENGINE", "opencode")
        assert resolve_workspace_engine(None, ws.repo_path) == "opencode"

    def test_flag_beats_env(self, ws, monkeypatch):
        monkeypatch.setenv("CODEFRAME_ENGINE", "opencode")
        assert resolve_workspace_engine("claude-code", ws.repo_path) == "claude-code"


# ---------------------------------------------------------------------------
# resume and retry use it
# ---------------------------------------------------------------------------


class TestResumeAndRetryKeepTheEngine:
    def test_resume_follows_codeframe_engine(self, ws, seen, monkeypatch):
        monkeypatch.setenv("CODEFRAME_ENGINE", "claude-code")
        task = _blocked_task(ws)

        result = _cf(ws, "work", "resume", task.id)

        assert result.exit_code == 0, result.output
        assert seen == {"keys": "claude-code", "agent": "claude-code", "dry_run": False}

    def test_resume_follows_the_workspace_config(self, ws, seen):
        save_environment_config(ws.repo_path, EnvironmentConfig(engine="codex"))
        task = _blocked_task(ws)

        _cf(ws, "work", "resume", task.id)

        assert seen["agent"] == "codex" and seen["keys"] == "codex"

    def test_retry_follows_codeframe_engine(self, ws, seen, monkeypatch):
        monkeypatch.setenv("CODEFRAME_ENGINE", "claude-code")
        task = _failed_task(ws)

        result = _cf(ws, "work", "retry", task.id)

        assert result.exit_code == 0, result.output
        assert seen["agent"] == "claude-code" and seen["keys"] == "claude-code"

    def test_retry_takes_an_engine_flag(self, ws, seen):
        task = _failed_task(ws)

        _cf(ws, "work", "retry", task.id, "--engine", "opencode")

        assert seen["agent"] == "opencode" and seen["keys"] == "opencode"


# ---------------------------------------------------------------------------
# --dry-run is refused for an engine that cannot honour it
# ---------------------------------------------------------------------------


class TestDryRunWithAnExternalEngine:
    def test_start_refuses_before_creating_a_run(self, ws, seen):
        task = tasks.create(ws, title="t", status=TaskStatus.READY)

        result = _cf(ws, "work", "start", task.id, "--execute", "--dry-run", "--engine", "claude-code")

        assert result.exit_code != 0
        assert "dry-run" in result.output.lower()
        assert runtime.get_latest_run(ws, task.id) is None
        assert "agent" not in seen

    def test_resume_refuses_before_resuming_the_run(self, ws, seen):
        task = _blocked_task(ws)

        result = _cf(ws, "work", "resume", task.id, "--dry-run", "--engine", "codex")

        assert result.exit_code != 0
        assert runtime.get_latest_run(ws, task.id).status == runtime.RunStatus.BLOCKED
        assert "agent" not in seen

    def test_retry_refuses_before_starting_a_run(self, ws, seen):
        task = _failed_task(ws)
        before = runtime.get_latest_run(ws, task.id).id

        result = _cf(ws, "work", "retry", task.id, "--dry-run", "--engine", "opencode")

        assert result.exit_code != 0
        assert runtime.get_latest_run(ws, task.id).id == before
        assert "agent" not in seen

    def test_the_builtin_engine_still_dry_runs(self, ws, seen):
        task = tasks.create(ws, title="t", status=TaskStatus.READY)

        result = _cf(ws, "work", "start", task.id, "--execute", "--dry-run")

        assert result.exit_code == 0, result.output
        assert seen["dry_run"] is True and seen["agent"] == "react"

    def test_the_core_refuses_it_too(self, ws):
        """A caller that skips the CLI (the web route, a script) is refused by
        execute_agent itself, and the run is not left RUNNING."""
        task = tasks.create(ws, title="t", status=TaskStatus.READY)
        run = runtime.start_task_run(ws, task.id)

        with pytest.raises(ValueError, match="dry-run"):
            runtime.execute_agent(ws, run, dry_run=True, engine="claude-code")
        assert runtime.get_run(ws, run.id).status == runtime.RunStatus.FAILED
