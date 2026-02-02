"""Task template management for CodeFRAME v2.

This module provides v2-compatible wrappers around the template functionality.
It bridges v2 Workspace/Task models with the TaskTemplateManager.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

from codeframe.core.workspace import Workspace
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.planning.task_templates import TaskTemplateManager

logger = logging.getLogger(__name__)


# ============================================================================
# V2-Compatible Data Classes
# ============================================================================


@dataclass
class TemplateInfo:
    """Summary information about a template (v2 compatible)."""

    id: str
    name: str
    description: str
    category: str
    total_estimated_hours: float


@dataclass
class TemplateTaskInfo:
    """Information about a task within a template (v2 compatible)."""

    title: str
    description: str
    estimated_hours: float
    complexity_score: int
    uncertainty_level: Literal["low", "medium", "high"]
    depends_on_indices: list[int]
    tags: list[str]


@dataclass
class TemplateDetails:
    """Full details of a template including tasks (v2 compatible)."""

    id: str
    name: str
    description: str
    category: str
    tags: list[str]
    total_estimated_hours: float
    tasks: list[TemplateTaskInfo]


@dataclass
class ApplyTemplateResult:
    """Result of applying a template (v2 compatible)."""

    template_id: str
    tasks_created: int
    task_ids: list[str]  # v2 uses string UUIDs


# ============================================================================
# Template Functions
# ============================================================================


def list_templates(category: Optional[str] = None) -> list[TemplateInfo]:
    """List all available task templates.

    Args:
        category: Optional category filter

    Returns:
        List of TemplateInfo with basic info
    """
    manager = TaskTemplateManager()
    templates = manager.list_templates(category=category)

    return [
        TemplateInfo(
            id=t.id,
            name=t.name,
            description=t.description,
            category=t.category,
            total_estimated_hours=t.total_estimated_hours,
        )
        for t in templates
    ]


def get_template(template_id: str) -> Optional[TemplateDetails]:
    """Get details for a specific template.

    Args:
        template_id: Template ID

    Returns:
        TemplateDetails with full information, or None if not found
    """
    manager = TaskTemplateManager()
    template = manager.get_template(template_id)

    if not template:
        return None

    return TemplateDetails(
        id=template.id,
        name=template.name,
        description=template.description,
        category=template.category,
        tags=template.tags,
        total_estimated_hours=template.total_estimated_hours,
        tasks=[
            TemplateTaskInfo(
                title=task.title,
                description=task.description,
                estimated_hours=task.estimated_hours,
                complexity_score=task.complexity_score,
                uncertainty_level=task.uncertainty_level,
                depends_on_indices=task.depends_on_indices,
                tags=task.tags,
            )
            for task in template.tasks
        ],
    )


def get_categories() -> list[str]:
    """List all template categories.

    Returns:
        List of category names
    """
    manager = TaskTemplateManager()
    return manager.get_categories()


def apply_template(
    workspace: Workspace,
    template_id: str,
    issue_number: str = "1",
    context: Optional[dict[str, Any]] = None,
) -> ApplyTemplateResult:
    """Apply a template to create tasks in a workspace.

    Creates tasks from the template and adds them to the workspace,
    including dependency relationships.

    Args:
        workspace: Target workspace
        template_id: Template ID to apply
        issue_number: Parent issue number for task numbering
        context: Optional context dict for template variables

    Returns:
        ApplyTemplateResult with created task IDs

    Raises:
        ValueError: If template not found
    """
    manager = TaskTemplateManager()
    template = manager.get_template(template_id)

    if not template:
        raise ValueError(f"Template not found: {template_id}")

    # Apply template to get task definitions
    task_dicts = manager.apply_template(
        template_id=template_id,
        context=context or {},
        issue_number=issue_number,
    )

    # Create tasks using v2 API
    created_tasks: list[tuple[tasks.Task, list[int]]] = []
    for task_dict in task_dicts:
        task = tasks.create(
            workspace,
            title=task_dict["title"],
            description=task_dict["description"],
            status=TaskStatus.BACKLOG,
            estimated_hours=task_dict.get("estimated_hours"),
            complexity_score=task_dict.get("complexity_score"),
            uncertainty_level=task_dict.get("uncertainty_level"),
        )
        created_tasks.append((task, task_dict.get("depends_on_indices", [])))

    # Wire up dependencies using indices -> actual task IDs
    for task, dep_indices in created_tasks:
        if dep_indices:
            # Map 0-based indices to actual task IDs
            depends_on_ids = [
                created_tasks[idx][0].id
                for idx in dep_indices
                if 0 <= idx < len(created_tasks)
            ]
            if depends_on_ids:
                tasks.update_depends_on(workspace, task.id, depends_on_ids)

    created_task_ids = [task.id for task, _ in created_tasks]

    logger.info(
        f"Applied template '{template_id}' to workspace {workspace.id}: "
        f"{len(created_task_ids)} tasks created"
    )

    return ApplyTemplateResult(
        template_id=template_id,
        tasks_created=len(created_task_ids),
        task_ids=created_task_ids,
    )
