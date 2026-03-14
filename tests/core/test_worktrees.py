"""Tests for worktree-per-task isolation in parallel batch execution."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


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

        # Set up a real git repo
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1")

        assert worktree_path.exists()
        assert worktree_path.name == "task-1"
        assert (worktree_path / ".git").exists()  # worktrees have a .git file

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)

        wt = TaskWorktree()
        path = wt.create(tmp_path, "my-task")

        expected = tmp_path / ".codeframe" / "worktrees" / "my-task"
        assert path == expected

    def test_creates_branch_with_cf_prefix(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)

        wt = TaskWorktree()
        wt.create(tmp_path, "task-1")

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

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1")

        # Make a change in the worktree
        (worktree_path / "new_file.txt").write_text("hello")
        subprocess.run(["git", "-C", str(worktree_path), "add", "new_file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(worktree_path), "commit", "-m", "add file"], capture_output=True)

        # Merge back
        result = wt.merge_back(tmp_path, "task-1")

        assert result.success is True
        assert result.merge_commit is not None
        # File should now be in main branch
        assert (tmp_path / "new_file.txt").exists()

    def test_merge_conflict_returns_failure(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        (tmp_path / "file.txt").write_text("original")
        subprocess.run(["git", "-C", str(tmp_path), "add", "file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"], capture_output=True)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1")

        # Change in worktree
        (worktree_path / "file.txt").write_text("worktree change")
        subprocess.run(["git", "-C", str(worktree_path), "add", "file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(worktree_path), "commit", "-m", "wt change"], capture_output=True)

        # Conflicting change on main
        (tmp_path / "file.txt").write_text("main change")
        subprocess.run(["git", "-C", str(tmp_path), "add", "file.txt"], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "main change"], capture_output=True)

        result = wt.merge_back(tmp_path, "task-1")

        assert result.success is False
        assert result.conflict_details != ""


class TestTaskWorktreeCleanup:
    """Test TaskWorktree.cleanup()."""

    def test_removes_worktree_and_branch(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import TaskWorktree

        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"], capture_output=True)

        wt = TaskWorktree()
        worktree_path = wt.create(tmp_path, "task-1")
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
# BatchRun isolation field tests
# ---------------------------------------------------------------------------


class TestBatchRunIsolate:
    """Test BatchRun.isolate field."""

    def test_defaults_to_true(self) -> None:
        from codeframe.core.conductor import BatchRun, BatchStatus, OnFailure
        from datetime import datetime, timezone

        batch = BatchRun(
            id="b1", workspace_id="w1", task_ids=["t1"],
            status=BatchStatus.PENDING, strategy="parallel",
            max_parallel=4, on_failure=OnFailure.CONTINUE,
            started_at=datetime.now(timezone.utc), completed_at=None,
        )
        assert batch.isolate is True


class TestStartBatchIsolate:
    """Test start_batch with isolate parameter."""

    def test_passes_isolate_to_batch(self) -> None:
        from codeframe.core.conductor import start_batch

        workspace = MagicMock()
        workspace.id = "w1"
        mock_task = MagicMock()
        mock_task.id = "t1"

        with patch("codeframe.core.conductor.tasks.get", return_value=mock_task):
            with patch("codeframe.core.conductor._save_batch"):
                with patch("codeframe.core.conductor.events.emit_for_workspace"):
                    with patch("codeframe.core.conductor._execute_serial"):
                        batch = start_batch(workspace, ["t1"], isolate=False)

        assert batch.isolate is False
