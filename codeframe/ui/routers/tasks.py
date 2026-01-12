"""Task management router.

This module provides API endpoints for:
- Task creation
- Task updates
- Task status management
- Task approval (for planning phase automation)
- Multi-agent execution trigger (P0 fix)
"""

import asyncio
import logging
import os
from datetime import datetime, UTC
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.models import Task, TaskStatus
from codeframe.core.phase_manager import PhaseManager
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager
from codeframe.ui.websocket_broadcasts import broadcast_development_started
from codeframe.auth.dependencies import get_current_user
from codeframe.auth.models import User
from codeframe.agents.lead_agent import LeadAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# Also register under project-scoped prefix for task approval
project_router = APIRouter(prefix="/api/projects", tags=["tasks"])


# ============================================================================
# Background Task for Multi-Agent Execution (P0 Fix)
# ============================================================================


async def start_development_execution(
    project_id: int,
    db: Database,
    ws_manager: Any,
    api_key: str
) -> None:
    """
    Background task to start multi-agent execution after task approval.

    This function:
    1. Creates a LeadAgent instance for the project
    2. Calls start_multi_agent_execution() to create agents and assign tasks
    3. Handles errors gracefully with logging and WebSocket notifications

    Workflow:
    - LeadAgent loads all approved tasks from database
    - Builds dependency graph for task ordering
    - Creates agents on-demand via AgentPoolManager
    - Assigns tasks to agents and executes in parallel
    - Broadcasts agent_created and task_assigned events via WebSocket
    - Continues until all tasks complete or fail

    Args:
        project_id: Project ID to start execution for
        db: Database instance
        ws_manager: WebSocket manager for broadcasts
        api_key: Anthropic API key for agent creation
    """
    try:
        logger.info(f"🚀 Starting multi-agent execution for project {project_id}")

        # Create LeadAgent instance with WebSocket manager for event broadcasts
        lead_agent = LeadAgent(
            project_id=project_id,
            db=db,
            api_key=api_key,
            ws_manager=ws_manager
        )

        # Start multi-agent execution (creates agents and assigns tasks)
        # This is the main coordination loop that:
        # 1. Loads all tasks and builds dependency graph
        # 2. Creates agents on-demand via agent_pool_manager.get_or_create_agent()
        # 3. Assigns tasks to agents and executes in parallel
        # 4. Broadcasts agent_created events when agents are created
        # 5. Broadcasts task_assigned events when tasks are assigned
        # 6. Continues until all tasks complete or fail
        summary = await lead_agent.start_multi_agent_execution(
            max_retries=3,
            max_concurrent=5,
            timeout=300
        )

        logger.info(
            f"✅ Multi-agent execution completed for project {project_id}: "
            f"{summary.get('completed', 0)}/{summary.get('total_tasks', 0)} tasks completed, "
            f"{summary.get('failed', 0)} failed, {summary.get('execution_time', 0):.2f}s"
        )

    except asyncio.TimeoutError:
        logger.error(
            f"❌ Multi-agent execution timed out for project {project_id} after 300s"
        )
        # Broadcast timeout error to UI (guarded to prevent masking original error)
        try:
            await ws_manager.broadcast(
                {
                    "type": "development_failed",
                    "project_id": project_id,
                    "error": "Multi-agent execution timed out after 300 seconds",
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z")
                },
                project_id=project_id
            )
        except Exception:
            logger.exception("Failed to broadcast development_failed (timeout)")
    except Exception as e:
        logger.error(
            f"❌ Failed to start multi-agent execution for project {project_id}: {e}",
            exc_info=True
        )
        # Broadcast error to UI (guarded to prevent masking original error)
        try:
            await ws_manager.broadcast(
                {
                    "type": "development_failed",
                    "project_id": project_id,
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z")
                },
                project_id=project_id
            )
        except Exception:
            logger.exception("Failed to broadcast development_failed (error)")


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
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskApprovalResponse:
    """Approve tasks and transition project to development phase.

    This endpoint allows users to approve generated tasks after reviewing them.
    Approved tasks are updated to 'pending' status and the project phase
    transitions to 'active' (development). After approval, multi-agent execution
    is triggered in the background.

    Args:
        project_id: Project ID
        request: Approval request with approved flag and optional exclusions
        background_tasks: FastAPI background tasks for async execution
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
    # Note: Excluded tasks remain unchanged in the database for audit trail.
    # They are not deleted or modified - users can re-include them later if needed.
    excluded_ids = set(request.excluded_task_ids)
    approved_tasks = [t for t in tasks if t.id not in excluded_ids]
    excluded_tasks = [t for t in tasks if t.id in excluded_ids]

    # Transition project phase to active FIRST (fails early before modifying tasks)
    # This ensures we don't leave tasks in pending status if phase transition fails
    try:
        PhaseManager.transition(project_id, "active", db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to transition phase for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to transition project to development phase"
        )

    # Update approved tasks to pending status (after phase transition succeeds)
    for task in approved_tasks:
        db.update_task(task.id, {"status": "pending"})

    # Broadcast development started event
    await broadcast_development_started(
        manager=manager,
        project_id=project_id,
        approved_count=len(approved_tasks),
        excluded_count=len(excluded_tasks),
    )

    # START MULTI-AGENT EXECUTION IN BACKGROUND
    # Schedule background task to create agents and start task execution
    # This follows the same pattern as start_project_agent in agents.py
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        # Schedule background task to start multi-agent execution
        background_tasks.add_task(
            start_development_execution,
            project_id,
            db,
            manager,
            api_key
        )
        logger.info(f"✅ Scheduled multi-agent execution for project {project_id}")
    else:
        logger.warning(
            f"⚠️  ANTHROPIC_API_KEY not configured - cannot start agents for project {project_id}"
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


# ============================================================================
# Task Assignment Endpoint (Issue #248 - Manual trigger for stuck tasks)
# ============================================================================


class TaskAssignmentResponse(BaseModel):
    """Response model for task assignment."""
    success: bool
    pending_count: int
    message: str


@project_router.post("/{project_id}/tasks/assign")
async def assign_pending_tasks(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskAssignmentResponse:
    """Manually trigger task assignment for pending unassigned tasks.

    This endpoint allows users to restart the multi-agent execution process
    when tasks are stuck in 'pending' state with no agent assigned. This can
    happen when:
    - User joins a session after the initial execution completed/failed
    - The original execution timed out or crashed
    - WebSocket messages were missed

    Args:
        project_id: Project ID
        background_tasks: FastAPI background tasks for async execution
        db: Database connection
        current_user: Authenticated user

    Returns:
        TaskAssignmentResponse with pending task count and status

    Raises:
        HTTPException:
            - 400: Project not in active phase
            - 403: Access denied
            - 404: Project not found
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

    # Validate project is in active phase (development)
    current_phase = project.get("phase", "discovery")
    if current_phase != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in active (development) phase to assign tasks. Current phase: {current_phase}"
        )

    # Get all tasks and count pending unassigned ones
    tasks = db.get_project_tasks(project_id)
    pending_unassigned = [
        t for t in tasks
        if t.status == TaskStatus.PENDING and not t.assigned_to
    ]
    pending_count = len(pending_unassigned)

    if pending_count == 0:
        # Debug logging to help diagnose why tasks might appear stuck
        logger.debug(
            f"assign_pending_tasks called for project {project_id} but found 0 pending unassigned tasks. "
            f"Total tasks: {len(tasks)}, statuses: {[t.status.value for t in tasks]}"
        )
        return TaskAssignmentResponse(
            success=True,
            pending_count=0,
            message="No pending unassigned tasks to assign."
        )

    # Check if execution is already in progress (Phase 1 fix for concurrent execution)
    # Include ASSIGNED status to prevent race between assignment and execution start
    executing_tasks = [
        t for t in tasks
        if t.status in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]
    ]
    if executing_tasks:
        logger.info(
            f"⏳ Execution already in progress for project {project_id}: "
            f"{len(executing_tasks)} tasks assigned/running"
        )
        return TaskAssignmentResponse(
            success=True,
            pending_count=pending_count,
            message=f"Execution already in progress ({len(executing_tasks)} task(s) assigned/running). Please wait."
        )

    # Schedule multi-agent execution in background
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning(
            f"⚠️  ANTHROPIC_API_KEY not configured - cannot assign tasks for project {project_id}"
        )
        return TaskAssignmentResponse(
            success=False,
            pending_count=pending_count,
            message="Cannot assign tasks: API key not configured. Please contact administrator."
        )

    background_tasks.add_task(
        start_development_execution,
        project_id,
        db,
        manager,
        api_key
    )
    logger.info(f"✅ Scheduled task assignment for project {project_id} ({pending_count} pending tasks)")

    return TaskAssignmentResponse(
        success=True,
        pending_count=pending_count,
        message=f"Assignment started for {pending_count} pending task(s)."
    )
