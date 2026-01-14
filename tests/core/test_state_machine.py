"""Unit tests for codeframe/core/state_machine.py."""

import pytest

from codeframe.core.state_machine import (
    TaskStatus,
    InvalidTransitionError,
    can_transition,
    validate_transition,
    get_allowed_transitions,
    parse_status,
    ALLOWED_TRANSITIONS,
)


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_exist(self):
        """Verify all expected statuses are defined."""
        expected = {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "DONE", "MERGED"}
        actual = {s.value for s in TaskStatus}
        assert actual == expected

    def test_status_is_string(self):
        """TaskStatus should serialize as string."""
        assert TaskStatus.READY == "READY"
        assert TaskStatus.IN_PROGRESS.value == "IN_PROGRESS"


class TestCanTransition:
    """Tests for can_transition function."""

    def test_backlog_to_ready(self):
        assert can_transition(TaskStatus.BACKLOG, TaskStatus.READY) is True

    def test_backlog_to_in_progress_not_allowed(self):
        """Can't skip READY and go directly to IN_PROGRESS."""
        assert can_transition(TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS) is False

    def test_ready_to_in_progress(self):
        assert can_transition(TaskStatus.READY, TaskStatus.IN_PROGRESS) is True

    def test_ready_to_backlog(self):
        """Can demote back to BACKLOG."""
        assert can_transition(TaskStatus.READY, TaskStatus.BACKLOG) is True

    def test_in_progress_to_blocked(self):
        assert can_transition(TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED) is True

    def test_in_progress_to_done(self):
        assert can_transition(TaskStatus.IN_PROGRESS, TaskStatus.DONE) is True

    def test_blocked_to_in_progress(self):
        """Can resume after being blocked."""
        assert can_transition(TaskStatus.BLOCKED, TaskStatus.IN_PROGRESS) is True

    def test_done_to_ready(self):
        """Can reopen a completed task."""
        assert can_transition(TaskStatus.DONE, TaskStatus.READY) is True

    def test_done_to_merged(self):
        assert can_transition(TaskStatus.DONE, TaskStatus.MERGED) is True

    def test_merged_is_terminal(self):
        """MERGED is a terminal state - no transitions allowed."""
        for status in TaskStatus:
            assert can_transition(TaskStatus.MERGED, status) is False

    def test_ready_to_done_not_allowed(self):
        """Can't complete without doing work."""
        assert can_transition(TaskStatus.READY, TaskStatus.DONE) is False


class TestValidateTransition:
    """Tests for validate_transition function."""

    def test_valid_transition_passes(self):
        """Valid transitions should not raise."""
        validate_transition(TaskStatus.BACKLOG, TaskStatus.READY)
        validate_transition(TaskStatus.READY, TaskStatus.IN_PROGRESS)
        validate_transition(TaskStatus.IN_PROGRESS, TaskStatus.DONE)

    def test_invalid_transition_raises(self):
        """Invalid transitions should raise InvalidTransitionError."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(TaskStatus.READY, TaskStatus.DONE)

        error = exc_info.value
        assert error.current == TaskStatus.READY
        assert error.target == TaskStatus.DONE
        assert "READY -> DONE" in str(error)
        assert "IN_PROGRESS" in str(error)  # Should show allowed transitions

    def test_error_message_shows_allowed(self):
        """Error message should list allowed transitions."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(TaskStatus.BACKLOG, TaskStatus.DONE)

        assert "READY" in str(exc_info.value)


class TestGetAllowedTransitions:
    """Tests for get_allowed_transitions function."""

    def test_backlog_allowed(self):
        allowed = get_allowed_transitions(TaskStatus.BACKLOG)
        assert allowed == {TaskStatus.READY}

    def test_ready_allowed(self):
        allowed = get_allowed_transitions(TaskStatus.READY)
        assert TaskStatus.IN_PROGRESS in allowed
        assert TaskStatus.BACKLOG in allowed

    def test_in_progress_allowed(self):
        allowed = get_allowed_transitions(TaskStatus.IN_PROGRESS)
        assert TaskStatus.BLOCKED in allowed
        assert TaskStatus.DONE in allowed
        assert TaskStatus.READY in allowed

    def test_merged_allowed_empty(self):
        allowed = get_allowed_transitions(TaskStatus.MERGED)
        assert allowed == set()

    def test_returns_copy(self):
        """Should return a copy, not the original set."""
        allowed1 = get_allowed_transitions(TaskStatus.BACKLOG)
        allowed2 = get_allowed_transitions(TaskStatus.BACKLOG)
        allowed1.add(TaskStatus.DONE)  # Mutate
        assert TaskStatus.DONE not in allowed2  # Original unchanged


class TestParseStatus:
    """Tests for parse_status function."""

    def test_uppercase(self):
        assert parse_status("READY") == TaskStatus.READY
        assert parse_status("IN_PROGRESS") == TaskStatus.IN_PROGRESS

    def test_lowercase(self):
        assert parse_status("ready") == TaskStatus.READY
        assert parse_status("in_progress") == TaskStatus.IN_PROGRESS

    def test_mixed_case(self):
        assert parse_status("Ready") == TaskStatus.READY
        assert parse_status("In_Progress") == TaskStatus.IN_PROGRESS

    def test_hyphen_to_underscore(self):
        """Support hyphens as alternative to underscores."""
        assert parse_status("in-progress") == TaskStatus.IN_PROGRESS
        assert parse_status("IN-PROGRESS") == TaskStatus.IN_PROGRESS

    def test_invalid_raises_valueerror(self):
        with pytest.raises(ValueError) as exc_info:
            parse_status("INVALID")

        assert "Invalid status" in str(exc_info.value)
        assert "INVALID" in str(exc_info.value)
        assert "READY" in str(exc_info.value)  # Shows valid options


class TestAllowedTransitionsComplete:
    """Verify ALLOWED_TRANSITIONS covers all statuses."""

    def test_all_statuses_have_entry(self):
        """Every status should have an entry in ALLOWED_TRANSITIONS."""
        for status in TaskStatus:
            assert status in ALLOWED_TRANSITIONS

    def test_transition_targets_are_valid(self):
        """All transition targets should be valid TaskStatus values."""
        for source, targets in ALLOWED_TRANSITIONS.items():
            for target in targets:
                assert isinstance(target, TaskStatus)
