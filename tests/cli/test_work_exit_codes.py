"""Tests for CLI exit codes on work commands (start, retry, batch run).

Issue #375: CLI was returning exit code 0 even when the agent state was
BLOCKED or FAILED, causing false positives in test automation.

Covers: work start (issue #374), work retry, and batch run.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.agent import AgentStatus
from codeframe.core import tasks
from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure
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


@pytest.fixture
def workspace_with_failed_task(tmp_path, monkeypatch):
    """Workspace with one FAILED task, API key set."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")

    ws = create_or_load_workspace(repo)
    task = tasks.create(ws, title="Retry task", description="A task to retry",
                        status=TaskStatus.FAILED)

    return ws, repo, task.id[:8], task.id


@pytest.fixture
def workspace_with_two_ready_tasks(tmp_path, monkeypatch):
    """Workspace with two READY tasks for batch execution."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")

    ws = create_or_load_workspace(repo)
    t1 = tasks.create(ws, title="Batch task 1", description="First batch task",
                      status=TaskStatus.READY)
    t2 = tasks.create(ws, title="Batch task 2", description="Second batch task",
                      status=TaskStatus.READY)

    return ws, repo, t1.id[:8], t2.id[:8], t1.id, t2.id


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


class TestWorkRetryExitCodes:
    """Verify work retry returns correct exit codes."""

    def test_retry_completed_returns_exit_zero(self, workspace_with_failed_task):
        ws, repo, tid, full_id = workspace_with_failed_task
        fake_state = _FakeAgentState(status=AgentStatus.COMPLETED)

        with patch("codeframe.core.runtime.execute_agent", return_value=fake_state):
            result = runner.invoke(
                app, ["work", "retry", tid, "-w", str(repo)]
            )

        assert result.exit_code == 0, f"Expected 0 for COMPLETED: {result.output}"
        assert "completed successfully" in result.output.lower()

    def test_retry_failed_returns_exit_one(self, workspace_with_failed_task):
        ws, repo, tid, full_id = workspace_with_failed_task
        fake_state = _FakeAgentState(status=AgentStatus.FAILED)

        with patch("codeframe.core.runtime.execute_agent", return_value=fake_state):
            result = runner.invoke(
                app, ["work", "retry", tid, "-w", str(repo)]
            )

        assert result.exit_code == 1, f"Expected 1 for FAILED: {result.output}"
        assert "failed" in result.output.lower()

    def test_retry_blocked_returns_exit_one(self, workspace_with_failed_task):
        ws, repo, tid, full_id = workspace_with_failed_task
        fake_state = _FakeAgentState(status=AgentStatus.BLOCKED)

        with patch("codeframe.core.runtime.execute_agent", return_value=fake_state):
            result = runner.invoke(
                app, ["work", "retry", tid, "-w", str(repo)]
            )

        assert result.exit_code == 1, f"Expected 1 for BLOCKED: {result.output}"
        assert "blocked" in result.output.lower()


def _make_batch(ws, task_ids, results):
    """Helper to create a fake BatchRun with given results."""
    return BatchRun(
        id="batch-test-1234",
        workspace_id=ws.id if hasattr(ws, 'id') else "test-ws",
        task_ids=task_ids,
        status=BatchStatus.COMPLETED if all(v == "COMPLETED" for v in results.values())
               else BatchStatus.PARTIAL,
        strategy="serial",
        max_parallel=1,
        on_failure=OnFailure.CONTINUE,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        results=results,
    )


class TestBatchRunExitCodes:
    """Verify batch run returns correct exit codes."""

    def test_batch_all_completed_returns_exit_zero(self, workspace_with_two_ready_tasks):
        ws, repo, tid1, tid2, fid1, fid2 = workspace_with_two_ready_tasks
        batch = _make_batch(ws, [fid1, fid2], {fid1: "COMPLETED", fid2: "COMPLETED"})

        with patch("codeframe.core.conductor.start_batch", return_value=batch):
            result = runner.invoke(
                app, ["work", "batch", "run", tid1, tid2, "-w", str(repo)]
            )

        assert result.exit_code == 0, f"Expected 0 for all COMPLETED: {result.output}"

    def test_batch_with_failure_returns_exit_one(self, workspace_with_two_ready_tasks):
        ws, repo, tid1, tid2, fid1, fid2 = workspace_with_two_ready_tasks
        batch = _make_batch(ws, [fid1, fid2], {fid1: "COMPLETED", fid2: "FAILED"})

        with patch("codeframe.core.conductor.start_batch", return_value=batch):
            result = runner.invoke(
                app, ["work", "batch", "run", tid1, tid2, "-w", str(repo)]
            )

        assert result.exit_code == 1, f"Expected 1 for FAILED batch: {result.output}"

    def test_batch_with_blocked_returns_exit_one(self, workspace_with_two_ready_tasks):
        ws, repo, tid1, tid2, fid1, fid2 = workspace_with_two_ready_tasks
        batch = _make_batch(ws, [fid1, fid2], {fid1: "COMPLETED", fid2: "BLOCKED"})

        with patch("codeframe.core.conductor.start_batch", return_value=batch):
            result = runner.invoke(
                app, ["work", "batch", "run", tid1, tid2, "-w", str(repo)]
            )

        assert result.exit_code == 1, f"Expected 1 for BLOCKED batch: {result.output}"
