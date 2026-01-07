"""Task management router.

This module provides API endpoints for:
- Task creation
- Task updates
- Task status management
- Task approval (for planning phase automation)
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.models import Task, TaskStatus
from codeframe.core.phase_manager import PhaseManager
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager
from codeframe.ui.websocket_broadcasts import broadcast_development_started
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Also register under project-scoped prefix for task approval
project_router = APIRouter(prefix="/api/projects", tags=["tasks"])


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


# ============================================================================
# Task Approval Models and Endpoint (Feature: 016-planning-phase-automation)
# ============================================================================


class TaskApprovalRequest(BaseModel):
    """Request model for task approval."""
    approved: bool
    excluded_task_ids: List[int] = Field(default_factory=list)


class TaskApprovalResponse(BaseModel):
    """Response model for task approval."""
    success: bool
    phase: str
    approved_count: int
    excluded_count: int
    message: str


@project_router.post("/{project_id}/tasks/approve")
async def approve_tasks(
    project_id: int,
    request: TaskApprovalRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskApprovalResponse:
    """Approve tasks and transition project to development phase.

    This endpoint allows users to approve generated tasks after reviewing them.
    Approved tasks are updated to 'pending' status and the project phase
    transitions to 'active' (development).

    Args:
        project_id: Project ID
        request: Approval request with approved flag and optional exclusions
        db: Database connection
        current_user: Authenticated user

    Returns:
        TaskApprovalResponse with summary of approval

    Raises:
        HTTPException:
            - 400: Project not in planning phase
            - 403: Access denied
            - 404: Project or tasks not found
    """
    # Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if user is rejecting
    if not request.approved:
        return TaskApprovalResponse(
            success=False,
            phase=project.get("phase", "planning"),
            approved_count=0,
            excluded_count=0,
            message="Tasks were not approved. Please review and modify tasks before approving."
        )

    # Validate project is in planning phase
    current_phase = project.get("phase", "discovery")
    if current_phase != "planning":
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in planning phase to approve tasks. Current phase: {current_phase}"
        )

    # Get all tasks for the project
    tasks = db.get_project_tasks(project_id)
    if not tasks:
        raise HTTPException(
            status_code=404,
            detail="No tasks found for this project. Generate tasks before approving."
        )

    # Separate approved and excluded tasks
    excluded_ids = set(request.excluded_task_ids)
    approved_tasks = [t for t in tasks if t.id not in excluded_ids]
    excluded_tasks = [t for t in tasks if t.id in excluded_ids]

    # Update approved tasks to pending status
    for task in approved_tasks:
        db.update_task(task.id, {"status": "pending"})

    # Transition project phase to active (development)
    try:
        PhaseManager.transition(project_id, "active", db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to transition phase for project {project_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to transition project to development phase"
        )

    # Broadcast development started event
    await broadcast_development_started(
        manager=manager,
        project_id=project_id,
        approved_count=len(approved_tasks),
        excluded_count=len(excluded_tasks),
    )

    logger.info(
        f"Tasks approved for project {project_id}: "
        f"{len(approved_tasks)} approved, {len(excluded_tasks)} excluded"
    )

    return TaskApprovalResponse(
        success=True,
        phase="active",
        approved_count=len(approved_tasks),
        excluded_count=len(excluded_tasks),
        message=f"Successfully approved {len(approved_tasks)} tasks. Development phase started."
    )
