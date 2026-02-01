"""Code review operations for CodeFRAME v2.

This module provides v2-compatible code review operations that work with
the Workspace model. It provides a simplified interface to the quality
analyzers without requiring v1 database persistence.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from codeframe.core.workspace import Workspace
from codeframe.lib.quality.complexity_analyzer import ComplexityAnalyzer
from codeframe.lib.quality.security_scanner import SecurityScanner
from codeframe.lib.quality.owasp_patterns import OWASPPatterns

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ReviewFinding:
    """Individual review finding."""

    category: str  # complexity, security, style
    severity: Literal["critical", "high", "medium", "low", "info"]
    message: str
    file_path: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class ReviewResult:
    """Result of a code review."""

    status: Literal["approved", "changes_requested", "rejected"]
    overall_score: float
    findings: list[ReviewFinding]
    summary: str


@dataclass
class ReviewStatus:
    """Review status for a task."""

    has_review: bool
    status: Optional[str]
    overall_score: Optional[float]
    findings_count: int


# ============================================================================
# Score Thresholds
# ============================================================================

EXCELLENT_THRESHOLD = 90
GOOD_THRESHOLD = 70
ACCEPTABLE_THRESHOLD = 50


# ============================================================================
# Review Functions
# ============================================================================


def _determine_status(score: float) -> Literal["approved", "changes_requested", "rejected"]:
    """Determine review status based on score.

    Args:
        score: Overall review score (0-100)

    Returns:
        Review status
    """
    if score >= GOOD_THRESHOLD:
        return "approved"
    elif score >= ACCEPTABLE_THRESHOLD:
        return "changes_requested"
    else:
        return "rejected"


def _severity_from_score(score: float) -> Literal["critical", "high", "medium", "low", "info"]:
    """Determine severity based on score.

    Args:
        score: Individual finding score

    Returns:
        Severity level
    """
    if score < 30:
        return "critical"
    elif score < 50:
        return "high"
    elif score < 70:
        return "medium"
    elif score < 90:
        return "low"
    else:
        return "info"


def review_files(
    workspace: Workspace,
    files: list[str],
) -> ReviewResult:
    """Run code review on specified files.

    Performs complexity analysis, security scanning, and OWASP pattern
    detection on the given files.

    Args:
        workspace: Target workspace
        files: List of file paths to review (relative to repo root)

    Returns:
        ReviewResult with findings and overall score
    """
    project_path = workspace.repo_path
    findings: list[ReviewFinding] = []

    # Initialize analyzers
    complexity_analyzer = ComplexityAnalyzer(project_path)
    security_scanner = SecurityScanner(project_path)
    owasp_checker = OWASPPatterns()

    # Track scores for averaging
    scores: list[float] = []

    for file_path in files:
        full_path = project_path / file_path

        if not full_path.exists():
            logger.warning(f"File not found: {file_path}")
            continue

        if not full_path.suffix == ".py":
            # Only analyze Python files for now
            continue

        # Complexity analysis
        try:
            complexity_result = complexity_analyzer.analyze_file(str(full_path))
            if complexity_result:
                # Check for high complexity functions
                for func in complexity_result.get("functions", []):
                    if func.get("complexity", 0) > 10:
                        findings.append(
                            ReviewFinding(
                                category="complexity",
                                severity=_severity_from_score(100 - func["complexity"] * 5),
                                message=f"Function '{func['name']}' has complexity of {func['complexity']}",
                                file_path=file_path,
                                line_number=func.get("line_number"),
                                suggestion="Consider breaking into smaller functions",
                            )
                        )
                        scores.append(max(0, 100 - func["complexity"] * 5))
        except Exception as e:
            logger.warning(f"Complexity analysis failed for {file_path}: {e}")

        # Security scan
        try:
            security_issues = security_scanner.scan_file(str(full_path))
            for issue in security_issues:
                findings.append(
                    ReviewFinding(
                        category="security",
                        severity=issue.get("severity", "medium"),
                        message=issue.get("message", "Security issue detected"),
                        file_path=file_path,
                        line_number=issue.get("line_number"),
                        suggestion=issue.get("recommendation"),
                    )
                )
                # Security issues have heavier weight on score
                severity_scores = {"critical": 20, "high": 40, "medium": 60, "low": 80, "info": 95}
                scores.append(severity_scores.get(issue.get("severity", "medium"), 60))
        except Exception as e:
            logger.warning(f"Security scan failed for {file_path}: {e}")

        # OWASP pattern check
        try:
            try:
                file_content = full_path.read_text()
            except Exception:
                continue

            owasp_findings = owasp_checker.check(file_content)
            for finding in owasp_findings:
                findings.append(
                    ReviewFinding(
                        category="security",
                        severity="high",
                        message=f"OWASP pattern detected: {finding.get('pattern', 'unknown')}",
                        file_path=file_path,
                        line_number=finding.get("line_number"),
                        suggestion=finding.get("remediation"),
                    )
                )
                scores.append(50)  # OWASP findings are significant
        except Exception as e:
            logger.warning(f"OWASP check failed for {file_path}: {e}")

    # Calculate overall score
    if scores:
        overall_score = sum(scores) / len(scores)
    else:
        # No issues found = perfect score
        overall_score = 100.0

    status = _determine_status(overall_score)

    # Generate summary
    if not findings:
        summary = "No issues found. Code looks good!"
    else:
        critical_count = sum(1 for f in findings if f.severity == "critical")
        high_count = sum(1 for f in findings if f.severity == "high")
        summary = f"Found {len(findings)} issues: {critical_count} critical, {high_count} high severity"

    logger.info(f"Review completed: {status} (score: {overall_score:.1f})")

    return ReviewResult(
        status=status,
        overall_score=round(overall_score, 1),
        findings=findings,
        summary=summary,
    )


def review_task(
    workspace: Workspace,
    task_id: str,
    files_modified: list[str],
) -> ReviewResult:
    """Run code review for a task's modified files.

    Convenience function that wraps review_files with task context.

    Args:
        workspace: Target workspace
        task_id: Task ID (for logging)
        files_modified: List of modified file paths

    Returns:
        ReviewResult with findings and overall score
    """
    logger.info(f"Starting review for task {task_id} ({len(files_modified)} files)")
    return review_files(workspace, files_modified)


def get_review_summary(result: ReviewResult) -> dict:
    """Get a summary dict from review result.

    Args:
        result: ReviewResult from review_files/review_task

    Returns:
        Summary dict suitable for API responses
    """
    severity_counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    for finding in result.findings:
        if finding.severity in severity_counts:
            severity_counts[finding.severity] += 1

    return {
        "status": result.status,
        "overall_score": result.overall_score,
        "total_findings": len(result.findings),
        "severity_counts": severity_counts,
        "summary": result.summary,
        "has_blocking_issues": severity_counts["critical"] + severity_counts["high"] > 0,
    }
