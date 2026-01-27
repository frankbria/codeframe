"""
Tests for Tactical Pattern Detection System.

Test coverage for supervisor intervention pattern matching:
- Pattern definition and structure
- Pattern matching for "File already exists" errors
- Pattern matching for "File not found" errors
- No match for unrelated errors
- Intervention strategy extraction

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from dataclasses import dataclass
from typing import Optional

# Import will fail until we create the module (TDD RED phase)
from codeframe.agents.tactical_patterns import (
    TacticalPattern,
    TacticalPatternMatcher,
    InterventionStrategy,
)


class TestTacticalPatternDataclass:
    """Test TacticalPattern dataclass structure."""

    def test_pattern_has_required_fields(self):
        """Test TacticalPattern has all required fields."""
        pattern = TacticalPattern(
            pattern_id="test_pattern",
            error_pattern=r"test.*error",
            category="test",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
        )

        assert pattern.pattern_id == "test_pattern"
        assert pattern.error_pattern == r"test.*error"
        assert pattern.category == "test"
        assert pattern.intervention_strategy == InterventionStrategy.CONVERT_CREATE_TO_EDIT

    def test_pattern_has_optional_description(self):
        """Test TacticalPattern can have optional description."""
        pattern = TacticalPattern(
            pattern_id="test_pattern",
            error_pattern=r"test.*error",
            category="test",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
            description="Test pattern for unit testing",
        )

        assert pattern.description == "Test pattern for unit testing"

    def test_pattern_without_description_defaults_to_none(self):
        """Test TacticalPattern description defaults to None."""
        pattern = TacticalPattern(
            pattern_id="test_pattern",
            error_pattern=r"test.*error",
            category="test",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
        )

        assert pattern.description is None


class TestInterventionStrategy:
    """Test InterventionStrategy enum values."""

    def test_convert_create_to_edit_strategy_exists(self):
        """Test CONVERT_CREATE_TO_EDIT strategy is available."""
        assert InterventionStrategy.CONVERT_CREATE_TO_EDIT.value == "convert_create_to_edit"

    def test_skip_file_creation_strategy_exists(self):
        """Test SKIP_FILE_CREATION strategy is available."""
        assert InterventionStrategy.SKIP_FILE_CREATION.value == "skip_file_creation"

    def test_create_backup_strategy_exists(self):
        """Test CREATE_BACKUP strategy is available."""
        assert InterventionStrategy.CREATE_BACKUP.value == "create_backup"

    def test_retry_with_context_strategy_exists(self):
        """Test RETRY_WITH_CONTEXT strategy is available."""
        assert InterventionStrategy.RETRY_WITH_CONTEXT.value == "retry_with_context"


class TestTacticalPatternMatcher:
    """Test TacticalPatternMatcher class."""

    def test_matcher_initializes_with_default_patterns(self):
        """Test matcher has predefined patterns on initialization."""
        matcher = TacticalPatternMatcher()

        assert len(matcher.patterns) > 0

    def test_matcher_has_file_exists_pattern(self):
        """Test matcher has pattern for 'File already exists' errors."""
        matcher = TacticalPatternMatcher()

        # Find the file_exists pattern
        file_exists_patterns = [
            p for p in matcher.patterns if p.pattern_id == "file_already_exists"
        ]

        assert len(file_exists_patterns) == 1
        assert file_exists_patterns[0].category == "file_conflict"

    def test_matcher_has_file_not_found_pattern(self):
        """Test matcher has pattern for 'File not found' errors."""
        matcher = TacticalPatternMatcher()

        file_not_found_patterns = [
            p for p in matcher.patterns if p.pattern_id == "file_not_found"
        ]

        assert len(file_not_found_patterns) == 1
        assert file_not_found_patterns[0].category == "file_conflict"


class TestPatternMatchingFileExists:
    """Test pattern matching for 'File already exists' errors."""

    def test_matches_file_exists_error_standard_format(self):
        """Test matching standard FileExistsError message."""
        matcher = TacticalPatternMatcher()
        error_msg = "FileExistsError: [Errno 17] File exists: '/path/to/file.py'"

        result = matcher.match_error(error_msg)

        assert result is not None
        assert result.pattern_id == "file_already_exists"
        assert result.intervention_strategy == InterventionStrategy.CONVERT_CREATE_TO_EDIT

    def test_matches_file_already_exists_message(self):
        """Test matching 'file already exists' in error message."""
        matcher = TacticalPatternMatcher()
        error_msg = "Component file already exists: /components/Button.tsx"

        result = matcher.match_error(error_msg)

        assert result is not None
        assert result.pattern_id == "file_already_exists"

    def test_matches_component_exists_frontend_error(self):
        """Test matching FrontendWorkerAgent's FileExistsError message."""
        matcher = TacticalPatternMatcher()
        error_msg = (
            "Component file already exists: src/components/Header.tsx. "
            "Please choose a different name or delete the existing file."
        )

        result = matcher.match_error(error_msg)

        assert result is not None
        assert result.pattern_id == "file_already_exists"

    def test_matches_case_insensitive(self):
        """Test pattern matching is case insensitive."""
        matcher = TacticalPatternMatcher()
        error_msg = "FILE ALREADY EXISTS: /path/to/file.py"

        result = matcher.match_error(error_msg)

        assert result is not None
        assert result.pattern_id == "file_already_exists"

    def test_extracts_file_path_from_error(self):
        """Test matcher can extract file path from error message."""
        matcher = TacticalPatternMatcher()
        error_msg = "FileExistsError: File already exists: src/components/Button.tsx"

        result = matcher.match_error(error_msg)
        file_path = matcher.extract_file_path(error_msg)

        assert result is not None
        assert file_path == "src/components/Button.tsx"


class TestPatternMatchingFileNotFound:
    """Test pattern matching for 'File not found' errors."""

    def test_matches_file_not_found_error(self):
        """Test matching FileNotFoundError message."""
        matcher = TacticalPatternMatcher()
        error_msg = "FileNotFoundError: [Errno 2] No such file or directory: '/path/to/file.py'"

        result = matcher.match_error(error_msg)

        assert result is not None
        assert result.pattern_id == "file_not_found"
        assert result.category == "file_conflict"

    def test_matches_cannot_modify_nonexistent(self):
        """Test matching 'Cannot modify non-existent file' error."""
        matcher = TacticalPatternMatcher()
        error_msg = "Cannot modify non-existent file: src/utils/helper.py"

        result = matcher.match_error(error_msg)

        assert result is not None
        assert result.pattern_id == "file_not_found"


class TestPatternMatchingNoMatch:
    """Test that unrelated errors don't match any pattern."""

    def test_no_match_for_syntax_error(self):
        """Test SyntaxError doesn't match file conflict patterns."""
        matcher = TacticalPatternMatcher()
        error_msg = "SyntaxError: invalid syntax at line 42"

        result = matcher.match_error(error_msg)

        assert result is None

    def test_no_match_for_import_error(self):
        """Test ImportError doesn't match file conflict patterns."""
        matcher = TacticalPatternMatcher()
        error_msg = "ImportError: No module named 'nonexistent_module'"

        result = matcher.match_error(error_msg)

        assert result is None

    def test_no_match_for_generic_runtime_error(self):
        """Test generic RuntimeError doesn't match."""
        matcher = TacticalPatternMatcher()
        error_msg = "RuntimeError: Something unexpected happened"

        result = matcher.match_error(error_msg)

        assert result is None

    def test_no_match_for_empty_string(self):
        """Test empty string doesn't match any pattern."""
        matcher = TacticalPatternMatcher()

        result = matcher.match_error("")

        assert result is None

    def test_no_match_for_none(self):
        """Test None doesn't cause crash and returns None."""
        matcher = TacticalPatternMatcher()

        result = matcher.match_error(None)

        assert result is None


class TestPatternExtension:
    """Test that patterns can be extended."""

    def test_can_add_custom_pattern(self):
        """Test adding a custom pattern to the matcher."""
        matcher = TacticalPatternMatcher()
        custom_pattern = TacticalPattern(
            pattern_id="custom_error",
            error_pattern=r"CustomError:.*",
            category="custom",
            intervention_strategy=InterventionStrategy.RETRY_WITH_CONTEXT,
        )

        matcher.add_pattern(custom_pattern)

        result = matcher.match_error("CustomError: Something went wrong")
        assert result is not None
        assert result.pattern_id == "custom_error"

    def test_can_remove_pattern(self):
        """Test removing a pattern from the matcher."""
        matcher = TacticalPatternMatcher()
        initial_count = len(matcher.patterns)

        matcher.remove_pattern("file_already_exists")

        assert len(matcher.patterns) == initial_count - 1
        # Should no longer match file exists errors
        result = matcher.match_error("FileExistsError: file exists")
        assert result is None or result.pattern_id != "file_already_exists"


class TestDiagnosticOutput:
    """Test diagnostic output for debugging."""

    def test_match_returns_diagnostic_info(self):
        """Test that match_error can return diagnostic information."""
        matcher = TacticalPatternMatcher()
        error_msg = "FileExistsError: File already exists: /path/to/file.py"

        result, diagnostics = matcher.match_error_with_diagnostics(error_msg)

        assert result is not None
        assert "matched_pattern" in diagnostics
        assert "patterns_checked" in diagnostics
        assert diagnostics["patterns_checked"] > 0

    def test_no_match_returns_diagnostic_info(self):
        """Test diagnostics are returned even when no match."""
        matcher = TacticalPatternMatcher()
        error_msg = "SyntaxError: invalid syntax"

        result, diagnostics = matcher.match_error_with_diagnostics(error_msg)

        assert result is None
        assert diagnostics["matched_pattern"] is None
        assert diagnostics["patterns_checked"] == len(matcher.patterns)
