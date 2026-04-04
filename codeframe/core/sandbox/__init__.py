"""Execution environment sandbox abstraction.

Provides ExecutionContext and IsolationLevel for isolating task execution
from the shared filesystem, plus worktree registry helpers.
"""

from codeframe.core.sandbox.context import (
    ExecutionContext,
    IsolationLevel,
    create_execution_context,
)
from codeframe.core.sandbox.worktree import (
    MergeResult,
    TaskWorktree,
    WorktreeRegistry,
    get_base_branch,
)

__all__ = [
    "ExecutionContext",
    "IsolationLevel",
    "create_execution_context",
    "MergeResult",
    "TaskWorktree",
    "WorktreeRegistry",
    "get_base_branch",
]
