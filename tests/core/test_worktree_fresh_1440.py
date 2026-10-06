"""Resuming a stopped worktree run is visible, and --fresh discards it (#1440).

Since #1363 a worktree run left by Stop or a failure is resumed by the next
start, uncommitted edits included, and merged at the end. That fits "I paused
it"; it is risky when the run was stopped because the agent was going wrong.
So: the CLI warns when it resumes one, and `--fresh` throws it away first.
Real git; only `execute_agent` is stubbed in the CLI tests.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.core.sandbox.context import (
    IsolationLevel,
    create_execution_context,
    discard_leftover_run,
    leftover_run,
)
from tests.core import test_sandbox_context as _sandbox

pytestmark = pytest.mark.v2

git_repo = _sandbox.git_repo


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True).stdout


def _stopped_run(repo: Path, task_id: str = "task-abc") -> Path:
    """A run that committed one file, left one uncommitted, and was preserved."""
    ctx = create_execution_context(task_id, IsolationLevel.WORKTREE, repo)
    (ctx.workspace_path / "committed.txt").write_text("step one")
    _git(ctx.workspace_path, "add", "committed.txt")
    _git(ctx.workspace_path, "commit", "-m", "agent step one")
    (ctx.workspace_path / "in_progress.txt").write_text("half done")
    ctx.preserve()
    return ctx.workspace_path


# --- core -------------------------------------------------------------------

def test_no_leftover_run_reports_none(git_repo):
    assert leftover_run("task-abc", git_repo) is None


def test_a_leftover_run_reports_what_it_carries(git_repo):
    _stopped_run(git_repo)
    left = leftover_run("task-abc", git_repo)
    assert left is not None
    assert (left.branch, left.commits, left.uncommitted) == ("cf/task-abc", 1, 1)


def test_discard_removes_the_branch_and_worktree_so_the_next_run_starts_from_base(git_repo):
    path = _stopped_run(git_repo)

    assert discard_leftover_run("task-abc", git_repo) is True

    assert not path.exists()
    assert _git(git_repo, "branch", "--list", "cf/task-abc").strip() == ""
    ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
    assert not (ctx.workspace_path / "committed.txt").exists()
    assert not (ctx.workspace_path / "in_progress.txt").exists()


def test_discard_never_touches_a_stray_directory_that_is_not_the_tasks_worktree(git_repo):
    """#1363 refuses to overwrite one; --fresh must not delete it either. The
    branch is real, so only the registration check stands between a stray
    directory in the worktree slot and `git worktree remove --force`."""
    path = _stopped_run(git_repo)
    _git(git_repo, "worktree", "remove", "--force", str(path))
    path.mkdir(parents=True)
    (path / "someone_elses.txt").write_text("x")

    assert discard_leftover_run("task-abc", git_repo) is False
    assert (path / "someone_elses.txt").exists()
    assert "cf/task-abc" in _git(git_repo, "branch", "--list", "cf/task-abc")


# --- CLI ----------------------------------------------------------------------

@dataclass
class _State:
    status: object
    blocker: object = None
    step_results: list = field(default_factory=list)


@pytest.fixture
def task_repo(git_repo, monkeypatch):
    from codeframe.core import tasks
    from codeframe.core.state_machine import TaskStatus
    from codeframe.core.workspace import create_or_load_workspace

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-fake")
    ws = create_or_load_workspace(git_repo)
    task = tasks.create(ws, title="T", description="d", status=TaskStatus.READY)
    return git_repo, task.id


def _start(repo, task_id, *extra):
    """Run `cf work start` and report what the leftover held when execution began."""
    from codeframe.cli.app import app
    from codeframe.core.agent import AgentStatus

    seen = {}

    def fake_execute(workspace, run, **kw):
        seen["leftover"] = leftover_run(task_id, repo)
        return _State(status=AgentStatus.COMPLETED)

    with patch("codeframe.core.runtime.execute_agent", side_effect=fake_execute):
        result = CliRunner().invoke(
            app, ["work", "start", task_id[:8], "--execute", "--isolation", "worktree", "-w", str(repo), *extra],
        )
    return result, seen


def test_starting_over_a_leftover_run_warns_that_it_will_be_resumed(task_repo):
    repo, task_id = task_repo
    _stopped_run(repo, task_id)

    result, seen = _start(repo, task_id)

    assert result.exit_code == 0, result.output
    assert seen["leftover"] is not None  # resumed by default
    out = " ".join(result.output.split())
    assert f"cf/{task_id}" in out and "--fresh" in out, out
    assert "1 commit" in out and "1 uncommitted" in out, out


def test_fresh_discards_the_leftover_run_before_executing(task_repo):
    repo, task_id = task_repo
    _stopped_run(repo, task_id)

    result, seen = _start(repo, task_id, "--fresh")

    assert result.exit_code == 0, result.output
    assert seen["leftover"] is None, result.output
    assert "Discarded" in result.output, result.output


def test_fresh_without_worktree_isolation_is_refused(task_repo):
    from codeframe.cli.app import app

    repo, task_id = task_repo
    result = CliRunner().invoke(app, ["work", "start", task_id[:8], "--execute", "--fresh", "-w", str(repo)])

    assert result.exit_code != 0
    assert "--isolation worktree" in " ".join(result.output.split()), result.output


def test_fresh_with_dry_run_is_refused_and_deletes_nothing(task_repo):
    """A preview must not destroy work (codex review)."""
    repo, task_id = task_repo
    _stopped_run(repo, task_id)

    result, seen = _start(repo, task_id, "--fresh", "--dry-run")

    assert result.exit_code != 0
    assert "--dry-run" in " ".join(result.output.split()), result.output
    assert leftover_run(task_id, repo) is not None  # still there
    assert "leftover" not in seen  # never executed


def test_fresh_does_not_discard_while_the_task_has_a_live_run(task_repo):
    """Discarding before start_task_run's liveness checks destroyed a running
    agent's worktree, then refused to start anyway (codex review)."""
    from codeframe.core import runtime
    from codeframe.core.workspace import get_workspace

    repo, task_id = task_repo
    _stopped_run(repo, task_id)
    runtime.start_task_run(get_workspace(repo), task_id)  # a run is active

    result, seen = _start(repo, task_id, "--fresh")

    assert result.exit_code != 0, result.output
    assert "leftover" not in seen
    left = leftover_run(task_id, repo)
    assert left is not None and (left.commits, left.uncommitted) == (1, 1), result.output
