"""Stall detection monitor for agent execution.

Detects when an agent stops making progress (no tool calls for a
configurable duration) and triggers a callback. Uses a daemon thread
that polls at regular intervals.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class StallEvent:
    """Information about a detected stall.

    Attributes:
        task_id: The task that stalled.
        stall_timeout_s: Configured timeout threshold.
        elapsed_s: Seconds since last tool execution.
        last_tool_call_at: Timestamp of the last tool execution (None if no tools ran).
        iterations_completed: Number of loop iterations completed before stall.
    """

    task_id: str
    stall_timeout_s: float
    elapsed_s: float
    last_tool_call_at: Optional[datetime]
    iterations_completed: int


class StallMonitor:
    """Thread-based watchdog that fires when agent activity stops.

    Create one instance per agent invocation. The monitor is stateless
    between runs.

    Usage::

        monitor = StallMonitor(stall_timeout_s=300, on_stall=my_callback)
        monitor.start("task-123")
        try:
            for iteration in agent_loop:
                # ... do work ...
                monitor.notify_tool_executed("task-123", iteration)
        finally:
            monitor.stop()
    """

    def __init__(
        self,
        stall_timeout_s: float,
        on_stall: Callable[[StallEvent], None],
        poll_interval_s: float = 5.0,
    ) -> None:
        self._stall_timeout_s = stall_timeout_s
        self._on_stall = on_stall
        self._poll_interval_s = poll_interval_s

        self._task_id: Optional[str] = None
        self._last_activity: Optional[datetime] = None
        self._last_tool_call_at: Optional[datetime] = None
        self._iterations: int = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self, task_id: str) -> None:
        """Begin monitoring for the given task."""
        if self._stall_timeout_s <= 0:
            return  # Disabled

        self.stop()  # Clean up any previous run
        self._task_id = task_id
        self._last_activity = datetime.now(timezone.utc)
        self._iterations = 0
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._watch_loop,
            name=f"stall-monitor-{task_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the watcher thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def notify_tool_executed(self, task_id: str, iteration: int) -> None:
        """Record that a tool was successfully executed.

        Call this after each successful tool execution to reset the
        inactivity timer.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            self._last_activity = now
            self._last_tool_call_at = now
            self._iterations = iteration

    def _watch_loop(self) -> None:
        """Daemon thread loop: check for stall at regular intervals."""
        while not self._stop_event.wait(timeout=self._poll_interval_s):
            with self._lock:
                if self._last_activity is None:
                    continue
                elapsed = (datetime.now(timezone.utc) - self._last_activity).total_seconds()
                iterations = self._iterations
                last_tool_call = self._last_tool_call_at

            if elapsed >= self._stall_timeout_s:
                event = StallEvent(
                    task_id=self._task_id or "",
                    stall_timeout_s=self._stall_timeout_s,
                    elapsed_s=elapsed,
                    last_tool_call_at=last_tool_call,
                    iterations_completed=iterations,
                )
                try:
                    self._on_stall(event)
                except Exception:
                    logger.exception("Stall callback failed")
                self._stop_event.set()
                return
