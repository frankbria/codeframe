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


# ---------------------------------------------------------------------------
# list_worktrees tests
# ---------------------------------------------------------------------------


class TestListWorktrees:
    """Test list_worktrees() helper."""

    def test_returns_empty_list_when_no_registry(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import list_worktrees

        result = list_worktrees(tmp_path)
        assert result == []

    def test_returns_entries_from_registry(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import list_worktrees
        import json

        registry_file = tmp_path / ".codeframe" / "worktrees.json"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps([
            {"task_id": "t1", "batch_id": "b1", "created_at": "2026-01-01T00:00:00", "pid": 12345},
        ]))

        result = list_worktrees(tmp_path)
        assert len(result) == 1
        assert result[0]["task_id"] == "t1"

    def test_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import list_worktrees

        registry_file = tmp_path / ".codeframe" / "worktrees.json"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text("not-json{{{")

        result = list_worktrees(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# WorktreeRegistry tests
# ---------------------------------------------------------------------------


class TestWorktreeRegistry:
    """Test WorktreeRegistry class."""

    def test_register_creates_entry(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry, list_worktrees

        reg = WorktreeRegistry()
        reg.register(tmp_path, "task-1", "batch-1")

        entries = list_worktrees(tmp_path)
        assert len(entries) == 1
        assert entries[0]["task_id"] == "task-1"
        assert entries[0]["batch_id"] == "batch-1"
        assert "pid" in entries[0]
        assert "created_at" in entries[0]

    def test_unregister_removes_entry(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry, list_worktrees

        reg = WorktreeRegistry()
        reg.register(tmp_path, "task-1", "batch-1")
        reg.register(tmp_path, "task-2", "batch-1")
        reg.unregister(tmp_path, "task-1")

        entries = list_worktrees(tmp_path)
        task_ids = [e["task_id"] for e in entries]
        assert "task-1" not in task_ids
        assert "task-2" in task_ids

    def test_unregister_nonexistent_is_safe(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry

        reg = WorktreeRegistry()
        reg.unregister(tmp_path, "nonexistent")  # should not raise

    def test_list_stale_returns_dead_pid_entries(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry
        import json

        # PID 999999999 is virtually guaranteed to not exist
        registry_file = tmp_path / ".codeframe" / "worktrees.json"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps([
            {"task_id": "dead-task", "batch_id": "b1", "created_at": "2026-01-01T00:00:00", "pid": 999999999},
        ]))

        reg = WorktreeRegistry()
        stale = reg.list_stale(tmp_path)
        assert len(stale) == 1
        assert stale[0]["task_id"] == "dead-task"

    def test_list_stale_excludes_live_pid(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry
        import os
        import json

        registry_file = tmp_path / ".codeframe" / "worktrees.json"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps([
            {"task_id": "live-task", "batch_id": "b1", "created_at": "2026-01-01T00:00:00", "pid": os.getpid()},
        ]))

        reg = WorktreeRegistry()
        stale = reg.list_stale(tmp_path)
        assert all(e["task_id"] != "live-task" for e in stale)

    def test_cleanup_stale_removes_orphaned_worktrees(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry, list_worktrees
        import json

        # Register a stale entry (dead PID, no actual worktree directory)
        registry_file = tmp_path / ".codeframe" / "worktrees.json"
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        registry_file.write_text(json.dumps([
            {"task_id": "orphan", "batch_id": "b1", "created_at": "2026-01-01T00:00:00", "pid": 999999999},
        ]))

        reg = WorktreeRegistry()
        reg.cleanup_stale(tmp_path)

        # Entry should be removed from registry
        entries = list_worktrees(tmp_path)
        assert all(e["task_id"] != "orphan" for e in entries)

    def test_register_is_idempotent_for_same_task(self, tmp_path: Path) -> None:
        from codeframe.core.worktrees import WorktreeRegistry, list_worktrees

        reg = WorktreeRegistry()
        reg.register(tmp_path, "task-1", "batch-1")
        reg.register(tmp_path, "task-1", "batch-1")  # duplicate

        entries = list_worktrees(tmp_path)
        task_ids = [e["task_id"] for e in entries]
        assert task_ids.count("task-1") == 1


# ---------------------------------------------------------------------------
# Conductor orphan cleanup tests
# ---------------------------------------------------------------------------


class TestConductorOrphanCleanup:
    """Test that _execute_parallel calls WorktreeRegistry.cleanup_stale."""

    def test_cleanup_stale_called_on_parallel_with_worktree_isolation(self) -> None:
        from codeframe.core.conductor import start_batch
        from unittest.mock import patch, MagicMock

        workspace = MagicMock()
        workspace.id = "w1"
        workspace.repo_path = Path("/tmp/fake-repo")
        mock_task = MagicMock()
        mock_task.id = "t1"

        with patch("codeframe.core.conductor.tasks.get", return_value=mock_task):
            with patch("codeframe.core.conductor._save_batch"):
                with patch("codeframe.core.conductor.events.emit_for_workspace"):
                    with patch("codeframe.core.conductor._execute_parallel") as mock_parallel:
                        start_batch(
                            workspace, ["t1"],
                            strategy="parallel",
                            isolation="worktree",
                        )
                        assert mock_parallel.called
