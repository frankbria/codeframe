"""
Tactical Pattern Detection System for Supervisor Intervention.

This module provides pattern matching for common agent failure scenarios,
enabling the supervisor (LeadAgent) to detect errors that can be recovered
from with targeted intervention strategies.

Patterns are extensible - new error patterns can be added without modifying
the core orchestration logic.
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class InterventionStrategy(Enum):
    """Strategies for supervisor intervention when patterns match.

    Each strategy defines how the supervisor should modify task context
    or agent behavior before retrying.
    """
    CONVERT_CREATE_TO_EDIT = "convert_create_to_edit"
    SKIP_FILE_CREATION = "skip_file_creation"
    CREATE_BACKUP = "create_backup"
    RETRY_WITH_CONTEXT = "retry_with_context"


@dataclass
class TacticalPattern:
    """Definition of an error pattern for supervisor intervention.

    Attributes:
        pattern_id: Unique identifier for this pattern
        error_pattern: Regex pattern to match against error messages
        category: Category of error (e.g., "file_conflict", "permission")
        intervention_strategy: How to handle errors matching this pattern
        description: Human-readable description of what this pattern detects
    """
    pattern_id: str
    error_pattern: str
    category: str
    intervention_strategy: InterventionStrategy
    description: Optional[str] = None

    def matches(self, error_message: str) -> bool:
        """Check if this pattern matches the given error message.

        Args:
            error_message: The error message to check

        Returns:
            True if pattern matches, False otherwise
        """
        if not error_message:
            return False
        try:
            return bool(re.search(self.error_pattern, error_message, re.IGNORECASE))
        except re.error:
            logger.warning(f"Invalid regex pattern: {self.error_pattern}")
            return False


class TacticalPatternMatcher:
    """Matches error messages against known tactical patterns.

    The matcher maintains a collection of patterns and provides methods
    to check error messages against all patterns, returning the first match.

    Patterns are checked in order, so more specific patterns should be
    added before more general ones.
    """

    def __init__(self):
        """Initialize with default patterns for common errors."""
        self.patterns: List[TacticalPattern] = []
        self._initialize_default_patterns()

    def _initialize_default_patterns(self):
        """Add default patterns for known error scenarios."""
        # File already exists pattern - multiple variations
        self.patterns.append(TacticalPattern(
            pattern_id="file_already_exists",
            error_pattern=r"(file\s+(already\s+)?exists|FileExistsError|Errno\s*17)",
            category="file_conflict",
            intervention_strategy=InterventionStrategy.CONVERT_CREATE_TO_EDIT,
            description="Detects when agent tries to create a file that already exists",
        ))

        # File not found pattern
        self.patterns.append(TacticalPattern(
            pattern_id="file_not_found",
            error_pattern=r"(FileNotFoundError|No such file|Cannot modify non-existent|Errno\s*2)",
            category="file_conflict",
            intervention_strategy=InterventionStrategy.RETRY_WITH_CONTEXT,
            description="Detects when agent tries to access a non-existent file",
        ))

    def match_error(self, error_message: Optional[str]) -> Optional[TacticalPattern]:
        """Match an error message against all patterns.

        Args:
            error_message: The error message to match

        Returns:
            The first matching TacticalPattern, or None if no match
        """
        if error_message is None:
            return None

        for pattern in self.patterns:
            if pattern.matches(error_message):
                logger.debug(
                    f"[DIAG] Matched tactical pattern: {pattern.pattern_id} "
                    f"for error: {error_message[:100]}"
                )
                return pattern

        return None

    def match_error_with_diagnostics(
        self, error_message: Optional[str]
    ) -> Tuple[Optional[TacticalPattern], Dict[str, Any]]:
        """Match an error message and return diagnostic information.

        Args:
            error_message: The error message to match

        Returns:
            Tuple of (matched_pattern, diagnostics_dict)
        """
        diagnostics: Dict[str, Any] = {
            "matched_pattern": None,
            "patterns_checked": 0,
            "error_message_empty": error_message is None or error_message == "",
        }

        if error_message is None:
            return None, diagnostics

        for i, pattern in enumerate(self.patterns):
            diagnostics["patterns_checked"] = i + 1
            if pattern.matches(error_message):
                diagnostics["matched_pattern"] = pattern.pattern_id
                return pattern, diagnostics

        return None, diagnostics

    def extract_file_path(self, error_message: str) -> Optional[str]:
        """Extract file path from an error message.

        Attempts to extract the file path from common error formats:
        - "file already exists: <path>"
        - "FileExistsError: <path>"
        - "No such file or directory: '<path>'"

        Args:
            error_message: The error message containing a file path

        Returns:
            Extracted file path, or None if not found
        """
        if not error_message:
            return None

        # Try multiple patterns to extract file path
        patterns = [
            # "file already exists: path/to/file.py" - match path with extension
            r"exists:\s*['\"]?([^\s'\"]+\.[a-zA-Z]+)['\"]?",
            # "No such file or directory: '/path/to/file.py'"
            r"directory:\s*['\"]?([^'\"]+)['\"]?",
            # "Cannot modify non-existent file: path/to/file.py"
            r"non-existent file:\s*([^\s]+)",
            # Generic path extraction - file path with extension
            r":\s*['\"]?([^\s'\":]+\.[a-zA-Z0-9]+)['\"]?\s*$",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                path = match.group(1).strip()
                # Clean up any trailing punctuation
                path = path.rstrip(".,;:'\"")
                return path

        return None

    def add_pattern(self, pattern: TacticalPattern) -> None:
        """Add a custom pattern to the matcher.

        Args:
            pattern: The TacticalPattern to add
        """
        self.patterns.append(pattern)
        logger.info(f"Added tactical pattern: {pattern.pattern_id}")

    def remove_pattern(self, pattern_id: str) -> bool:
        """Remove a pattern by its ID.

        Args:
            pattern_id: The ID of the pattern to remove

        Returns:
            True if pattern was removed, False if not found
        """
        for i, pattern in enumerate(self.patterns):
            if pattern.pattern_id == pattern_id:
                self.patterns.pop(i)
                logger.info(f"Removed tactical pattern: {pattern_id}")
                return True
        return False

    def get_patterns_by_category(self, category: str) -> List[TacticalPattern]:
        """Get all patterns in a given category.

        Args:
            category: The category to filter by

        Returns:
            List of patterns in that category
        """
        return [p for p in self.patterns if p.category == category]
