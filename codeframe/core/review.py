"""Code review operations for CodeFRAME v2.

This module provides v2-compatible code review operations that work with
the Workspace model. It provides a simplified interface to the quality
analyzers without requiring v1 database persistence.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Literal, Optional

from codeframe.core.workspace import Workspace
from codeframe.lib.quality.complexity_analyzer import ComplexityAnalyzer
from codeframe.lib.quality.security_scanner import ScannerUnavailableError, SecurityScanner
from codeframe.lib.quality.owasp_patterns import OWASPPatterns

logger = logging.getLogger(__name__)


class TaskNotFoundError(Exception):
    """`review_task` was given an id no task in this workspace has (#1066)."""


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

    status: Literal["approved", "changes_requested", "rejected", "not_analyzed"]
    overall_score: float
    findings: list[ReviewFinding]
    summary: str
    #: Files that no analyzer looked at (e.g. non-Python files, #910). Reported
    #: rather than silently counted as clean.
    files_skipped: list[str] = dataclass_field(default_factory=list)
    #: Analyzers that could not run at all. A non-empty list means the review is
    #: incomplete, and the result is never "approved".
    analyzers_unavailable: list[str] = dataclass_field(default_factory=list)


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
    # Resolved once: containment is checked against the real directory, so a
    # symlinked repo root does not make every candidate look external.
    project_root = Path(project_path).resolve()
    findings: list[ReviewFinding] = []

    # Initialize analyzers
    complexity_analyzer = ComplexityAnalyzer(project_path)
    security_scanner = SecurityScanner(project_path)
    owasp_checker = OWASPPatterns(project_path)

    # Track scores for averaging
    scores: list[float] = []
    # Analyzer name -> why it could not run. Non-empty means the review is
    # incomplete and must never come back "approved" (#910).
    analyzers_unavailable: dict[str, str] = {}
    files_skipped: list[str] = []
    files_analyzed = 0

    for file_path in files:
        # Security: the caller controls this string, so it is confined to the
        # workspace BEFORE anything touches the filesystem (issue #899). An
        # absolute path silently replaces the base in ``/`` and ``../`` walks
        # out, which would let any authenticated principal scan any .py file the
        # server user can read — and read back the literal secret strings the
        # security scanner quotes in its findings. resolve() also collapses
        # symlinks, so a link planted inside the workspace cannot smuggle an
        # outside file in. Same check as core/git.py's commit path.
        #
        # Order matters: rejecting before the exists() probe keeps a real
        # outside file indistinguishable from a missing one.
        #
        # resolve() itself raises on input the OS cannot represent — an embedded
        # NUL (ValueError) or an over-long/looping path (OSError). Those are
        # skipped like any other rejected entry rather than propagating: this
        # call sits outside the per-analyzer try/except below, so an unhandled
        # raise becomes a 500 that discards the whole batch, letting one
        # malformed entry deny review of every legitimate file sent with it.
        try:
            full_path = (project_root / file_path).resolve()
        except (OSError, ValueError):
            logger.warning(f"Malformed path, skipping: {file_path!r}")
            continue

        if not full_path.is_relative_to(project_root):
            logger.warning(f"Path outside workspace, skipping: {file_path}")
            continue

        if not full_path.exists():
            logger.warning(f"File not found: {file_path}")
            # Recorded like any other unexamined file, so the summary's count
            # matches what the caller asked for (#910).
            files_skipped.append(file_path)
            continue

        if full_path.suffix != ".py":
            # No analyzer handles this language yet. Recorded and reported
            # rather than silently dropped: a TypeScript-only change used to
            # fall straight through to score 100 / "approved" (#910).
            files_skipped.append(file_path)
            continue

        files_analyzed += 1

        # Complexity analysis
        try:
            complexity_findings = complexity_analyzer.analyze_file(full_path)
            for finding in complexity_findings:
                findings.append(
                    ReviewFinding(
                        category=finding.category,
                        severity=finding.severity,
                        message=finding.message,
                        file_path=file_path,
                        line_number=finding.line_number,
                        suggestion=finding.suggestion,
                    )
                )
                # Map severity to score for averaging
                severity_scores = {"critical": 20, "high": 40, "medium": 60, "low": 80, "info": 95}
                scores.append(severity_scores.get(finding.severity, 60))
        except Exception as e:
            logger.warning(f"Complexity analysis failed for {file_path}: {e}")

        # Security scan
        try:
            security_findings = security_scanner.analyze_file(full_path)
            for finding in security_findings:
                findings.append(
                    ReviewFinding(
                        category=finding.category,
                        severity=finding.severity,
                        message=finding.message,
                        file_path=file_path,
                        line_number=finding.line_number,
                        suggestion=finding.suggestion,
                    )
                )
                # Security issues have heavier weight on score
                severity_scores = {"critical": 20, "high": 40, "medium": 60, "low": 80, "info": 95}
                scores.append(severity_scores.get(finding.severity, 60))
        except ScannerUnavailableError as exc:
            # The scanner is absent, not clean. Recorded once and reported as a
            # finding so it drags the score and blocks "approved" (#910).
            if "security" not in analyzers_unavailable:
                analyzers_unavailable["security"] = str(exc)
        except Exception as e:
            logger.warning(f"Security scan failed for {file_path}: {e}")

        # OWASP pattern check
        try:
            owasp_findings = owasp_checker.check_file(full_path)
            for finding in owasp_findings:
                findings.append(
                    ReviewFinding(
                        category=finding.category,
                        severity=finding.severity,
                        message=finding.message,
                        file_path=file_path,
                        line_number=finding.line_number,
                        suggestion=finding.suggestion,
                    )
                )
                # OWASP findings are typically high severity
                severity_scores = {"critical": 20, "high": 40, "medium": 60, "low": 80, "info": 95}
                scores.append(severity_scores.get(finding.severity, 40))
        except Exception as e:
            logger.warning(f"OWASP check failed for {file_path}: {e}")

    # An unavailable analyzer becomes a finding of its own, so it is visible in
    # every surface that shows findings, drags the score, and cannot be mistaken
    # for a clean scan (#910).
    for analyzer, reason in analyzers_unavailable.items():
        findings.append(
            ReviewFinding(
                category="tooling",
                severity="high",
                message=f"{analyzer} analysis did not run: {reason}",
                file_path="",
                line_number=0,
                suggestion="Install the missing tool and re-run the review.",
            )
        )
        scores.append(40)  # same weight as any other high-severity finding

    # Calculate overall score
    if scores:
        overall_score = sum(scores) / len(scores)
    else:
        # No issues found = perfect score
        overall_score = 100.0

    if files_analyzed == 0:
        # Nothing was examined — a perfect score here is a lie. This is the
        # TypeScript-only change to a Next.js app that came back "approved"
        # unexamined (#910).
        status: str = "not_analyzed"
        overall_score = 0.0
    else:
        status = _determine_status(overall_score)

    # Generate summary
    parts: list[str] = []
    if findings:
        critical_count = sum(1 for f in findings if f.severity == "critical")
        high_count = sum(1 for f in findings if f.severity == "high")
        parts.append(
            f"Found {len(findings)} issues: {critical_count} critical, "
            f"{high_count} high severity"
        )
    elif files_analyzed:
        parts.append("No issues found. Code looks good!")

    if files_analyzed == 0:
        parts.insert(0, f"No files were analyzed ({len(files_skipped)} skipped)")
    elif files_skipped:
        parts.append(f"{len(files_skipped)} file(s) skipped: no analyzer for this language")

    summary = ". ".join(parts) if parts else "Nothing to review."

    logger.info(f"Review completed: {status} (score: {overall_score:.1f})")

    return ReviewResult(
        status=status,  # type: ignore[arg-type]
        overall_score=round(overall_score, 1),
        findings=findings,
        summary=summary,
        files_skipped=files_skipped,
        analyzers_unavailable=sorted(analyzers_unavailable),
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
    # The id used to be a log line and nothing else (#1066), so this endpoint
    # presented as task-scoped and was not: a stale, wrong or invented id got a
    # confident 200 scoring whatever files_modified the caller also sent.
    from codeframe.core import tasks as _tasks

    if _tasks.get(workspace, task_id) is None:
        raise TaskNotFoundError(f"Task not found: {task_id}")

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
