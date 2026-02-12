"""Unit tests for GoldenPathRunner._detect_success().

Validates that the success detection logic uses conservative defaults:
- Explicit success patterns → True
- Explicit failure patterns → False
- No patterns matched → False (not True!)
- Non-zero exit code → always False
"""

import pytest

from tests.e2e.cli.golden_path_runner import GoldenPathRunner


@pytest.fixture
def runner(tmp_path):
    """Create a GoldenPathRunner instance for testing."""
    return GoldenPathRunner(project_path=tmp_path, engine="react")


class TestDetectSuccess:
    """Tests for _detect_success() conservative detection logic."""

    def test_explicit_success_pattern_returns_true(self, runner):
        output = "Some output\nTask completed successfully!\nDone."
        assert runner._detect_success(exit_code=0, output=output) is True

    def test_explicit_failure_pattern_returns_false(self, runner):
        output = "Task execution failed\nSome error occurred"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_api_key_missing_returns_false(self, runner):
        output = "ANTHROPIC_API_KEY environment variable is required"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_error_pattern_returns_false(self, runner):
        output = "Error: something went wrong"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_blocked_pattern_returns_false(self, runner):
        output = "Task blocked - needs human input"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_empty_output_exit_zero_returns_false(self, runner):
        """The core bug: empty output should NOT be treated as success."""
        assert runner._detect_success(exit_code=0, output="") is False

    def test_no_patterns_exit_zero_returns_false(self, runner):
        """Output with no matching patterns should be failure (conservative)."""
        output = "Some random output that matches nothing"
        assert runner._detect_success(exit_code=0, output=output) is False

    def test_nonzero_exit_code_always_returns_false(self, runner):
        output = "Task completed successfully!"
        assert runner._detect_success(exit_code=1, output=output) is False

    def test_nonzero_exit_code_with_no_output(self, runner):
        assert runner._detect_success(exit_code=1, output="") is False

    def test_mixed_success_and_failure_returns_false(self, runner):
        """When both success and failure patterns present, failure wins."""
        output = "Task completed successfully!\nBut then Error: crash"
        assert runner._detect_success(exit_code=0, output=output) is False
