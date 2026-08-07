"""Worktree re-export for the sandbox namespace.

Re-exports ``TaskWorktree``, ``MergeResult`` and ``get_base_branch`` from
``codeframe.core.worktrees`` so callers can import from a single
``codeframe.core.sandbox`` sub-package.

``WorktreeRegistry`` used to be re-exported here too; it was deleted in #958 —
nothing ever registered into it, because ``sandbox/context.py`` deliberately
skips registration so liveness-keyed cleanup cannot force-delete a preserved
branch.
"""

from codeframe.core.worktrees import (
    MergeResult,
    TaskWorktree,
    get_base_branch,
)

__all__ = [
    "MergeResult",
    "TaskWorktree",
    "get_base_branch",
]
