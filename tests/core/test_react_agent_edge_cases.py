"""Edge case tests for agent execution components.

Focuses on boundary conditions, disabled states, and unusual inputs
for StallDetector, StallDetectedError, and StallAction.
"""

import time

import pytest

from codeframe.core.stall_detector import StallDetectedError, StallDetector

pytestmark = pytest.mark.edge_case


class TestStallDetectorEdgeCases:
    """Edge case tests for stall detection."""

    def test_stall_detector_disabled_with_zero_timeout(self, monkeypatch):
        """StallDetector with timeout_s=0 should never report stalled."""
        call_count = 0
        base_time = 1000.0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            # First call is in __init__, subsequent calls simulate large elapsed time
            if call_count == 1:
                return base_time
            return base_time + 999999.0

        monkeypatch.setattr(time, "monotonic", fake_monotonic)
        detector = StallDetector(timeout_s=0)

        assert detector.is_stalled() is False

    def test_stall_detector_disabled_with_negative_timeout(self, monkeypatch):
        """StallDetector with timeout_s=-1 should never report stalled."""
        call_count = 0
        base_time = 1000.0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return base_time
            return base_time + 999999.0

        monkeypatch.setattr(time, "monotonic", fake_monotonic)
        detector = StallDetector(timeout_s=-1)

        assert detector.is_stalled() is False

    def test_stall_detector_records_activity_resets_timer(self, monkeypatch):
        """After record_activity(), is_stalled() should be False even if time
        had previously exceeded the timeout, because the timer was reset."""
        call_count = 0
        base_time = 1000.0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            # 1: __init__ sets _last_activity to base_time
            # 2: is_stalled check — well past timeout
            # 3: record_activity resets _last_activity
            # 4: is_stalled check — same moment as reset
            times = [base_time, base_time + 100.0, base_time + 100.0, base_time + 100.0]
            return times[call_count - 1] if call_count <= len(times) else base_time + 100.0

        monkeypatch.setattr(time, "monotonic", fake_monotonic)
        detector = StallDetector(timeout_s=10)

        # Should be stalled (100s elapsed, 10s timeout)
        assert detector.is_stalled() is True

        # Reset activity timer
        detector.record_activity()

        # Should no longer be stalled (0s elapsed since reset)
        assert detector.is_stalled() is False

    def test_stall_detected_error_with_empty_last_tool(self):
        """StallDetectedError with empty last_tool should have correct attributes and message."""
        err = StallDetectedError(elapsed_s=60.0, iterations=5, last_tool="")

        assert err.elapsed_s == 60.0
        assert err.iterations == 5
        assert err.last_tool == ""
        assert "60" in str(err)
        assert "iterations=5" in str(err)
        assert isinstance(err, Exception)

    def test_stall_detected_error_with_long_tool_name(self):
        """StallDetectedError with a very long last_tool string should construct properly."""
        long_name = "x" * 500
        err = StallDetectedError(elapsed_s=120.5, iterations=42, last_tool=long_name)

        assert err.last_tool == long_name
        assert len(err.last_tool) == 500
        assert err.elapsed_s == 120.5
        assert err.iterations == 42
        assert long_name in str(err)

    def test_stall_detector_boundary_at_exact_timeout(self, monkeypatch):
        """When elapsed time equals exactly timeout_s, is_stalled() should return
        False because the comparison uses strict greater-than (>), not >=."""
        call_count = 0
        base_time = 1000.0
        timeout = 30.0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return base_time  # __init__
            return base_time + timeout  # exactly at boundary

        monkeypatch.setattr(time, "monotonic", fake_monotonic)
        detector = StallDetector(timeout_s=timeout)

        assert detector.is_stalled() is False

    def test_stall_detector_elapsed_since_activity_ms(self, monkeypatch):
        """elapsed_since_activity_ms() should return correct milliseconds."""
        call_count = 0
        base_time = 1000.0
        elapsed_s = 2.5

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return base_time  # __init__
            return base_time + elapsed_s

        monkeypatch.setattr(time, "monotonic", fake_monotonic)
        detector = StallDetector(timeout_s=300)

        result = detector.elapsed_since_activity_ms()
        assert result == 2500
