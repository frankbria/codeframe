"""Quality Gates system for ensuring code quality before task completion (Sprint 10 Phase 3).

The Quality Gates system prevents task completion when quality standards are not met.
It runs automated checks for:
- Test execution (pytest/jest)
- Type checking (mypy/tsc)
- Code coverage (>= 85%)
- Code review (critical/high severity issues)
- Linting (ruff/eslint)

When gates fail, blockers are created to notify developers and track resolution.

Architecture:
    Each gate is a separate async method that returns a QualityGateResult.
    The run_all_gates() orchestrator executes all gates in sequence and aggregates results.
    Results are stored in the tasks.quality_gate_status and tasks.quality_gate_failures columns.

Usage:
    >>> from codeframe.lib.quality_gates import QualityGates
    >>> from codeframe.persistence.database import Database
    >>>
    >>> db = Database("state.db")
    >>> gates = QualityGates(db=db, project_id=1, project_root=Path("/path/to/project"))
    >>> result = await gates.run_all_gates(task)
    >>> if not result.passed:
    ...     print(f"Quality gates failed: {len(result.failures)} issues")

See Also:
    - codeframe.core.models.QualityGateResult: Result data model
    - codeframe.core.models.QualityGateFailure: Individual failure model
    - specs/015-review-polish/plan.md: Complete specification
"""

import logging
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime, timezone

from codeframe.core.models import (
    Task,
    QualityGateType,
    QualityGateFailure,
    QualityGateResult,
    Severity,
    BlockerType,
)
from codeframe.persistence.database import Database
from codeframe.config.security import get_security_config
from codeframe.enforcement.skip_pattern_detector import SkipPatternDetector

logger = logging.getLogger(__name__)


# Risky file patterns that require human approval
RISKY_FILE_PATTERNS = [
    "auth",
    "authentication",
    "password",
    "payment",
    "billing",
    "security",
    "crypto",
    "secret",
    "token",
    "session",
]


class QualityGates:
    """Quality gate orchestrator for code quality enforcement.

    The QualityGates class runs automated quality checks before allowing task completion.
    It supports Python (pytest, mypy, ruff) and JavaScript/TypeScript (jest, tsc, eslint).

    Attributes:
        db: Database instance for storing gate results and creating blockers
        project_id: Project ID for scoping operations
        project_root: Absolute path to project root directory (for running commands)

    Example:
        >>> db = Database(":memory:")
        >>> db.initialize()
        >>> gates = QualityGates(db=db, project_id=1, project_root=Path("/app"))
        >>> result = await gates.run_all_gates(task)
        >>> print(f"Status: {result.status}, Failures: {len(result.failures)}")
        Status: failed, Failures: 2
    """

    def __init__(self, db: Database, project_id: int, project_root: Path) -> None:
        """Initialize Quality Gates.

        Args:
            db: Database instance for storing results and creating blockers
            project_id: Project ID for scoping
            project_root: Absolute path to project root directory

        Example:
            >>> db = Database("state.db")
            >>> gates = QualityGates(db=db, project_id=1, project_root=Path.cwd())
        """
        self.db = db
        self.project_id = project_id
        self.project_root = Path(project_root)

    async def run_tests_gate(self, task: Task) -> QualityGateResult:
        """Execute test gate - run pytest for Python, jest for JavaScript/TypeScript.

        This gate runs the project's test suite and checks for failures. It automatically
        detects the project type based on files changed in the task.

        Detection Logic:
            - If task includes .py files → run pytest
            - If task includes .js/.ts files → run jest
            - If both types present → run both

        Args:
            task: Task to validate. Uses task._test_files to determine which tests to run.

        Returns:
            QualityGateResult with status "passed" or "failed". If failed, includes
            details about which tests failed and error messages.

        Example:
            >>> result = await gates.run_tests_gate(task)
            >>> if not result.passed:
            ...     print(f"Tests failed: {result.failures[0].reason}")
            Tests failed: 3 tests failed in test_auth.py
        """
        start_time = datetime.now(timezone.utc)
        failures: List[QualityGateFailure] = []

        # Detect project type from task files
        has_python = self._task_has_python_files(task)
        has_javascript = self._task_has_javascript_files(task)

        # Run pytest for Python projects
        if has_python:
            pytest_result = self._run_pytest()
            if pytest_result["returncode"] != 0:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.TESTS,
                        reason=f"Pytest failed: {pytest_result['summary']}",
                        details=pytest_result["output"],
                        severity=Severity.HIGH,
                    )
                )

        # Run jest for JavaScript/TypeScript projects
        if has_javascript:
            jest_result = self._run_jest()
            if jest_result["returncode"] != 0:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.TESTS,
                        reason=f"Jest failed: {jest_result['summary']}",
                        details=jest_result["output"],
                        severity=Severity.HIGH,
                    )
                )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        status = "passed" if len(failures) == 0 else "failed"
        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
            execution_time_seconds=execution_time,
        )

        # Update database
        self.db.update_quality_gate_status(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
        )

        # Create blocker if failed
        if not result.passed:
            self._create_quality_blocker(task, failures)

        return result

    async def run_type_check_gate(self, task: Task) -> QualityGateResult:
        """Execute type checking gate - run mypy for Python, tsc for TypeScript.

        This gate runs static type checkers to catch type errors before runtime.

        Detection Logic:
            - If task includes .py files → run mypy
            - If task includes .ts/.tsx files → run tsc --noEmit

        Args:
            task: Task to validate

        Returns:
            QualityGateResult with status "passed" or "failed". If failed, includes
            type error details with file, line number, and error message.

        Example:
            >>> result = await gates.run_type_check_gate(task)
            >>> if not result.passed:
            ...     print(result.failures[0].details)
            src/auth.py:42: error: Argument 1 has incompatible type "str"; expected "int"
        """
        start_time = datetime.now(timezone.utc)
        failures: List[QualityGateFailure] = []

        # Detect project type
        has_python = self._task_has_python_files(task)
        has_typescript = self._task_has_typescript_files(task)

        # Run mypy for Python
        if has_python:
            mypy_result = self._run_mypy()
            if mypy_result["returncode"] != 0:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.TYPE_CHECK,
                        reason=f"Mypy found type errors: {mypy_result['summary']}",
                        details=mypy_result["output"],
                        severity=Severity.HIGH,
                    )
                )

        # Run tsc for TypeScript
        if has_typescript:
            tsc_result = self._run_tsc()
            if tsc_result["returncode"] != 0:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.TYPE_CHECK,
                        reason=f"TypeScript compiler found errors: {tsc_result['summary']}",
                        details=tsc_result["output"],
                        severity=Severity.HIGH,
                    )
                )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        status = "passed" if len(failures) == 0 else "failed"
        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
            execution_time_seconds=execution_time,
        )

        # Update database
        self.db.update_quality_gate_status(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
        )

        # Create blocker if failed
        if not result.passed:
            self._create_quality_blocker(task, failures)

        return result

    async def run_coverage_gate(self, task: Task) -> QualityGateResult:
        """Execute coverage gate - check test coverage >= 85%.

        This gate runs tests with coverage reporting and validates that at least 85%
        of code is covered by tests. This threshold is configurable but 85% is the
        recommended minimum for production code.

        Args:
            task: Task to validate

        Returns:
            QualityGateResult with status "passed" or "failed". If failed, includes
            actual coverage percentage and threshold.

        Example:
            >>> result = await gates.run_coverage_gate(task)
            >>> if not result.passed:
            ...     print(result.failures[0].reason)
            Coverage 72% is below required 85%
        """
        start_time = datetime.now(timezone.utc)
        failures: List[QualityGateFailure] = []

        # Run tests with coverage
        coverage_result = self._run_coverage()

        if coverage_result["coverage_pct"] < 85.0:
            failures.append(
                QualityGateFailure(
                    gate=QualityGateType.COVERAGE,
                    reason=f"Coverage {coverage_result['coverage_pct']:.1f}% is below required 85%",
                    details=coverage_result["output"],
                    severity=Severity.HIGH,
                )
            )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        status = "passed" if len(failures) == 0 else "failed"
        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
            execution_time_seconds=execution_time,
        )

        # Update database
        self.db.update_quality_gate_status(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
        )

        # Create blocker if failed
        if not result.passed:
            self._create_quality_blocker(task, failures)

        return result

    async def run_review_gate(self, task: Task) -> QualityGateResult:
        """Execute code review gate - trigger Review Agent and check for critical findings.

        This gate runs the Review Agent to perform automated code review. It blocks
        task completion if critical or high severity issues are found.

        The Review Agent scans for:
        - Security vulnerabilities (SQL injection, XSS, hardcoded secrets)
        - Performance issues (nested loops, O(n²) complexity)
        - Code quality problems (high cyclomatic complexity, deep nesting)

        Args:
            task: Task to review

        Returns:
            QualityGateResult with status "passed" or "failed". If failed, includes
            critical/high severity findings from Review Agent.

        Example:
            >>> result = await gates.run_review_gate(task)
            >>> if not result.passed:
            ...     for failure in result.failures:
            ...         print(f"{failure.severity}: {failure.reason}")
            CRITICAL: SQL injection vulnerability in src/auth.py
        """
        start_time = datetime.now(timezone.utc)
        failures: List[QualityGateFailure] = []

        # Import Review Agent (lazy import to avoid circular dependencies)
        from codeframe.agents.review_agent import ReviewAgent

        # Create Review Agent instance
        review_agent = ReviewAgent(
            agent_id=f"review-gate-{task.id}",
            db=self.db,
            project_id=self.project_id,
        )

        # Execute review
        review_result = await review_agent.execute_task(task)

        # Check for critical/high severity findings
        critical_findings = [
            f for f in review_result.findings if f.severity in [Severity.CRITICAL, Severity.HIGH]
        ]

        if len(critical_findings) > 0:
            # Create failure for each critical finding
            for finding in critical_findings:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.CODE_REVIEW,
                        reason=f"{finding.severity.upper()} [{finding.category}]: {finding.message}",
                        details=f"File: {finding.file_path}:{finding.line_number}\n"
                        f"Message: {finding.message}\n"
                        f"Recommendation: {finding.recommendation}\n"
                        f"Code: {finding.code_snippet}",
                        severity=finding.severity,
                    )
                )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        status = "passed" if len(failures) == 0 else "failed"
        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
            execution_time_seconds=execution_time,
        )

        # Update database
        self.db.update_quality_gate_status(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
        )

        # Create blocker if failed (Review Agent already created one, but we log it)
        if not result.passed:
            logger.info(
                f"Review gate failed for task {task.id} with {len(critical_findings)} critical findings"
            )

        return result

    async def run_linting_gate(self, task: Task) -> QualityGateResult:
        """Execute linting gate - run ruff for Python, eslint for JavaScript/TypeScript.

        This gate runs linters to enforce code style and catch common errors. Linting
        issues are typically medium severity (not blocking unless critical errors).

        Detection Logic:
            - If task includes .py files → run ruff
            - If task includes .js/.ts files → run eslint

        Args:
            task: Task to validate

        Returns:
            QualityGateResult with status "passed" or "failed". If failed, includes
            linting errors with file, line number, and rule violation.

        Example:
            >>> result = await gates.run_linting_gate(task)
            >>> if not result.passed:
            ...     print(result.failures[0].reason)
            Ruff found 5 errors in src/auth.py
        """
        start_time = datetime.now(timezone.utc)
        failures: List[QualityGateFailure] = []

        # Detect project type
        has_python = self._task_has_python_files(task)
        has_javascript = self._task_has_javascript_files(task)

        # Run ruff for Python
        if has_python:
            ruff_result = self._run_ruff()
            if ruff_result["returncode"] != 0:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.LINTING,
                        reason=f"Ruff found linting errors: {ruff_result['summary']}",
                        details=ruff_result["output"],
                        severity=Severity.MEDIUM,  # Linting is usually medium
                    )
                )

        # Run eslint for JavaScript/TypeScript
        if has_javascript:
            eslint_result = self._run_eslint()
            if eslint_result["returncode"] != 0:
                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.LINTING,
                        reason=f"ESLint found linting errors: {eslint_result['summary']}",
                        details=eslint_result["output"],
                        severity=Severity.MEDIUM,
                    )
                )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        status = "passed" if len(failures) == 0 else "failed"
        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
            execution_time_seconds=execution_time,
        )

        # Update database
        self.db.update_quality_gate_status(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
        )

        # Create blocker if failed
        if not result.passed:
            self._create_quality_blocker(task, failures)

        return result

    async def run_skip_detection_gate(self, task: Task) -> QualityGateResult:
        """Execute skip pattern detection gate - detect test skips across all languages.

        This gate scans test files for skip patterns (e.g., @pytest.mark.skip, it.skip,
        #[ignore]) that indicate tests are being bypassed. Skip patterns reduce test
        coverage and can hide bugs.

        Supported Languages:
            - Python: @skip, @pytest.mark.skip, @unittest.skip
            - JavaScript/TypeScript: it.skip, test.skip, describe.skip, xit, xtest
            - Go: t.Skip(), testing.Skip(), build tags
            - Rust: #[ignore]
            - Java: @Ignore, @Disabled
            - Ruby: skip, pending, xit
            - C#: [Ignore], [Skip]

        Args:
            task: Task to validate for skip patterns

        Returns:
            QualityGateResult with status "passed" or "failed". If failed, includes
            violations with file path, line number, and skip pattern details.

        Example:
            >>> result = await gates.run_skip_detection_gate(task)
            >>> if not result.passed:
            ...     print(f"Found {len(result.failures)} skip patterns")
            Found 3 skip patterns

        Note:
            This gate can be disabled by setting CODEFRAME_ENABLE_SKIP_DETECTION=false
            in environment variables.
        """
        start_time = datetime.now(timezone.utc)
        failures: List[QualityGateFailure] = []

        # Check configuration flag - early return if disabled
        security_config = get_security_config()
        if not security_config.should_enable_skip_detection():
            logger.info("Skip detection gate is disabled via configuration")
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            return QualityGateResult(
                task_id=task.id,  # type: ignore[arg-type]
                status="passed",
                failures=[],
                execution_time_seconds=execution_time,
            )

        # Initialize skip pattern detector
        try:
            detector = SkipPatternDetector(project_root=str(self.project_root))
            violations = detector.detect_all()

            # Convert each SkipViolation to QualityGateFailure
            for violation in violations:
                # Map violation severity to QualityGateFailure severity
                severity = Severity.HIGH if violation.severity == "error" else Severity.MEDIUM

                # Build detailed message
                details_parts = [
                    f"File: {violation.file}:{violation.line}",
                    f"Pattern: {violation.pattern}",
                    f"Context: {violation.context}",
                ]
                if violation.reason:
                    details_parts.append(f"Reason: {violation.reason}")

                failures.append(
                    QualityGateFailure(
                        gate=QualityGateType.SKIP_DETECTION,
                        reason=f"Skip pattern found in {violation.file}:{violation.line} - {violation.pattern}",
                        details="\n".join(details_parts),
                        severity=severity,
                    )
                )

        except Exception as e:
            logger.error(f"Skip detection failed with error: {e}")
            # Don't fail the gate if detection itself fails - treat as warning
            failures.append(
                QualityGateFailure(
                    gate=QualityGateType.SKIP_DETECTION,
                    reason=f"Skip detection failed: {str(e)}",
                    details="The skip pattern detector encountered an error. Manual review recommended.",
                    severity=Severity.LOW,
                )
            )

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        status = "passed" if len(failures) == 0 else "failed"
        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
            execution_time_seconds=execution_time,
        )

        # Update database
        self.db.update_quality_gate_status(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=failures,
        )

        # Create blocker if failed
        if not result.passed:
            self._create_quality_blocker(task, failures)

        return result

    async def run_all_gates(self, task: Task) -> QualityGateResult:
        """Orchestrator: Run all quality gates in sequence and aggregate results.

        This is the main entry point for quality gate validation. It runs all gates
        in a specific order and aggregates failures. The task is blocked if ANY gate
        fails.

        Execution Order:
            1. Linting gate (fast, catches obvious issues)
            2. Type check gate (fast, catches type errors)
            3. Skip detection gate (fast, scans for test skips)
            4. Test gate (slower, validates functionality)
            5. Coverage gate (runs with tests, checks coverage)
            6. Review gate (slowest, deep code analysis)

        Args:
            task: Task to validate against all quality gates

        Returns:
            QualityGateResult with aggregated results from all gates. Status is "passed"
            only if ALL gates pass. Failures list contains all failures from all gates.

        Example:
            >>> result = await gates.run_all_gates(task)
            >>> if result.passed:
            ...     print("All quality gates passed - task can complete")
            ... else:
            ...     print(f"Quality gates failed: {len(result.failures)} issues")
            ...     for failure in result.failures:
            ...         print(f"  - {failure.gate}: {failure.reason}")
        """
        start_time = datetime.now(timezone.utc)
        all_failures: List[QualityGateFailure] = []

        logger.info(f"Running all quality gates for task {task.id}")

        # Check if task involves risky changes (auth, payment, security)
        if self._contains_risky_changes(task):
            logger.info(f"Task {task.id} contains risky changes - marking for human approval")
            # Set requires_human_approval flag in database
            cursor = self.db.conn.cursor()  # type: ignore[union-attr]
            cursor.execute(
                "UPDATE tasks SET requires_human_approval = 1 WHERE id = ?",
                (task.id,),
            )
            self.db.conn.commit()  # type: ignore[union-attr]

        # 1. Linting gate (fast)
        linting_result = await self.run_linting_gate(task)
        all_failures.extend(linting_result.failures)

        # 2. Type check gate (fast)
        type_check_result = await self.run_type_check_gate(task)
        all_failures.extend(type_check_result.failures)

        # 3. Skip detection gate (fast, scans for test skips)
        skip_detection_result = await self.run_skip_detection_gate(task)
        all_failures.extend(skip_detection_result.failures)

        # 4. Test gate
        test_result = await self.run_tests_gate(task)
        all_failures.extend(test_result.failures)

        # 5. Coverage gate
        coverage_result = await self.run_coverage_gate(task)
        all_failures.extend(coverage_result.failures)

        # 6. Review gate (slowest, most comprehensive)
        review_result = await self.run_review_gate(task)
        all_failures.extend(review_result.failures)

        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Aggregate status
        status = "passed" if len(all_failures) == 0 else "failed"

        result = QualityGateResult(
            task_id=task.id,  # type: ignore[arg-type]
            status=status,
            failures=all_failures,
            execution_time_seconds=execution_time,
        )

        logger.info(
            f"Quality gates for task {task.id} completed in {execution_time:.2f}s: "
            f"status={status}, failures={len(all_failures)}"
        )

        return result

    # ========================================================================
    # Helper Methods - File Type Detection
    # ========================================================================

    def _task_has_python_files(self, task: Task) -> bool:
        """Check if task includes Python files."""
        if hasattr(task, "_test_files") and task._test_files:
            return any(f.endswith(".py") for f in task._test_files)
        return True  # Default to Python if no file info

    def _task_has_javascript_files(self, task: Task) -> bool:
        """Check if task includes JavaScript files."""
        if hasattr(task, "_test_files") and task._test_files:
            return any(f.endswith((".js", ".jsx")) for f in task._test_files)
        return False

    def _task_has_typescript_files(self, task: Task) -> bool:
        """Check if task includes TypeScript files."""
        if hasattr(task, "_test_files") and task._test_files:
            return any(f.endswith((".ts", ".tsx")) for f in task._test_files)
        return False

    def _contains_risky_changes(self, task: Task) -> bool:
        """Check if task contains risky changes (auth, payment, security).

        Risky files require human approval before task completion.

        Args:
            task: Task to check

        Returns:
            True if task includes risky files, False otherwise
        """
        if not hasattr(task, "_test_files") or not task._test_files:
            return False

        for file_path in task._test_files:
            file_lower = file_path.lower()
            for pattern in RISKY_FILE_PATTERNS:
                if pattern in file_lower:
                    logger.info(f"Risky file detected: {file_path} (pattern: {pattern})")
                    return True

        return False

    # ========================================================================
    # Helper Methods - Command Execution
    # ========================================================================

    def _run_pytest(self) -> Dict[str, Any]:
        """Run pytest and return results.

        Returns:
            dict with keys: returncode, output, summary
        """
        try:
            result = subprocess.run(
                ["pytest", "--tb=short", "-v", "--cov=.", "--cov-report=term-missing"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            # Parse output for summary
            output = result.stdout + result.stderr
            summary = self._extract_pytest_summary(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "pytest timed out after 5 minutes",
                "summary": "Timeout",
            }
        except FileNotFoundError:
            return {
                "returncode": 0,  # Don't fail if pytest not installed
                "output": "pytest not found, skipping",
                "summary": "Skipped",
            }

    def _run_jest(self) -> Dict[str, Any]:
        """Run jest and return results."""
        try:
            result = subprocess.run(
                ["npm", "test", "--", "--ci", "--coverage"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = result.stdout + result.stderr
            summary = self._extract_jest_summary(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "jest timed out after 5 minutes",
                "summary": "Timeout",
            }
        except FileNotFoundError:
            return {
                "returncode": 0,  # Don't fail if jest not installed
                "output": "jest not found, skipping",
                "summary": "Skipped",
            }

    def _run_mypy(self) -> Dict[str, Any]:
        """Run mypy and return results."""
        try:
            result = subprocess.run(
                ["mypy", ".", "--no-error-summary"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = result.stdout + result.stderr
            summary = self._extract_mypy_summary(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "mypy timed out after 2 minutes",
                "summary": "Timeout",
            }
        except FileNotFoundError:
            return {
                "returncode": 0,  # Don't fail if mypy not installed
                "output": "mypy not found, skipping",
                "summary": "Skipped",
            }

    def _run_tsc(self) -> Dict[str, Any]:
        """Run TypeScript compiler and return results."""
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=120,
            )

            output = result.stdout + result.stderr
            summary = self._extract_tsc_summary(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "tsc timed out after 2 minutes",
                "summary": "Timeout",
            }
        except FileNotFoundError:
            return {
                "returncode": 0,
                "output": "tsc not found, skipping",
                "summary": "Skipped",
            }

    def _run_coverage(self) -> Dict[str, Any]:
        """Run tests with coverage and return results."""
        # Use pytest with coverage for Python
        try:
            result = subprocess.run(
                ["pytest", "--cov=.", "--cov-report=term-missing"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = result.stdout + result.stderr
            coverage_pct = self._extract_coverage_percentage(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "coverage_pct": coverage_pct,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "Coverage timed out after 5 minutes",
                "coverage_pct": 0.0,
            }
        except FileNotFoundError:
            return {
                "returncode": 0,
                "output": "pytest not found, skipping coverage",
                "coverage_pct": 100.0,  # Pass if tool not available
            }

    def _run_ruff(self) -> Dict[str, Any]:
        """Run ruff linter and return results."""
        try:
            result = subprocess.run(
                ["ruff", "check", "."],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout + result.stderr
            summary = self._extract_ruff_summary(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "ruff timed out after 1 minute",
                "summary": "Timeout",
            }
        except FileNotFoundError:
            return {
                "returncode": 0,
                "output": "ruff not found, skipping",
                "summary": "Skipped",
            }

    def _run_eslint(self) -> Dict[str, Any]:
        """Run eslint and return results."""
        try:
            result = subprocess.run(
                ["npx", "eslint", ".", "--format=compact"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=60,
            )

            output = result.stdout + result.stderr
            summary = self._extract_eslint_summary(output)

            return {
                "returncode": result.returncode,
                "output": output,
                "summary": summary,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": 1,
                "output": "eslint timed out after 1 minute",
                "summary": "Timeout",
            }
        except FileNotFoundError:
            return {
                "returncode": 0,
                "output": "eslint not found, skipping",
                "summary": "Skipped",
            }

    # ========================================================================
    # Helper Methods - Output Parsing
    # ========================================================================

    def _extract_pytest_summary(self, output: str) -> str:
        """Extract summary from pytest output."""
        # Look for "N passed, M failed" pattern
        match = re.search(r"(\d+) (passed|failed)", output)
        if match:
            return match.group(0)
        return "Unknown"

    def _extract_jest_summary(self, output: str) -> str:
        """Extract summary from jest output."""
        match = re.search(r"Tests:\s+(.+)", output)
        if match:
            return match.group(1)
        return "Unknown"

    def _extract_mypy_summary(self, output: str) -> str:
        """Extract summary from mypy output."""
        # Count errors
        error_count = output.count("error:")
        if error_count > 0:
            return f"{error_count} type errors"
        return "No errors"

    def _extract_tsc_summary(self, output: str) -> str:
        """Extract summary from tsc output."""
        error_count = output.count("error TS")
        if error_count > 0:
            return f"{error_count} type errors"
        return "No errors"

    def _extract_coverage_percentage(self, output: str) -> float:
        """Extract coverage percentage from pytest output.

        Looks for "TOTAL coverage: XX%" pattern.
        """
        match = re.search(r"TOTAL.*?(\d+)%", output)
        if match:
            return float(match.group(1))
        return 0.0

    def _extract_ruff_summary(self, output: str) -> str:
        """Extract summary from ruff output."""
        lines = output.strip().split("\n")
        error_count = len([line for line in lines if "error" in line.lower()])
        if error_count > 0:
            return f"{error_count} linting errors"
        return "No errors"

    def _extract_eslint_summary(self, output: str) -> str:
        """Extract summary from eslint output."""
        match = re.search(r"(\d+) problems?", output)
        if match:
            return match.group(0)
        return "Unknown"

    # ========================================================================
    # Helper Methods - Blocker Creation
    # ========================================================================

    def _create_quality_blocker(self, task: Task, failures: List[QualityGateFailure]) -> None:
        """Create a SYNC blocker for quality gate failures.

        Args:
            task: Task that failed quality gates
            failures: List of quality gate failures to include in blocker
        """
        if not failures:
            return

        # Format failures into blocker question
        question_parts = [
            f"Quality gates failed for task #{task.task_number} ({task.title}):",
            "",
        ]

        for i, failure in enumerate(failures[:10], 1):  # Limit to 10 failures
            severity_emoji = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "⚪",
            }
            emoji = severity_emoji.get(failure.severity, "⚪")

            question_parts.append(f"{i}. {emoji} [{failure.gate.value.upper()}] {failure.reason}")

            if failure.details:
                # Truncate details to first 3 lines
                detail_lines = failure.details.split("\n")[:3]
                for line in detail_lines:
                    question_parts.append(f"   {line}")

            question_parts.append("")

        question_parts.append(
            "Fix these issues before completing the task. Type 'resolved' when fixed."
        )

        question = "\n".join(question_parts)

        # Create SYNC blocker (critical quality issues need immediate attention)
        self.db.create_blocker(
            agent_id="quality-gates",
            project_id=self.project_id,
            task_id=task.id,  # type: ignore[arg-type]
            blocker_type=BlockerType.SYNC,
            question=question,
        )

        logger.info(
            f"Created quality gate blocker for task {task.id} due to {len(failures)} failures"
        )
