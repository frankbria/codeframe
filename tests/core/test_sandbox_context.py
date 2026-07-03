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

pytestmark = pytest.mark.v2


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
    """Issue #714 / P0.3: worktree isolation is disabled until merge-back ships
    because cleanup() force-deleted the branch/worktree without merging agent
    work back — silent data loss. create_execution_context must fail closed and
    create NOTHING (no worktree dir, no branch)."""

    def test_worktree_is_rejected(self, git_repo: Path):
        with pytest.raises(ValueError, match="worktree isolation is temporarily disabled"):
            create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)

    def test_reject_message_points_at_the_issue(self, git_repo: Path):
        with pytest.raises(ValueError, match="#714"):
            create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)

    def test_no_worktree_created_on_reject(self, git_repo: Path):
        with pytest.raises(ValueError):
            create_execution_context("task-abc", IsolationLevel.WORKTREE, git_repo)
        # Nothing was created before the guard fired.
        assert not (git_repo / ".codeframe" / "worktrees" / "task-abc").exists()


class TestValidateIsolation:
    def test_none_is_allowed(self):
        from codeframe.core.sandbox.context import validate_isolation

        validate_isolation(IsolationLevel.NONE)  # no raise

    def test_worktree_raises(self):
        from codeframe.core.sandbox.context import validate_isolation

        with pytest.raises(ValueError, match="#714"):
            validate_isolation(IsolationLevel.WORKTREE)


class TestCreateExecutionContextCloud:
    def test_raises_not_implemented(self, tmp_path: Path):
        with pytest.raises(NotImplementedError, match="E2B"):
            create_execution_context("task-1", IsolationLevel.CLOUD, tmp_path)


class TestSandboxWorktreeReexports:
    """sandbox.worktree re-exports resolve correctly (issue #535)."""

    def test_task_worktree_importable_from_sandbox(self):
        from codeframe.core.sandbox import TaskWorktree
        assert TaskWorktree is not None

    def test_merge_result_importable_from_sandbox(self):
        from codeframe.core.sandbox import MergeResult
        assert MergeResult is not None

    def test_worktree_registry_importable_from_sandbox(self):
        from codeframe.core.sandbox import WorktreeRegistry
        assert WorktreeRegistry is not None

    def test_get_base_branch_importable_from_sandbox(self):
        from codeframe.core.sandbox import get_base_branch
        assert callable(get_base_branch)

    def test_sandbox_worktree_module_importable(self):
        from codeframe.core.sandbox import worktree as wt_mod
        assert hasattr(wt_mod, "TaskWorktree")
        assert hasattr(wt_mod, "WorktreeRegistry")
