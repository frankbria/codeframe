"""Tests for worktree-per-task isolation in parallel batch execution."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


def _get_default_branch(repo_path: Path) -> str:
    """Get the default branch name of a git repo."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "main"


# ---------------------------------------------------------------------------
# MergeResult tests
# ---------------------------------------------------------------------------


class TestMergeResult:
    """Test MergeResult dataclass."""

    def test_successful_merge(self) -> None:
        from codeframe.core.worktrees import MergeResult

        r = MergeResult(task_id="t1", success=True, conflict_details="", merge_commit="abc123")
        assert r.success is True
        assert r.merge_commit == "abc123"

    def test_conflict_merge(self) -> None:
        from codeframe.core.worktrees import MergeResult

        r = MergeResult(task_id="t1", success=False, conflict_details="CONFLICT in file.py", merge_commit=None)
        assert r.success is False
        assert "CONFLICT" in r.conflict_details


# ---------------------------------------------------------------------------
# TaskWorktree tests
# ---------------------------------------------------------------------------


class TestTaskWorktreeCreate:
    """Test TaskWorktree.create()."""

    def test_creates_worktree(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        base = _get_default_branch(tmp_path)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1", base_branch=base)

        assert worktree_path.exists()
        assert worktree_path.name == "task-1"
        assert (worktree_path / ".git").exists()

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        base = _get_default_branch(tmp_path)

        wt = TaskWorktree()
        path = wt.create(tmp_path, "my-task", base_branch=base)

        expected = tmp_path / ".codeframe" / "worktrees" / "my-task"
        assert path == expected

    def test_creates_branch_with_cf_prefix(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        base = _get_default_branch(tmp_path)

        wt = TaskWorktree()
        wt.create(tmp_path, "task-1", base_branch=base)

        # Check branch exists
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--list", "cf/task-1"],
            capture_output=True, text=True,
        )
        assert "cf/task-1" in result.stdout


class TestTaskWorktreeMergeBack:
    """Test TaskWorktree.merge_back()."""

    def test_successful_merge(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        # Set up repo with initial commit
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        base_branch = _get_default_branch(tmp_path)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1", base_branch=base_branch)

        # Make a change in the worktree
        (worktree_path / "new_file.txt").write_text("hello")
        subprocess.run(["git", "-C", str(worktree_path), "add", "new_file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(worktree_path), "commit", "-m", "add file"], capture_output=True)

        # Merge back
        result = wt.merge_back(tmp_path, "task-1", base_branch=base_branch)

        assert result.success is True
        assert result.merge_commit is not None
        # File should now be in base branch
        assert (tmp_path / "new_file.txt").exists()

    def test_merge_conflict_returns_failure(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        (tmp_path / "file.txt").write_text("original")
        subprocess.run(["git", "-C", str(tmp_path), "add", "file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"], capture_output=True)
        base_branch = _get_default_branch(tmp_path)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1", base_branch=base_branch)

        # Change in worktree
        (worktree_path / "file.txt").write_text("worktree change")
        subprocess.run(["git", "-C", str(worktree_path), "add", "file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(worktree_path), "commit", "-m", "wt change"], capture_output=True)

        # Conflicting change on base branch
        (tmp_path / "file.txt").write_text("main change")
        subprocess.run(["git", "-C", str(tmp_path), "add", "file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "main change"], capture_output=True)

        result = wt.merge_back(tmp_path, "task-1", base_branch=base_branch)

        assert result.success is False
        assert result.conflict_details != ""


class TestTaskWorktreeCleanup:
    """Test TaskWorktree.cleanup()."""

    def test_removes_worktree_and_branch(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        base = _get_default_branch(tmp_path)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1", base_branch=base)
        assert worktree_path.exists()

        wt.cleanup(tmp_path, "task-1")

        assert not worktree_path.exists()
        # Branch should be deleted
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "branch", "--list", "cf/task-1"],
            capture_output=True, text=True,
        )
        assert "cf/task-1" not in result.stdout

    def test_cleanup_nonexistent_does_not_raise(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)

        wt = TaskWorktree()
        # Should not raise
        wt.cleanup(tmp_path, "nonexistent-task")


# ---------------------------------------------------------------------------
# get_base_branch tests
# ---------------------------------------------------------------------------


class TestGetBaseBranch:
    """Test get_base_branch() helper."""

    def test_returns_current_branch(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import get_base_branch

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)

        result = get_base_branch(tmp_path)
        assert isinstance(result, str)
        assert result  # non-empty

    def test_returns_main_on_failure(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import get_base_branch

        # Non-git directory → should default to "main"
        result = get_base_branch(tmp_path)
        assert result == "main"

    def test_returns_main_in_detached_head_state(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import get_base_branch

        # Simulate git returning "HEAD" (detached HEAD)
        mock_result = MagicMock(returncode=0, stdout="HEAD\n")
        with patch("subprocess.run", return_value=mock_result):
            result = get_base_branch(tmp_path)
        assert result == "main"
