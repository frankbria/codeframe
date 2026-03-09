"""Tests for StallDetector, StallAction, and StallDetectedError.

Tests cover:
- StallDetector time tracking and threshold detection
- record_activity() resetting the timer
- Disabled detection (timeout <= 0)
- elapsed_since_activity_ms() accuracy
- StallAction enum values and str inheritance
- StallDetectedError exception attributes
- ReactAgent stall_action parameter integration
- execute_agent stall_action parameter
"""

import inspect
import time
from unittest.mock import MagicMock

import pytest

from codeframe.core.stall_detector import StallAction, StallDetectedError, StallDetector

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
        # Deterministic: backdate activity to guarantee stall
        short_detector._last_activity = time.monotonic() - 1.0
        assert short_detector.is_stalled() is True


class TestStallDetectedError:
    """Test StallDetectedError exception."""

    def test_attributes(self):
        err = StallDetectedError(elapsed_s=305.2, iterations=7, last_tool="run_tests")
        assert err.elapsed_s == 305.2
        assert err.iterations == 7
        assert err.last_tool == "run_tests"

    def test_is_exception(self):
        err = StallDetectedError(elapsed_s=100, iterations=3)
        assert isinstance(err, Exception)

    def test_message_format(self):
        err = StallDetectedError(elapsed_s=300, iterations=5, last_tool="edit_file")
        assert "300" in str(err)
        assert "edit_file" in str(err)

    def test_default_last_tool(self):
        err = StallDetectedError(elapsed_s=100, iterations=2)
        assert err.last_tool == ""


class TestReactAgentStallAction:
    """Test ReactAgent stall_action parameter."""

    def test_accepts_stall_action_param(self):
        from codeframe.core.react_agent import ReactAgent
        mock_provider = MagicMock()
        mock_workspace = MagicMock()
        agent = ReactAgent(
            workspace=mock_workspace,
            llm_provider=mock_provider,
            stall_action=StallAction.RETRY,
        )
        assert agent._stall_action == StallAction.RETRY

    def test_default_stall_action_is_blocker(self):
        from codeframe.core.react_agent import ReactAgent
        mock_provider = MagicMock()
        mock_workspace = MagicMock()
        agent = ReactAgent(
            workspace=mock_workspace,
            llm_provider=mock_provider,
        )
        assert agent._stall_action == StallAction.BLOCKER

    def test_stall_action_fail(self):
        from codeframe.core.react_agent import ReactAgent
        mock_provider = MagicMock()
        mock_workspace = MagicMock()
        agent = ReactAgent(
            workspace=mock_workspace,
            llm_provider=mock_provider,
            stall_action=StallAction.FAIL,
        )
        assert agent._stall_action == StallAction.FAIL


class TestExecuteAgentStallAction:
    """Test that execute_agent accepts stall_action parameter."""

    def test_has_stall_action_param(self):
        from codeframe.core.runtime import execute_agent
        sig = inspect.signature(execute_agent)
        assert "stall_action" in sig.parameters
        assert sig.parameters["stall_action"].default == "blocker"


class TestConductorStallAction:
    """Test stall_action threading through conductor."""

    def test_batch_run_has_stall_action(self):
        from codeframe.core.conductor import BatchRun
        # Verify the field exists with correct default
        import dataclasses
        fields = {f.name: f for f in dataclasses.fields(BatchRun)}
        assert "stall_action" in fields
        assert fields["stall_action"].default == "blocker"

    def test_start_batch_accepts_stall_action(self):
        from codeframe.core.conductor import start_batch
        sig = inspect.signature(start_batch)
        assert "stall_action" in sig.parameters
        assert sig.parameters["stall_action"].default == "blocker"
