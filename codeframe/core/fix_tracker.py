"""Fix attempt tracking for self-correction loop prevention.

Tracks which fixes have been attempted for which errors to:
1. Prevent repeating the same failed fix
2. Detect patterns indicating we should escalate to a blocker
3. Provide context for escalation decisions

This module is headless - no FastAPI or HTTP dependencies.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class FixOutcome(str, Enum):
    """Outcome of a fix attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class FixAttempt:
    """Record of a single fix attempt.

    Attributes:
        error_signature: Hash of the normalized error
        fix_description: What fix was attempted
        outcome: Result of the attempt
        timestamp: When the attempt was made
        file_path: File being fixed (if applicable)
        error_type: Categorized error type (e.g., "ModuleNotFoundError")
    """

    error_signature: str
    fix_description: str
    outcome: FixOutcome = FixOutcome.PENDING
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    file_path: Optional[str] = None
    error_type: Optional[str] = None


@dataclass
class EscalationDecision:
    """Decision about whether to escalate to a blocker.

    Attributes:
        should_escalate: Whether to create a blocker
        reason: Why escalation is recommended
        attempted_fixes: List of fixes that were tried
        error_summary: Summary of the error pattern
    """

    should_escalate: bool
    reason: str
    attempted_fixes: list[str] = field(default_factory=list)
    error_summary: str = ""


# Thresholds for escalation
MAX_SAME_ERROR_ATTEMPTS = 3
MAX_SAME_FILE_ATTEMPTS = 3
MAX_TOTAL_FAILURES = 5


class FixAttemptTracker:
    """Tracks fix attempts to prevent loops and detect escalation patterns.

    Usage:
        tracker = FixAttemptTracker()

        # Before applying a fix, check if it's been tried
        if tracker.was_attempted(error_msg, fix_description):
            # Skip this fix, try something else
            pass
        else:
            # Record the attempt
            tracker.record_attempt(error_msg, fix_description, file_path="main.py")
            # Apply the fix...
            # Record the outcome
            tracker.record_outcome(error_msg, fix_description, FixOutcome.FAILED)

        # Check if we should escalate
        decision = tracker.should_escalate(error_msg)
        if decision.should_escalate:
            # Create blocker with decision.reason and decision.attempted_fixes
            pass
    """

    def __init__(self):
        """Initialize the tracker."""
        self._attempts: list[FixAttempt] = []
        self._error_counts: dict[str, int] = {}  # error_sig -> count
        self._file_counts: dict[str, int] = {}  # file_path -> failure count

    def normalize_error(self, error: str) -> str:
        """Normalize an error message for comparison.

        Removes variable parts like:
        - Line numbers
        - File paths (keeps basename)
        - Memory addresses
        - Timestamps
        - Specific values in quotes

        Args:
            error: Raw error message

        Returns:
            Normalized error string
        """
        if not error:
            return ""

        normalized = error.lower()

        # Remove line numbers (e.g., "line 42", "at line 123")
        normalized = re.sub(r'\bline\s+\d+\b', 'line N', normalized)
        normalized = re.sub(r':\d+:', ':N:', normalized)

        # Remove file paths but keep the filename
        normalized = re.sub(r'["\']?(/[^"\':\s]+/)?([^"\':\s/]+\.(py|js|ts|go|rs))["\']?',
                          r'\2', normalized)

        # Remove memory addresses
        normalized = re.sub(r'0x[0-9a-f]+', '0xADDR', normalized)

        # Remove timestamps
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', 'TIMESTAMP', normalized)

        # Normalize quoted strings (keep the quotes but replace content)
        normalized = re.sub(r'"[^"]{20,}"', '"..."', normalized)
        normalized = re.sub(r"'[^']{20,}'", "'...'", normalized)

        # Remove extra whitespace
        normalized = ' '.join(normalized.split())

        return normalized

    def hash_error(self, error: str) -> str:
        """Create a hash signature for an error message.

        Args:
            error: Error message (will be normalized)

        Returns:
            Short hash string
        """
        normalized = self.normalize_error(error)
        return hashlib.sha256(normalized.encode()).hexdigest()[:12]

    def extract_error_type(self, error: str) -> Optional[str]:
        """Extract the error type from an error message.

        Args:
            error: Error message

        Returns:
            Error type like "ModuleNotFoundError" or None
        """
        # Common Python error patterns
        patterns = [
            r'(\w+Error):',
            r'(\w+Exception):',
            r'(\w+Warning):',
            r'^(E\d+)',  # ruff/flake8 codes
        ]

        for pattern in patterns:
            match = re.search(pattern, error, re.MULTILINE)
            if match:
                return match.group(1)

        return None

    def record_attempt(
        self,
        error: str,
        fix_description: str,
        file_path: Optional[str] = None,
    ) -> FixAttempt:
        """Record a fix attempt.

        Args:
            error: The error being fixed
            fix_description: Description of the fix being attempted
            file_path: File being fixed (if applicable)

        Returns:
            The recorded FixAttempt
        """
        error_sig = self.hash_error(error)
        error_type = self.extract_error_type(error)

        attempt = FixAttempt(
            error_signature=error_sig,
            fix_description=fix_description,
            outcome=FixOutcome.PENDING,
            file_path=file_path,
            error_type=error_type,
        )

        self._attempts.append(attempt)
        return attempt

    def record_outcome(
        self,
        error: str,
        fix_description: str,
        outcome: FixOutcome,
    ) -> None:
        """Record the outcome of a fix attempt.

        Args:
            error: The error that was being fixed
            fix_description: Description of the fix
            outcome: Whether it succeeded or failed
        """
        error_sig = self.hash_error(error)

        # Find the matching attempt and update it
        for attempt in reversed(self._attempts):
            if (attempt.error_signature == error_sig and
                attempt.fix_description == fix_description and
                attempt.outcome == FixOutcome.PENDING):
                attempt.outcome = outcome
                break

        # Update counts
        if outcome == FixOutcome.FAILED:
            self._error_counts[error_sig] = self._error_counts.get(error_sig, 0) + 1

            # Also track file-level failures
            for attempt in reversed(self._attempts):
                if (attempt.error_signature == error_sig and
                    attempt.file_path):
                    self._file_counts[attempt.file_path] = \
                        self._file_counts.get(attempt.file_path, 0) + 1
                    break

    def was_attempted(self, error: str, fix_description: str) -> bool:
        """Check if a specific fix was already attempted for an error.

        Args:
            error: The error message
            fix_description: The fix to check

        Returns:
            True if this fix was already tried for this error
        """
        error_sig = self.hash_error(error)

        for attempt in self._attempts:
            if (attempt.error_signature == error_sig and
                attempt.fix_description.lower() == fix_description.lower()):
                return True

        return False

    def get_attempted_fixes(self, error: str) -> list[str]:
        """Get list of fixes already attempted for an error.

        Args:
            error: The error message

        Returns:
            List of fix descriptions that were tried
        """
        error_sig = self.hash_error(error)
        return [
            a.fix_description
            for a in self._attempts
            if a.error_signature == error_sig
        ]

    def get_failure_count(self, error: str) -> int:
        """Get number of failed fix attempts for an error.

        Args:
            error: The error message

        Returns:
            Number of failed attempts
        """
        error_sig = self.hash_error(error)
        return self._error_counts.get(error_sig, 0)

    def get_file_failure_count(self, file_path: str) -> int:
        """Get number of failures for a specific file.

        Args:
            file_path: Path to the file

        Returns:
            Number of failed attempts for this file
        """
        return self._file_counts.get(file_path, 0)

    def get_total_failures(self) -> int:
        """Get total number of failed fix attempts.

        Returns:
            Total failure count across all errors
        """
        return sum(self._error_counts.values())

    def should_escalate(self, error: str, file_path: Optional[str] = None) -> EscalationDecision:
        """Determine if we should escalate to a blocker.

        Escalation rules:
        1. Same error type fails 3+ times → blocker
        2. Same file fails 3+ times with different errors → blocker
        3. Total failures in run > 5 → blocker

        Args:
            error: Current error message
            file_path: File being worked on (if applicable)

        Returns:
            EscalationDecision with recommendation and context
        """
        error_sig = self.hash_error(error)
        error_count = self._error_counts.get(error_sig, 0)
        total_failures = self.get_total_failures()
        attempted = self.get_attempted_fixes(error)

        # Rule 1: Same error fails too many times
        if error_count >= MAX_SAME_ERROR_ATTEMPTS:
            error_type = self.extract_error_type(error) or "error"
            return EscalationDecision(
                should_escalate=True,
                reason=f"Same {error_type} has failed {error_count} times despite fixes",
                attempted_fixes=attempted,
                error_summary=self.normalize_error(error)[:200],
            )

        # Rule 2: Same file keeps failing
        if file_path:
            file_count = self._file_counts.get(file_path, 0)
            if file_count >= MAX_SAME_FILE_ATTEMPTS:
                return EscalationDecision(
                    should_escalate=True,
                    reason=f"File '{file_path}' has failed {file_count} times with various errors",
                    attempted_fixes=attempted,
                    error_summary=f"Multiple errors in {file_path}",
                )

        # Rule 3: Too many total failures
        if total_failures >= MAX_TOTAL_FAILURES:
            return EscalationDecision(
                should_escalate=True,
                reason=f"Total of {total_failures} failures in this run exceeds threshold",
                attempted_fixes=attempted,
                error_summary="Multiple errors across the task",
            )

        # No escalation needed
        return EscalationDecision(
            should_escalate=False,
            reason="Within acceptable failure limits",
            attempted_fixes=attempted,
        )

    def get_blocker_context(self, error: str) -> dict:
        """Generate context for creating an informative blocker.

        Args:
            error: Current error message

        Returns:
            Dictionary with blocker context
        """
        error_sig = self.hash_error(error)
        error_type = self.extract_error_type(error)
        attempted = self.get_attempted_fixes(error)

        # Find all files affected by this error
        affected_files = set()
        for attempt in self._attempts:
            if attempt.error_signature == error_sig and attempt.file_path:
                affected_files.add(attempt.file_path)

        return {
            "error_type": error_type,
            "error_signature": error_sig,
            "attempt_count": self._error_counts.get(error_sig, 0),
            "attempted_fixes": attempted,
            "affected_files": list(affected_files),
            "total_run_failures": self.get_total_failures(),
            "normalized_error": self.normalize_error(error),
        }

    def reset(self) -> None:
        """Reset all tracking state.

        Call this when starting a new task or run.
        """
        self._attempts.clear()
        self._error_counts.clear()
        self._file_counts.clear()

    def to_dict(self) -> dict:
        """Serialize tracker state for persistence.

        Returns:
            Dictionary representation of tracker state
        """
        return {
            "attempts": [
                {
                    "error_signature": a.error_signature,
                    "fix_description": a.fix_description,
                    "outcome": a.outcome.value,
                    "timestamp": a.timestamp.isoformat(),
                    "file_path": a.file_path,
                    "error_type": a.error_type,
                }
                for a in self._attempts
            ],
            "error_counts": dict(self._error_counts),
            "file_counts": dict(self._file_counts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FixAttemptTracker":
        """Restore tracker state from persistence.

        Args:
            data: Dictionary from to_dict()

        Returns:
            Restored FixAttemptTracker
        """
        tracker = cls()

        for a in data.get("attempts", []):
            attempt = FixAttempt(
                error_signature=a["error_signature"],
                fix_description=a["fix_description"],
                outcome=FixOutcome(a["outcome"]),
                timestamp=datetime.fromisoformat(a["timestamp"]),
                file_path=a.get("file_path"),
                error_type=a.get("error_type"),
            )
            tracker._attempts.append(attempt)

        tracker._error_counts = dict(data.get("error_counts", {}))
        tracker._file_counts = dict(data.get("file_counts", {}))

        return tracker
