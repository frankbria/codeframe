"""Tests for stall detection monitor.

Tests cover:
- StallMonitor standalone behavior
- StallEvent creation
- Thread-based watchdog timing
- ReactAgent integration (stall → BLOCKED path)
- Disabled stall detection (timeout=0)
"""

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.stall_monitor import StallEvent, StallMonitor

pytestmark = pytest.mark.v2


class TestStallEvent:
    """Test StallEvent dataclass."""

    def test_create_stall_event(self):
        event = StallEvent(
            task_id="task-1",
            stall_timeout_s=300,
            elapsed_s=305.2,
            last_tool_call_at=datetime.now(timezone.utc),
            iterations_completed=5,
        )
        assert event.task_id == "task-1"
        assert event.stall_timeout_s == 300
        assert event.elapsed_s == 305.2
        assert event.iterations_completed == 5

    def test_stall_event_without_last_tool_call(self):
        event = StallEvent(
            task_id="task-1",
            stall_timeout_s=300,
            elapsed_s=300.0,
            last_tool_call_at=None,
            iterations_completed=0,
        )
        assert event.last_tool_call_at is None


class TestStallMonitor:
    """Test StallMonitor watchdog behavior."""

    def test_init(self):
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=300, on_stall=callback)
        assert monitor._stall_timeout_s == 300
        assert monitor._on_stall is callback

    def test_start_sets_last_activity(self):
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=300, on_stall=callback)
        monitor.start("task-1")
        try:
            assert monitor._task_id == "task-1"
            assert monitor._last_activity is not None
        finally:
            monitor.stop()

    def test_stop_terminates_watcher(self):
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=300, on_stall=callback)
        monitor.start("task-1")
        monitor.stop()
        # Give the thread time to exit
        time.sleep(0.1)
        assert monitor._stop_event.is_set()

    def test_notify_tool_executed_resets_activity(self):
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=300, on_stall=callback)
        monitor.start("task-1")
        try:
            before = monitor._last_activity
            time.sleep(0.05)
            monitor.notify_tool_executed("task-1", iteration=1)
            after = monitor._last_activity
            assert after > before
        finally:
            monitor.stop()

    def test_stall_fires_callback_after_timeout(self):
        """Use a very short timeout to test the stall detection fires."""
        callback = MagicMock()
        # Use 0.2s timeout with 0.05s poll interval for fast testing
        monitor = StallMonitor(stall_timeout_s=0.2, on_stall=callback, poll_interval_s=0.05)
        monitor.start("task-1")
        try:
            # Wait for stall to trigger
            time.sleep(0.5)
            assert callback.called
            event = callback.call_args[0][0]
            assert isinstance(event, StallEvent)
            assert event.task_id == "task-1"
            assert event.elapsed_s >= 0.2
        finally:
            monitor.stop()

    def test_notify_prevents_stall(self):
        """Notifying tool execution prevents stall from firing."""
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=0.3, on_stall=callback, poll_interval_s=0.05)
        monitor.start("task-1")
        try:
            # Keep notifying to prevent stall
            for _ in range(6):
                time.sleep(0.1)
                monitor.notify_tool_executed("task-1", iteration=1)
            # Should not have stalled since we kept notifying
            assert not callback.called
        finally:
            monitor.stop()

    def test_disabled_when_timeout_zero(self):
        """Stall monitor does nothing when timeout is 0 (disabled)."""
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=0, on_stall=callback)
        monitor.start("task-1")
        time.sleep(0.2)
        monitor.stop()
        assert not callback.called

    def test_callback_receives_correct_iteration_count(self):
        """StallEvent should include the iteration count at time of stall."""
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=0.15, on_stall=callback, poll_interval_s=0.05)
        monitor.start("task-1")
        try:
            monitor.notify_tool_executed("task-1", iteration=3)
            time.sleep(0.3)
            assert callback.called
            event = callback.call_args[0][0]
            assert event.iterations_completed == 3
        finally:
            monitor.stop()

    def test_thread_is_daemon(self):
        """Watcher thread must be daemon so it doesn't block process exit."""
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=300, on_stall=callback)
        monitor.start("task-1")
        try:
            assert monitor._thread.daemon is True
        finally:
            monitor.stop()

    def test_stop_is_idempotent(self):
        """Calling stop() multiple times should not raise."""
        callback = MagicMock()
        monitor = StallMonitor(stall_timeout_s=300, on_stall=callback)
        monitor.start("task-1")
        monitor.stop()
        monitor.stop()  # Should not raise


class TestStallMonitorConfig:
    """Test stall_timeout_s in AgentBudgetConfig."""

    def test_config_has_stall_timeout(self):
        from codeframe.core.config import AgentBudgetConfig
        config = AgentBudgetConfig()
        assert config.stall_timeout_s == 300

    def test_config_custom_timeout(self):
        from codeframe.core.config import AgentBudgetConfig
        config = AgentBudgetConfig(stall_timeout_s=600)
        assert config.stall_timeout_s == 600

    def test_config_disabled_timeout(self):
        from codeframe.core.config import AgentBudgetConfig
        config = AgentBudgetConfig(stall_timeout_s=0)
        assert config.stall_timeout_s == 0

    def test_config_validation_rejects_negative(self):
        from codeframe.core.config import AgentBudgetConfig, EnvironmentConfig
        config = EnvironmentConfig(
            agent_budget=AgentBudgetConfig(stall_timeout_s=-1)
        )
        errors = config.validate()
        assert any("stall_timeout_s" in e for e in errors)


class TestStallEventType:
    """Test that AGENT_STALL_DETECTED event type exists."""

    def test_event_type_exists(self):
        from codeframe.core.events import EventType
        assert hasattr(EventType, "AGENT_STALL_DETECTED")
        assert EventType.AGENT_STALL_DETECTED == "AGENT_STALL_DETECTED"
