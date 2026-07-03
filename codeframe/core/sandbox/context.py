"""ExecutionContext abstraction for task isolation.

Defines the IsolationLevel enum and ExecutionContext dataclass that allow
conductor.py and agent adapters to run tasks in isolated environments.

Isolation levels:
  NONE     — shared filesystem, preserves current behavior (default)
  WORKTREE — git worktree per task, safe for parallel execution
  CLOUD    — E2B Linux VM per task (reserved, raises NotImplementedError)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class IsolationLevel(str, Enum):
    """Task execution isolation strategy."""

    NONE = "none"
    WORKTREE = "worktree"
    CLOUD = "cloud"


@dataclass
class ExecutionContext:
    """Execution environment for a single task run.

    Attributes:
        task_id: Task being executed.
        isolation: Isolation strategy in use.
        workspace_path: Root path the agent should use for all file I/O.
        cleanup: Called after task completion to release resources.
    """

    task_id: str
    isolation: IsolationLevel
    workspace_path: Path
    cleanup: Callable[[], None]


# worktree isolation is disabled until real merge-back ships (issue #714).
# It force-deleted the per-task branch/worktree in cleanup() WITHOUT ever
# merging the agent's work back to the base branch — silently discarding all
# changes. Re-enable once merge-back (+ auto-commit of worktree changes) lands;
# that work is gated behind #715 (builtin engines ignore the worktree path) and
# #716 (verification runs against the wrong tree).
_WORKTREE_DISABLED_MSG = (
    "worktree isolation is temporarily disabled: it discards agent work without "
    "merging it back to the base branch (silent data loss — see issue #714). "
    "Use --isolation none (the default) until merge-back ships."
)


def validate_isolation(isolation: IsolationLevel) -> None:
    """Reject isolation levels that are not currently safe to run.

    Raises:
        ValueError: If ``isolation`` is WORKTREE (see #714). Callers (CLI,
            server, conductor) should surface this to the user *before*
            creating a run so no task is stranded IN_PROGRESS.
    """
    if isolation == IsolationLevel.WORKTREE:
        raise ValueError(_WORKTREE_DISABLED_MSG)


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
        ExecutionContext with workspace_path and cleanup configured.

    Raises:
        ValueError: If isolation is WORKTREE (disabled until merge-back — #714).
        NotImplementedError: If isolation is CLOUD (future E2B phase).
    """
    # Fail closed before creating anything: WORKTREE would destroy agent work.
    validate_isolation(isolation)

    if isolation == IsolationLevel.NONE:
        return ExecutionContext(
            task_id=task_id,
            isolation=isolation,
            workspace_path=repo_path,
            cleanup=lambda: None,
        )

    if isolation == IsolationLevel.CLOUD:
        raise NotImplementedError(
            "IsolationLevel.CLOUD is reserved for the future E2B agent adapter phase. "
            "Use 'none' instead."
        )

    raise ValueError(f"Unknown isolation level: {isolation}")
