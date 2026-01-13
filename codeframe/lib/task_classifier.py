"""Task Classifier module for intelligent quality gate selection.

This module analyzes task titles and descriptions to determine the task category,
which then determines which quality gates should be applied. This prevents
false failures when non-code tasks (design, documentation) go through
code-specific quality gates.

Task Categories:
- CODE_IMPLEMENTATION: Tasks that produce executable code
- DESIGN: Tasks that produce design artifacts (schemas, diagrams, specs)
- DOCUMENTATION: Tasks that produce documentation (docs, readme, guides)
- CONFIGURATION: Tasks that modify configuration (env, deploy, setup)
- TESTING: Tasks focused on writing tests
- REFACTORING: Tasks that improve existing code without adding features
- MIXED: Tasks with multiple categories (conservative: all gates apply)

Usage:
    >>> from codeframe.lib.task_classifier import TaskClassifier
    >>> classifier = TaskClassifier()
    >>> category = classifier.classify_task(task)
    >>> if category == TaskCategory.DESIGN:
    ...     # Only run review gate
"""

import re
from enum import Enum

from codeframe.core.models import Task


class TaskCategory(str, Enum):
    """Categories of tasks for quality gate selection.

    Each category maps to a different set of applicable quality gates.
    """

    CODE_IMPLEMENTATION = "code_implementation"
    DESIGN = "design"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    TESTING = "testing"
    REFACTORING = "refactoring"
    MIXED = "mixed"


# Keyword definitions for each category
# Using word boundaries to avoid matching keywords embedded in other words

# Strong keywords are definitive markers for a category
# Weak keywords are common verbs that can appear with multiple categories
_DESIGN_KEYWORDS = frozenset([
    "design", "schema", "architecture", "diagram", "plan",
    "blueprint", "outline", "structure", "model", "prototype"
])

_DOCUMENTATION_KEYWORDS = frozenset([
    "document", "readme", "guide", "tutorial", "comment", "docs",
    "documentation", "wiki", "manual", "help", "changelog"
])

_CONFIGURATION_KEYWORDS = frozenset([
    "config", "setup", "install", "deploy", "environment", "env",
    "configure", "settings", "provision", "migrate", "infrastructure"
])

# Strong code keywords - specific to code implementation actions
_CODE_KEYWORDS_STRONG = frozenset([
    "implement", "develop", "code", "function", "class",
    "fix", "bug", "handler", "service", "module",
    "component", "method"
])

# Weak code keywords - generic verbs or nouns that can appear with other categories
# These describe the target (what) rather than the action (how)
_CODE_KEYWORDS_WEAK = frozenset([
    "create", "build", "add", "feature", "write", "api", "endpoint"
])

_TESTING_KEYWORDS = frozenset([
    "test", "tests", "testing", "coverage", "unittest", "pytest",
    "jest", "tdd", "bdd"
])

# 'spec' is context-dependent - if with test keywords it's TESTING,
# otherwise it could be design spec
_SPEC_KEYWORD = "spec"

_REFACTORING_KEYWORDS = frozenset([
    "refactor", "cleanup", "optimize", "improve", "simplify",
    "restructure", "reorganize", "consolidate", "modernize"
])


class TaskClassifier:
    """Classifies tasks based on their title and description.

    Uses keyword analysis to determine the task category. Distinguishes between
    "strong" keywords (definitive markers) and "weak" keywords (generic verbs
    that can appear with any category). When no clear category is found,
    defaults to CODE_IMPLEMENTATION (conservative approach).
    """

    def __init__(self):
        """Initialize the classifier with keyword patterns."""
        # Pre-compile regex patterns for word boundary matching
        self._design_pattern = self._compile_pattern(_DESIGN_KEYWORDS)
        self._doc_pattern = self._compile_pattern(_DOCUMENTATION_KEYWORDS)
        self._config_pattern = self._compile_pattern(_CONFIGURATION_KEYWORDS)
        self._code_strong_pattern = self._compile_pattern(_CODE_KEYWORDS_STRONG)
        self._code_weak_pattern = self._compile_pattern(_CODE_KEYWORDS_WEAK)
        self._testing_pattern = self._compile_pattern(_TESTING_KEYWORDS)
        self._refactoring_pattern = self._compile_pattern(_REFACTORING_KEYWORDS)
        self._spec_pattern = re.compile(r'\bspec\b', re.IGNORECASE)

    def _compile_pattern(self, keywords: frozenset) -> re.Pattern:
        """Compile keywords into a regex pattern with word boundaries."""
        # Sort by length descending to match longer keywords first
        sorted_keywords = sorted(keywords, key=len, reverse=True)
        pattern = r'\b(' + '|'.join(re.escape(kw) for kw in sorted_keywords) + r')\b'
        return re.compile(pattern, re.IGNORECASE)

    def classify_task(self, task: Task) -> TaskCategory:
        """Classify a task based on its title and description.

        Args:
            task: Task to classify

        Returns:
            TaskCategory indicating the type of task

        Priority Order (when multiple categories match):
            1. TESTING (test-related tasks take precedence)
            2. REFACTORING (refactoring takes precedence over generic code)
            3. DESIGN (design tasks shouldn't run code gates)
            4. DOCUMENTATION (doc tasks shouldn't run code gates)
            5. CONFIGURATION (config tasks need limited gates)
            6. CODE_IMPLEMENTATION (default for code-related tasks)
            7. MIXED (only when strong code + strong non-code keywords present)
        """
        # Normalize inputs - handle None values gracefully
        title = task.title or ""
        description = task.description or ""
        text = f"{title} {description}".lower()

        # Check each category
        has_design = bool(self._design_pattern.search(text))
        has_doc = bool(self._doc_pattern.search(text))
        has_config = bool(self._config_pattern.search(text))
        has_code_strong = bool(self._code_strong_pattern.search(text))
        has_code_weak = bool(self._code_weak_pattern.search(text))
        has_testing = bool(self._testing_pattern.search(text))
        has_refactoring = bool(self._refactoring_pattern.search(text))
        has_spec = bool(self._spec_pattern.search(text))

        # Handle 'spec' keyword specially - it's DESIGN unless testing keywords present
        if has_spec and not has_testing:
            has_design = True

        # Testing takes highest priority (even if other keywords present)
        if has_testing:
            return TaskCategory.TESTING

        # Refactoring takes next priority
        if has_refactoring:
            return TaskCategory.REFACTORING

        # Check for MIXED: strong code keywords + strong non-code keywords
        # Weak code keywords (create, add, write) don't trigger MIXED
        has_strong_non_code = has_design or has_doc
        if has_strong_non_code and has_code_strong:
            return TaskCategory.MIXED

        # Non-code categories (with or without weak code keywords)
        if has_design:
            return TaskCategory.DESIGN

        if has_doc:
            return TaskCategory.DOCUMENTATION

        if has_config:
            return TaskCategory.CONFIGURATION

        # Code implementation (strong or weak keywords)
        if has_code_strong or has_code_weak:
            return TaskCategory.CODE_IMPLEMENTATION

        # Default fallback - assume code implementation (conservative)
        return TaskCategory.CODE_IMPLEMENTATION
