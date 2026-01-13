"""Unit tests for Quality Gate Rules module.

Tests the mapping of task categories to applicable quality gates,
based on the Quality Gate Applicability Matrix:

| Task Category       | Tests | Coverage | Type Check | Linting | Code Review | Skip Detection |
|---------------------|-------|----------|------------|---------|-------------|----------------|
| CODE_IMPLEMENTATION | ✅    | ✅       | ✅         | ✅      | ✅          | ✅             |
| DESIGN              | ❌    | ❌       | ❌         | ❌      | ✅          | ❌             |
| DOCUMENTATION       | ❌    | ❌       | ❌         | ✅      | ❌          | ❌             |
| CONFIGURATION       | ❌    | ❌       | ✅         | ✅      | ❌          | ❌             |
| TESTING             | ✅    | ✅       | ❌         | ❌      | ❌          | ✅             |
| REFACTORING         | ✅    | ✅       | ✅         | ✅      | ✅          | ✅             |
| MIXED               | ✅    | ✅       | ✅         | ✅      | ✅          | ✅             |
"""

import pytest
from codeframe.core.models import QualityGateType
from codeframe.lib.task_classifier import TaskCategory
from codeframe.lib.quality_gate_rules import QualityGateRules


class TestQualityGateRules:
    """Tests for QualityGateRules class."""

    @pytest.fixture
    def rules(self):
        """Create QualityGateRules instance."""
        return QualityGateRules()

    # =========================================================================
    # CODE_IMPLEMENTATION Gate Tests
    # =========================================================================

    def test_code_implementation_gets_all_gates(self, rules):
        """CODE_IMPLEMENTATION tasks should have all quality gates applied."""
        gates = rules.get_applicable_gates(TaskCategory.CODE_IMPLEMENTATION)

        assert QualityGateType.TESTS in gates
        assert QualityGateType.COVERAGE in gates
        assert QualityGateType.TYPE_CHECK in gates
        assert QualityGateType.LINTING in gates
        assert QualityGateType.CODE_REVIEW in gates
        assert QualityGateType.SKIP_DETECTION in gates
        assert len(gates) == 6

    # =========================================================================
    # DESIGN Gate Tests
    # =========================================================================

    def test_design_only_gets_code_review(self, rules):
        """DESIGN tasks should only have code review gate."""
        gates = rules.get_applicable_gates(TaskCategory.DESIGN)

        assert QualityGateType.CODE_REVIEW in gates
        assert len(gates) == 1

    def test_design_does_not_get_tests(self, rules):
        """DESIGN tasks should NOT have test gate."""
        gates = rules.get_applicable_gates(TaskCategory.DESIGN)
        assert QualityGateType.TESTS not in gates

    def test_design_does_not_get_coverage(self, rules):
        """DESIGN tasks should NOT have coverage gate."""
        gates = rules.get_applicable_gates(TaskCategory.DESIGN)
        assert QualityGateType.COVERAGE not in gates

    # =========================================================================
    # DOCUMENTATION Gate Tests
    # =========================================================================

    def test_documentation_only_gets_linting(self, rules):
        """DOCUMENTATION tasks should only have linting gate."""
        gates = rules.get_applicable_gates(TaskCategory.DOCUMENTATION)

        assert QualityGateType.LINTING in gates
        assert len(gates) == 1

    def test_documentation_does_not_get_type_check(self, rules):
        """DOCUMENTATION tasks should NOT have type check gate."""
        gates = rules.get_applicable_gates(TaskCategory.DOCUMENTATION)
        assert QualityGateType.TYPE_CHECK not in gates

    # =========================================================================
    # CONFIGURATION Gate Tests
    # =========================================================================

    def test_configuration_gets_linting_and_type_check(self, rules):
        """CONFIGURATION tasks should have linting and type check gates."""
        gates = rules.get_applicable_gates(TaskCategory.CONFIGURATION)

        assert QualityGateType.LINTING in gates
        assert QualityGateType.TYPE_CHECK in gates
        assert len(gates) == 2

    def test_configuration_does_not_get_tests(self, rules):
        """CONFIGURATION tasks should NOT have test gate."""
        gates = rules.get_applicable_gates(TaskCategory.CONFIGURATION)
        assert QualityGateType.TESTS not in gates

    # =========================================================================
    # TESTING Gate Tests
    # =========================================================================

    def test_testing_gets_tests_coverage_skip_detection(self, rules):
        """TESTING tasks should have tests, coverage, and skip detection gates."""
        gates = rules.get_applicable_gates(TaskCategory.TESTING)

        assert QualityGateType.TESTS in gates
        assert QualityGateType.COVERAGE in gates
        assert QualityGateType.SKIP_DETECTION in gates
        assert len(gates) == 3

    def test_testing_does_not_get_code_review(self, rules):
        """TESTING tasks should NOT have code review gate."""
        gates = rules.get_applicable_gates(TaskCategory.TESTING)
        assert QualityGateType.CODE_REVIEW not in gates

    # =========================================================================
    # REFACTORING Gate Tests
    # =========================================================================

    def test_refactoring_gets_all_gates(self, rules):
        """REFACTORING tasks should have all quality gates applied."""
        gates = rules.get_applicable_gates(TaskCategory.REFACTORING)

        assert QualityGateType.TESTS in gates
        assert QualityGateType.COVERAGE in gates
        assert QualityGateType.TYPE_CHECK in gates
        assert QualityGateType.LINTING in gates
        assert QualityGateType.CODE_REVIEW in gates
        assert QualityGateType.SKIP_DETECTION in gates
        assert len(gates) == 6

    # =========================================================================
    # MIXED Gate Tests
    # =========================================================================

    def test_mixed_gets_all_gates(self, rules):
        """MIXED tasks should have all quality gates applied (conservative)."""
        gates = rules.get_applicable_gates(TaskCategory.MIXED)

        assert QualityGateType.TESTS in gates
        assert QualityGateType.COVERAGE in gates
        assert QualityGateType.TYPE_CHECK in gates
        assert QualityGateType.LINTING in gates
        assert QualityGateType.CODE_REVIEW in gates
        assert QualityGateType.SKIP_DETECTION in gates
        assert len(gates) == 6

    # =========================================================================
    # should_skip_gate Tests
    # =========================================================================

    def test_should_skip_tests_for_design(self, rules):
        """Tests gate should be skipped for DESIGN tasks."""
        assert rules.should_skip_gate(TaskCategory.DESIGN, QualityGateType.TESTS) is True

    def test_should_not_skip_code_review_for_design(self, rules):
        """Code review gate should NOT be skipped for DESIGN tasks."""
        assert rules.should_skip_gate(TaskCategory.DESIGN, QualityGateType.CODE_REVIEW) is False

    def test_should_skip_coverage_for_documentation(self, rules):
        """Coverage gate should be skipped for DOCUMENTATION tasks."""
        assert rules.should_skip_gate(TaskCategory.DOCUMENTATION, QualityGateType.COVERAGE) is True

    def test_should_not_skip_any_for_code_implementation(self, rules):
        """No gates should be skipped for CODE_IMPLEMENTATION tasks."""
        for gate in QualityGateType:
            assert rules.should_skip_gate(TaskCategory.CODE_IMPLEMENTATION, gate) is False

    # =========================================================================
    # get_skip_reason Tests
    # =========================================================================

    def test_get_skip_reason_for_design_tests(self, rules):
        """Should return reason why tests gate is skipped for DESIGN."""
        reason = rules.get_skip_reason(TaskCategory.DESIGN, QualityGateType.TESTS)

        assert reason is not None
        assert "design" in reason.lower()

    def test_get_skip_reason_returns_none_for_applicable_gate(self, rules):
        """Should return None when gate is applicable."""
        reason = rules.get_skip_reason(TaskCategory.CODE_IMPLEMENTATION, QualityGateType.TESTS)
        assert reason is None

    # =========================================================================
    # All Gates Enumeration
    # =========================================================================

    def test_all_gates_returns_all_gate_types(self, rules):
        """all_gates property should return all QualityGateType values."""
        all_gates = rules.all_gates

        assert len(all_gates) == 6
        for gate in QualityGateType:
            assert gate in all_gates
