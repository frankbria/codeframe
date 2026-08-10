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

import contextlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX (e.g. native Windows)
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

WORKTREE_DIR = ".codeframe/worktrees"


@contextlib.contextmanager
def _main_tree_lock(workspace_path: Path) -> Iterator[None]:
    """Serialize operations that mutate the shared main working tree.

    ``merge_back`` runs ``git checkout`` + ``git merge`` directly in the main
    repo's single working directory. Two concurrent single-run worktree merges
    against the same repo would otherwise interleave in that one directory and
    corrupt it. This is a cross-process advisory lock (``flock``) keyed on the
    repo. Best-effort: a no-op where ``fcntl`` is unavailable (non-POSIX).
    """
    if fcntl is None:
        yield
        return
    lock_path = workspace_path / ".git" / "cf-merge.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


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
            encoding="utf-8",
            errors="replace",
            check=True,
        )

        logger.info("Created worktree for %s at %s", task_id, worktree_path)
        return worktree_path

    def auto_commit(
        self,
        worktree_path: Path,
        task_id: str,
    ) -> bool:
        """Stage and commit all changes in the worktree on its branch.

        Agent adapters write files but never commit, so ``git merge cf/<task_id>``
        would merge nothing. This commits any pending work first.

        Args:
            worktree_path: Path to the task's worktree directory
            task_id: Task identifier (for the commit message)

        Returns:
            True if a commit was created, False if the worktree was clean.

        Raises:
            RuntimeError: If staging or committing fails. Failing loudly is
                deliberate — a silent failure here would report "clean"/"committed"
                while agent work sits uncommitted, and the caller's merge-back
                would then merge nothing and cleanup would delete the branch,
                discarding that work (the #714 class of bug). On raise, the run's
                merge-back aborts and the branch/worktree are preserved.
        """
        add = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if add.returncode != 0:
            raise RuntimeError(
                f"git add failed in worktree for {task_id}: {add.stderr.strip()}"
            )

        # Nothing staged → genuinely clean; nothing to commit.
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(worktree_path),
            capture_output=True,
        )
        if staged.returncode == 0:
            return False

        commit = subprocess.run(
            ["git", "commit", "-m", f"cf: auto-commit worktree changes for {task_id}"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if commit.returncode != 0:
            # Staged changes exist but couldn't be committed (hook rejection,
            # missing identity, object-DB error). Do NOT report success — that
            # would route to cleanup and discard the staged work.
            raise RuntimeError(
                f"git commit failed in worktree for {task_id}: "
                f"{(commit.stderr or commit.stdout).strip()}"
            )
        logger.info("Auto-committed worktree changes for %s", task_id)
        return True

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

        # checkout + merge mutate the shared main working tree — serialize against
        # concurrent worktree merges on the same repo (see _main_tree_lock).
        with _main_tree_lock(workspace_path):
            # Checkout base branch
            subprocess.run(
                ["git", "checkout", base_branch],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )

            # Attempt merge
            result = subprocess.run(
                ["git", "merge", branch_name, "--no-ff", "-m", f"Merge {branch_name} into {base_branch}"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0:
                # Get merge commit hash
                head = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(workspace_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                merge_commit = head.stdout.strip() if head.returncode == 0 else None

                logger.info("Merged %s back to %s", branch_name, base_branch)
                return MergeResult(
                    task_id=task_id,
                    success=True,
                    conflict_details="",
                    merge_commit=merge_commit,
                )

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

        Git's **exit code** is inspected, not just the absence of an exception
        (#958). Both commands used to be fire-and-forget, so a failed branch
        delete left ``cf/<task_id>`` behind and the *next* run of that task died
        in ``_create_worktree_context`` ("a worktree or branch already exists")
        with nothing in the log explaining why.
        """
        worktree_path = workspace_path / WORKTREE_DIR / task_id
        branch_name = f"cf/{task_id}"

        for what, cmd in (
            (
                f"remove worktree for {task_id}",
                ["git", "worktree", "remove", str(worktree_path), "--force"],
            ),
            (f"delete branch {branch_name}", ["git", "branch", "-D", branch_name]),
        ):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(workspace_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception as exc:
                logger.warning("Failed to %s: %s", what, exc)
                continue
            if result.returncode != 0:
                logger.warning(
                    "Failed to %s (git exit %s): %s",
                    what,
                    result.returncode,
                    (result.stderr or result.stdout or "").strip()[:500],
                )


def get_base_branch(workspace_path: Path) -> str:
    """Return the current HEAD branch name, defaulting to 'main' on failure.

    Returns 'main' when git is unavailable, the directory is not a repo,
    or HEAD is detached (rev-parse returns 'HEAD' literally).
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(workspace_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch or branch == "HEAD":
        return "main"
    return branch

