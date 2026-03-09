"""Standalone stall detection for agent execution.

Provides a synchronous, non-threaded detector that tracks time since
the last meaningful agent activity. Use ``StallMonitor`` (in
``stall_monitor.py``) for the threaded watchdog that wraps this logic.

This module has no runtime dependencies beyond the stdlib.
"""

import time
from enum import Enum


class StallAction(str, Enum):
    """Recovery action when a stall is detected.

    RETRY   - Kill the current attempt and retry the task.
    BLOCKER - Create a blocker for human intervention.
    FAIL    - Transition the task to FAILED.
    """

    RETRY = "retry"
    BLOCKER = "blocker"
    FAIL = "fail"


class StallDetectedError(Exception):
    """Raised when a stall is detected with RETRY action.

    Propagates up to ``execute_agent()`` so the runtime can re-invoke
    the agent with context about why the previous attempt stalled.
    """

    def __init__(self, elapsed_s: float, iterations: int, last_tool: str = "") -> None:
        self.elapsed_s = elapsed_s
        self.iterations = iterations
        self.last_tool = last_tool
        super().__init__(
            f"Agent stalled after {elapsed_s:.0f}s "
            f"(iterations={iterations}, last_tool={last_tool!r})"
        )


class StallDetector:
    """Tracks elapsed time since the last recorded activity.

    Call ``record_activity()`` after each tool execution or meaningful
    event.  Call ``is_stalled()`` to check whether the configured
    timeout has been exceeded.

    A ``timeout_s`` of 0 or negative disables detection (``is_stalled``
    always returns ``False``).
    """

    def __init__(self, timeout_s: float = 300) -> None:
        self.timeout_s = timeout_s
        self._last_activity: float = time.monotonic()

    def record_activity(self) -> None:
        """Reset the inactivity timer to *now*."""
        self._last_activity = time.monotonic()

    def is_stalled(self) -> bool:
        """Return ``True`` if no activity for longer than *timeout_s*."""
        if self.timeout_s <= 0:
            return False
        return (time.monotonic() - self._last_activity) > self.timeout_s

    def elapsed_since_activity_ms(self) -> int:
        """Milliseconds since the last recorded activity."""
        return int((time.monotonic() - self._last_activity) * 1000)
