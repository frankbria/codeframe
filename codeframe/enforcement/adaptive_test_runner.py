"""
Adaptive Test Runner

Runs tests for any language/framework by detecting the project type
and using appropriate commands.

This is what agents use to verify their work, regardless of what
language they're working on.
"""

import subprocess
import shlex
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Union
from pathlib import Path

from .language_detector import LanguageDetector, LanguageInfo

logger = logging.getLogger(__name__)

# Safe commands that can run without shell=True
# These are common test commands that don't require shell features
SAFE_COMMANDS = {
    "pytest",
    "python",
    "python3",
    "npm",
    "node",
    "yarn",
    "pnpm",
    "go",
    "cargo",
    "mvn",
    "gradle",
    "ruby",
    "rspec",
    "dotnet",
}


@dataclass
class TestResult:
    """Results from running tests."""

    success: bool  # True if all tests passed
    total_tests: int  # Total number of tests
    passed_tests: int  # Number of passed tests
    failed_tests: int  # Number of failed tests
    skipped_tests: int  # Number of skipped tests
    pass_rate: float  # Percentage of tests that passed (0-100)
    coverage: Optional[float]  # Coverage percentage if available
    output: str  # Full test output
    duration: float  # Test duration in seconds


class AdaptiveTestRunner:
    """
    Runs tests adaptively based on detected language.

    Usage:
        runner = AdaptiveTestRunner(project_path="/path/to/project")
        result = await runner.run_tests()

        if result.success:
            print(f"✓ {result.passed_tests} tests passed")
        else:
            print(f"✗ {result.failed_tests} tests failed")
    """

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.detector = LanguageDetector(project_path)
        self.language_info: Optional[LanguageInfo] = None

    def _parse_command_safely(
        self, command: str
    ) -> tuple[Union[str, List[str]], bool]:
        """
        Parse command and determine if shell=True is needed.

        Args:
            command: Command string to parse

        Returns:
            Tuple of (parsed_command, use_shell)
            - parsed_command: List of args for shell=False, or str for shell=True
            - use_shell: Boolean indicating if shell=True is needed

        Security:
            - Commands starting with SAFE_COMMANDS are parsed with shlex.split()
              and run with shell=False (secure)
            - Commands containing shell operators require shell=True (less secure,
              logged as warning)
            - Simple commands without operators use shell=False when possible
        """
        # Check for dangerous shell operators
        dangerous_operators = [";", "&&", "||", "|", "`", "$(",  "$()", ">", "<", ">>"]
        has_shell_operators = any(op in command for op in dangerous_operators)

        # Parse command to get the base command
        try:
            parts = shlex.split(command)
        except ValueError as e:
            logger.warning(
                f"Failed to parse command safely: {command}. "
                f"Error: {e}. Using shell=True as fallback."
            )
            return command, True

        if not parts:
            logger.warning(f"Empty command after parsing: {command}")
            return command, True

        base_command = parts[0]

        # If command contains shell operators, we need shell=True
        if has_shell_operators:
            logger.warning(
                f"Command contains shell operators and will run with shell=True: {command}. "
                f"This may pose a security risk if the command comes from untrusted input."
            )
            return command, True

        # If base command is in SAFE_COMMANDS, use shell=False
        if base_command in SAFE_COMMANDS:
            logger.debug(f"Running safe command without shell: {parts}")
            return parts, False

        # For other simple commands, try without shell
        logger.info(
            f"Command '{base_command}' not in SAFE_COMMANDS list. "
            f"Running without shell, but consider adding to SAFE_COMMANDS if legitimate."
        )
        return parts, False

    async def run_tests(
        self, with_coverage: bool = False
    ) -> TestResult:
        """
        Run tests for the project.

        Args:
            with_coverage: Whether to collect coverage data

        Returns:
            TestResult with test execution details
        """
        # Detect language if not already done
        if not self.language_info:
            self.language_info = self.detector.detect()

        # Choose command
        command = (
            self.language_info.coverage_command
            if with_coverage and self.language_info.coverage_command
            else self.language_info.test_command
        )

        # Parse command safely
        parsed_command, use_shell = self._parse_command_safely(command)

        # Run tests with appropriate shell setting
        result = subprocess.run(
            parsed_command,
            shell=use_shell,
            cwd=self.project_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        # Parse output based on language
        parsed = self._parse_output(
            result.stdout + result.stderr,
            self.language_info.language,
            self.language_info.framework,
        )

        return TestResult(
            success=result.returncode == 0,
            total_tests=parsed["total"],
            passed_tests=parsed["passed"],
            failed_tests=parsed["failed"],
            skipped_tests=parsed["skipped"],
            pass_rate=parsed["pass_rate"],
            coverage=parsed.get("coverage"),
            output=result.stdout + result.stderr,
            duration=0.0,  # Would need timing logic
        )

    def _parse_output(
        self, output: str, language: str, framework: Optional[str]
    ) -> Dict[str, Any]:
        """
        Parse test output to extract metrics.

        Args:
            output: Raw test output
            language: Detected language
            framework: Detected framework

        Returns:
            Dict with total, passed, failed, skipped, pass_rate, coverage
        """
        # Default values
        result = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "pass_rate": 0.0,
            "coverage": None,
        }

        # Language-specific parsing
        if language == "python" and framework == "pytest":
            result.update(self._parse_pytest(output))
        elif language in ["javascript", "typescript"] and framework == "jest":
            result.update(self._parse_jest(output))
        elif language == "go":
            result.update(self._parse_go_test(output))
        elif language == "rust":
            result.update(self._parse_cargo_test(output))
        elif language == "java":
            result.update(self._parse_java_test(output))
        else:
            # Generic parsing - look for common patterns
            result.update(self._parse_generic(output))

        return result

    def _parse_pytest(self, output: str) -> Dict[str, Any]:
        """Parse pytest output."""
        import re

        result = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Look for summary line like "5 passed, 2 failed, 1 skipped in 1.23s"
        summary_match = re.search(
            r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+skipped", output
        )

        if summary_match:
            # Extract numbers
            passed_match = re.search(r"(\d+)\s+passed", output)
            failed_match = re.search(r"(\d+)\s+failed", output)
            skipped_match = re.search(r"(\d+)\s+skipped", output)

            result["passed"] = int(passed_match.group(1)) if passed_match else 0
            result["failed"] = int(failed_match.group(1)) if failed_match else 0
            result["skipped"] = int(skipped_match.group(1)) if skipped_match else 0
            result["total"] = result["passed"] + result["failed"] + result["skipped"]

        # Look for coverage in output
        cov_match = re.search(r"TOTAL.*?(\d+)%", output)
        if cov_match:
            result["coverage"] = float(cov_match.group(1))

        # Calculate pass rate
        if result["total"] > 0:
            result["pass_rate"] = (result["passed"] / result["total"]) * 100

        return result

    def _parse_jest(self, output: str) -> Dict[str, Any]:
        """Parse Jest output."""
        import re

        result = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Jest summary: "Tests: 2 failed, 8 passed, 10 total"
        tests_match = re.search(r"Tests:\s+.*?(\d+)\s+total", output)
        passed_match = re.search(r"(\d+)\s+passed", output)
        failed_match = re.search(r"(\d+)\s+failed", output)

        if tests_match:
            result["total"] = int(tests_match.group(1))
        if passed_match:
            result["passed"] = int(passed_match.group(1))
        if failed_match:
            result["failed"] = int(failed_match.group(1))

        # Coverage
        cov_match = re.search(r"All files\s+\|\s+(\d+\.?\d*)", output)
        if cov_match:
            result["coverage"] = float(cov_match.group(1))

        if result["total"] > 0:
            result["pass_rate"] = (result["passed"] / result["total"]) * 100

        return result

    def _parse_go_test(self, output: str) -> Dict[str, Any]:
        """Parse go test output."""
        import re

        result = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Count PASS and FAIL lines
        passed = len(re.findall(r"^PASS:", output, re.MULTILINE))
        failed = len(re.findall(r"^FAIL:", output, re.MULTILINE))

        result["passed"] = passed
        result["failed"] = failed
        result["total"] = passed + failed

        # Coverage: "coverage: 85.2% of statements"
        cov_match = re.search(r"coverage:\s+(\d+\.?\d*)%", output)
        if cov_match:
            result["coverage"] = float(cov_match.group(1))

        if result["total"] > 0:
            result["pass_rate"] = (result["passed"] / result["total"]) * 100

        return result

    def _parse_cargo_test(self, output: str) -> Dict[str, Any]:
        """Parse cargo test output."""
        import re

        result = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Cargo: "test result: ok. 10 passed; 0 failed; 0 ignored"
        match = re.search(
            r"test result:.*?(\d+)\s+passed;\s+(\d+)\s+failed;\s+(\d+)\s+ignored",
            output,
        )

        if match:
            result["passed"] = int(match.group(1))
            result["failed"] = int(match.group(2))
            result["skipped"] = int(match.group(3))
            result["total"] = result["passed"] + result["failed"] + result["skipped"]

        if result["total"] > 0:
            result["pass_rate"] = (result["passed"] / result["total"]) * 100

        return result

    def _parse_java_test(self, output: str) -> Dict[str, Any]:
        """Parse JUnit/Maven/Gradle test output."""
        import re

        result = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Maven/Gradle: "Tests run: 10, Failures: 0, Errors: 0, Skipped: 1"
        match = re.search(
            r"Tests run:\s+(\d+),\s+Failures:\s+(\d+),\s+Errors:\s+(\d+),\s+Skipped:\s+(\d+)",
            output,
        )

        if match:
            total = int(match.group(1))
            failures = int(match.group(2))
            errors = int(match.group(3))
            skipped = int(match.group(4))

            result["total"] = total
            result["failed"] = failures + errors
            result["skipped"] = skipped
            result["passed"] = total - result["failed"] - result["skipped"]

        if result["total"] > 0:
            result["pass_rate"] = (result["passed"] / result["total"]) * 100

        return result

    def _parse_generic(self, output: str) -> Dict[str, Any]:
        """Generic parsing for unknown frameworks."""
        import re

        result = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        # Look for common patterns
        # Try to find numbers that might be test counts
        lines = output.split("\n")

        for line in lines:
            # Look for summary-like lines
            if "passed" in line.lower() and "failed" in line.lower():
                numbers = re.findall(r"\d+", line)
                if len(numbers) >= 2:
                    result["passed"] = int(numbers[0])
                    result["failed"] = int(numbers[1])
                    result["total"] = result["passed"] + result["failed"]
                    break

        if result["total"] > 0:
            result["pass_rate"] = (result["passed"] / result["total"]) * 100

        return result

    def get_language_info(self) -> Optional[LanguageInfo]:
        """Get the detected language information."""
        if not self.language_info:
            self.language_info = self.detector.detect()
        return self.language_info
