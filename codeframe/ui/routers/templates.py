"""Task templates management router.

This module provides API endpoints for:
- Listing available task templates
- Getting template details
- Applying templates to create tasks
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.planning.task_templates import TaskTemplateManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/templates", tags=["templates"])


# ============================================================================
# Response Models
# ============================================================================


class TemplateTaskResponse(BaseModel):
    """Response model for a template task."""

    title: str
    description: str
    estimated_hours: float
    complexity_score: int
    uncertainty_level: str
    depends_on_indices: List[int]
    tags: List[str]


class TemplateResponse(BaseModel):
    """Response model for a task template."""

    id: str
    name: str
    description: str
    category: str
    tags: List[str]
    total_estimated_hours: float
    tasks: List[TemplateTaskResponse]


class TemplateListResponse(BaseModel):
    """Response model for template list."""

    id: str
    name: str
    description: str
    category: str
    total_estimated_hours: float


class ApplyTemplateRequest(BaseModel):
    """Request model for applying a template."""

    template_id: str
    context: Dict[str, Any] = Field(default_factory=dict)
    issue_number: str = "1"


class ApplyTemplateResponse(BaseModel):
    """Response model for applied template."""

    template_id: str
    tasks_created: int
    task_ids: List[int]


class CategoryListResponse(BaseModel):
    """Response model for category list."""

    categories: List[str]


# ============================================================================
# Template Endpoints
# ============================================================================


@router.get("/", response_model=List[TemplateListResponse])
async def list_templates(
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all available task templates.

    Args:
        category: Optional category filter

    Returns:
        List of templates with basic info
    """
    try:
        manager = TaskTemplateManager()
        templates = manager.list_templates(category=category)

        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "total_estimated_hours": t.total_estimated_hours,
            }
            for t in templates
        ]

    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories() -> Dict[str, List[str]]:
    """List all template categories.

    Returns:
        List of category names
    """
    try:
        manager = TaskTemplateManager()
        categories = manager.get_categories()
        return {"categories": categories}

    except Exception as e:
        logger.error(f"Error listing categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
) -> Dict[str, Any]:
    """Get details for a specific template.

    Args:
        template_id: Template ID

    Returns:
        Template with full details including tasks
    """
    try:
        manager = TaskTemplateManager()
        template = manager.get_template(template_id)

        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

        return {
            "id": template.id,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "tags": template.tags,
            "total_estimated_hours": template.total_estimated_hours,
            "tasks": [
                {
                    "title": task.title,
                    "description": task.description,
                    "estimated_hours": task.estimated_hours,
                    "complexity_score": task.complexity_score,
                    "uncertainty_level": task.uncertainty_level,
                    "depends_on_indices": task.depends_on_indices,
                    "tags": task.tags,
                }
                for task in template.tasks
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/apply", response_model=ApplyTemplateResponse)
async def apply_template(
    project_id: int,
    request: ApplyTemplateRequest,
    db: Database = Depends(get_db),
) -> Dict[str, Any]:
    """Apply a template to create tasks for a project.

    Args:
        project_id: Project ID
        request: Template application request
        db: Database connection

    Returns:
        Result with created task IDs
    """
    try:
        manager = TaskTemplateManager()
        template = manager.get_template(request.template_id)

        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template '{request.template_id}' not found"
            )

        # Check project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Get first issue or create one
        issues = db.get_project_issues(project_id)
        if issues:
            issue_id = issues[0].id
        else:
            # Create a default issue for the tasks
            from codeframe.core.models import Issue, TaskStatus

            default_issue = Issue(
                project_id=project_id,
                issue_number=request.issue_number,
                title=f"Tasks from template: {template.name}",
                description=f"Tasks generated from {template.id} template",
                status=TaskStatus.PENDING,
                priority=2,
                workflow_step=1,
            )
            issue_id = db.create_issue(default_issue)

        # Apply template
        task_dicts = manager.apply_template(
            template_id=request.template_id,
            context=request.context,
            issue_number=request.issue_number,
        )

        # Create tasks in database
        created_task_ids = []
        for task_dict in task_dicts:
            from codeframe.core.models import TaskStatus

            task_id = db.create_task_with_issue(
                project_id=project_id,
                issue_id=issue_id,
                task_number=task_dict["task_number"],
                parent_issue_number=request.issue_number,
                title=task_dict["title"],
                description=task_dict["description"],
                status=TaskStatus.PENDING,
                priority=2,
                workflow_step=1,
                can_parallelize=False,
                estimated_hours=task_dict.get("estimated_hours"),
            )
            created_task_ids.append(task_id)

        logger.info(
            f"Applied template '{request.template_id}' to project {project_id}: "
            f"{len(created_task_ids)} tasks created"
        )

        return {
            "template_id": request.template_id,
            "tasks_created": len(created_task_ids),
            "task_ids": created_task_ids,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying template to project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
