"""ExecutionContext abstraction for task isolation.

Defines the IsolationLevel enum and ExecutionContext dataclass that allow
conductor.py and agent adapters to run tasks in isolated environments.

Isolation levels:
  NONE     — shared filesystem, preserves current behavior (default)
  WORKTREE — git worktree per task with merge-back (single-run path only; #787)
  CLOUD    — E2B Linux VM per task (reserved, raises NotImplementedError)

Worktree scope (#787): worktree isolation is enabled for the in-process
single-run path (``cf work start --isolation worktree`` → runtime.execute_agent),
which rebases the workspace so code + gates land in the worktree while task/
blocker/event state stays in the main repo's ``.codeframe`` DB. The batch
subprocess path (conductor) stays rejected at the CLI: a spawned child runs with
``cwd=worktree`` and cannot reach the gitignored ``.codeframe`` DB there.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from codeframe.core.workspace import Workspace
    from codeframe.core.worktrees import MergeResult


class IsolationLevel(str, Enum):
    """Task execution isolation strategy."""

    NONE = "none"
    WORKTREE = "worktree"
    CLOUD = "cloud"


def _noop() -> None:
    return None


@dataclass
class ExecutionContext:
    """Execution environment for a single task run.

    Attributes:
        task_id: Task being executed.
        isolation: Isolation strategy in use.
        workspace_path: Root path the agent should use for all file I/O.
        cleanup: Full teardown — removes the worktree and deletes its branch
            (no-op for NONE). Called only when the run's work has been merged
            back (or when there is nothing to preserve).
        merge_back: For WORKTREE, auto-commits worktree changes then merges the
            task branch into the base branch, returning a MergeResult. ``None``
            when there is no worktree to merge (NONE).
        preserve: Leave the worktree + branch intact for recovery (no-op for
            NONE). Called instead of ``cleanup`` on failure, block, or merge
            conflict so agent work is never silently discarded (the #714 bug).
    """

    task_id: str
    isolation: IsolationLevel
    workspace_path: Path
    cleanup: Callable[[], None]
    merge_back: Optional[Callable[[], "MergeResult"]] = None
    preserve: Callable[[], None] = field(default=_noop)


def rebased_workspace(workspace: "Workspace", workspace_path: Path) -> "Workspace":
    """Return a Workspace whose code root is ``workspace_path``.

    Used by the builtin adapters (#715) and the verification wrapper (#716) so
    that code I/O and verification gates run against the worktree, while the
    ``state_dir``/``db_path`` (task, blocker, and event state) stay pointed at
    the original main-repo ``.codeframe`` directory. Returns the workspace
    unchanged when ``workspace_path`` already is its repo root (the NONE case).
    """
    if Path(workspace_path) == workspace.repo_path:
        return workspace
    return dataclasses.replace(workspace, repo_path=Path(workspace_path))


def validate_isolation(isolation: IsolationLevel) -> None:
    """Reject isolation levels that are not currently safe to run.

    WORKTREE is now allowed for the in-process single-run path (#787): it
    auto-commits and merges agent work back to the base branch, and preserves
    the branch on failure/conflict rather than discarding it (the #714 bug).

    Raises:
        NotImplementedError: If ``isolation`` is CLOUD (reserved for E2B).

    Note:
        The batch subprocess path (conductor) still rejects WORKTREE at the CLI
        because a child process cannot reach the gitignored ``.codeframe`` DB in
        a worktree. That guard lives in ``cli/app.py`` (batch command), not here.
    """
    if isolation == IsolationLevel.CLOUD:
        raise NotImplementedError(
            "IsolationLevel.CLOUD is reserved for the future E2B agent adapter phase. "
            "Use 'none' instead."
        )


def create_execution_context(
    task_id: str,
    isolation: IsolationLevel,
    repo_path: Path,
) -> ExecutionContext:
    """Create an ExecutionContext for the given isolation level.

    Args:
        task_id: Task identifier (used as worktree directory name).
        isolation: Desired isolation level.
        repo_path: Canonical repository root path.

    Returns:
        ExecutionContext with workspace_path, merge_back, cleanup, and preserve
        configured for the isolation level.

    Raises:
        NotImplementedError: If isolation is CLOUD (future E2B phase).
        ValueError: If isolation is an unknown level.
    """
    validate_isolation(isolation)

    if isolation == IsolationLevel.NONE:
        return ExecutionContext(
            task_id=task_id,
            isolation=isolation,
            workspace_path=repo_path,
            cleanup=_noop,
        )

    if isolation == IsolationLevel.WORKTREE:
        return _create_worktree_context(task_id, repo_path)

    raise ValueError(f"Unknown isolation level: {isolation}")


def _create_worktree_context(task_id: str, repo_path: Path) -> ExecutionContext:
    """Create a git worktree and wire its merge-back / cleanup / preserve hooks.

    The worktree is intentionally NOT registered in WorktreeRegistry: orphan
    cleanup (keyed on process liveness) would force-delete a preserved branch
    once this process exits, defeating the failure/conflict preservation the
    acceptance criteria require.
    """
    import subprocess

    from codeframe.core.worktrees import WORKTREE_DIR, TaskWorktree, get_base_branch

    # A preserved cf/<task_id> branch or worktree dir from a prior failed/conflicted
    # run would make `git worktree add -b` fail. Surface an actionable error instead
    # of a raw git traceback (runtime creates this inside its try, so this becomes a
    # handled failure rather than a stranded IN_PROGRESS run).
    branch_name = f"cf/{task_id}"
    existing = subprocess.run(
        ["git", "branch", "--list", branch_name],
        cwd=str(repo_path), capture_output=True, text=True,
    )
    worktree_dir = repo_path / WORKTREE_DIR / task_id
    if branch_name in existing.stdout or worktree_dir.exists():
        raise ValueError(
            f"a worktree or branch '{branch_name}' from a previous run of this task "
            "still exists (preserved for recovery). Recover or discard it, then "
            f"retry — e.g. `git worktree remove --force {worktree_dir}` and "
            f"`git branch -D {branch_name}`."
        )

    base_branch = get_base_branch(repo_path)
    worktree = TaskWorktree()
    worktree_path = worktree.create(repo_path, task_id, base_branch=base_branch)

    def _merge_back() -> "MergeResult":
        worktree.auto_commit(worktree_path, task_id)
        return worktree.merge_back(repo_path, task_id, base_branch=base_branch)

    return ExecutionContext(
        task_id=task_id,
        isolation=IsolationLevel.WORKTREE,
        workspace_path=worktree_path,
        cleanup=lambda: worktree.cleanup(repo_path, task_id),
        merge_back=_merge_back,
        preserve=_noop,  # leave worktree + branch on disk for recovery
    )
