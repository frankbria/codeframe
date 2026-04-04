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
        NotImplementedError: If isolation is CLOUD (future E2B phase).
        subprocess.CalledProcessError: If git worktree creation fails.
    """
    if isolation == IsolationLevel.NONE:
        return ExecutionContext(
            task_id=task_id,
            isolation=isolation,
            workspace_path=repo_path,
            cleanup=lambda: None,
        )

    if isolation == IsolationLevel.WORKTREE:
        from codeframe.core.worktrees import TaskWorktree, WorktreeRegistry, get_base_branch

        worktree = TaskWorktree()
        registry = WorktreeRegistry()
        base_branch = get_base_branch(repo_path)
        worktree_path = worktree.create(repo_path, task_id, base_branch=base_branch)
        registry.register(repo_path, task_id, batch_id="unknown")

        def cleanup() -> None:
            worktree.cleanup(repo_path, task_id)
            registry.unregister(repo_path, task_id)

        return ExecutionContext(
            task_id=task_id,
            isolation=isolation,
            workspace_path=worktree_path,
            cleanup=cleanup,
        )

    if isolation == IsolationLevel.CLOUD:
        raise NotImplementedError(
            "IsolationLevel.CLOUD is reserved for the future E2B agent adapter phase. "
            "Use 'none' or 'worktree' instead."
        )

    raise ValueError(f"Unknown isolation level: {isolation}")
