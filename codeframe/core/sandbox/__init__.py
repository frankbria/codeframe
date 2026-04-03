"""Execution environment sandbox abstraction.

Provides ExecutionContext and IsolationLevel for isolating task execution
from the shared filesystem.
"""

from codeframe.core.sandbox.context import (
    ExecutionContext,
    IsolationLevel,
    create_execution_context,
)

__all__ = ["ExecutionContext", "IsolationLevel", "create_execution_context"]
