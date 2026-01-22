"""Tests for fix attempt tracking."""


from codeframe.core.fix_tracker import (
    FixAttemptTracker,
    FixOutcome,
    MAX_SAME_ERROR_ATTEMPTS,
    MAX_SAME_FILE_ATTEMPTS,
    MAX_TOTAL_FAILURES,
)


class TestFixAttemptTracker:
    """Tests for FixAttemptTracker class."""

    def test_normalize_error_removes_line_numbers(self):
        """Line numbers should be normalized."""
        tracker = FixAttemptTracker()

        error1 = "SyntaxError at line 42: invalid syntax"
        error2 = "SyntaxError at line 100: invalid syntax"

        assert tracker.normalize_error(error1) == tracker.normalize_error(error2)

    def test_normalize_error_removes_memory_addresses(self):
        """Memory addresses should be normalized."""
        tracker = FixAttemptTracker()

        error1 = "Object at 0x7f1234567890"
        error2 = "Object at 0xaabbccddee00"

        assert tracker.normalize_error(error1) == tracker.normalize_error(error2)

    def test_normalize_error_preserves_filename(self):
        """Filenames should be preserved but paths removed."""
        tracker = FixAttemptTracker()

        error = "/home/user/project/src/main.py: error"
        normalized = tracker.normalize_error(error)

        assert "main.py" in normalized
        assert "/home/user/" not in normalized

    def test_hash_error_consistency(self):
        """Same normalized error should produce same hash."""
        tracker = FixAttemptTracker()

        error1 = "ModuleNotFoundError: No module named 'requests'"
        error2 = "ModuleNotFoundError: No module named 'requests'"

        assert tracker.hash_error(error1) == tracker.hash_error(error2)

    def test_hash_error_different_for_different_errors(self):
        """Different errors should produce different hashes."""
        tracker = FixAttemptTracker()

        error1 = "ModuleNotFoundError: No module named 'requests'"
        error2 = "ImportError: cannot import name 'foo'"

        assert tracker.hash_error(error1) != tracker.hash_error(error2)

    def test_extract_error_type_python_errors(self):
        """Should extract Python error types."""
        tracker = FixAttemptTracker()

        assert tracker.extract_error_type("ModuleNotFoundError: No module named 'x'") == "ModuleNotFoundError"
        assert tracker.extract_error_type("ImportError: cannot import name 'x'") == "ImportError"
        assert tracker.extract_error_type("SyntaxError: invalid syntax") == "SyntaxError"
        assert tracker.extract_error_type("NameError: name 'x' is not defined") == "NameError"

    def test_extract_error_type_ruff_codes(self):
        """Should extract ruff/flake8 error codes."""
        tracker = FixAttemptTracker()

        assert tracker.extract_error_type("E501 line too long") == "E501"

    def test_record_attempt(self):
        """Should record fix attempts."""
        tracker = FixAttemptTracker()

        attempt = tracker.record_attempt(
            error="ModuleNotFoundError: No module named 'requests'",
            fix_description="pip install requests",
            file_path="main.py",
        )

        assert attempt.fix_description == "pip install requests"
        assert attempt.file_path == "main.py"
        assert attempt.outcome == FixOutcome.PENDING
        assert len(tracker._attempts) == 1

    def test_record_outcome_success(self):
        """Should record successful outcomes."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"
        fix = "pip install requests"

        tracker.record_attempt(error, fix)
        tracker.record_outcome(error, fix, FixOutcome.SUCCESS)

        # Success shouldn't increment error count
        assert tracker.get_failure_count(error) == 0

    def test_record_outcome_failure(self):
        """Should record failed outcomes and increment counts."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"
        fix = "pip install requests"

        tracker.record_attempt(error, fix)
        tracker.record_outcome(error, fix, FixOutcome.FAILED)

        assert tracker.get_failure_count(error) == 1

    def test_was_attempted_true(self):
        """Should detect previously attempted fixes."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"
        fix = "pip install requests"

        tracker.record_attempt(error, fix)

        assert tracker.was_attempted(error, fix) is True
        assert tracker.was_attempted(error, "different fix") is False

    def test_was_attempted_case_insensitive(self):
        """Fix descriptions should be compared case-insensitively."""
        tracker = FixAttemptTracker()
        error = "some error"

        tracker.record_attempt(error, "pip install requests")

        assert tracker.was_attempted(error, "PIP INSTALL REQUESTS") is True

    def test_get_attempted_fixes(self):
        """Should return list of attempted fixes."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"

        tracker.record_attempt(error, "pip install requests")
        tracker.record_attempt(error, "uv pip install requests")

        fixes = tracker.get_attempted_fixes(error)

        assert len(fixes) == 2
        assert "pip install requests" in fixes
        assert "uv pip install requests" in fixes

    def test_get_total_failures(self):
        """Should count total failures across all errors."""
        tracker = FixAttemptTracker()

        # Record multiple failures
        for i in range(3):
            error = f"Error {i}"
            tracker.record_attempt(error, f"fix {i}")
            tracker.record_outcome(error, f"fix {i}", FixOutcome.FAILED)

        assert tracker.get_total_failures() == 3


class TestEscalationDecision:
    """Tests for escalation decision logic."""

    def test_no_escalation_initially(self):
        """No escalation with no failures."""
        tracker = FixAttemptTracker()

        decision = tracker.should_escalate("some error")

        assert decision.should_escalate is False

    def test_escalate_after_max_same_error_attempts(self):
        """Should escalate after MAX_SAME_ERROR_ATTEMPTS failures."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"

        # Record MAX_SAME_ERROR_ATTEMPTS failures
        for i in range(MAX_SAME_ERROR_ATTEMPTS):
            tracker.record_attempt(error, f"fix attempt {i}")
            tracker.record_outcome(error, f"fix attempt {i}", FixOutcome.FAILED)

        decision = tracker.should_escalate(error)

        assert decision.should_escalate is True
        assert "failed" in decision.reason.lower()

    def test_escalate_after_max_file_failures(self):
        """Should escalate after MAX_SAME_FILE_ATTEMPTS failures on same file."""
        tracker = FixAttemptTracker()
        file_path = "main.py"

        # Record MAX_SAME_FILE_ATTEMPTS failures on same file
        for i in range(MAX_SAME_FILE_ATTEMPTS):
            error = f"Error type {i}"
            tracker.record_attempt(error, f"fix {i}", file_path=file_path)
            tracker.record_outcome(error, f"fix {i}", FixOutcome.FAILED)

        decision = tracker.should_escalate("new error", file_path=file_path)

        assert decision.should_escalate is True
        assert file_path in decision.reason

    def test_escalate_after_max_total_failures(self):
        """Should escalate after MAX_TOTAL_FAILURES total failures."""
        tracker = FixAttemptTracker()

        # Record MAX_TOTAL_FAILURES different errors
        for i in range(MAX_TOTAL_FAILURES):
            error = f"Different error {i}"
            tracker.record_attempt(error, f"fix {i}")
            tracker.record_outcome(error, f"fix {i}", FixOutcome.FAILED)

        decision = tracker.should_escalate("new error")

        assert decision.should_escalate is True
        assert "total" in decision.reason.lower()

    def test_escalation_includes_attempted_fixes(self):
        """Escalation decision should include list of attempted fixes."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"

        tracker.record_attempt(error, "pip install requests")
        tracker.record_outcome(error, "pip install requests", FixOutcome.FAILED)

        tracker.record_attempt(error, "uv pip install requests")
        tracker.record_outcome(error, "uv pip install requests", FixOutcome.FAILED)

        tracker.record_attempt(error, "poetry add requests")
        tracker.record_outcome(error, "poetry add requests", FixOutcome.FAILED)

        decision = tracker.should_escalate(error)

        assert len(decision.attempted_fixes) == 3


class TestBlockerContext:
    """Tests for blocker context generation."""

    def test_get_blocker_context_includes_error_type(self):
        """Context should include error type."""
        tracker = FixAttemptTracker()
        error = "ModuleNotFoundError: No module named 'requests'"

        tracker.record_attempt(error, "fix")
        tracker.record_outcome(error, "fix", FixOutcome.FAILED)

        context = tracker.get_blocker_context(error)

        assert context["error_type"] == "ModuleNotFoundError"

    def test_get_blocker_context_includes_attempt_count(self):
        """Context should include attempt count."""
        tracker = FixAttemptTracker()
        error = "some error"

        for i in range(3):
            tracker.record_attempt(error, f"fix {i}")
            tracker.record_outcome(error, f"fix {i}", FixOutcome.FAILED)

        context = tracker.get_blocker_context(error)

        assert context["attempt_count"] == 3

    def test_get_blocker_context_includes_affected_files(self):
        """Context should include affected files."""
        tracker = FixAttemptTracker()
        error = "some error"

        tracker.record_attempt(error, "fix 1", file_path="main.py")
        tracker.record_attempt(error, "fix 2", file_path="utils.py")

        context = tracker.get_blocker_context(error)

        assert "main.py" in context["affected_files"]
        assert "utils.py" in context["affected_files"]


class TestTrackerPersistence:
    """Tests for tracker serialization/deserialization."""

    def test_to_dict(self):
        """Should serialize tracker state."""
        tracker = FixAttemptTracker()
        error = "some error"

        tracker.record_attempt(error, "fix 1", file_path="main.py")
        tracker.record_outcome(error, "fix 1", FixOutcome.SUCCESS)

        data = tracker.to_dict()

        assert len(data["attempts"]) == 1
        assert data["attempts"][0]["fix_description"] == "fix 1"
        assert data["attempts"][0]["outcome"] == "success"

    def test_from_dict(self):
        """Should restore tracker from serialized state."""
        original = FixAttemptTracker()
        error = "some error"

        original.record_attempt(error, "fix 1")
        original.record_outcome(error, "fix 1", FixOutcome.FAILED)

        data = original.to_dict()
        restored = FixAttemptTracker.from_dict(data)

        assert restored.get_failure_count(error) == 1
        assert len(restored.get_attempted_fixes(error)) == 1

    def test_reset(self):
        """Should clear all tracking state."""
        tracker = FixAttemptTracker()

        tracker.record_attempt("error 1", "fix 1")
        tracker.record_outcome("error 1", "fix 1", FixOutcome.FAILED)

        tracker.reset()

        assert tracker.get_total_failures() == 0
        assert len(tracker._attempts) == 0
