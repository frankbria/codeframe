"""Tests that `cf work start --execute` returns non-zero exit codes for BLOCKED/FAILED.

Issue #374: CLI was returning exit code 0 even when the agent state was
BLOCKED or FAILED, causing false positives in test automation.
"""

from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.agent import AgentStatus
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@dataclass
class _FakeAgentState:
    status: AgentStatus
    blocker: object = None
    step_results: list = field(default_factory=list)


@pytest.fixture
def workspace_with_ready_task(tmp_path, monkeypatch):
    """Workspace with one READY task, API key set."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")

    ws = create_or_load_workspace(repo)
    task = tasks.create(ws, title="Test task", description="A test task",
                        status=TaskStatus.READY)

    return repo, task.id[:8]


class TestWorkStartExitCodes:
    """Verify CLI exit codes match agent execution outcomes."""

    def test_completed_returns_exit_zero(self, workspace_with_ready_task):
        repo, tid = workspace_with_ready_task
        fake_state = _FakeAgentState(status=AgentStatus.COMPLETED)

        with patch("codeframe.core.runtime.execute_agent", return_value=fake_state):
            result = runner.invoke(
                app, ["work", "start", tid, "--execute", "-w", str(repo)]
            )

        assert result.exit_code == 0, f"Expected 0 for COMPLETED: {result.output}"
        assert "completed successfully" in result.output.lower()

    def test_failed_returns_exit_one(self, workspace_with_ready_task):
        repo, tid = workspace_with_ready_task
        fake_state = _FakeAgentState(status=AgentStatus.FAILED)

        with patch("codeframe.core.runtime.execute_agent", return_value=fake_state):
            result = runner.invoke(
                app, ["work", "start", tid, "--execute", "-w", str(repo)]
            )

        assert result.exit_code == 1, f"Expected 1 for FAILED: {result.output}"
        assert "failed" in result.output.lower()

    def test_blocked_returns_exit_one(self, workspace_with_ready_task):
        repo, tid = workspace_with_ready_task
        fake_state = _FakeAgentState(status=AgentStatus.BLOCKED)

        with patch("codeframe.core.runtime.execute_agent", return_value=fake_state):
            result = runner.invoke(
                app, ["work", "start", tid, "--execute", "-w", str(repo)]
            )

        assert result.exit_code == 1, f"Expected 1 for BLOCKED: {result.output}"
        assert "blocked" in result.output.lower()
