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
import threading
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_ai, rate_limit_standard
from codeframe.core import runtime, tasks, conductor, streaming
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
    estimated_hours: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TaskListResponse(BaseModel):
    """Response for task list."""

    tasks: list[TaskResponse]
    total: int
    by_status: dict[str, int]


class UpdateTaskRequest(BaseModel):
    """Request for updating a task."""

    title: Optional[str] = Field(None, min_length=1, description="New task title")
    description: Optional[str] = Field(None, description="New task description")
    priority: Optional[int] = Field(None, ge=0, description="New task priority (0 = highest)")
    status: Optional[str] = Field(None, description="New task status (use for manual transitions)")


# ============================================================================
# Task List/Status Endpoints
# ============================================================================


@router.get("", response_model=TaskListResponse)
@rate_limit_standard()
async def list_tasks(
    request: Request,
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
                estimated_hours=t.estimated_hours,
                created_at=t.created_at.isoformat() if t.created_at else None,
                updated_at=t.updated_at.isoformat() if t.updated_at else None,
            )
            for t in task_list
        ],
        total=len(task_list),
        by_status=status_counts,
    )


@router.get("/{task_id}", response_model=TaskResponse)
@rate_limit_standard()
async def get_task(
    request: Request,
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
        estimated_hours=task.estimated_hours,
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
    )


@router.patch("/{task_id}", response_model=TaskResponse)
@rate_limit_standard()
async def update_task(
    request: Request,
    task_id: str,
    body: UpdateTaskRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> TaskResponse:
    """Update a task's title, description, priority, or status.

    Only provided fields are updated; others are left unchanged.

    Args:
        request: HTTP request for rate limiting
        task_id: Task ID to update
        body: Update request with fields to change
        workspace: v2 Workspace

    Returns:
        Updated task

    Raises:
        HTTPException:
            - 404: Task not found
            - 400: Invalid status or status transition
    """
    try:
        # Handle status update separately if provided
        if body.status:
            try:
                new_status = TaskStatus(body.status.upper())
                tasks.update_status(workspace, task_id, new_status)
            except ValueError as e:
                if "Invalid status" in str(e) or "not a valid" in str(e).lower():
                    raise HTTPException(
                        status_code=400,
                        detail=api_error(
                            f"Invalid status: {body.status}",
                            ErrorCodes.VALIDATION_ERROR,
                            f"Valid values: {[s.value for s in TaskStatus]}",
                        ),
                    )
                # Status transition error
                raise HTTPException(
                    status_code=400,
                    detail=api_error("Invalid status transition", ErrorCodes.INVALID_STATE, str(e)),
                )

        # Update other fields
        task = tasks.update(
            workspace,
            task_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
        )

        return TaskResponse(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            priority=task.priority,
            depends_on=task.depends_on,
            estimated_hours=task.estimated_hours,
            created_at=task.created_at.isoformat() if task.created_at else None,
            updated_at=task.updated_at.isoformat() if task.updated_at else None,
        )

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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Update failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.delete("/{task_id}")
@rate_limit_standard()
async def delete_task(
    request: Request,
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Delete a task.

    Args:
        task_id: Task ID to delete
        workspace: v2 Workspace

    Returns:
        Deletion confirmation

    Raises:
        HTTPException: 404 if task not found
    """
    deleted = tasks.delete(workspace, task_id)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
        )

    return {
        "success": True,
        "message": f"Task {task_id[:8]} deleted successfully",
    }


# ============================================================================
# Task Approval Endpoints
# ============================================================================


@router.post("/approve", response_model=ApproveTasksResponse)
@rate_limit_standard()
async def approve_tasks_endpoint(
    request: Request,
    body: ApproveTasksRequest,
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
            excluded_task_ids=body.excluded_task_ids,
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
        if body.start_execution:
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
@rate_limit_standard()
async def get_assignment_status(
    request: Request,
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
@rate_limit_ai()
async def start_execution(
    request: Request,
    body: StartExecutionRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> StartExecutionResponse:
    """Start task execution.

    Triggers batch execution for specified tasks or all READY tasks.

    This is the v2 equivalent of POST /api/projects/{id}/tasks/assign.

    Args:
        request: HTTP request for rate limiting
        body: Execution request with task IDs and strategy
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
        task_ids = body.task_ids or runtime.get_ready_task_ids(workspace)
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
            strategy=body.strategy,
            max_parallel=body.max_parallel,
            retry_count=body.retry_count,
            on_failure="continue",
        )

        return StartExecutionResponse(
            success=True,
            batch_id=batch.id,
            task_count=len(task_ids),
            strategy=body.strategy,
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
@rate_limit_ai()
async def start_single_task(
    request: Request,
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
            from codeframe.ui.routers.streaming_v2 import get_event_publisher
            from codeframe.core.models import ErrorEvent

            publisher = get_event_publisher()

            def _run_agent():
                try:
                    runtime.execute_agent(
                        workspace,
                        run,
                        dry_run=dry_run,
                        verbose=verbose,
                        event_publisher=publisher,
                    )
                except Exception as exc:
                    logger.error(f"Background agent failed for task {task_id}: {exc}", exc_info=True)
                    publisher.publish_sync(
                        task_id,
                        ErrorEvent(
                            task_id=task_id,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        ),
                    )
                    publisher.complete_task_sync(task_id)

            thread = threading.Thread(target=_run_agent, daemon=True)
            thread.start()

            result["status"] = "executing"
            result["message"] = f"Execution started in background for task {task_id[:8]}. Connect to GET /{task_id}/stream for events."

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
@rate_limit_standard()
async def stop_task(
    request: Request,
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
@rate_limit_ai()
async def resume_task(
    request: Request,
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


# ============================================================================
# Streaming Endpoints
# ============================================================================


@router.get("/{task_id}/output")
@rate_limit_standard()
async def stream_task_output_lines(
    request: Request,
    task_id: str,
    tail: int = Query(0, ge=0, le=1000, description="Show last N lines before streaming"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> StreamingResponse:
    """Stream raw output lines from a running task.

    Returns Server-Sent Events (SSE) with raw text output lines.
    This is the API equivalent of `cf work follow <task-id>`.

    For structured JSON execution events (progress, output, blocker,
    completion, error), use GET /{task_id}/stream instead.

    Event types:
        - `line`: A line of output from the task
        - `info`: Informational message (e.g., "showing last N lines")
        - `error`: Error message
        - `done`: Stream completed (task finished or no more output)

    Args:
        task_id: Task to stream output from
        tail: Number of historical lines to show before live streaming
        workspace: v2 Workspace

    Returns:
        SSE stream of task output

    Raises:
        HTTPException:
            - 404: Task not found or no run exists
    """
    # Get the task first to validate it exists
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
        )

    # Get the active run for this task
    run = runtime.get_active_run(workspace, task_id)

    # If no active run, try to find the most recent completed run
    if not run:
        run = runtime.get_latest_run(workspace, task_id)

    if not run:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "No run found",
                ErrorCodes.NOT_FOUND,
                f"No run exists for task {task_id}. Start the task first with POST /{task_id}/start",
            ),
        )

    def generate_events():
        """Generator that yields SSE events."""
        run_id = run.id
        current_line = 0

        # Check if output exists
        if not streaming.run_output_exists(workspace, run_id):
            yield "event: info\ndata: Waiting for output...\n\n"

        # If tail requested, show historical lines first
        if tail > 0:
            lines, total = streaming.get_latest_lines_with_count(workspace, run_id, tail)
            if lines:
                skipped = total - len(lines)
                if skipped > 0:
                    yield f"event: info\ndata: (skipped {skipped} lines, showing last {len(lines)})\n\n"

                for line in lines:
                    # Remove trailing newline for SSE format
                    yield f"event: line\ndata: {line.rstrip()}\n\n"

                current_line = total

        # Stream new lines as they appear
        # Use a reasonable timeout to allow the connection to close gracefully
        for line in streaming.tail_run_output(
            workspace,
            run_id,
            since_line=current_line,
            poll_interval=0.5,
            max_wait=300.0,  # 5 minute timeout
        ):
            yield f"event: line\ndata: {line.rstrip()}\n\n"

        yield "event: done\ndata: Stream ended\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/{task_id}/stream")
async def stream_task_events(
    request: Request,
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> StreamingResponse:
    """Stream structured execution events for a task via SSE.

    Returns Server-Sent Events with JSON-formatted ExecutionEvent payloads.
    Compatible with browser EventSource (no custom auth headers required).

    Event types (in data.event_type):
        - ``progress``: Phase/step transitions
        - ``output``: stdout/stderr lines
        - ``blocker``: Human input needed
        - ``completion``: Task finished (success/failure/blocked)
        - ``error``: Execution error
        - ``heartbeat``: Keep-alive

    For raw text output lines (cf work follow equivalent),
    use GET /{task_id}/output instead.
    """
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
        )

    from codeframe.ui.routers.streaming_v2 import event_stream_generator, get_event_publisher

    publisher = get_event_publisher()

    return StreamingResponse(
        event_stream_generator(task_id, publisher, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{task_id}/run")
@rate_limit_standard()
async def get_task_run(
    request: Request,
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Get the current or most recent run for a task.

    This is the v2 equivalent of `cf work status <task-id>`.

    Args:
        task_id: Task to get run status for
        workspace: v2 Workspace

    Returns:
        Run details including status, timing, and output availability

    Raises:
        HTTPException:
            - 404: Task not found or no run exists
    """
    # Get the task first to validate it exists
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
        )

    # Get the active run, or fall back to latest run
    run = runtime.get_active_run(workspace, task_id)
    if not run:
        run = runtime.get_latest_run(workspace, task_id)

    if not run:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "No run found",
                ErrorCodes.NOT_FOUND,
                f"No run exists for task {task_id}",
            ),
        )

    # Check if output exists
    has_output = streaming.run_output_exists(workspace, run.id)

    return {
        "success": True,
        "run_id": run.id,
        "task_id": task_id,
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "has_output": has_output,
        "message": f"Run {run.id[:8]} is {run.status.value}",
    }
