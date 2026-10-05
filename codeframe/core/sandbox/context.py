"""ExecutionContext abstraction for task isolation.

Defines the IsolationLevel enum and ExecutionContext dataclass that allow
conductor.py and agent adapters to run tasks in isolated environments.

Isolation levels:
  NONE     — shared filesystem, preserves current behavior (default)
  WORKTREE — git worktree per task with merge-back (single-run path only; #787)
  CLOUD    — not implemented, raises NotImplementedError. Cloud execution
             exists only as an EXPERIMENTAL, unsupported engine gated behind
             CODEFRAME_ENABLE_CLOUD_ENGINE (#966), not as an isolation level.

Worktree scope (#787): worktree isolation is enabled for the in-process
single-run path (``cf work start --isolation worktree`` → runtime.execute_agent),
which rebases the workspace so code + gates land in the worktree while task/
blocker/event state stays in the main repo's ``.codeframe`` DB. The batch
subprocess path (conductor) stays rejected at the CLI: a spawned child runs with
``cwd=worktree`` and cannot reach the gitignored ``.codeframe`` DB there.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

logger = logging.getLogger(__name__)

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
            "IsolationLevel.CLOUD is not implemented. For local isolation use "
            "`--isolation worktree`. Cloud execution exists only as an "
            "EXPERIMENTAL, unsupported E2B engine (`--engine cloud`, gated behind "
            "CODEFRAME_ENABLE_CLOUD_ENGINE=1) — see the known limitations in "
            "CLAUDE.md before relying on it (#966)."
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


def _registered_on(porcelain: str, path: Path, branch: str) -> bool:
    """Whether ``git worktree list --porcelain`` lists ``path`` on ``branch``."""
    target = path.resolve()
    for block in porcelain.split("\n\n"):
        lines = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        if lines.get("worktree") and Path(lines["worktree"]).resolve() == target:
            return lines.get("branch") == f"refs/heads/{branch}"
    return False


def _create_worktree_context(task_id: str, repo_path: Path) -> ExecutionContext:
    """Create a git worktree and wire its merge-back / cleanup / preserve hooks.

    Worktrees are deliberately not tracked in any liveness-keyed registry:
    orphan cleanup keyed on process liveness would force-delete a *preserved*
    branch once this process exits, defeating the failure/conflict preservation
    the acceptance criteria require. The old ``WorktreeRegistry`` was therefore
    never written to, and was deleted in #958. A leftover worktree of this task
    is resumed on the next run (#1363); only something in its place that is not
    that worktree raises the actionable error below.
    """
    import subprocess

    from codeframe.core.worktrees import WORKTREE_DIR, TaskWorktree, get_base_branch

    def _git(*args: str) -> "subprocess.CompletedProcess[str]":
        return subprocess.run(
            ["git", *args], cwd=str(repo_path), capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )

    # A run that ended before merge-back (stopped, failed, conflicted) leaves
    # cf/<task_id> and its worktree preserved so no agent work is lost. The next
    # start resumes on it rather than refusing (#1363): committed and
    # uncommitted work carries over, and merge-back at the end lands it all.
    branch_name = f"cf/{task_id}"
    worktree_dir = repo_path / WORKTREE_DIR / task_id
    branch_exists = branch_name in _git("branch", "--list", branch_name).stdout
    base_branch = get_base_branch(repo_path)
    worktree = TaskWorktree()

    listing = _git("worktree", "list", "--porcelain") if branch_exists else None
    if listing is not None and listing.returncode != 0:
        # Fails closed below (the refusal), but say why, or a transient git
        # failure reads as "not a worktree of that branch".
        logger.warning("git worktree list failed: %s", (listing.stderr or "").strip()[:300])
    if (
        listing is not None
        and worktree_dir.exists()  # rm -rf leaves the registration behind
        and _registered_on(listing.stdout, worktree_dir, branch_name)
    ):
        worktree_path = worktree_dir
        logger.info("Resuming preserved worktree for %s at %s", task_id, worktree_path)
    elif branch_exists and not worktree_dir.exists():
        # The worktree dir was removed but the branch (the work) survives.
        _git("worktree", "prune")
        added = _git("worktree", "add", str(worktree_dir), branch_name)
        if added.returncode != 0:
            raise ValueError(
                f"could not reattach the preserved branch '{branch_name}': "
                f"{(added.stderr or added.stdout).strip()[:300]}"
            )
        worktree_path = worktree_dir
        logger.info("Reattached preserved branch %s at %s", branch_name, worktree_path)
    elif branch_exists or worktree_dir.exists():
        # Something is in the way that is provably not this task's worktree:
        # surface it rather than overwrite it (runtime turns this into a handled
        # failure, not a stranded IN_PROGRESS run).
        raise ValueError(
            f"a worktree or branch '{branch_name}' from a previous run of this task "
            "still exists but is not a worktree of that branch. Recover or discard "
            f"it, then retry — e.g. `git worktree remove --force {worktree_dir}` "
            f"and `git branch -D {branch_name}`."
        )
    else:
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
