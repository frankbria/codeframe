"""Task management router.

This module provides API endpoints for:
- Task creation
- Task updates
- Task status management
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.models import Task, TaskStatus
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreateRequest(BaseModel):
    """Request model for creating a task."""
    project_id: int
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    priority: int = Field(default=3, ge=0, le=4)
    status: str = Field(default="pending")
    workflow_step: int = Field(default=1, ge=1)
    depends_on: Optional[str] = None
    requires_mcp: bool = False


@router.post("", status_code=201)
async def create_task(
    request: TaskCreateRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new task.

    Args:
        request: Task creation request
        db: Database connection
        current_user: Authenticated user

    Returns:
        Created task details

    Raises:
        HTTPException:
            - 403: Access denied (user doesn't have access to project)
            - 404: Project not found
    """
    # Verify project exists
    project = db.get_project(request.project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {request.project_id} not found"
        )

    # Authorization check - user must have access to the project
    if not db.user_has_project_access(current_user.id, request.project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Create task
    try:
        task = Task(
            id=None,  # Will be assigned by database
            project_id=request.project_id,
            title=request.title,
            description=request.description,
            status=TaskStatus(request.status),
            priority=request.priority,
            workflow_step=request.workflow_step,
            depends_on=request.depends_on,
            requires_mcp=request.requires_mcp,
        )

        task_id = db.create_task(task)

        # Fetch created task
        created_task = db.get_task(task_id)

        return {
            "id": created_task.id,
            "project_id": created_task.project_id,
            "title": created_task.title,
            "description": created_task.description,
            "status": created_task.status.value,
            "priority": created_task.priority,
            "workflow_step": created_task.workflow_step,
            "depends_on": created_task.depends_on,
            "requires_mcp": created_task.requires_mcp,
            "created_at": created_task.created_at,
        }

    except Exception as e:
        logger.error(f"Error creating task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error creating task")
