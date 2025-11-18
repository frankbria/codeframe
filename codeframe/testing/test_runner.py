"""
Test Runner for CodeFRAME (cf-42).

Executes pytest and parses results into structured format.
"""

import subprocess
import json
import logging
from pathlib import Path
from typing import Optional, List

from codeframe.testing.models import TestResult


logger = logging.getLogger(__name__)


class TestRunner:
    """
    Executes pytest tests and returns structured results.

    The TestRunner integrates with pytest using the JSON report plugin
    to get structured test results that can be stored in the database
    and used for self-correction (cf-43).

    Example:
        runner = TestRunner(project_root=Path("/path/to/project"))
        result = runner.run_tests()
        print(f"Status: {result.status}, Passed: {result.passed}/{result.total}")
    """

    __test__ = False  # Not a test class - it's a utility that runs tests

    def __init__(self, project_root: Path = Path("."), timeout: int = 300):
        """
        Initialize TestRunner.

        Args:
            project_root: Root directory of the project to test
            timeout: Maximum time in seconds for test execution (default: 300s)
        """
        self.project_root = Path(project_root)
        self.timeout = timeout

    def run_tests(self, test_paths: Optional[List[str]] = None) -> TestResult:
        """
        Run pytest tests and return structured results.

        Args:
            test_paths: Optional list of specific test files/directories to run.
                       If None, runs all tests in project_root.

        Returns:
            TestResult object with test outcomes and metadata

        The method:
        1. Executes pytest with --json-report flag
        2. Parses JSON output into TestResult
        3. Handles errors gracefully (timeout, missing pytest, etc.)
        """
        import tempfile
        import os

        # Validate project root exists
        if not self.project_root.exists():
            logger.error(f"Project root does not exist: {self.project_root}")
            return TestResult(
                status="error", output=f"Project directory not found: {self.project_root}"
            )

        # Create temporary file for JSON report
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp_file:
            json_report_path = tmp_file.name

        try:
            # Build pytest command
            cmd = ["pytest", "--json-report", f"--json-report-file={json_report_path}", "-v"]

            # Add specific test paths if provided
            if test_paths:
                cmd.extend(test_paths)

            logger.info(f"Running tests in {self.project_root} with timeout={self.timeout}s")

            # Execute pytest
            result = subprocess.run(
                cmd, cwd=self.project_root, capture_output=True, text=True, timeout=self.timeout
            )

            # Read JSON report from file
            with open(json_report_path, "r") as f:
                json_output = f.read()

            # Parse results
            return self._parse_results(json_output, result.returncode)

        except subprocess.TimeoutExpired:
            logger.warning(f"Test execution timeout after {self.timeout}s")
            return TestResult(
                status="timeout", output=f"Test execution exceeded timeout of {self.timeout}s"
            )

        except FileNotFoundError:
            logger.error("pytest not found - is it installed?")
            return TestResult(
                status="error",
                output="pytest not found. Install with: pip install pytest pytest-json-report",
            )

        except Exception as e:
            logger.error(f"Unexpected error running tests: {e}")
            return TestResult(
                status="error", output=f"Unexpected error: {type(e).__name__}: {str(e)}"
            )

        finally:
            # Clean up temporary file
            try:
                os.unlink(json_report_path)
            except Exception:
                pass  # Ignore cleanup errors

    def _parse_results(self, json_output: str, returncode: int) -> TestResult:
        """
        Parse pytest JSON output into TestResult.

        Args:
            json_output: JSON string from pytest --json-report
            returncode: pytest exit code (0=success, 1=failures, 5=no tests)

        Returns:
            TestResult object with parsed data

        Pytest return codes:
        - 0: All tests passed
        - 1: Tests failed
        - 2: Test execution interrupted
        - 3: Internal error
        - 4: pytest command line usage error
        - 5: No tests collected
        """
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse pytest JSON output: {e}")
            return TestResult(status="error", output=f"Failed to parse pytest output: {str(e)}")

        # Extract summary data
        summary = data.get("summary", {})
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        errors = summary.get("error", 0)
        skipped = summary.get("skipped", 0)
        duration = data.get("duration", 0.0)

        # Determine status
        # Priority: no_tests > error (if errors exist) > failed (if failures exist) > passed
        if returncode == 5 or total == 0:
            status = "no_tests"
        elif failed > 0 and errors == 0:
            status = "failed"
        elif errors > 0 and failed == 0:
            status = "error"
        elif errors > 0 and failed > 0:
            # Both errors and failures - prefer "failed" as it's more common
            status = "failed"
        else:
            status = "passed"

        logger.info(
            f"Test results: {status} - {passed}/{total} passed, "
            f"{failed} failed, {errors} errors, {skipped} skipped ({duration:.2f}s)"
        )

        return TestResult(
            status=status,
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration=duration,
            output=data,  # Store full JSON for debugging
        )
