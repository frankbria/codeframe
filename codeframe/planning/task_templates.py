"""Task Template System for CodeFRAME.

This module provides a template system for common task patterns:
- TaskTemplate: Dataclass defining a task template
- TemplateTask: Individual task within a template
- TaskTemplateManager: Manage and apply templates
- BUILTIN_TEMPLATES: Predefined templates for common patterns
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class TemplateTask:
    """Individual task within a template.

    Attributes:
        title: Task title
        description: Task description
        estimated_hours: Time estimate in hours
        complexity_score: Complexity rating (1-5)
        uncertainty_level: "low", "medium", "high" (optional)
        depends_on_indices: List of task indices this task depends on
        tags: Optional tags for the task
    """

    title: str
    description: str
    estimated_hours: float
    complexity_score: int
    uncertainty_level: str = "medium"
    depends_on_indices: List[int] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class TaskTemplate:
    """Template for generating a set of related tasks.

    Attributes:
        id: Unique identifier for the template
        name: Human-readable name
        description: Description of what this template is for
        category: Category (backend, frontend, testing, etc.)
        tasks: List of TemplateTask objects
        tags: Optional tags for the template
    """

    id: str
    name: str
    description: str
    category: str
    tasks: List[TemplateTask]
    tags: List[str] = field(default_factory=list)

    @property
    def total_estimated_hours(self) -> float:
        """Calculate total estimated hours for all tasks."""
        return sum(t.estimated_hours for t in self.tasks)


# Predefined builtin templates
BUILTIN_TEMPLATES: List[TaskTemplate] = [
    TaskTemplate(
        id="api-endpoint",
        name="API Endpoint",
        description="Create a new REST API endpoint with validation, handlers, and tests",
        category="backend",
        tags=["api", "rest", "backend"],
        tasks=[
            TemplateTask(
                title="Define API schema and models",
                description="Create request/response models and validation schemas",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Implement endpoint handler",
                description="Write the endpoint logic and business rules",
                estimated_hours=2.0,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Add error handling",
                description="Implement proper error responses and edge cases",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Write unit tests",
                description="Create comprehensive unit tests for the endpoint",
                estimated_hours=1.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Add API documentation",
                description="Document endpoint in OpenAPI/Swagger spec",
                estimated_hours=0.5,
                complexity_score=1,
                uncertainty_level="low",
                depends_on_indices=[0, 1],
            ),
        ],
    ),
    TaskTemplate(
        id="ui-component",
        name="UI Component",
        description="Create a new React/frontend UI component with styling and tests",
        category="frontend",
        tags=["ui", "react", "frontend", "component"],
        tasks=[
            TemplateTask(
                title="Design component interface",
                description="Define props, state, and component API",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Implement component structure",
                description="Create the component with JSX/TSX structure",
                estimated_hours=1.5,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Add styling",
                description="Style the component with CSS/Tailwind",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Implement interactions",
                description="Add event handlers and state management",
                estimated_hours=1.0,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Write component tests",
                description="Create unit and integration tests",
                estimated_hours=1.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1, 2, 3],
            ),
            TemplateTask(
                title="Add accessibility features",
                description="Ensure WCAG compliance and keyboard navigation",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
        ],
    ),
    TaskTemplate(
        id="database-migration",
        name="Database Migration",
        description="Create a database schema migration with rollback support",
        category="backend",
        tags=["database", "migration", "schema"],
        tasks=[
            TemplateTask(
                title="Design schema changes",
                description="Document the schema modifications needed",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Write migration script",
                description="Create the forward migration SQL/script",
                estimated_hours=1.0,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Write rollback script",
                description="Create the rollback migration for reversal",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Update model definitions",
                description="Update ORM models to match new schema",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Test migration",
                description="Test migration on staging/test database",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="medium",
                depends_on_indices=[1, 2, 3],
            ),
        ],
    ),
    TaskTemplate(
        id="test-suite",
        name="Test Suite",
        description="Create a comprehensive test suite for a feature",
        category="testing",
        tags=["testing", "quality", "tdd"],
        tasks=[
            TemplateTask(
                title="Identify test scenarios",
                description="Document all test cases and edge cases",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Set up test fixtures",
                description="Create test data and mock objects",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Write unit tests",
                description="Create unit tests for individual functions",
                estimated_hours=2.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Write integration tests",
                description="Create integration tests for component interactions",
                estimated_hours=2.0,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Add edge case tests",
                description="Test error conditions and boundary cases",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[2, 3],
            ),
        ],
    ),
    TaskTemplate(
        id="feature-flag",
        name="Feature Flag",
        description="Implement a feature behind a feature flag for gradual rollout",
        category="backend",
        tags=["feature-flag", "rollout", "backend"],
        tasks=[
            TemplateTask(
                title="Define feature flag",
                description="Create feature flag configuration",
                estimated_hours=0.5,
                complexity_score=1,
                uncertainty_level="low",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Implement feature code",
                description="Write the feature implementation",
                estimated_hours=3.0,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Add flag checks",
                description="Wrap feature code with flag checks",
                estimated_hours=0.5,
                complexity_score=1,
                uncertainty_level="low",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Write tests with flag variations",
                description="Test both enabled and disabled states",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[1, 2],
            ),
        ],
    ),
    TaskTemplate(
        id="bug-fix",
        name="Bug Fix",
        description="Standard workflow for fixing a bug with proper testing",
        category="general",
        tags=["bug", "fix", "maintenance"],
        tasks=[
            TemplateTask(
                title="Reproduce and document bug",
                description="Create reliable reproduction steps",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="medium",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Write failing test",
                description="Create test that demonstrates the bug",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Implement fix",
                description="Fix the underlying issue",
                estimated_hours=1.0,
                complexity_score=3,
                uncertainty_level="high",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Verify fix",
                description="Ensure test passes and no regressions",
                estimated_hours=0.5,
                complexity_score=1,
                uncertainty_level="low",
                depends_on_indices=[2],
            ),
        ],
    ),
    TaskTemplate(
        id="refactoring",
        name="Code Refactoring",
        description="Refactor code while maintaining behavior",
        category="general",
        tags=["refactoring", "cleanup", "maintenance"],
        tasks=[
            TemplateTask(
                title="Ensure test coverage",
                description="Verify adequate tests exist for code being refactored",
                estimated_hours=1.0,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[],
            ),
            TemplateTask(
                title="Plan refactoring approach",
                description="Document the changes to be made",
                estimated_hours=0.5,
                complexity_score=2,
                uncertainty_level="low",
                depends_on_indices=[0],
            ),
            TemplateTask(
                title="Implement refactoring",
                description="Make the code changes incrementally",
                estimated_hours=2.0,
                complexity_score=3,
                uncertainty_level="medium",
                depends_on_indices=[1],
            ),
            TemplateTask(
                title="Verify no regressions",
                description="Run all tests and verify behavior",
                estimated_hours=0.5,
                complexity_score=1,
                uncertainty_level="low",
                depends_on_indices=[2],
            ),
        ],
    ),
]


class TaskTemplateManager:
    """Manager for task templates.

    Handles:
    - Loading and storing templates
    - Retrieving templates by ID or category
    - Applying templates to generate task definitions
    - Registering custom templates
    """

    def __init__(self):
        """Initialize with builtin templates."""
        self.templates: Dict[str, TaskTemplate] = {}

        # Load builtin templates
        for template in BUILTIN_TEMPLATES:
            self.templates[template.id] = template

        logger.info(f"TaskTemplateManager initialized with {len(self.templates)} templates")

    def get_template(self, template_id: str) -> Optional[TaskTemplate]:
        """Get a template by ID.

        Args:
            template_id: Template identifier

        Returns:
            TaskTemplate if found, None otherwise
        """
        return self.templates.get(template_id)

    def list_templates(self, category: Optional[str] = None) -> List[TaskTemplate]:
        """List all available templates.

        Args:
            category: Optional category filter

        Returns:
            List of TaskTemplate objects
        """
        templates = list(self.templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        return sorted(templates, key=lambda t: t.name)

    def get_categories(self) -> List[str]:
        """Get list of all template categories.

        Returns:
            List of category names
        """
        categories = set(t.category for t in self.templates.values())
        return sorted(categories)

    def register_template(self, template: TaskTemplate) -> None:
        """Register a custom template.

        Args:
            template: TaskTemplate to register
        """
        self.templates[template.id] = template
        logger.info(f"Registered template: {template.id}")

    def apply_template(
        self,
        template_id: str,
        context: Dict[str, Any],
        issue_number: str = "1",
    ) -> List[Dict[str, Any]]:
        """Apply a template to generate task definitions.

        Args:
            template_id: ID of template to apply
            context: Context variables for template substitution
            issue_number: Parent issue number for task numbering

        Returns:
            List of task dictionaries ready for creation

        Raises:
            ValueError: If template not found
        """
        template = self.get_template(template_id)
        if not template:
            raise ValueError(f"Template '{template_id}' not found")

        tasks = []
        for idx, template_task in enumerate(template.tasks):
            task_number = f"{issue_number}.{idx + 1}"

            task_dict = {
                "task_number": task_number,
                "title": self._apply_context(template_task.title, context),
                "description": self._apply_context(template_task.description, context),
                "estimated_hours": template_task.estimated_hours,
                "complexity_score": template_task.complexity_score,
                "uncertainty_level": template_task.uncertainty_level,
                "depends_on_indices": template_task.depends_on_indices,
                "tags": template_task.tags,
            }

            tasks.append(task_dict)

        logger.info(f"Applied template '{template_id}': generated {len(tasks)} tasks")
        return tasks

    def calculate_template_hours(self, template: TaskTemplate) -> float:
        """Calculate total estimated hours for a template.

        Args:
            template: TaskTemplate to calculate

        Returns:
            Total hours
        """
        return template.total_estimated_hours

    def _apply_context(self, text: str, context: Dict[str, Any]) -> str:
        """Apply context variables to text.

        Simple placeholder replacement using {variable} syntax.

        Args:
            text: Text with optional placeholders
            context: Context variables

        Returns:
            Text with placeholders replaced
        """
        result = text
        for key, value in context.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value))
        return result
