"""
Unit tests for CorrectionAttempt model (cf-43) - TDD Implementation.

Tests written FIRST following RED-GREEN-REFACTOR methodology.
"""

import pytest
from datetime import datetime
from codeframe.testing.models import CorrectionAttempt


class TestCorrectionAttemptModel:
    """Test the CorrectionAttempt dataclass."""

    def test_correction_attempt_creation(self):
        """Test CorrectionAttempt can be created with all fields."""
        timestamp = datetime.now()
        attempt = CorrectionAttempt(
            task_id="task-123",
            attempt_number=1,
            error_analysis="AssertionError: expected 5, got 3",
            fix_description="Added missing edge case handling",
            code_changes="+ if n == 0: return 1",
            test_result_id=42,
            timestamp=timestamp
        )

        assert attempt.task_id == "task-123"
        assert attempt.attempt_number == 1
        assert attempt.error_analysis == "AssertionError: expected 5, got 3"
        assert attempt.fix_description == "Added missing edge case handling"
        assert attempt.code_changes == "+ if n == 0: return 1"
        assert attempt.test_result_id == 42
        assert attempt.timestamp == timestamp

    def test_correction_attempt_minimal(self):
        """Test CorrectionAttempt with minimal required fields."""
        attempt = CorrectionAttempt(
            task_id="task-456",
            attempt_number=2,
            error_analysis="ValueError: invalid input",
            fix_description="Added input validation"
        )

        assert attempt.task_id == "task-456"
        assert attempt.attempt_number == 2
        assert attempt.error_analysis == "ValueError: invalid input"
        assert attempt.fix_description == "Added input validation"
        assert attempt.code_changes == ""
        assert attempt.test_result_id is None
        assert attempt.timestamp is not None

    def test_correction_attempt_validates_attempt_number(self):
        """Test CorrectionAttempt validates attempt_number range."""
        # Valid: 1-3
        attempt1 = CorrectionAttempt(
            task_id="task-1",
            attempt_number=1,
            error_analysis="error",
            fix_description="fix"
        )
        assert attempt1.attempt_number == 1

        attempt3 = CorrectionAttempt(
            task_id="task-3",
            attempt_number=3,
            error_analysis="error",
            fix_description="fix"
        )
        assert attempt3.attempt_number == 3

        # Invalid: 0 or > 3
        with pytest.raises(ValueError, match="attempt_number must be between 1 and 3"):
            CorrectionAttempt(
                task_id="task-0",
                attempt_number=0,
                error_analysis="error",
                fix_description="fix"
            )

        with pytest.raises(ValueError, match="attempt_number must be between 1 and 3"):
            CorrectionAttempt(
                task_id="task-4",
                attempt_number=4,
                error_analysis="error",
                fix_description="fix"
            )

    def test_correction_attempt_auto_timestamp(self):
        """Test CorrectionAttempt auto-generates timestamp if not provided."""
        before = datetime.now()
        attempt = CorrectionAttempt(
            task_id="task-789",
            attempt_number=1,
            error_analysis="error",
            fix_description="fix"
        )
        after = datetime.now()

        assert before <= attempt.timestamp <= after

    def test_correction_attempt_empty_strings(self):
        """Test CorrectionAttempt handles empty strings correctly."""
        attempt = CorrectionAttempt(
            task_id="task-empty",
            attempt_number=1,
            error_analysis="",
            fix_description=""
        )

        assert attempt.error_analysis == ""
        assert attempt.fix_description == ""
        assert attempt.code_changes == ""
