"""Shared utilities for linting integration.

This module provides common utilities for worker agents to format
lint results into blocker messages and handle lint error parsing.
"""

import json
import logging
from typing import List

from codeframe.core.models import LintResult

logger = logging.getLogger(__name__)


def format_lint_blocker(lint_results: List[LintResult]) -> str:
    """Format lint results into blocker message.

    Creates a detailed markdown-formatted message listing all critical
    errors from linting, suitable for use in blocker descriptions.

    Args:
        lint_results: List of LintResult objects containing error details

    Returns:
        Formatted markdown string with error details

    Example:
        >>> results = [LintResult(linter="ruff", error_count=2, ...)]
        >>> msg = format_lint_blocker(results)
        >>> print(msg)
        ## Linting Failed

        ### ruff - 2 errors, 1 warnings

        - **F401**: Imported but unused
          File: backend.py:10
        ...
    """
    lines = ["## Linting Failed\n"]

    for result in lint_results:
        if result.error_count > 0:
            lines.append(
                f"### {result.linter} - {result.error_count} errors, {result.warning_count} warnings\n"
            )

            # Parse output JSON for details
            try:
                issues = json.loads(result.output) if result.output else []

                # Handle both list and dict outputs
                if isinstance(issues, dict):
                    issues = issues.get("messages", [])

                # Limit to first 10 critical issues
                critical_issues = [issue for issue in issues if _is_critical_issue(issue)][:10]

                for issue in critical_issues:
                    code = _extract_error_code(issue)
                    message = _extract_error_message(issue)
                    location = _extract_error_location(issue)

                    lines.append(f"- **{code}**: {message}")
                    lines.append(f"  {location}\n")

            except json.JSONDecodeError:
                # If output is not JSON, include raw output (truncated)
                lines.append(f"```\n{result.output[:500]}\n```\n")
            except Exception as e:
                logger.warning(f"Failed to parse lint output: {e}")
                lines.append("(Unable to parse error details)\n")

    lines.append("\n**Action Required**: Fix critical errors and re-run task.")
    return "\n".join(lines)


def _is_critical_issue(issue: dict) -> bool:
    """Check if lint issue is critical (error vs warning).

    Args:
        issue: Lint issue dict from ruff or eslint

    Returns:
        True if critical error, False if warning
    """
    # Ruff: F-codes (fatal), E-codes (errors) are critical
    code = issue.get("code", "")
    if isinstance(code, str) and code:
        if code.startswith(("F", "E")):
            return True

    # ESLint: severity 2 is error
    severity = issue.get("severity", 0)
    if severity == 2:
        return True

    return False


def _extract_error_code(issue: dict) -> str:
    """Extract error code from lint issue.

    Args:
        issue: Lint issue dict

    Returns:
        Error code string (e.g., "F401", "no-unused-vars")
    """
    # Ruff format
    if "code" in issue:
        return str(issue["code"])

    # ESLint format
    if "ruleId" in issue:
        return str(issue["ruleId"])

    return "unknown"


def _extract_error_message(issue: dict) -> str:
    """Extract error message from lint issue.

    Args:
        issue: Lint issue dict

    Returns:
        Error message string
    """
    return issue.get("message", "No message")


def _extract_error_location(issue: dict) -> str:
    """Extract file location from lint issue.

    Args:
        issue: Lint issue dict

    Returns:
        Formatted location string (e.g., "File: backend.py:42")
    """
    # Ruff format
    if "location" in issue:
        loc = issue["location"]
        filename = issue.get("filename", "unknown")
        row = loc.get("row", "?")
        return f"File: {filename}:{row}"

    # ESLint format
    if "line" in issue:
        filename = issue.get("filePath", "unknown")
        line = issue.get("line", "?")
        return f"File: {filename}:{line}"

    return "File: unknown"
