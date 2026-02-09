"""Tests for blocker_detection module — extracted pattern matching from agent.py."""

import pytest

from codeframe.core.blocker_detection import classify_error_for_blocker, should_create_blocker

pytestmark = pytest.mark.v2


class TestClassifyErrorForBlocker:
    """Tests for classify_error_for_blocker function."""

    def test_classify_requirements_ambiguity(self):
        assert classify_error_for_blocker("conflicting requirements found") == "requirements"
        assert classify_error_for_blocker("spec unclear about return type") == "requirements"
        assert classify_error_for_blocker("business decision needed") == "requirements"
        assert classify_error_for_blocker("domain knowledge required for pricing") == "requirements"

    def test_classify_access_denied(self):
        assert classify_error_for_blocker("permission denied on /etc/secrets") == "access"
        assert classify_error_for_blocker("authentication required for API") == "access"
        assert classify_error_for_blocker("api key not configured") == "access"
        assert classify_error_for_blocker("credentials missing") == "access"
        assert classify_error_for_blocker("unauthorized access") == "access"

    def test_classify_external_service(self):
        assert classify_error_for_blocker("service unavailable") == "external_service"
        assert classify_error_for_blocker("rate limited by provider") == "external_service"
        assert classify_error_for_blocker("quota exceeded for API") == "external_service"
        assert classify_error_for_blocker("connection refused on port 5432") == "external_service"

    def test_classify_technical_error(self):
        """Technical errors should return None — agent self-corrects."""
        assert classify_error_for_blocker("file not found: config.py") is None
        assert classify_error_for_blocker("syntax error on line 42") is None
        assert classify_error_for_blocker("ModuleNotFoundError: no module named foo") is None
        assert classify_error_for_blocker("NameError: x is not defined") is None

    def test_classify_tactical_decision(self):
        """Tactical decisions should return None — agent resolves autonomously."""
        assert classify_error_for_blocker("which approach should I use?") is None
        assert classify_error_for_blocker("should i use pytest or unittest?") is None
        assert classify_error_for_blocker("multiple options available") is None
        assert classify_error_for_blocker("file already exists, overwrite?") is None
        assert classify_error_for_blocker("do you want me to proceed?") is None

    def test_classify_case_insensitive(self):
        """Pattern matching must be case-insensitive."""
        assert classify_error_for_blocker("CONFLICTING REQUIREMENTS") == "requirements"
        assert classify_error_for_blocker("Permission Denied") == "access"
        assert classify_error_for_blocker("Service Unavailable") == "external_service"
        assert classify_error_for_blocker("FILE NOT FOUND") is None

    def test_classify_no_match(self):
        """Text that matches no pattern returns None."""
        assert classify_error_for_blocker("everything is fine") is None
        assert classify_error_for_blocker("") is None

    def test_tactical_takes_priority_over_requirements(self):
        """If text matches both tactical and requirements patterns, tactical wins (returns None)."""
        # "please clarify" is tactical; "requirements conflict" is requirements
        # A text containing a tactical pattern should return None even if it also
        # contains a requirements-like phrase
        assert classify_error_for_blocker("please clarify the design decision") is None


class TestShouldCreateBlocker:
    """Tests for should_create_blocker function."""

    def test_should_create_blocker_requirements(self):
        result, reason = should_create_blocker("conflicting requirements in spec")
        assert result is True
        assert "requirements" in reason.lower()

    def test_should_create_blocker_access(self):
        result, reason = should_create_blocker("permission denied on resource")
        assert result is True
        assert "access" in reason.lower()

    def test_should_create_blocker_external_first_attempt(self):
        """External service issues should NOT create blocker on first attempt."""
        result, reason = should_create_blocker("service unavailable", attempt_count=0)
        assert result is False
        assert reason == ""

    def test_should_create_blocker_external_second_attempt(self):
        """External service issues should NOT create blocker on second attempt (attempt_count=1)."""
        result, reason = should_create_blocker("service unavailable", attempt_count=1)
        assert result is False
        assert reason == ""

    def test_should_create_blocker_external_after_retry(self):
        """External service issues should create blocker after retry (attempt_count > 1)."""
        result, reason = should_create_blocker("service unavailable", attempt_count=2)
        assert result is True
        assert "external" in reason.lower()

    def test_should_create_blocker_technical(self):
        """Technical errors should not create blockers."""
        result, reason = should_create_blocker("file not found: main.py")
        assert result is False
        assert reason == ""

    def test_should_create_blocker_empty_text(self):
        result, reason = should_create_blocker("")
        assert result is False
        assert reason == ""

    def test_should_create_blocker_tactical(self):
        """Tactical decisions should never create blockers."""
        result, reason = should_create_blocker("which approach should I use?")
        assert result is False
        assert reason == ""
