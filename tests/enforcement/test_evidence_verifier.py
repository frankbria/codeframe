"""
Tests for EvidenceVerifier - validates agent claims.
"""

from datetime import datetime
from codeframe.enforcement import EvidenceVerifier, TestResult, SkipViolation


class TestEvidenceVerifier:
    """Test evidence verification."""

    def test_verifies_passing_tests_with_coverage(self):
        """Test verification of passing evidence"""
        verifier = EvidenceVerifier(min_coverage=85.0)

        test_result = TestResult(
            success=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            skipped_tests=0,
            pass_rate=100.0,
            coverage=90.0,
            output="All tests passed",
            duration=1.23
        )

        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=[],
            language="python",
            agent_id="worker-001",
            task_description="Implement user auth"
        )

        assert verifier.verify(evidence) is True
        assert evidence.verified is True

    def test_rejects_failing_tests(self):
        """Test rejection when tests fail"""
        verifier = EvidenceVerifier()

        test_result = TestResult(
            success=False,
            total_tests=10,
            passed_tests=8,
            failed_tests=2,
            skipped_tests=0,
            pass_rate=80.0,
            coverage=85.0,
            output="2 tests failed",
            duration=1.23
        )

        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=[],
            language="python",
            agent_id="worker-001",
            task_description="Test task"
        )

        assert verifier.verify(evidence) is False
        assert any("failed" in error.lower() for error in evidence.verification_errors)

    def test_rejects_low_coverage(self):
        """Test rejection when coverage too low"""
        verifier = EvidenceVerifier(min_coverage=85.0)

        test_result = TestResult(
            success=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            skipped_tests=0,
            pass_rate=100.0,
            coverage=70.0,  # Below threshold
            output="All tests passed",
            duration=1.23
        )

        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=[],
            language="python",
            agent_id="worker-001",
            task_description="Test task"
        )

        assert verifier.verify(evidence) is False
        assert any("coverage" in error.lower() for error in evidence.verification_errors)

    def test_rejects_skip_violations(self):
        """Test rejection when skip violations found"""
        verifier = EvidenceVerifier(allow_skipped_tests=False)

        test_result = TestResult(
            success=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            skipped_tests=0,
            pass_rate=100.0,
            coverage=90.0,
            output="All tests passed",
            duration=1.23
        )

        skip_violations = [
            SkipViolation(
                file="test_user.py",
                line=10,
                pattern="@skip",
                context="test_something",
                reason=None,
                severity="error"
            )
        ]

        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=skip_violations,
            language="python",
            agent_id="worker-001",
            task_description="Test task"
        )

        assert verifier.verify(evidence) is False
        assert any("skip" in error.lower() for error in evidence.verification_errors)

    def test_generates_report(self):
        """Test report generation"""
        verifier = EvidenceVerifier()

        test_result = TestResult(
            success=True,
            total_tests=10,
            passed_tests=10,
            failed_tests=0,
            skipped_tests=0,
            pass_rate=100.0,
            coverage=90.0,
            output="All tests passed",
            duration=1.23
        )

        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=[],
            language="python",
            agent_id="worker-001",
            task_description="Implement feature X"
        )

        verifier.verify(evidence)
        report = verifier.generate_report(evidence)

        assert "EVIDENCE VERIFICATION REPORT" in report
        assert "worker-001" in report
        assert "Implement feature X" in report
        assert "PASSED" in report

    def test_works_with_any_language(self):
        """Test language-agnostic verification"""
        verifier = EvidenceVerifier(min_coverage=80.0)

        # Go project
        test_result = TestResult(
            success=True,
            total_tests=20,
            passed_tests=20,
            failed_tests=0,
            skipped_tests=0,
            pass_rate=100.0,
            coverage=85.0,
            output="ok  \tgithub.com/example/pkg\t2.500s",  # More realistic Go output
            duration=2.5
        )

        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=[],
            language="go",
            agent_id="worker-002",
            task_description="Add API endpoint",
            framework="go test"
        )

        assert verifier.verify(evidence) is True
        assert evidence.quality_metrics.language == "go"
        assert evidence.quality_metrics.framework == "go test"
