"""Unit tests for Task Classifier module.

Tests task classification logic that determines which quality gates should apply
based on task characteristics (title, description).

Task Categories:
- CODE_IMPLEMENTATION: Code tasks that need all quality gates
- DESIGN: Design/architecture tasks that only need review gate
- DOCUMENTATION: Doc tasks that only need linting gate
- CONFIGURATION: Config tasks that need linting + type check
- TESTING: Test-focused tasks that need test gates
- REFACTORING: Refactoring tasks that need all gates
- MIXED: Ambiguous tasks defaulting to all gates
"""

import pytest
from codeframe.core.models import Task, TaskStatus
from codeframe.lib.task_classifier import TaskClassifier, TaskCategory


class TestTaskCategory:
    """Tests for TaskCategory enum values."""

    def test_task_category_values(self):
        """Verify all expected task categories exist."""
        assert TaskCategory.CODE_IMPLEMENTATION is not None
        assert TaskCategory.DESIGN is not None
        assert TaskCategory.DOCUMENTATION is not None
        assert TaskCategory.CONFIGURATION is not None
        assert TaskCategory.TESTING is not None
        assert TaskCategory.REFACTORING is not None
        assert TaskCategory.MIXED is not None


class TestTaskClassifier:
    """Tests for TaskClassifier.classify_task() method."""

    @pytest.fixture
    def classifier(self):
        """Create TaskClassifier instance."""
        return TaskClassifier()

    def _make_task(self, title: str, description: str = "") -> Task:
        """Helper to create test Task."""
        return Task(
            id=1,
            project_id=1,
            task_number="1.1.1",
            title=title,
            description=description,
            status=TaskStatus.IN_PROGRESS,
        )

    # =========================================================================
    # DESIGN Task Classification Tests
    # =========================================================================

    def test_classify_design_task_by_title(self, classifier):
        """Tasks with 'design' in title should be classified as DESIGN."""
        task = self._make_task("Design database schema for events")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_classify_schema_task(self, classifier):
        """Tasks with 'schema' should be classified as DESIGN."""
        task = self._make_task("Create schema for user authentication")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_classify_architecture_task(self, classifier):
        """Tasks with 'architecture' should be classified as DESIGN."""
        task = self._make_task("Define microservices architecture")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_classify_diagram_task(self, classifier):
        """Tasks with 'diagram' should be classified as DESIGN."""
        task = self._make_task("Create system diagram")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_classify_plan_task(self, classifier):
        """Tasks with 'plan' should be classified as DESIGN."""
        task = self._make_task("Plan API endpoints")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_classify_spec_task(self, classifier):
        """Tasks with 'spec' should be classified as DESIGN."""
        task = self._make_task("Write feature spec")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_classify_design_by_description(self, classifier):
        """Description should also be used for classification."""
        task = self._make_task(
            "Phase 1 preparation",
            description="Design the database schema for the new feature"
        )
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    # =========================================================================
    # DOCUMENTATION Task Classification Tests
    # =========================================================================

    def test_classify_document_task(self, classifier):
        """Tasks with 'document' should be classified as DOCUMENTATION."""
        task = self._make_task("Document the API endpoints")
        assert classifier.classify_task(task) == TaskCategory.DOCUMENTATION

    def test_classify_readme_task(self, classifier):
        """Tasks with 'readme' should be classified as DOCUMENTATION."""
        task = self._make_task("Update README file")
        assert classifier.classify_task(task) == TaskCategory.DOCUMENTATION

    def test_classify_guide_task(self, classifier):
        """Tasks with 'guide' should be classified as DOCUMENTATION."""
        task = self._make_task("Write user guide")
        assert classifier.classify_task(task) == TaskCategory.DOCUMENTATION

    def test_classify_tutorial_task(self, classifier):
        """Tasks with 'tutorial' should be classified as DOCUMENTATION."""
        task = self._make_task("Create tutorial for beginners")
        assert classifier.classify_task(task) == TaskCategory.DOCUMENTATION

    # =========================================================================
    # CONFIGURATION Task Classification Tests
    # =========================================================================

    def test_classify_config_task(self, classifier):
        """Tasks with 'config' should be classified as CONFIGURATION."""
        task = self._make_task("Update config settings")
        assert classifier.classify_task(task) == TaskCategory.CONFIGURATION

    def test_classify_setup_task(self, classifier):
        """Tasks with 'setup' should be classified as CONFIGURATION."""
        task = self._make_task("Setup CI/CD pipeline")
        assert classifier.classify_task(task) == TaskCategory.CONFIGURATION

    def test_classify_install_task(self, classifier):
        """Tasks with 'install' should be classified as CONFIGURATION."""
        task = self._make_task("Install dependencies")
        assert classifier.classify_task(task) == TaskCategory.CONFIGURATION

    def test_classify_deploy_task(self, classifier):
        """Tasks with 'deploy' should be classified as CONFIGURATION."""
        task = self._make_task("Deploy to staging")
        assert classifier.classify_task(task) == TaskCategory.CONFIGURATION

    def test_classify_environment_task(self, classifier):
        """Tasks with 'environment' should be classified as CONFIGURATION."""
        task = self._make_task("Configure environment variables")
        assert classifier.classify_task(task) == TaskCategory.CONFIGURATION

    # =========================================================================
    # CODE_IMPLEMENTATION Task Classification Tests
    # =========================================================================

    def test_classify_implement_task(self, classifier):
        """Tasks with 'implement' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Implement user authentication")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_create_function_task(self, classifier):
        """Tasks mentioning function creation should be CODE_IMPLEMENTATION."""
        task = self._make_task("Create function for data validation")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_build_task(self, classifier):
        """Tasks with 'build' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Build the login component")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_develop_task(self, classifier):
        """Tasks with 'develop' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Develop payment integration")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_code_task(self, classifier):
        """Tasks with 'code' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Code the API handler")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_class_task(self, classifier):
        """Tasks mentioning class should be CODE_IMPLEMENTATION."""
        task = self._make_task("Add class for user management")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_api_task(self, classifier):
        """Tasks with 'api' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Create REST API for orders")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_endpoint_task(self, classifier):
        """Tasks with 'endpoint' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Add endpoint for user profile")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_fix_task(self, classifier):
        """Tasks with 'fix' should be classified as CODE_IMPLEMENTATION."""
        task = self._make_task("Fix bug in payment processing")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    # =========================================================================
    # TESTING Task Classification Tests
    # =========================================================================

    def test_classify_write_tests_task(self, classifier):
        """Tasks about writing tests should be classified as TESTING."""
        task = self._make_task("Write unit tests for authentication")
        assert classifier.classify_task(task) == TaskCategory.TESTING

    def test_classify_add_tests_task(self, classifier):
        """Tasks about adding tests should be classified as TESTING."""
        task = self._make_task("Add integration tests")
        assert classifier.classify_task(task) == TaskCategory.TESTING

    def test_classify_test_coverage_task(self, classifier):
        """Tasks about test coverage should be classified as TESTING."""
        task = self._make_task("Improve test coverage")
        assert classifier.classify_task(task) == TaskCategory.TESTING

    # =========================================================================
    # REFACTORING Task Classification Tests
    # =========================================================================

    def test_classify_refactor_task(self, classifier):
        """Tasks with 'refactor' should be classified as REFACTORING."""
        task = self._make_task("Refactor authentication module")
        assert classifier.classify_task(task) == TaskCategory.REFACTORING

    def test_classify_cleanup_task(self, classifier):
        """Tasks with 'cleanup' should be classified as REFACTORING."""
        task = self._make_task("Code cleanup and optimization")
        assert classifier.classify_task(task) == TaskCategory.REFACTORING

    def test_classify_optimize_task(self, classifier):
        """Tasks with 'optimize' should be classified as REFACTORING."""
        task = self._make_task("Optimize database queries")
        assert classifier.classify_task(task) == TaskCategory.REFACTORING

    # =========================================================================
    # MIXED and Edge Case Tests
    # =========================================================================

    def test_classify_mixed_design_and_implement(self, classifier):
        """Tasks with both design and implement keywords should be MIXED."""
        task = self._make_task("Design and implement user authentication")
        assert classifier.classify_task(task) == TaskCategory.MIXED

    def test_classify_empty_description(self, classifier):
        """Tasks with ambiguous title and empty description default to CODE_IMPLEMENTATION."""
        task = self._make_task("Feature X", description="")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_classify_ambiguous_task(self, classifier):
        """Ambiguous tasks default to CODE_IMPLEMENTATION (conservative approach)."""
        task = self._make_task("Do something")
        assert classifier.classify_task(task) == TaskCategory.CODE_IMPLEMENTATION

    def test_case_insensitive_classification(self, classifier):
        """Classification should be case insensitive."""
        task = self._make_task("DESIGN DATABASE SCHEMA")
        assert classifier.classify_task(task) == TaskCategory.DESIGN

    def test_keyword_in_middle_of_word_not_matched(self, classifier):
        """Keywords embedded in other words should not match."""
        # 'sign' contains 'sign' but not 'design'
        task = self._make_task("Sign the document")
        # This should NOT be classified as DESIGN
        assert classifier.classify_task(task) != TaskCategory.DESIGN

    # =========================================================================
    # Priority/Precedence Tests
    # =========================================================================

    def test_testing_takes_precedence_over_code(self, classifier):
        """Testing keywords should take precedence when both are present."""
        task = self._make_task("Implement tests for feature X")
        # When both 'implement' and 'tests' are present, TESTING wins
        assert classifier.classify_task(task) == TaskCategory.TESTING

    def test_refactoring_over_code(self, classifier):
        """Refactoring should take precedence over generic code keywords."""
        task = self._make_task("Refactor and fix the code")
        assert classifier.classify_task(task) == TaskCategory.REFACTORING
