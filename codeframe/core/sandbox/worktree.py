"""Worktree registry re-export for the sandbox namespace.

Re-exports ``TaskWorktree``, ``MergeResult``, ``WorktreeRegistry``, and
``get_base_branch`` from ``codeframe.core.worktrees`` so callers can import
from a single ``codeframe.core.sandbox`` sub-package.
"""

from codeframe.core.worktrees import (
    MergeResult,
    TaskWorktree,
    WorktreeRegistry,
    get_base_branch,
)

__all__ = [
    "MergeResult",
    "TaskWorktree",
    "WorktreeRegistry",
    "get_base_branch",
]
