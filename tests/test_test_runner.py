"""
Unit tests for TestRunner (cf-42) - TDD Implementation.

Tests written FIRST following RED-GREEN-REFACTOR methodology.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime

from codeframe.testing.models import TestResult
from codeframe.testing.test_runner import TestRunner


class TestTestResultModel:
    """Test the TestResult dataclass."""

    def test_test_result_creation(self):
        """Test TestResult can be created with all fields."""
        result = TestResult(
            status="passed",
            total=10,
            passed=10,
            failed=0,
            errors=0,
            skipped=0,
            duration=1.5,
            output={"summary": "all passed"},
        )

        assert result.status == "passed"
        assert result.total == 10
        assert result.passed == 10
        assert result.failed == 0
        assert result.errors == 0
        assert result.skipped == 0
        assert result.duration == 1.5
        assert result.output == {"summary": "all passed"}

    def test_test_result_default_values(self):
        """Test TestResult has sensible defaults."""
        result = TestResult(status="passed")

        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0
        assert result.skipped == 0
        assert result.duration == 0.0
        assert result.output is None

    def test_test_result_failed_status(self):
        """Test TestResult with failed tests."""
        result = TestResult(
            status="failed", total=10, passed=7, failed=3, errors=0, skipped=0, duration=2.3
        )

        assert result.status == "failed"
        assert result.failed == 3
        assert result.passed == 7

    def test_test_result_error_status(self):
        """Test TestResult with test errors."""
        result = TestResult(
            status="error", total=10, passed=5, failed=2, errors=3, skipped=0, duration=1.8
        )

        assert result.status == "error"
        assert result.errors == 3


class TestTestRunnerInit:
    """Test TestRunner initialization."""

    def test_test_runner_init_with_path(self, tmp_path):
        """Test TestRunner can be initialized with a project path."""
        runner = TestRunner(project_root=tmp_path)
        assert runner.project_root == tmp_path

    def test_test_runner_init_default_path(self):
        """Test TestRunner uses current directory by default."""
        runner = TestRunner()
        assert runner.project_root == Path(".")

    def test_test_runner_init_timeout(self, tmp_path):
        """Test TestRunner accepts custom timeout."""
        runner = TestRunner(project_root=tmp_path, timeout=600)
        assert runner.timeout == 600

    def test_test_runner_default_timeout(self, tmp_path):
        """Test TestRunner has default timeout of 300s."""
        runner = TestRunner(project_root=tmp_path)
        assert runner.timeout == 300


class TestTestRunnerExecution:
    """Test TestRunner pytest execution."""

    def test_run_tests_all_pass(self, tmp_path):
        """Test run_tests with all passing tests."""
        runner = TestRunner(project_root=tmp_path)

        # Mock subprocess.run and file operations to simulate pytest success
        mock_json_data = {
            "summary": {"total": 10, "passed": 10, "failed": 0, "error": 0, "skipped": 0},
            "duration": 1.5,
        }

        with patch("subprocess.run") as mock_run, patch("builtins.open", create=True) as mock_open:
            mock_run.return_value = MagicMock(returncode=0)
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                mock_json_data
            )

            result = runner.run_tests()

            assert result.status == "passed"
            assert result.total == 10
            assert result.passed == 10
            assert result.failed == 0
            assert result.duration == 1.5

    def test_run_tests_some_fail(self, tmp_path):
        """Test run_tests with some failing tests."""
        runner = TestRunner(project_root=tmp_path)

        mock_json_data = {
            "summary": {"total": 10, "passed": 7, "failed": 3, "error": 0, "skipped": 0},
            "duration": 2.3,
            "tests": [{"outcome": "failed", "nodeid": "test_foo.py::test_bar"}],
        }

        with patch("subprocess.run") as mock_run, patch("builtins.open", create=True) as mock_open:
            mock_run.return_value = MagicMock(returncode=1)
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                mock_json_data
            )

            result = runner.run_tests()

            assert result.status == "failed"
            assert result.total == 10
            assert result.passed == 7
            assert result.failed == 3

    def test_run_tests_with_errors(self, tmp_path):
        """Test run_tests with test errors/exceptions only (no failures)."""
        runner = TestRunner(project_root=tmp_path)

        mock_json_data = {
            "summary": {"total": 10, "passed": 7, "failed": 0, "error": 3, "skipped": 0},
            "duration": 1.8,
        }

        with patch("subprocess.run") as mock_run, patch("builtins.open", create=True) as mock_open:
            mock_run.return_value = MagicMock(returncode=1)
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                mock_json_data
            )

            result = runner.run_tests()

            assert result.status == "error"
            assert result.errors == 3
            assert result.failed == 0

    def test_run_tests_no_tests_found(self, tmp_path):
        """Test run_tests when no tests are found."""
        runner = TestRunner(project_root=tmp_path)

        mock_json_data = {
            "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0},
            "duration": 0.1,
        }

        with patch("subprocess.run") as mock_run, patch("builtins.open", create=True) as mock_open:
            mock_run.return_value = MagicMock(
                returncode=5
            )  # pytest exit code for no tests collected
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(
                mock_json_data
            )

            result = runner.run_tests()

            assert result.status == "no_tests"
            assert result.total == 0

    def test_run_tests_timeout(self, tmp_path):
        """Test run_tests handles timeout."""
        runner = TestRunner(project_root=tmp_path, timeout=1)

        with patch("subprocess.run") as mock_run:
            import subprocess

            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=1)

            result = runner.run_tests()

            assert result.status == "timeout"
            assert "timeout" in result.output.lower()

    def test_run_tests_invalid_path(self):
        """Test run_tests with non-existent directory."""
        runner = TestRunner(project_root=Path("/nonexistent/path"))

        result = runner.run_tests()

        assert result.status == "error"
        assert "path" in result.output.lower() or "directory" in result.output.lower()

    def test_run_tests_pytest_not_installed(self, tmp_path):
        """Test run_tests gracefully handles missing pytest."""
        runner = TestRunner(project_root=tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("pytest not found")

            result = runner.run_tests()

            assert result.status == "error"
            assert "pytest" in result.output.lower()


class TestPytestJSONParsing:
    """Test pytest JSON output parsing."""

    def test_parse_pytest_json_success(self, tmp_path):
        """Test parsing valid pytest JSON output."""
        runner = TestRunner(project_root=tmp_path)

        json_output = {
            "summary": {"total": 15, "passed": 12, "failed": 2, "error": 1, "skipped": 0},
            "duration": 3.5,
            "tests": [{"nodeid": "test_foo.py::test_bar", "outcome": "passed"}],
        }

        result = runner._parse_results(json.dumps(json_output), returncode=1)

        assert result.status == "failed"  # Because some tests failed
        assert result.total == 15
        assert result.passed == 12
        assert result.failed == 2
        assert result.errors == 1
        assert result.duration == 3.5

    def test_parse_pytest_json_malformed(self, tmp_path):
        """Test parsing malformed JSON output."""
        runner = TestRunner(project_root=tmp_path)

        result = runner._parse_results("not valid json", returncode=1)

        assert result.status == "error"
        assert "parse" in result.output.lower() or "json" in result.output.lower()

    def test_parse_pytest_json_missing_fields(self, tmp_path):
        """Test parsing JSON with missing fields."""
        runner = TestRunner(project_root=tmp_path)

        json_output = {
            "summary": {
                "total": 5
                # Missing passed, failed, error, skipped
            }
        }

        result = runner._parse_results(json.dumps(json_output), returncode=0)

        # Should handle gracefully with defaults
        assert result.total == 5
        assert result.passed >= 0
        assert result.failed >= 0


class TestTestRunnerRealPytestExecution:
    """Integration tests with real pytest execution (cf-42 Phase 4)."""

    def test_run_tests_with_real_pytest_passing(self, tmp_path):
        """Test run_tests executes real pytest with passing tests."""
        # Create a simple test file
        test_file = tmp_path / "test_simple.py"
        test_file.write_text(
            """
def test_addition():
    assert 1 + 1 == 2

def test_subtraction():
    assert 5 - 3 == 2
"""
        )

        runner = TestRunner(project_root=tmp_path)
        result = runner.run_tests()

        assert result.status == "passed"
        assert result.total == 2
        assert result.passed == 2
        assert result.failed == 0
        assert result.errors == 0

    def test_run_tests_with_real_pytest_failing(self, tmp_path):
        """Test run_tests executes real pytest with failing tests."""
        # Create a test file with failures
        test_file = tmp_path / "test_failures.py"
        test_file.write_text(
            """
def test_pass():
    assert True

def test_fail():
    assert False, "This test should fail"

def test_also_pass():
    assert 1 == 1
"""
        )

        runner = TestRunner(project_root=tmp_path)
        result = runner.run_tests()

        assert result.status == "failed"
        assert result.total == 3
        assert result.passed == 2
        assert result.failed == 1
        assert result.errors == 0

    def test_run_tests_with_real_pytest_errors(self, tmp_path):
        """Test run_tests executes real pytest with test errors.

        Note: pytest treats exceptions in tests as 'failed', not 'error'.
        Errors in pytest are typically collection failures or fixture issues.
        """
        # Create a test file with an exception (pytest treats this as failed)
        test_file = tmp_path / "test_errors.py"
        test_file.write_text(
            """
def test_pass():
    assert True

def test_error():
    raise ValueError("This is an error")
"""
        )

        runner = TestRunner(project_root=tmp_path)
        result = runner.run_tests()

        # pytest treats exceptions in test bodies as "failed", not "error"
        assert result.status == "failed"
        assert result.total == 2
        assert result.passed == 1
        assert result.failed == 1
        assert result.errors == 0

    def test_run_tests_with_specific_test_paths(self, tmp_path):
        """Test run_tests can run specific test files."""
        # Create multiple test files
        test1 = tmp_path / "test_one.py"
        test1.write_text(
            """
def test_one():
    assert True
"""
        )

        test2 = tmp_path / "test_two.py"
        test2.write_text(
            """
def test_two():
    assert True

def test_two_b():
    assert True
"""
        )

        runner = TestRunner(project_root=tmp_path)
        # Run only test_two.py
        result = runner.run_tests(test_paths=["test_two.py"])

        assert result.status == "passed"
        assert result.total == 2  # Only tests from test_two.py
        assert result.passed == 2
