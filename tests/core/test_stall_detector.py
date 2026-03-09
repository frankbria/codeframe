"""Tests for StallDetector and StallAction.

Tests cover:
- StallDetector time tracking and threshold detection
- record_activity() resetting the timer
- Disabled detection (timeout <= 0)
- elapsed_since_activity_ms() accuracy
- StallAction enum values and str inheritance
"""

import time

import pytest

from codeframe.core.stall_detector import StallAction, StallDetector

pytestmark = pytest.mark.v2


class TestStallAction:
    """Test StallAction enum."""

    def test_values(self):
        assert StallAction.RETRY == "retry"
        assert StallAction.BLOCKER == "blocker"
        assert StallAction.FAIL == "fail"

    def test_is_str(self):
        assert isinstance(StallAction.RETRY, str)
        assert isinstance(StallAction.BLOCKER, str)
        assert isinstance(StallAction.FAIL, str)

    def test_member_count(self):
        assert len(StallAction) == 3


class TestStallDetector:
    """Test StallDetector time tracking."""

    @pytest.fixture
    def detector(self):
        return StallDetector()

    @pytest.fixture
    def short_detector(self):
        return StallDetector(timeout_s=0.001)

    def test_default_timeout(self, detector):
        assert detector.timeout_s == 300

    def test_custom_timeout(self):
        d = StallDetector(timeout_s=600)
        assert d.timeout_s == 600

    def test_initial_not_stalled(self, detector):
        assert detector.is_stalled() is False

    def test_stalled_after_timeout(self, detector):
        # Simulate time passing by backdating _last_activity
        detector._last_activity = time.monotonic() - 301
        assert detector.is_stalled() is True

    def test_not_stalled_before_timeout(self, detector):
        detector._last_activity = time.monotonic() - 299
        assert detector.is_stalled() is False

    def test_record_activity_resets_stall(self, detector):
        detector._last_activity = time.monotonic() - 301
        assert detector.is_stalled() is True
        detector.record_activity()
        assert detector.is_stalled() is False

    def test_elapsed_since_activity_ms(self, detector):
        elapsed = detector.elapsed_since_activity_ms()
        assert isinstance(elapsed, int)
        assert elapsed >= 0

    def test_elapsed_increases(self, detector):
        detector._last_activity = time.monotonic() - 1.0
        elapsed = detector.elapsed_since_activity_ms()
        assert elapsed >= 1000

    def test_disabled_when_zero(self):
        d = StallDetector(timeout_s=0)
        d._last_activity = time.monotonic() - 99999
        assert d.is_stalled() is False

    def test_disabled_when_negative(self):
        d = StallDetector(timeout_s=-1)
        d._last_activity = time.monotonic() - 99999
        assert d.is_stalled() is False

    def test_very_short_timeout_stalls_quickly(self, short_detector):
        # With 1ms timeout, should be stalled almost immediately
        time.sleep(0.01)
        assert short_detector.is_stalled() is True
