"""
Evidence Verifier

Validates that AI agents provide proper evidence before claiming tasks are complete.
Works with ANY language - adapts to the project being worked on.

Evidence required:
1. Test execution output
2. Coverage report (if applicable)
3. Skip pattern check results
4. Quality metrics

This prevents agents from claiming "tests pass" without proof.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime

from .adaptive_test_runner import TestResult
from .skip_pattern_detector import SkipViolation
from .quality_tracker import QualityMetrics


@dataclass
class Evidence:
    """
    Complete evidence package from an AI agent.

    This is what agents must provide before claiming a task is complete.
    """

    # Test results
    test_result: TestResult
    test_output: str  # Full test output for verification

    # Skip pattern check
    skip_violations: List[SkipViolation]
    skip_check_passed: bool

    # Quality metrics
    quality_metrics: QualityMetrics

    # Metadata
    timestamp: str
    language: str
    framework: Optional[str]
    agent_id: str
    task_description: str

    # Verification status
    verified: bool = False
    verification_errors: List[str] = None


class EvidenceVerifier:
    """
    Verifies evidence provided by AI agents.

    Usage:
        verifier = EvidenceVerifier()

        # Collect evidence
        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=skip_violations,
            language="python",
            agent_id="worker-001",
            task="Implement user authentication"
        )

        # Verify evidence
        is_valid = verifier.verify(evidence)

        if is_valid:
            print("✓ Evidence validated - task complete")
        else:
            print("✗ Evidence insufficient:")
            for error in evidence.verification_errors:
                print(f"  - {error}")
    """

    def __init__(
        self,
        require_coverage: bool = True,
        min_coverage: float = 85.0,
        allow_skipped_tests: bool = False,
        min_pass_rate: float = 100.0,
    ):
        """
        Initialize verifier with requirements.

        Args:
            require_coverage: Whether coverage is required
            min_coverage: Minimum coverage percentage (default: 85%)
            allow_skipped_tests: Whether skipped tests are allowed
            min_pass_rate: Minimum test pass rate (default: 100%)
        """
        self.require_coverage = require_coverage
        self.min_coverage = min_coverage
        self.allow_skipped_tests = allow_skipped_tests
        self.min_pass_rate = min_pass_rate

    def collect_evidence(
        self,
        test_result: TestResult,
        skip_violations: List[SkipViolation],
        language: str,
        agent_id: str,
        task_description: str,
        framework: Optional[str] = None,
    ) -> Evidence:
        """
        Collect evidence from various sources into a single package.

        Args:
            test_result: Results from running tests
            skip_violations: List of skip pattern violations
            language: Programming language
            agent_id: Identifier for the agent
            task_description: Description of task being completed
            framework: Test framework (optional)

        Returns:
            Evidence object
        """
        # Create quality metrics from test result
        quality_metrics = QualityMetrics(
            timestamp=datetime.now().isoformat(),
            response_count=0,  # Will be set by tracker
            test_pass_rate=test_result.pass_rate,
            coverage_percentage=test_result.coverage or 0.0,
            total_tests=test_result.total_tests,
            passed_tests=test_result.passed_tests,
            failed_tests=test_result.failed_tests,
            language=language,
            framework=framework,
        )

        evidence = Evidence(
            test_result=test_result,
            test_output=test_result.output,
            skip_violations=skip_violations,
            skip_check_passed=len(skip_violations) == 0,
            quality_metrics=quality_metrics,
            timestamp=datetime.now().isoformat(),
            language=language,
            framework=framework,
            agent_id=agent_id,
            task_description=task_description,
            verification_errors=[],
        )

        return evidence

    def verify(self, evidence: Evidence) -> bool:
        """
        Verify that evidence meets requirements.

        Args:
            evidence: Evidence to verify

        Returns:
            True if evidence is valid, False otherwise
        """
        errors = []

        # Check 1: Tests must pass
        if not evidence.test_result.success:
            errors.append(f"Tests failed: {evidence.test_result.failed_tests} failures")

        # Check 2: Pass rate must meet threshold
        if evidence.test_result.pass_rate < self.min_pass_rate:
            errors.append(
                f"Pass rate too low: {evidence.test_result.pass_rate:.1f}% "
                f"(minimum: {self.min_pass_rate:.1f}%)"
            )

        # Check 3: Coverage must meet threshold (if required)
        if self.require_coverage:
            coverage = evidence.test_result.coverage
            if coverage is None:
                errors.append("Coverage data missing (required)")
            elif coverage < self.min_coverage:
                errors.append(
                    f"Coverage too low: {coverage:.1f}% " f"(minimum: {self.min_coverage:.1f}%)"
                )

        # Check 4: No skip violations (unless allowed)
        if not self.allow_skipped_tests and not evidence.skip_check_passed:
            errors.append(f"Skip violations detected: {len(evidence.skip_violations)} violations")

        # Check 5: Must have test output
        if not evidence.test_output or len(evidence.test_output) < 10:
            errors.append("Test output missing or too short")

        # Check 6: No skipped tests in test results
        if not self.allow_skipped_tests and evidence.test_result.skipped_tests > 0:
            errors.append(
                f"Skipped tests detected: {evidence.test_result.skipped_tests} tests skipped"
            )

        # Update evidence
        evidence.verification_errors = errors
        evidence.verified = len(errors) == 0

        return evidence.verified

    def generate_report(self, evidence: Evidence) -> str:
        """
        Generate a human-readable verification report.

        Args:
            evidence: Evidence to report on

        Returns:
            Formatted report string
        """
        report_lines = [
            "=" * 70,
            "  EVIDENCE VERIFICATION REPORT",
            "=" * 70,
            "",
            f"Agent ID: {evidence.agent_id}",
            f"Task: {evidence.task_description}",
            f"Language: {evidence.language}",
            f"Framework: {evidence.framework or 'N/A'}",
            f"Timestamp: {evidence.timestamp}",
            "",
            "Test Results:",
            f"  • Total tests: {evidence.test_result.total_tests}",
            f"  • Passed: {evidence.test_result.passed_tests}",
            f"  • Failed: {evidence.test_result.failed_tests}",
            f"  • Skipped: {evidence.test_result.skipped_tests}",
            f"  • Pass rate: {evidence.test_result.pass_rate:.1f}%",
            "",
        ]

        if evidence.test_result.coverage is not None:
            report_lines.extend(
                [
                    "Coverage:",
                    f"  • Coverage: {evidence.test_result.coverage:.1f}%",
                    f"  • Threshold: {self.min_coverage:.1f}%",
                    f"  • Status: {'✓ PASS' if evidence.test_result.coverage >= self.min_coverage else '✗ FAIL'}",
                    "",
                ]
            )

        report_lines.extend(
            [
                "Skip Pattern Check:",
                f"  • Violations found: {len(evidence.skip_violations)}",
                f"  • Status: {'✓ PASS' if evidence.skip_check_passed else '✗ FAIL'}",
                "",
            ]
        )

        if evidence.skip_violations:
            report_lines.append("  Skip violations:")
            for v in evidence.skip_violations[:5]:  # Show first 5
                report_lines.append(f"    - {v.file}:{v.line} - {v.pattern}")
            if len(evidence.skip_violations) > 5:
                report_lines.append(f"    ... and {len(evidence.skip_violations) - 5} more")
            report_lines.append("")

        report_lines.extend(
            [
                "=" * 70,
                f"VERIFICATION RESULT: {'✓ PASSED' if evidence.verified else '✗ FAILED'}",
                "=" * 70,
            ]
        )

        if not evidence.verified:
            report_lines.extend(
                [
                    "",
                    "Errors:",
                ]
            )
            for error in evidence.verification_errors:
                report_lines.append(f"  ✗ {error}")

        report_lines.append("")

        return "\n".join(report_lines)

    def validate_claim(
        self,
        claim: str,
        evidence: Evidence,
    ) -> Dict:
        """
        Validate an agent's claim against provided evidence.

        Args:
            claim: What the agent is claiming (e.g., "tests pass")
            evidence: Evidence provided

        Returns:
            Dict with valid, claim, evidence_supports, discrepancies
        """
        claim_lower = claim.lower()

        # Parse claim
        claims_tests_pass = "test" in claim_lower and (
            "pass" in claim_lower or "passing" in claim_lower
        )
        claims_coverage = "coverage" in claim_lower
        claims_complete = "complete" in claim_lower or "done" in claim_lower

        discrepancies = []

        # Check test passing claim
        if claims_tests_pass:
            if not evidence.test_result.success:
                discrepancies.append(
                    f"Claim: 'tests pass' | Reality: {evidence.test_result.failed_tests} tests failed"
                )

        # Check coverage claim
        if claims_coverage:
            if evidence.test_result.coverage is None:
                discrepancies.append("Claim mentions coverage | Reality: No coverage data")
            elif evidence.test_result.coverage < self.min_coverage:
                discrepancies.append(
                    f"Claim implies adequate coverage | Reality: {evidence.test_result.coverage:.1f}% (below {self.min_coverage}%)"
                )

        # Check completion claim
        if claims_complete:
            if not evidence.verified:
                discrepancies.append(
                    f"Claim: 'task complete' | Reality: Verification failed with {len(evidence.verification_errors)} errors"
                )

        return {
            "valid": len(discrepancies) == 0,
            "claim": claim,
            "evidence_supports": len(discrepancies) == 0,
            "discrepancies": discrepancies,
            "verified": evidence.verified,
        }
