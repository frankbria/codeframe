"""
Test result models for CodeFRAME (cf-42).

Data structures for representing test execution results.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


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
