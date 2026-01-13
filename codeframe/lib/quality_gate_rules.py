"""Quality Gate Rules module for task-category-based gate applicability.

This module defines which quality gates should be applied based on the task
category. Different task types have different quality requirements:

- CODE_IMPLEMENTATION: Full quality gates (all 6)
- DESIGN: Only code review (for design document quality)
- DOCUMENTATION: Only linting (for markdown/doc linting)
- CONFIGURATION: Linting and type check
- TESTING: Tests, coverage, skip detection
- REFACTORING: Full quality gates (all 6)
- MIXED: Full quality gates (conservative approach)

Usage:
    >>> from codeframe.lib.quality_gate_rules import QualityGateRules
    >>> from codeframe.lib.task_classifier import TaskCategory
    >>> rules = QualityGateRules()
    >>> gates = rules.get_applicable_gates(TaskCategory.DESIGN)
    >>> # gates = [QualityGateType.CODE_REVIEW]
"""

from typing import List, Optional

from codeframe.core.models import QualityGateType
from codeframe.lib.task_classifier import TaskCategory


# Gate applicability mapping
# Based on the Quality Gate Applicability Matrix
_GATE_RULES: dict[TaskCategory, List[QualityGateType]] = {
    TaskCategory.CODE_IMPLEMENTATION: [
        QualityGateType.TESTS,
        QualityGateType.COVERAGE,
        QualityGateType.TYPE_CHECK,
        QualityGateType.LINTING,
        QualityGateType.CODE_REVIEW,
        QualityGateType.SKIP_DETECTION,
    ],
    TaskCategory.DESIGN: [
        QualityGateType.CODE_REVIEW,
    ],
    TaskCategory.DOCUMENTATION: [
        QualityGateType.LINTING,
    ],
    TaskCategory.CONFIGURATION: [
        QualityGateType.TYPE_CHECK,
        QualityGateType.LINTING,
    ],
    TaskCategory.TESTING: [
        QualityGateType.TESTS,
        QualityGateType.COVERAGE,
        QualityGateType.SKIP_DETECTION,
    ],
    TaskCategory.REFACTORING: [
        QualityGateType.TESTS,
        QualityGateType.COVERAGE,
        QualityGateType.TYPE_CHECK,
        QualityGateType.LINTING,
        QualityGateType.CODE_REVIEW,
        QualityGateType.SKIP_DETECTION,
    ],
    TaskCategory.MIXED: [
        QualityGateType.TESTS,
        QualityGateType.COVERAGE,
        QualityGateType.TYPE_CHECK,
        QualityGateType.LINTING,
        QualityGateType.CODE_REVIEW,
        QualityGateType.SKIP_DETECTION,
    ],
}

# Skip reasons for each category/gate combination
_SKIP_REASONS: dict[TaskCategory, dict[QualityGateType, str]] = {
    TaskCategory.DESIGN: {
        QualityGateType.TESTS: "Design tasks do not produce executable code to test",
        QualityGateType.COVERAGE: "Design tasks do not produce code requiring coverage",
        QualityGateType.TYPE_CHECK: "Design tasks do not produce typed code",
        QualityGateType.LINTING: "Design tasks may not produce lintable code",
        QualityGateType.SKIP_DETECTION: "Design tasks do not include test files",
    },
    TaskCategory.DOCUMENTATION: {
        QualityGateType.TESTS: "Documentation tasks do not produce executable code to test",
        QualityGateType.COVERAGE: "Documentation tasks do not produce code requiring coverage",
        QualityGateType.TYPE_CHECK: "Documentation tasks do not produce typed code",
        QualityGateType.CODE_REVIEW: "Documentation tasks are reviewed through linting",
        QualityGateType.SKIP_DETECTION: "Documentation tasks do not include test files",
    },
    TaskCategory.CONFIGURATION: {
        QualityGateType.TESTS: "Configuration tasks typically don't require unit tests",
        QualityGateType.COVERAGE: "Configuration tasks don't require coverage metrics",
        QualityGateType.CODE_REVIEW: "Configuration is reviewed through type checking",
        QualityGateType.SKIP_DETECTION: "Configuration tasks do not include test files",
    },
    TaskCategory.TESTING: {
        QualityGateType.TYPE_CHECK: "Test code may use dynamic patterns that fail type checks",
        QualityGateType.LINTING: "Test code may use patterns that trigger linting warnings",
        QualityGateType.CODE_REVIEW: "Test code is validated through execution rather than review",
    },
}


class QualityGateRules:
    """Rules engine for determining applicable quality gates per task category.

    This class encapsulates the logic for determining which quality gates should
    be executed for a given task category. It provides both positive (get gates)
    and negative (should skip) queries.
    """

    @property
    def all_gates(self) -> List[QualityGateType]:
        """Return all quality gate types."""
        return list(QualityGateType)

    def get_applicable_gates(self, category: TaskCategory) -> List[QualityGateType]:
        """Get the list of quality gates that should be applied for a task category.

        Args:
            category: The task category

        Returns:
            List of QualityGateType values that should be applied
        """
        return _GATE_RULES.get(category, _GATE_RULES[TaskCategory.MIXED])

    def should_skip_gate(self, category: TaskCategory, gate: QualityGateType) -> bool:
        """Check if a specific gate should be skipped for a task category.

        Args:
            category: The task category
            gate: The quality gate type to check

        Returns:
            True if the gate should be skipped, False if it should run
        """
        applicable_gates = self.get_applicable_gates(category)
        return gate not in applicable_gates

    def get_skip_reason(
        self, category: TaskCategory, gate: QualityGateType
    ) -> Optional[str]:
        """Get the reason why a gate is skipped for a category.

        Args:
            category: The task category
            gate: The quality gate type

        Returns:
            String explaining why the gate is skipped, or None if gate is applicable
        """
        if not self.should_skip_gate(category, gate):
            return None

        category_reasons = _SKIP_REASONS.get(category, {})
        return category_reasons.get(
            gate, f"{gate.value} gate is not applicable for {category.value} tasks"
        )
