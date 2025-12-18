"""ReviewWorkerAgent for automated code quality reviews.

Performs automated code reviews using complexity analysis, security scanning,
and OWASP pattern detection.
"""

import logging
from pathlib import Path
from typing import List

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import ReviewReport, ReviewFinding
from codeframe.lib.quality.complexity_analyzer import ComplexityAnalyzer
from codeframe.lib.quality.security_scanner import SecurityScanner
from codeframe.lib.quality.owasp_patterns import OWASPPatterns
from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


class ReviewWorkerAgent(WorkerAgent):
    """Worker agent that performs automated code reviews.

    Review scoring algorithm:
    - Complexity: 30% weight
    - Security: 40% weight (highest priority)
    - Style: 20% weight
    - Coverage: 10% weight

    Decision thresholds:
    - 90-100: Excellent (approve)
    - 70-89: Good (approve with suggestions)
    - 50-69: Needs improvement (request changes, create blocker)
    - 0-49: Poor (reject, create blocker)

    Max review iterations: 2
    """

    # Score thresholds
    EXCELLENT_THRESHOLD = 90
    GOOD_THRESHOLD = 70
    ACCEPTABLE_THRESHOLD = 50

    # Scoring weights
    COMPLEXITY_WEIGHT = 0.3
    SECURITY_WEIGHT = 0.4
    STYLE_WEIGHT = 0.2
    COVERAGE_WEIGHT = 0.1

    # Max re-review iterations
    MAX_ITERATIONS = 2

    def __init__(self, agent_id: str, db: Database, provider: str = "anthropic"):
        """Initialize ReviewWorkerAgent.

        Args:
            agent_id: Unique agent identifier
            db: Database instance
            provider: LLM provider (default: anthropic)
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="review",
            provider=provider,
            db=db,
        )

        # Initialize quality analyzers
        # We'll set the project_path dynamically when executing tasks
        self.complexity_analyzer = None
        self.security_scanner = None
        self.owasp_checker = None

    def _initialize_analyzers(self, project_path: Path):
        """Initialize analyzers with project path.

        Args:
            project_path: Path to project being analyzed
        """
        self.complexity_analyzer = ComplexityAnalyzer(project_path)
        self.security_scanner = SecurityScanner(project_path)
        self.owasp_checker = OWASPPatterns(project_path)

    async def execute_task(self, task: dict) -> ReviewReport:
        """Execute code review task.

        Args:
            task: Task dictionary with id, task_number, title, description, files_modified

        Returns:
            ReviewReport with scores, findings, and decision

        Raises:
            ValueError: If task is malformed
        """
        task_id = task.get("id")
        files_modified = task.get("files_modified", [])

        # Get project_id from task dict or database
        if "project_id" in task:
            project_id = task["project_id"]
        elif self.db and task_id:
            # Fallback: fetch from database
            task_from_db = self.db.get_task(task_id)
            project_id = task_from_db.project_id if task_from_db else None
        else:
            project_id = None

        # Set current_task to establish project context for blocker creation
        if project_id:
            from codeframe.core.models import Task, TaskStatus

            self.current_task = Task(
                id=task_id,
                project_id=project_id,
                task_number=task.get("task_number", ""),
                title=task.get("title", ""),
                description=task.get("description", ""),
                status=TaskStatus.IN_PROGRESS,
            )

        logger.info(f"ReviewWorkerAgent {self.agent_id} reviewing task {task_id}")

        # Handle empty files list
        if not files_modified:
            logger.warning(f"No files to review for task {task_id}")
            return ReviewReport(
                task_id=task_id,
                reviewer_agent_id=self.agent_id,
                overall_score=100.0,  # No code = perfect (or we could use a default)
                complexity_score=100.0,
                security_score=100.0,
                style_score=100.0,
                status="approved",
                findings=[],
                summary="No files to review",
            )

        # Convert file paths
        file_paths = [Path(f) for f in files_modified]

        # Initialize analyzers with project path (use parent of first file)
        if file_paths:
            project_path = file_paths[0].parent
            self._initialize_analyzers(project_path)

        # Run all quality checks
        all_findings = []

        # 1. Complexity analysis
        complexity_score = 100.0
        if self.complexity_analyzer:
            try:
                complexity_score = self.complexity_analyzer.calculate_score(file_paths)
                complexity_findings = self.complexity_analyzer.analyze_files(file_paths)
                all_findings.extend(complexity_findings)
                logger.debug(f"Complexity score: {complexity_score}")
            except Exception as e:
                logger.error(f"Error in complexity analysis: {e}")

        # 2. Security analysis
        security_score = 100.0
        if self.security_scanner:
            try:
                security_score = self.security_scanner.calculate_score(file_paths)
                security_findings = self.security_scanner.analyze_files(file_paths)
                all_findings.extend(security_findings)
                logger.debug(f"Security score: {security_score}")
            except Exception as e:
                logger.error(f"Error in security analysis: {e}")

        # 3. OWASP pattern checking
        if self.owasp_checker:
            try:
                owasp_findings = self.owasp_checker.check_files(file_paths)
                all_findings.extend(owasp_findings)
                # OWASP findings contribute to security score
                if owasp_findings:
                    # Deduct points for OWASP violations
                    owasp_penalty = sum(
                        30 if f.severity == "critical" else 15 if f.severity == "high" else 5
                        for f in owasp_findings
                    )
                    security_score = max(0, security_score - owasp_penalty / len(file_paths))
                logger.debug(f"Security score after OWASP: {security_score}")
            except Exception as e:
                logger.error(f"Error in OWASP checking: {e}")

        # 4. Style analysis (placeholder for now - could integrate ruff/black)
        style_score = 90.0  # Default good style score

        # 5. Coverage analysis (placeholder - would need test coverage data)
        coverage_score = 80.0  # Default acceptable coverage

        # Calculate overall score
        overall_score = self._calculate_overall_score(
            complexity_score, security_score, style_score, coverage_score
        )

        # Determine status based on score
        status = self._determine_status(overall_score, all_findings)

        # Generate summary
        summary = self._generate_summary(overall_score, all_findings, status)

        # Create review report
        report = ReviewReport(
            task_id=task_id,
            reviewer_agent_id=self.agent_id,
            overall_score=overall_score,
            complexity_score=complexity_score,
            security_score=security_score,
            style_score=style_score,
            status=status,
            findings=all_findings,
            summary=summary,
        )

        # Create blocker if needed
        if status in ["changes_requested", "rejected"]:
            await self._create_review_blocker(task_id, report)

        logger.info(f"Review complete: score={overall_score:.1f}, status={status}")

        return report

    def _calculate_overall_score(
        self,
        complexity_score: float,
        security_score: float,
        style_score: float,
        coverage_score: float,
    ) -> float:
        """Calculate weighted overall score.

        Args:
            complexity_score: Complexity score (0-100)
            security_score: Security score (0-100)
            style_score: Style score (0-100)
            coverage_score: Coverage score (0-100)

        Returns:
            Weighted overall score (0-100)
        """
        overall = (
            self.COMPLEXITY_WEIGHT * complexity_score
            + self.SECURITY_WEIGHT * security_score
            + self.STYLE_WEIGHT * style_score
            + self.COVERAGE_WEIGHT * coverage_score
        )

        return round(overall, 1)

    def _determine_status(self, overall_score: float, findings: List[ReviewFinding]) -> str:
        """Determine review status based on score and findings.

        Args:
            overall_score: Overall quality score
            findings: List of all findings

        Returns:
            Status: "approved", "changes_requested", or "rejected"
        """
        # Check for critical findings (always reject)
        has_critical = any(f.severity == "critical" for f in findings)
        if has_critical:
            return "rejected"

        # Score-based decision
        if overall_score >= self.EXCELLENT_THRESHOLD:
            return "approved"
        elif overall_score >= self.GOOD_THRESHOLD:
            return "approved"  # Still approve, but with findings
        elif overall_score >= self.ACCEPTABLE_THRESHOLD:
            return "changes_requested"
        else:
            return "rejected"

    def _generate_summary(
        self, overall_score: float, findings: List[ReviewFinding], status: str
    ) -> str:
        """Generate human-readable review summary.

        Args:
            overall_score: Overall quality score
            findings: List of all findings
            status: Review status

        Returns:
            Summary text
        """
        summary_parts = []

        # Overall assessment
        if status == "approved":
            if overall_score >= self.EXCELLENT_THRESHOLD:
                summary_parts.append(f"Excellent code quality! Score: {overall_score:.1f}/100")
            else:
                summary_parts.append(
                    f"Good code quality with minor improvements possible. Score: {overall_score:.1f}/100"
                )
        elif status == "changes_requested":
            summary_parts.append(f"Code needs improvements. Score: {overall_score:.1f}/100")
        else:  # rejected
            summary_parts.append(
                f"Code has significant quality issues. Score: {overall_score:.1f}/100"
            )

        # Findings summary
        if findings:
            critical_count = sum(1 for f in findings if f.severity == "critical")
            high_count = sum(1 for f in findings if f.severity == "high")
            medium_count = sum(1 for f in findings if f.severity == "medium")

            findings_summary = []
            if critical_count:
                findings_summary.append(f"{critical_count} critical")
            if high_count:
                findings_summary.append(f"{high_count} high")
            if medium_count:
                findings_summary.append(f"{medium_count} medium")

            if findings_summary:
                summary_parts.append(f"Found {len(findings)} issues: {', '.join(findings_summary)}")

        # Action items
        if status == "changes_requested":
            summary_parts.append("Please address the findings and re-submit for review.")
        elif status == "rejected":
            summary_parts.append("Critical issues must be fixed before this code can be merged.")

        return " ".join(summary_parts)

    async def _create_review_blocker(self, task_id: int, report: ReviewReport):
        """Create a SYNC blocker for review failures.

        Args:
            task_id: Task ID
            report: ReviewReport with findings
        """
        blocker_message = report.to_blocker_message()

        # Get project_id from current_task
        project_id = (
            self.current_task.project_id
            if hasattr(self, "current_task") and self.current_task
            else None
        )
        if not project_id:
            logger.error("Cannot create review blocker without project context")
            return

        try:
            self.db.create_blocker(
                agent_id=self.agent_id,
                project_id=project_id,
                task_id=task_id,
                blocker_type="SYNC",
                question=f"Code Review Failed: {report.status.replace('_', ' ').title()}\n\n{blocker_message}",
            )
            logger.info(f"Created review blocker for task {task_id}")
        except Exception as e:
            logger.error(f"Error creating review blocker: {e}")
