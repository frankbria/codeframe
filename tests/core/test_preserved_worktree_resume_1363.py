"""A stopped or failed worktree run can be started again (#1363).

A run that ends before merge-back preserves `cf/<task_id>` and its worktree so
no agent work is lost (#714/#787). The next start then refused ("a worktree or
branch ... still exists"), so a user who pressed Stop could not press Start
again without git surgery. Start now resumes on the preserved branch. Real
git throughout (no mocks), via test_sandbox_context's fixture.
"""

import subprocess
from pathlib import Path

import pytest

from codeframe.core.sandbox.context import IsolationLevel, create_execution_context
from tests.core import test_sandbox_context as _sandbox

pytestmark = pytest.mark.v2

git_repo = _sandbox.git_repo


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, text=True).stdout


def _stopped_run(repo: Path) -> Path:
    """A run that committed one file, left one uncommitted, and was preserved."""
    ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, repo)
    (ctx.workspace_path / "committed.txt").write_text("step one")
    _git(ctx.workspace_path, "add", "committed.txt")
    _git(ctx.workspace_path, "commit", "-m", "agent step one")
    (ctx.workspace_path / "in_progress.txt").write_text("half done")
    ctx.preserve()
    return ctx.workspace_path


def test_a_preserved_run_resumes_with_its_work(git_repo):
    path = _stopped_run(git_repo)

    ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)

    assert ctx.workspace_path == path
    assert (path / "committed.txt").read_text() == "step one"
    assert (path / "in_progress.txt").read_text() == "half done"  # uncommitted, kept
    assert _git(path, "rev-parse", "--abbrev-ref", "HEAD").strip() == "cf/task-abc"


def test_the_resumed_run_still_merges_everything_back(git_repo):
    _stopped_run(git_repo)
    ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
    (ctx.workspace_path / "finished.txt").write_text("step two")

    result = ctx.merge_back()

    assert result is not None and result.success is True
    for name in ("committed.txt", "in_progress.txt", "finished.txt"):
        assert (git_repo / name).exists(), name


def test_a_preserved_branch_whose_worktree_dir_was_removed_is_reattached(git_repo):
    path = _stopped_run(git_repo)
    _git(git_repo, "worktree", "remove", "--force", str(path))
    assert "cf/task-abc" in _git(git_repo, "branch", "--list", "cf/task-abc")

    ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)

    assert (ctx.workspace_path / "committed.txt").read_text() == "step one"
    assert _git(ctx.workspace_path, "rev-parse", "--abbrev-ref", "HEAD").strip() == "cf/task-abc"


def test_a_stray_directory_that_is_not_the_tasks_worktree_still_refuses(git_repo):
    """Only reuse what is provably this task's worktree; anything else is
    surfaced, not overwritten."""
    stray = git_repo / ".codeframe" / "worktrees" / "task-abc"
    stray.mkdir(parents=True)
    (stray / "someone_elses.txt").write_text("x")

    with pytest.raises(ValueError, match="from a previous run"):
        create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
    assert (stray / "someone_elses.txt").exists()
