"""V2 Templates router - delegates to core modules.

This module provides v2-style API endpoints for template management that
delegate to core/templates.py. It uses the v2 Workspace model.

The v1 router (templates.py) remains for backwards compatibility.
"""

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import templates
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/templates", tags=["templates-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class TemplateTaskResponse(BaseModel):
    """Response model for a template task."""

    title: str
    description: str
    estimated_hours: float = Field(..., gt=0, description="Estimated hours (must be positive)")
    complexity_score: int = Field(..., ge=1, le=5, description="Complexity rating (1-5)")
    uncertainty_level: Literal["low", "medium", "high"] = Field(
        ..., description="Uncertainty level"
    )
    depends_on_indices: list[int]
    tags: list[str]


class TemplateResponse(BaseModel):
    """Response model for a task template."""

    id: str
    name: str
    description: str
    category: str
    tags: list[str]
    total_estimated_hours: float
    tasks: list[TemplateTaskResponse]


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
    context: dict[str, Any] = Field(default_factory=dict)
    issue_number: str = "1"


class ApplyTemplateResponse(BaseModel):
    """Response model for applied template."""

    template_id: str
    tasks_created: int
    task_ids: list[str]  # v2 uses string UUIDs


class CategoryListResponse(BaseModel):
    """Response model for category list."""

    categories: list[str]


# ============================================================================
# Template Endpoints
# ============================================================================


@router.get("", response_model=list[TemplateListResponse])
@rate_limit_standard()
async def list_templates(
    request: Request,
    category: Optional[str] = Query(None, description="Optional category filter"),
) -> list[TemplateListResponse]:
    """List all available task templates.

    This is the v2 equivalent of `cf templates list`.

    Args:
        category: Optional category filter

    Returns:
        List of templates with basic info
    """
    try:
        template_list = templates.list_templates(category=category)

        return [
            TemplateListResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                category=t.category,
                total_estimated_hours=t.total_estimated_hours,
            )
            for t in template_list
        ]

    except Exception as e:
        logger.error(f"Failed to list templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories", response_model=CategoryListResponse)
@rate_limit_standard()
async def list_categories(request: Request) -> CategoryListResponse:
    """List all template categories.

    Returns:
        List of category names
    """
    try:
        categories = templates.get_categories()
        return CategoryListResponse(categories=categories)

    except Exception as e:
        logger.error(f"Failed to list categories: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{template_id}", response_model=TemplateResponse)
@rate_limit_standard()
async def get_template(
    request: Request,
    template_id: str,
) -> TemplateResponse:
    """Get details for a specific template.

    This is the v2 equivalent of `cf templates show`.

    Args:
        template_id: Template ID

    Returns:
        Template with full details including tasks
    """
    try:
        template = templates.get_template(template_id)

        if not template:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

        return TemplateResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            category=template.category,
            tags=template.tags,
            total_estimated_hours=template.total_estimated_hours,
            tasks=[
                TemplateTaskResponse(
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/apply", response_model=ApplyTemplateResponse)
@rate_limit_standard()
async def apply_template(
    request: Request,
    body: ApplyTemplateRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ApplyTemplateResponse:
    """Apply a template to create tasks for a workspace.

    This is the v2 equivalent of `cf templates apply`.

    Args:
        request: HTTP request for rate limiting
        body: Template application request
        workspace: v2 Workspace

    Returns:
        Result with created task IDs
    """
    try:
        result = templates.apply_template(
            workspace=workspace,
            template_id=body.template_id,
            issue_number=body.issue_number,
            context=body.context,
        )

        return ApplyTemplateResponse(
            template_id=result.template_id,
            tasks_created=result.tasks_created,
            task_ids=result.task_ids,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to apply template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
