"""V2 Task execution router - delegates to core modules.

This module provides v2-style API endpoints for task management that delegate
to core/runtime.py and core/conductor.py. It uses the v2 Workspace model and
is designed to work alongside the v1 tasks router during migration.

Key differences from v1:
- Uses Workspace (path-based) instead of project_id
- Delegates to core/runtime and core/conductor functions
- No LeadAgent dependency for execution
- Uses conductor.start_batch() for parallel execution

The v1 router (tasks.py) remains for backwards compatibility with
existing web UI until Phase 3 (Web UI Rebuild).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.core import runtime, tasks, conductor
from codeframe.core.state_machine import TaskStatus
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tasks", tags=["tasks-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ApproveTasksRequest(BaseModel):
    """Request for task approval."""

    excluded_task_ids: list[str] = Field(
        default_factory=list,
        description="Task IDs to exclude from approval",
    )
    start_execution: bool = Field(
        default=False,
        description="Whether to start batch execution after approval",
    )


class ApproveTasksResponse(BaseModel):
    """Response for task approval."""

    success: bool
    approved_count: int
    excluded_count: int
    approved_task_ids: list[str]
    excluded_task_ids: list[str]
    batch_id: Optional[str] = None
    message: str


class AssignmentStatusResponse(BaseModel):
    """Response for assignment status check."""

    pending_count: int
    executing_count: int
    can_assign: bool
    reason: str


class StartExecutionRequest(BaseModel):
    """Request for starting task execution."""

    task_ids: Optional[list[str]] = Field(
        None,
        description="Specific task IDs to execute (defaults to all READY tasks)",
    )
    strategy: str = Field(
        "serial",
        description="Execution strategy: serial, parallel, or auto",
    )
    max_parallel: int = Field(
        4,
        ge=1,
        le=10,
        description="Maximum parallel workers (for parallel/auto strategy)",
    )
    retry_count: int = Field(
        0,
        ge=0,
        le=5,
        description="Number of retries for failed tasks",
    )


class StartExecutionResponse(BaseModel):
    """Response for starting execution."""

    success: bool
    batch_id: str
    task_count: int
    strategy: str
    message: str


class TaskResponse(BaseModel):
    """Response for a single task."""

    id: str
    title: str
    description: str
    status: str
    priority: int
    depends_on: list[str] = []


class TaskListResponse(BaseModel):
    """Response for task list."""

    tasks: list[TaskResponse]
    total: int
    by_status: dict[str, int]


# ============================================================================
# Task List/Status Endpoints
# ============================================================================


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED, FAILED)"),
    limit: int = Query(100, ge=1, le=1000),
    workspace: Workspace = Depends(get_v2_workspace),
) -> TaskListResponse:
    """List tasks in the workspace.

    Args:
        status: Optional status filter
        limit: Maximum tasks to return
        workspace: v2 Workspace

    Returns:
        List of tasks with counts by status
    """
    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = TaskStatus(status.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    f"Invalid status: {status}",
                    ErrorCodes.VALIDATION_ERROR,
                    f"Valid values: {[s.value for s in TaskStatus]}",
                ),
            )

    # Get tasks
    task_list = tasks.list_tasks(workspace, status=status_filter, limit=limit)

    # Get counts by status
    status_counts = tasks.count_by_status(workspace)

    return TaskListResponse(
        tasks=[
            TaskResponse(
                id=t.id,
                title=t.title,
                description=t.description,
                status=t.status.value,
                priority=t.priority,
                depends_on=t.depends_on,
            )
            for t in task_list
        ],
        total=len(task_list),
        by_status=status_counts,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> TaskResponse:
    """Get a specific task by ID.

    Args:
        task_id: Task ID
        workspace: v2 Workspace

    Returns:
        Task details

    Raises:
        HTTPException: 404 if task not found
    """
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
        )

    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority,
        depends_on=task.depends_on,
    )


# ============================================================================
# Task Approval Endpoints
# ============================================================================


@router.post("/approve", response_model=ApproveTasksResponse)
async def approve_tasks_endpoint(
    request: ApproveTasksRequest,
    background_tasks: BackgroundTasks,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ApproveTasksResponse:
    """Approve tasks and optionally start execution.

    Transitions BACKLOG tasks to READY status (excluding specified tasks).
    Optionally triggers batch execution for approved tasks.

    This is the v2 equivalent of POST /api/projects/{id}/tasks/approve.

    Args:
        request: Approval request with exclusions and execution flag
        background_tasks: FastAPI background tasks
        workspace: v2 Workspace

    Returns:
        Approval result with counts and optional batch ID
    """
    try:
        # Approve tasks (transition BACKLOG → READY)
        result = runtime.approve_tasks(
            workspace,
            excluded_task_ids=request.excluded_task_ids,
        )

        batch_id = None
        message = f"Approved {result.approved_count} task(s)."

        if result.approved_count == 0:
            return ApproveTasksResponse(
                success=True,
                approved_count=0,
                excluded_count=result.excluded_count,
                approved_task_ids=[],
                excluded_task_ids=result.excluded_task_ids,
                batch_id=None,
                message="No tasks to approve (no BACKLOG tasks found).",
            )

        # Optionally start execution
        if request.start_execution:
            batch = conductor.start_batch(
                workspace,
                task_ids=result.approved_task_ids,
                strategy="serial",
                max_parallel=4,
                on_failure="continue",
            )
            batch_id = batch.id
            message = f"Approved {result.approved_count} task(s) and started execution (batch {batch_id[:8]})."

        return ApproveTasksResponse(
            success=True,
            approved_count=result.approved_count,
            excluded_count=result.excluded_count,
            approved_task_ids=result.approved_task_ids,
            excluded_task_ids=result.excluded_task_ids,
            batch_id=batch_id,
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to approve tasks: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Approval failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/assignment-status", response_model=AssignmentStatusResponse)
async def get_assignment_status(
    workspace: Workspace = Depends(get_v2_workspace),
) -> AssignmentStatusResponse:
    """Check if tasks can be assigned for execution.

    Returns the current execution status and whether new tasks can be assigned.

    This is the v2 equivalent of checking before POST /api/projects/{id}/tasks/assign.

    Args:
        workspace: v2 Workspace

    Returns:
        Assignment status with pending/executing counts
    """
    status = runtime.check_assignment_status(workspace)
    return AssignmentStatusResponse(
        pending_count=status.pending_count,
        executing_count=status.executing_count,
        can_assign=status.can_assign,
        reason=status.reason,
    )


# ============================================================================
# Task Execution Endpoints
# ============================================================================


@router.post("/execute", response_model=StartExecutionResponse)
async def start_execution(
    request: StartExecutionRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> StartExecutionResponse:
    """Start task execution.

    Triggers batch execution for specified tasks or all READY tasks.

    This is the v2 equivalent of POST /api/projects/{id}/tasks/assign.

    Args:
        request: Execution request with task IDs and strategy
        workspace: v2 Workspace

    Returns:
        Execution result with batch ID

    Raises:
        HTTPException:
            - 400: No tasks to execute or execution already in progress
            - 500: Execution error
    """
    try:
        # Check assignment status first
        status = runtime.check_assignment_status(workspace)
        if not status.can_assign:
            raise HTTPException(
                status_code=400,
                detail=api_error("Cannot execute", ErrorCodes.INVALID_STATE, status.reason),
            )

        # Get task IDs
        task_ids = request.task_ids or runtime.get_ready_task_ids(workspace)
        if not task_ids:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    "No tasks to execute",
                    ErrorCodes.INVALID_REQUEST,
                    "Approve tasks first with POST /api/v2/tasks/approve",
                ),
            )

        # Start batch execution
        batch = conductor.start_batch(
            workspace,
            task_ids=task_ids,
            strategy=request.strategy,
            max_parallel=request.max_parallel,
            retry_count=request.retry_count,
            on_failure="continue",
        )

        return StartExecutionResponse(
            success=True,
            batch_id=batch.id,
            task_count=len(task_ids),
            strategy=request.strategy,
            message=f"Started execution for {len(task_ids)} task(s) (batch {batch.id[:8]}).",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Execution failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/{task_id}/start")
async def start_single_task(
    task_id: str,
    execute: bool = Query(False, description="Run agent execution (requires ANTHROPIC_API_KEY)"),
    dry_run: bool = Query(False, description="Preview changes without making them"),
    verbose: bool = Query(False, description="Show detailed progress output"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Start a single task run.

    Creates a run record and optionally executes the agent.

    This is the v2 equivalent of `cf work start <task-id>`.

    Args:
        task_id: Task to start
        execute: Whether to run agent execution
        dry_run: Preview mode (no actual changes)
        verbose: Show detailed output
        workspace: v2 Workspace

    Returns:
        Run details

    Raises:
        HTTPException:
            - 400: Task already has active run
            - 404: Task not found
            - 500: Execution error
    """
    try:
        # Start the run
        run = runtime.start_task_run(workspace, task_id)

        result = {
            "success": True,
            "run_id": run.id,
            "task_id": task_id,
            "status": run.status.value,
            "message": f"Started run {run.id[:8]} for task {task_id[:8]}.",
        }

        if execute:
            # Execute agent synchronously (for API, might want to make this async/background)
            state = runtime.execute_agent(
                workspace,
                run,
                dry_run=dry_run,
                verbose=verbose,
            )
            result["agent_status"] = state.status.value if hasattr(state.status, 'value') else str(state.status)
            result["message"] = f"Execution completed with status: {result['agent_status']}"

        return result

    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Task not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        raise HTTPException(
            status_code=400,
            detail=api_error("Invalid request", ErrorCodes.INVALID_REQUEST, error_msg),
        )
    except Exception as e:
        logger.error(f"Failed to start task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Start failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/{task_id}/stop")
async def stop_task(
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Stop a running task.

    Marks the run as failed and transitions task back to READY.

    This is the v2 equivalent of `cf work stop <task-id>`.

    Args:
        task_id: Task to stop
        workspace: v2 Workspace

    Returns:
        Stop result

    Raises:
        HTTPException:
            - 400: No active run for task
            - 404: Task not found
    """
    try:
        run = runtime.stop_run(workspace, task_id)
        return {
            "success": True,
            "run_id": run.id,
            "task_id": task_id,
            "status": run.status.value,
            "message": f"Stopped run {run.id[:8]} for task {task_id[:8]}.",
        }
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Run not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        raise HTTPException(
            status_code=400,
            detail=api_error("Cannot stop", ErrorCodes.INVALID_STATE, error_msg),
        )


@router.post("/{task_id}/resume")
async def resume_task(
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Resume a blocked task.

    This is the v2 equivalent of `cf work resume <task-id>`.

    Args:
        task_id: Task to resume
        workspace: v2 Workspace

    Returns:
        Resume result

    Raises:
        HTTPException:
            - 400: Run not blocked
            - 404: No active run for task
    """
    try:
        run = runtime.resume_run(workspace, task_id)
        return {
            "success": True,
            "run_id": run.id,
            "task_id": task_id,
            "status": run.status.value,
            "message": f"Resumed run {run.id[:8]} for task {task_id[:8]}.",
        }
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=api_error("Run not found", ErrorCodes.NOT_FOUND, error_msg),
            )
        raise HTTPException(
            status_code=400,
            detail=api_error("Cannot resume", ErrorCodes.INVALID_STATE, error_msg),
        )
