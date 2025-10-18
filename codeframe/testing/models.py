"""
Test result models for CodeFRAME (cf-42, cf-43).

Data structures for representing test execution results and correction attempts.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class TestResult:
    """
    Represents the result of a test run.

    Attributes:
        status: Overall test status ("passed", "failed", "error", "timeout", "no_tests")
        total: Total number of tests run
        passed: Number of tests that passed
        failed: Number of tests that failed
        errors: Number of tests with errors/exceptions
        skipped: Number of tests skipped
        duration: Total execution time in seconds
        output: Raw output or structured data from test run
    """

    status: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0
    output: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate status values."""
        valid_statuses = {"passed", "failed", "error", "timeout", "no_tests"}
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of: {valid_statuses}"
            )


@dataclass
class CorrectionAttempt:
    """
    Represents a single attempt to fix failing tests (cf-43).

    Attributes:
        task_id: ID of the task being corrected
        attempt_number: Which attempt this is (1-3)
        error_analysis: Analysis of what went wrong
        fix_description: Human-readable description of the fix
        code_changes: Actual code changes applied (diff format)
        test_result_id: Optional reference to the test result after this fix
        timestamp: When this attempt was made
    """

    task_id: str
    attempt_number: int
    error_analysis: str
    fix_description: str
    code_changes: str = ""
    test_result_id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate attempt_number is in valid range (1-3)."""
        if not 1 <= self.attempt_number <= 3:
            raise ValueError(
                f"attempt_number must be between 1 and 3, got {self.attempt_number}"
            )
