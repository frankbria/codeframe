"""Worktree-per-task isolation for parallel batch execution.

Creates isolated git worktrees so parallel agents don't modify files in the
same working directory. Each task gets its own branch and working tree,
then merges back to the base branch on completion.

Lifecycle:
    1. create(workspace_path, task_id) → worktree path
    2. Agent runs with cwd set to worktree
    3. merge_back(workspace_path, task_id) → MergeResult
    4. cleanup(workspace_path, task_id)
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WORKTREE_DIR = ".codeframe/worktrees"


@dataclass
class MergeResult:
    """Result from merging a worktree branch back to base."""

    task_id: str
    success: bool
    conflict_details: str
    merge_commit: Optional[str]


class TaskWorktree:
    """Manages git worktrees for isolated parallel task execution."""

    def create(
        self,
        workspace_path: Path,
        task_id: str,
        base_branch: str = "main",
    ) -> Path:
        """Create an isolated worktree for a task.

        Args:
            workspace_path: Root of the git repository
            task_id: Task identifier (used for branch and directory name)
            base_branch: Branch to base the worktree on

        Returns:
            Path to the created worktree directory

        Raises:
            subprocess.CalledProcessError: If git worktree creation fails
        """
        worktree_path = workspace_path / WORKTREE_DIR / task_id
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        branch_name = f"cf/{task_id}"

        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), "-b", branch_name, base_branch],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            check=True,
        )

        logger.info("Created worktree for %s at %s", task_id, worktree_path)
        return worktree_path

    def merge_back(
        self,
        workspace_path: Path,
        task_id: str,
        base_branch: str = "main",
    ) -> MergeResult:
        """Merge worktree branch back to base branch.

        Args:
            workspace_path: Root of the git repository
            task_id: Task identifier
            base_branch: Branch to merge into

        Returns:
            MergeResult with success status and optional conflict details
        """
        branch_name = f"cf/{task_id}"

        # Checkout base branch
        subprocess.run(
            ["git", "checkout", base_branch],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            check=True,
        )

        # Attempt merge
        result = subprocess.run(
            ["git", "merge", branch_name, "--no-ff", "-m", f"Merge {branch_name} into {base_branch}"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            # Get merge commit hash
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
            )
            merge_commit = head.stdout.strip() if head.returncode == 0 else None

            logger.info("Merged %s back to %s", branch_name, base_branch)
            return MergeResult(
                task_id=task_id,
                success=True,
                conflict_details="",
                merge_commit=merge_commit,
            )
        else:
            # Merge conflict — abort and report
            conflict_output = result.stdout + result.stderr
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=str(workspace_path),
                capture_output=True,
            )

            logger.warning("Merge conflict for %s: %s", branch_name, conflict_output[:200])
            return MergeResult(
                task_id=task_id,
                success=False,
                conflict_details=conflict_output[:2000],
                merge_commit=None,
            )

    def cleanup(
        self,
        workspace_path: Path,
        task_id: str,
    ) -> None:
        """Remove worktree and delete task branch.

        Never raises — cleanup failures are logged as warnings.
        """
        worktree_path = workspace_path / WORKTREE_DIR / task_id
        branch_name = f"cf/{task_id}"

        # Remove worktree
        try:
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            logger.warning("Failed to remove worktree for %s: %s", task_id, exc)

        # Delete branch
        try:
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            logger.warning("Failed to delete branch %s: %s", branch_name, exc)
