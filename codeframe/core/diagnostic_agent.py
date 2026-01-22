"""Diagnostic Agent for CodeFRAME v2.

Analyzes failed runs and generates actionable recommendations.

This module provides:
- Pattern-based failure detection
- LLM-powered root cause analysis
- Recommendation generation
- Severity assessment

This module is headless - no FastAPI or HTTP dependencies.
"""

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from codeframe.adapters.llm import Purpose
from codeframe.core.diagnostics import (
    DiagnosticRecommendation,
    DiagnosticReport,
    FailureCategory,
    LogCategory,
    LogLevel,
    RemediationAction,
    RunLogEntry,
    Severity,
    get_run_errors,
    get_run_logs,
    save_diagnostic_report,
)
from codeframe.core.workspace import Workspace

if TYPE_CHECKING:
    from codeframe.adapters.llm.base import LLMProvider


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# Pattern Definitions for Failure Detection
# =============================================================================

# Patterns for task description issues
TASK_DESCRIPTION_PATTERNS = [
    r"ambiguous",
    r"unclear",
    r"vague",
    r"unspecified",
    r"missing.*requirement",
    r"cannot.*determine",
    r"lack.*acceptance.*criteria",
    r"need.*clarification",
    r"requirements.*incomplete",
]

# Patterns for model/API limitations
MODEL_LIMITATION_PATTERNS = [
    r"context.*length.*exceeded",
    r"token.*limit",
    r"maximum.*tokens",
    r"rate.*limit",
    r"api.*error.*429",
    r"quota.*exceeded",
    r"model.*unavailable",
]

# Patterns for dependency issues
DEPENDENCY_PATTERNS = [
    r"modulenotfounderror",
    r"importerror",
    r"no module named",
    r"package.*not.*found",
    r"dependency.*missing",
    r"cannot.*import",
]

# Patterns for code quality issues
CODE_QUALITY_PATTERNS = [
    r"test.*failed",
    r"pytest.*failed",
    r"lint.*error",
    r"type.*error",
    r"ruff.*check.*failed",
    r"mypy.*error",
    r"assertion.*failed",
]

# Patterns for environment issues
ENVIRONMENT_PATTERNS = [
    r"permission.*denied",
    r"file.*not.*found",
    r"directory.*not.*exist",
    r"environment.*variable.*not.*set",
    r"command.*not.*found",
]

# Patterns for blocker-related issues
BLOCKER_PATTERNS = [
    r"blocker.*created",
    r"human.*input.*needed",
    r"waiting.*for.*answer",
    r"escalated.*to.*human",
]


# =============================================================================
# Pattern Detection Functions
# =============================================================================


def detect_failure_patterns(logs: list[RunLogEntry]) -> set[FailureCategory]:
    """Detect failure patterns from log entries.

    Analyzes log messages to identify likely failure categories
    without using the LLM.

    Args:
        logs: List of log entries to analyze

    Returns:
        Set of detected failure categories
    """
    detected: set[FailureCategory] = set()

    # Combine all messages for pattern matching
    all_text = " ".join(
        f"{log.message} {log.metadata}" if log.metadata else log.message
        for log in logs
    ).lower()

    # Check each pattern category
    for pattern in TASK_DESCRIPTION_PATTERNS:
        if re.search(pattern, all_text):
            detected.add(FailureCategory.TASK_DESCRIPTION)
            break

    for pattern in MODEL_LIMITATION_PATTERNS:
        if re.search(pattern, all_text):
            detected.add(FailureCategory.MODEL_LIMITATION)
            break

    for pattern in DEPENDENCY_PATTERNS:
        if re.search(pattern, all_text):
            detected.add(FailureCategory.DEPENDENCY_ISSUE)
            break

    for pattern in CODE_QUALITY_PATTERNS:
        if re.search(pattern, all_text):
            detected.add(FailureCategory.CODE_QUALITY)
            break

    for pattern in ENVIRONMENT_PATTERNS:
        if re.search(pattern, all_text):
            detected.add(FailureCategory.ENVIRONMENT_ISSUE)
            break

    for pattern in BLOCKER_PATTERNS:
        if re.search(pattern, all_text):
            detected.add(FailureCategory.BLOCKER_UNRESOLVED)
            break

    return detected


def detect_primary_failure_category(logs: list[RunLogEntry]) -> FailureCategory:
    """Detect the primary failure category from logs.

    Returns the most likely failure category, prioritizing
    more actionable categories.

    Args:
        logs: List of log entries to analyze

    Returns:
        Primary failure category
    """
    detected = detect_failure_patterns(logs)

    # Priority order (most actionable first)
    priority = [
        FailureCategory.TASK_DESCRIPTION,
        FailureCategory.BLOCKER_UNRESOLVED,
        FailureCategory.DEPENDENCY_ISSUE,
        FailureCategory.ENVIRONMENT_ISSUE,
        FailureCategory.CODE_QUALITY,
        FailureCategory.MODEL_LIMITATION,
        FailureCategory.TECHNICAL_ERROR,
    ]

    for category in priority:
        if category in detected:
            return category

    return FailureCategory.UNKNOWN


# =============================================================================
# Recommendation Generation
# =============================================================================


def generate_recommendations(
    task_id: str,
    run_id: str,
    failure_category: FailureCategory,
    error_messages: list[str],
) -> list[DiagnosticRecommendation]:
    """Generate remediation recommendations based on failure category.

    Args:
        task_id: ID of the failed task
        run_id: ID of the failed run
        failure_category: Detected failure category
        error_messages: List of error messages from logs

    Returns:
        List of actionable recommendations
    """
    recommendations: list[DiagnosticRecommendation] = []

    if failure_category == FailureCategory.TASK_DESCRIPTION:
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.UPDATE_TASK_DESCRIPTION,
                reason="Task description may be ambiguous or incomplete. Adding clearer acceptance criteria will help the agent understand requirements.",
                command=f"cf tasks show {task_id}  # Review current description, then update with clearer criteria",
                parameters={"task_id": task_id},
            )
        )
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.RETRY_WITH_CONTEXT,
                reason="After updating the description, retry the task",
                command=f"cf work start {task_id} --execute",
                parameters={"task_id": task_id},
            )
        )

    elif failure_category == FailureCategory.BLOCKER_UNRESOLVED:
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.ANSWER_BLOCKER,
                reason="The task has an unresolved blocker that needs human input",
                command="cf blocker list  # Find and answer the open blocker",
                parameters={"task_id": task_id},
            )
        )

    elif failure_category == FailureCategory.DEPENDENCY_ISSUE:
        # Try to extract package name from error messages
        package_name = _extract_package_name(error_messages)
        if package_name:
            recommendations.append(
                DiagnosticRecommendation(
                    action=RemediationAction.RESOLVE_DEPENDENCY,
                    reason=f"Missing package: {package_name}. Install it and retry.",
                    command=f"uv pip install {package_name}  # or: pip install {package_name}",
                    parameters={"package": package_name},
                )
            )
        else:
            recommendations.append(
                DiagnosticRecommendation(
                    action=RemediationAction.RESOLVE_DEPENDENCY,
                    reason="Missing dependencies detected. Review the error and install required packages.",
                    command="# Review error messages and install missing dependencies",
                    parameters={},
                )
            )
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.RETRY_WITH_CONTEXT,
                reason="After resolving dependencies, retry the task",
                command=f"cf work start {task_id} --execute",
                parameters={"task_id": task_id},
            )
        )

    elif failure_category == FailureCategory.ENVIRONMENT_ISSUE:
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.FIX_ENVIRONMENT,
                reason="Environment configuration issue detected. Check file permissions, paths, and environment variables.",
                command="# Review error messages and fix environment configuration",
                parameters={},
            )
        )
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.RETRY_WITH_CONTEXT,
                reason="After fixing the environment, retry the task",
                command=f"cf work start {task_id} --execute",
                parameters={"task_id": task_id},
            )
        )

    elif failure_category == FailureCategory.CODE_QUALITY:
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.RETRY_WITH_CONTEXT,
                reason="Code quality issues (tests/lint) detected. The agent will try to self-correct on retry.",
                command=f"cf work start {task_id} --execute --verbose",
                parameters={"task_id": task_id, "verbose": True},
            )
        )

    elif failure_category == FailureCategory.MODEL_LIMITATION:
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.CHANGE_MODEL,
                reason="Model limitation detected (token limit, rate limit, etc.). Consider using a different model or breaking down the task.",
                command="# Consider splitting task or using a model with larger context",
                parameters={"task_id": task_id},
            )
        )
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.SPLIT_TASK,
                reason="The task may be too large. Consider splitting it into smaller subtasks.",
                command="# Review task and consider breaking into smaller pieces",
                parameters={"task_id": task_id},
            )
        )

    elif failure_category == FailureCategory.TECHNICAL_ERROR:
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.RETRY_WITH_CONTEXT,
                reason="Technical error occurred. A simple retry may resolve transient issues.",
                command=f"cf work start {task_id} --execute",
                parameters={"task_id": task_id},
            )
        )

    else:  # UNKNOWN
        recommendations.append(
            DiagnosticRecommendation(
                action=RemediationAction.RETRY_WITH_CONTEXT,
                reason="Unable to determine specific failure cause. Try running with verbose mode for more details.",
                command=f"cf work start {task_id} --execute --verbose",
                parameters={"task_id": task_id, "verbose": True},
            )
        )

    return recommendations


def _extract_package_name(error_messages: list[str]) -> Optional[str]:
    """Extract package name from error messages.

    Args:
        error_messages: List of error messages

    Returns:
        Package name if found, None otherwise
    """
    for msg in error_messages:
        # ModuleNotFoundError: No module named 'package_name'
        match = re.search(r"no module named ['\"]?(\w+)", msg, re.IGNORECASE)
        if match:
            return match.group(1)

        # ImportError: cannot import name 'x' from 'package'
        match = re.search(r"cannot import.*from ['\"]?(\w+)", msg, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


# =============================================================================
# Severity Assessment
# =============================================================================


def assess_severity(
    failure_category: FailureCategory,
    error_count: int,
    has_blocker: bool,
) -> Severity:
    """Assess the severity of a failure.

    Args:
        failure_category: The detected failure category
        error_count: Number of error log entries
        has_blocker: Whether a blocker was created

    Returns:
        Severity level
    """
    # Critical: Many errors or blockers
    if error_count >= 5 and has_blocker:
        return Severity.CRITICAL

    # High: Task description issues need attention
    if failure_category == FailureCategory.TASK_DESCRIPTION:
        return Severity.HIGH

    # High: Unresolved blockers
    if failure_category == FailureCategory.BLOCKER_UNRESOLVED:
        return Severity.HIGH

    # Medium: Code quality or environment issues
    if failure_category in (
        FailureCategory.CODE_QUALITY,
        FailureCategory.DEPENDENCY_ISSUE,
        FailureCategory.ENVIRONMENT_ISSUE,
    ):
        return Severity.MEDIUM

    # Medium: Multiple errors
    if error_count >= 3:
        return Severity.MEDIUM

    # Low: Single transient errors
    return Severity.LOW


# =============================================================================
# Log Summarization
# =============================================================================


def summarize_logs(logs: list[RunLogEntry], max_length: int = 1000) -> str:
    """Summarize log entries into a human-readable format.

    Args:
        logs: List of log entries to summarize
        max_length: Maximum length of summary

    Returns:
        Human-readable summary string
    """
    if not logs:
        return "No log entries found for this run."

    # Focus on errors and important events
    important_logs = [
        log for log in logs
        if log.log_level in (LogLevel.ERROR, LogLevel.WARNING)
        or log.category in (LogCategory.AGENT_ACTION, LogCategory.BLOCKER)
    ]

    # If no important logs, use all logs
    if not important_logs:
        important_logs = logs

    # Build summary
    lines = []
    for log in important_logs[:20]:  # Limit to 20 entries
        prefix = "ERROR" if log.log_level == LogLevel.ERROR else log.log_level.value
        lines.append(f"[{prefix}] {log.category.value}: {log.message[:200]}")

    summary = "\n".join(lines)

    # Truncate if necessary
    if len(summary) > max_length:
        summary = summary[:max_length - 3] + "..."

    return summary


# =============================================================================
# Diagnostic Agent
# =============================================================================


class DiagnosticAgent:
    """Agent that analyzes failed runs and generates diagnostic reports.

    Uses pattern matching for quick detection and optionally uses
    LLM for deeper analysis of complex failures.

    Usage:
        agent = DiagnosticAgent(workspace, llm_provider)
        report = agent.analyze(task_id, run_id)
        # report contains root cause, recommendations, etc.
    """

    def __init__(
        self,
        workspace: Workspace,
        llm_provider: Optional["LLMProvider"] = None,
    ):
        """Initialize the diagnostic agent.

        Args:
            workspace: Target workspace
            llm_provider: Optional LLM provider for deep analysis
        """
        self.workspace = workspace
        self.llm_provider = llm_provider

    def analyze(self, task_id: str, run_id: str) -> DiagnosticReport:
        """Analyze a failed run and generate a diagnostic report.

        Args:
            task_id: ID of the failed task
            run_id: ID of the failed run

        Returns:
            DiagnosticReport with analysis and recommendations
        """
        # Get logs for analysis
        logs = get_run_logs(self.workspace, run_id)
        errors = get_run_errors(self.workspace, run_id)

        # Detect failure category from patterns
        failure_category = detect_primary_failure_category(logs)

        # Extract error messages
        error_messages = [e.message for e in errors]

        # Check for blockers
        has_blocker = any(
            log.category == LogCategory.BLOCKER
            for log in logs
        )

        # Generate log summary
        log_summary = summarize_logs(logs)

        # Determine root cause (may update failure_category via LLM)
        if self.llm_provider and logs:
            root_cause = self._analyze_with_llm(logs, error_messages)
            # Parse LLM response to potentially update category
            llm_category = self._extract_category_from_llm(root_cause)
            if llm_category != FailureCategory.UNKNOWN:
                failure_category = llm_category
        else:
            root_cause = self._generate_root_cause(failure_category, error_messages)

        # Assess severity AFTER potential LLM category update
        severity = assess_severity(
            failure_category=failure_category,
            error_count=len(errors),
            has_blocker=has_blocker,
        )

        # Generate recommendations AFTER potential LLM category update
        recommendations = generate_recommendations(
            task_id=task_id,
            run_id=run_id,
            failure_category=failure_category,
            error_messages=error_messages,
        )

        # Create report
        report = DiagnosticReport(
            task_id=task_id,
            run_id=run_id,
            root_cause=root_cause,
            failure_category=failure_category,
            severity=severity,
            recommendations=recommendations,
            log_summary=log_summary,
            created_at=_utc_now(),
        )

        # Save to database
        save_diagnostic_report(self.workspace, report)

        return report

    def _analyze_with_llm(
        self,
        logs: list[RunLogEntry],
        error_messages: list[str],
    ) -> str:
        """Use LLM to analyze logs and determine root cause.

        Args:
            logs: Log entries to analyze
            error_messages: Extracted error messages

        Returns:
            Root cause description from LLM
        """
        if not self.llm_provider:
            return "LLM analysis not available"

        # Build prompt
        log_text = "\n".join(
            f"[{log.log_level.value}] {log.category.value}: {log.message}"
            for log in logs[-30:]  # Last 30 logs
        )

        prompt = f"""Analyze the following agent execution logs and determine the root cause of the failure.

Logs:
{log_text}

Error messages:
{chr(10).join(error_messages[:10])}

Provide your analysis in this format:
Root Cause: [One sentence description of the root cause]
Failure Category: [One of: task_description, blocker_unresolved, model_limitation, code_quality, dependency_issue, environment_issue, technical_error, unknown]
Severity: [One of: critical, high, medium, low]

Then provide recommendations."""

        try:
            response = self.llm_provider.complete(
                messages=[{"role": "user", "content": prompt}],
                purpose=Purpose.GENERATION,
            )
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"LLM analysis failed: {e}"

    def _extract_category_from_llm(self, llm_response: str) -> FailureCategory:
        """Extract failure category from LLM response.

        Args:
            llm_response: Response from LLM

        Returns:
            Extracted failure category
        """
        response_lower = llm_response.lower()

        category_map = {
            "task_description": FailureCategory.TASK_DESCRIPTION,
            "blocker_unresolved": FailureCategory.BLOCKER_UNRESOLVED,
            "model_limitation": FailureCategory.MODEL_LIMITATION,
            "code_quality": FailureCategory.CODE_QUALITY,
            "dependency_issue": FailureCategory.DEPENDENCY_ISSUE,
            "environment_issue": FailureCategory.ENVIRONMENT_ISSUE,
            "technical_error": FailureCategory.TECHNICAL_ERROR,
        }

        for key, category in category_map.items():
            if key in response_lower:
                return category

        return FailureCategory.UNKNOWN

    def _generate_root_cause(
        self,
        failure_category: FailureCategory,
        error_messages: list[str],
    ) -> str:
        """Generate a root cause description without LLM.

        Args:
            failure_category: Detected failure category
            error_messages: Error messages from logs

        Returns:
            Root cause description
        """
        category_descriptions = {
            FailureCategory.TASK_DESCRIPTION: (
                "Task description lacks clear requirements or acceptance criteria. "
                "The agent could not determine the expected implementation approach."
            ),
            FailureCategory.BLOCKER_UNRESOLVED: (
                "Task is blocked waiting for human input. "
                "An unresolved blocker needs to be answered before the task can continue."
            ),
            FailureCategory.MODEL_LIMITATION: (
                "The task exceeded model limitations (token limit, rate limit, etc.). "
                "Consider using a model with larger context or breaking down the task."
            ),
            FailureCategory.CODE_QUALITY: (
                "Code quality checks (tests or linting) failed. "
                "The agent's self-correction loop was unable to resolve the issues."
            ),
            FailureCategory.DEPENDENCY_ISSUE: (
                "Missing dependencies prevented task execution. "
                "Required packages need to be installed before retrying."
            ),
            FailureCategory.ENVIRONMENT_ISSUE: (
                "Environment configuration issues prevented task execution. "
                "Check file permissions, paths, and environment variables."
            ),
            FailureCategory.TECHNICAL_ERROR: (
                "A technical error occurred during task execution. "
                "This may be a transient issue that could resolve on retry."
            ),
            FailureCategory.UNKNOWN: (
                "Unable to determine the specific cause of failure. "
                "Review the logs for more details."
            ),
        }

        base_cause = category_descriptions.get(
            failure_category,
            "Unable to determine root cause.",
        )

        # Append first error if available
        if error_messages:
            first_error = error_messages[0][:200]
            base_cause += f"\n\nFirst error: {first_error}"

        return base_cause
