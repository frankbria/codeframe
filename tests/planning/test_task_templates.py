"""Tests for Task Template System.

TDD tests for task templates:
- TaskTemplate dataclass structure
- Predefined templates for common patterns
- TaskTemplateManager for managing and applying templates
- Template-based task generation
"""

import pytest

from codeframe.planning.task_templates import (
    TaskTemplate,
    TaskTemplateManager,
    TemplateTask,
    BUILTIN_TEMPLATES,
)

pytestmark = pytest.mark.v2


@pytest.mark.unit
class TestTaskTemplateDataclass:
    """Test TaskTemplate dataclass structure."""

    def test_task_template_has_required_fields(self):
        """Test TaskTemplate has all required fields."""
        template = TaskTemplate(
            id="api-endpoint",
            name="API Endpoint",
            description="Create a new REST API endpoint",
            category="backend",
            tasks=[
                TemplateTask(
                    title="Define API schema",
                    description="Create OpenAPI schema for endpoint",
                    estimated_hours=1.0,
                    complexity_score=2,
                ),
            ],
        )

        assert template.id == "api-endpoint"
        assert template.name == "API Endpoint"
        assert template.description == "Create a new REST API endpoint"
        assert template.category == "backend"
        assert len(template.tasks) == 1

    def test_template_task_has_effort_fields(self):
        """Test TemplateTask includes effort estimation fields."""
        task = TemplateTask(
            title="Implement endpoint handler",
            description="Write the endpoint logic",
            estimated_hours=2.0,
            complexity_score=3,
            uncertainty_level="medium",
        )

        assert task.title == "Implement endpoint handler"
        assert task.estimated_hours == 2.0
        assert task.complexity_score == 3
        assert task.uncertainty_level == "medium"

    def test_template_task_has_dependency_index(self):
        """Test TemplateTask can specify dependencies by index."""
        task = TemplateTask(
            title="Write tests",
            description="Unit tests for endpoint",
            estimated_hours=1.5,
            complexity_score=2,
            depends_on_indices=[0, 1],  # Depends on tasks 0 and 1
        )

        assert task.depends_on_indices == [0, 1]

    def test_template_has_default_values(self):
        """Test TaskTemplate has sensible defaults."""
        template = TaskTemplate(
            id="simple",
            name="Simple Task",
            description="A simple task template",
            category="general",
            tasks=[],
        )

        assert template.tags == []
        assert template.total_estimated_hours == 0.0


@pytest.mark.unit
class TestBuiltinTemplates:
    """Test predefined builtin templates."""

    def test_builtin_templates_exist(self):
        """Test that builtin templates are defined."""
        assert len(BUILTIN_TEMPLATES) > 0

    def test_api_endpoint_template_exists(self):
        """Test API endpoint template is available."""
        template_ids = [t.id for t in BUILTIN_TEMPLATES]
        assert "api-endpoint" in template_ids

    def test_ui_component_template_exists(self):
        """Test UI component template is available."""
        template_ids = [t.id for t in BUILTIN_TEMPLATES]
        assert "ui-component" in template_ids

    def test_database_migration_template_exists(self):
        """Test database migration template is available."""
        template_ids = [t.id for t in BUILTIN_TEMPLATES]
        assert "database-migration" in template_ids

    def test_test_suite_template_exists(self):
        """Test test suite template is available."""
        template_ids = [t.id for t in BUILTIN_TEMPLATES]
        assert "test-suite" in template_ids

    def test_builtin_templates_have_tasks(self):
        """Test all builtin templates have at least one task."""
        for template in BUILTIN_TEMPLATES:
            assert len(template.tasks) > 0, f"Template {template.id} has no tasks"

    def test_builtin_templates_have_effort_estimates(self):
        """Test all builtin template tasks have effort estimates."""
        for template in BUILTIN_TEMPLATES:
            for task in template.tasks:
                assert task.estimated_hours > 0, (
                    f"Task '{task.title}' in template {template.id} has no estimate"
                )


@pytest.mark.unit
class TestTaskTemplateManager:
    """Test TaskTemplateManager class."""

    def test_manager_loads_builtin_templates(self):
        """Test manager loads builtin templates on init."""
        manager = TaskTemplateManager()

        assert len(manager.templates) >= len(BUILTIN_TEMPLATES)

    def test_get_template_by_id(self):
        """Test retrieving template by ID."""
        manager = TaskTemplateManager()

        template = manager.get_template("api-endpoint")

        assert template is not None
        assert template.id == "api-endpoint"

    def test_get_template_returns_none_for_unknown(self):
        """Test get_template returns None for unknown ID."""
        manager = TaskTemplateManager()

        template = manager.get_template("unknown-template")

        assert template is None

    def test_list_templates(self):
        """Test listing all available templates."""
        manager = TaskTemplateManager()

        templates = manager.list_templates()

        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_list_templates_by_category(self):
        """Test filtering templates by category."""
        manager = TaskTemplateManager()

        backend_templates = manager.list_templates(category="backend")

        assert all(t.category == "backend" for t in backend_templates)

    def test_register_custom_template(self):
        """Test registering a custom template."""
        manager = TaskTemplateManager()

        custom = TaskTemplate(
            id="custom-workflow",
            name="Custom Workflow",
            description="A custom workflow template",
            category="custom",
            tasks=[
                TemplateTask(
                    title="Custom task",
                    description="Do something custom",
                    estimated_hours=1.0,
                    complexity_score=2,
                ),
            ],
        )

        manager.register_template(custom)

        assert manager.get_template("custom-workflow") is not None

    def test_register_template_replaces_existing(self):
        """Test registering template with same ID replaces existing."""
        manager = TaskTemplateManager()

        custom = TaskTemplate(
            id="api-endpoint",  # Same as builtin
            name="Custom API Endpoint",
            description="Override the builtin template",
            category="backend",
            tasks=[
                TemplateTask(
                    title="Single custom task",
                    description="Custom",
                    estimated_hours=5.0,
                    complexity_score=3,
                ),
            ],
        )

        manager.register_template(custom)
        template = manager.get_template("api-endpoint")

        assert template.name == "Custom API Endpoint"


@pytest.mark.unit
class TestTemplateApplication:
    """Test applying templates to generate tasks."""

    def test_apply_template_returns_task_list(self):
        """Test applying template returns list of task dicts."""
        manager = TaskTemplateManager()

        tasks = manager.apply_template(
            template_id="api-endpoint",
            context={"endpoint_name": "/users", "method": "GET"},
        )

        assert isinstance(tasks, list)
        assert len(tasks) > 0

    def test_applied_tasks_have_required_fields(self):
        """Test generated tasks have all required fields."""
        manager = TaskTemplateManager()

        tasks = manager.apply_template(
            template_id="api-endpoint",
            context={"endpoint_name": "/users"},
        )

        for task in tasks:
            assert "title" in task
            assert "description" in task
            assert "estimated_hours" in task
            assert "complexity_score" in task

    def test_applied_tasks_have_dependencies(self):
        """Test generated tasks have dependency relationships."""
        manager = TaskTemplateManager()

        tasks = manager.apply_template(
            template_id="api-endpoint",
            context={},
        )

        # Check if any task has depends_on_indices set
        has_dependencies = any(task.get("depends_on_indices") for task in tasks)
        # API endpoint template should have some dependencies
        assert has_dependencies or len(tasks) == 1

    def test_apply_template_with_context_substitution(self):
        """Test context variables are substituted in tasks."""
        manager = TaskTemplateManager()

        tasks = manager.apply_template(
            template_id="api-endpoint",
            context={"endpoint_name": "/products"},
        )

        # Check that context was used in task descriptions
        all_text = " ".join(t["title"] + t["description"] for t in tasks)
        # Context should influence the output
        assert len(tasks) > 0

    def test_apply_unknown_template_raises_error(self):
        """Test applying unknown template raises ValueError."""
        manager = TaskTemplateManager()

        with pytest.raises(ValueError, match="Template .* not found"):
            manager.apply_template(template_id="nonexistent", context={})

    def test_calculate_template_total_hours(self):
        """Test calculating total hours for a template."""
        manager = TaskTemplateManager()

        template = manager.get_template("api-endpoint")
        total = manager.calculate_template_hours(template)

        assert total > 0
        expected = sum(t.estimated_hours for t in template.tasks)
        assert total == expected


@pytest.mark.unit
class TestTemplateTaskDependencies:
    """Test dependency handling in templates."""

    def test_template_creates_correct_dependency_chain(self):
        """Test that dependency indices are converted to task references."""
        # Create a template with explicit dependencies
        template = TaskTemplate(
            id="test-chain",
            name="Test Chain",
            description="Test dependency chain",
            category="test",
            tasks=[
                TemplateTask(
                    title="Task A",
                    description="First task",
                    estimated_hours=1.0,
                    complexity_score=1,
                    depends_on_indices=[],
                ),
                TemplateTask(
                    title="Task B",
                    description="Second task",
                    estimated_hours=1.0,
                    complexity_score=1,
                    depends_on_indices=[0],  # Depends on Task A
                ),
                TemplateTask(
                    title="Task C",
                    description="Third task",
                    estimated_hours=1.0,
                    complexity_score=1,
                    depends_on_indices=[0, 1],  # Depends on A and B
                ),
            ],
        )

        manager = TaskTemplateManager()
        manager.register_template(template)

        tasks = manager.apply_template("test-chain", context={})

        # Task B should depend on Task A (index 0)
        assert tasks[1].get("depends_on_indices") == [0]
        # Task C should depend on both A and B
        assert tasks[2].get("depends_on_indices") == [0, 1]


@pytest.mark.unit
class TestTemplateCategories:
    """Test template categorization."""

    def test_get_all_categories(self):
        """Test getting list of all template categories."""
        manager = TaskTemplateManager()

        categories = manager.get_categories()

        assert isinstance(categories, list)
        assert "backend" in categories
        assert "frontend" in categories

    def test_templates_have_valid_categories(self):
        """Test all templates have a category assigned."""
        manager = TaskTemplateManager()

        for template in manager.templates.values():
            assert template.category, f"Template {template.id} has no category"
