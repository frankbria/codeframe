"""Tests for ExecutionContext abstraction (issue #532).

Tests the context lifecycle:
  - NONE: no-op wrapper, workspace_path == repo_path
  - WORKTREE: creates git worktree, cleanup removes it
  - CLOUD: raises NotImplementedError

Uses a real git repo via tmp_path fixture (no mocking of git).
"""

import subprocess
from pathlib import Path

import pytest

from codeframe.core.sandbox.context import (
    ExecutionContext,
    IsolationLevel,
    create_execution_context,
)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing with an explicit 'main' branch."""
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    # Need at least one commit for worktrees to work
    (tmp_path / "README.md").write_text("test")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    return tmp_path


class TestIsolationLevel:
    def test_enum_values(self):
        assert IsolationLevel.NONE == "none"
        assert IsolationLevel.WORKTREE == "worktree"
        assert IsolationLevel.CLOUD == "cloud"

    def test_from_string(self):
        assert IsolationLevel("none") is IsolationLevel.NONE
        assert IsolationLevel("worktree") is IsolationLevel.WORKTREE
        assert IsolationLevel("cloud") is IsolationLevel.CLOUD


class TestExecutionContextDataclass:
    def test_fields(self, tmp_path: Path):
        ctx = ExecutionContext(
            task_id="task-1",
            isolation=IsolationLevel.NONE,
            workspace_path=tmp_path,
            cleanup=lambda: None,
        )
        assert ctx.task_id == "task-1"
        assert ctx.isolation == IsolationLevel.NONE
        assert ctx.workspace_path == tmp_path

    def test_cleanup_is_callable(self, tmp_path: Path):
        called = []
        ctx = ExecutionContext(
            task_id="t",
            isolation=IsolationLevel.NONE,
            workspace_path=tmp_path,
            cleanup=lambda: called.append(True),
        )
        ctx.cleanup()
        assert called == [True]


class TestCreateExecutionContextNone:
    def test_workspace_path_equals_repo_path(self, tmp_path: Path):
        ctx = create_execution_context("task-1", IsolationLevel.NONE, tmp_path)
        assert ctx.workspace_path == tmp_path

    def test_isolation_level(self, tmp_path: Path):
        ctx = create_execution_context("task-1", IsolationLevel.NONE, tmp_path)
        assert ctx.isolation == IsolationLevel.NONE

    def test_cleanup_is_noop(self, tmp_path: Path):
        ctx = create_execution_context("task-1", IsolationLevel.NONE, tmp_path)
        # Should not raise and should not modify anything
        ctx.cleanup()
        assert tmp_path.exists()

    def test_task_id_stored(self, tmp_path: Path):
        ctx = create_execution_context("my-task", IsolationLevel.NONE, tmp_path)
        assert ctx.task_id == "my-task"


class TestCreateExecutionContextWorktree:
    def test_creates_worktree_directory(self, git_repo: Path):
        ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        assert ctx.workspace_path.exists()
        assert ctx.workspace_path.is_dir()
        ctx.cleanup()

    def test_workspace_path_differs_from_repo_path(self, git_repo: Path):
        ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        assert ctx.workspace_path != git_repo
        ctx.cleanup()

    def test_workspace_path_is_inside_worktrees_dir(self, git_repo: Path):
        ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        assert ".codeframe/worktrees" in str(ctx.workspace_path)
        ctx.cleanup()

    def test_cleanup_removes_worktree(self, git_repo: Path):
        ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        worktree_path = ctx.workspace_path
        assert worktree_path.exists()
        ctx.cleanup()
        assert not worktree_path.exists()

    def test_isolation_level_stored(self, git_repo: Path):
        ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        assert ctx.isolation == IsolationLevel.WORKTREE
        ctx.cleanup()

    def test_task_id_stored(self, git_repo: Path):
        ctx = create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        assert ctx.task_id == "task-abc"
        ctx.cleanup()

    def test_worktree_contains_repo_files(self, git_repo: Path):
        ctx = create_execution_context("task-wt", IsolationLevel.WORKTREE, git_repo)
        assert (ctx.workspace_path / "README.md").exists()
        ctx.cleanup()


class TestCreateExecutionContextCloud:
    def test_raises_not_implemented(self, tmp_path: Path):
        with pytest.raises(NotImplementedError, match="E2B"):
            create_execution_context("task-1", IsolationLevel.CLOUD, tmp_path)
