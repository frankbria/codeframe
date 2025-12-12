"""Quality gates router for CodeFRAME FastAPI server.

Handles quality gate endpoints including triggering quality gate execution,
retrieving quality gate status, and managing task quality validations.

Sprint 10 Phase 3 endpoints:
- POST /api/tasks/{task_id}/quality-gates - Manually trigger quality gates
- GET /api/tasks/{task_id}/quality-gates - Get quality gate status
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from datetime import datetime, UTC, timezone
import logging
import uuid

from codeframe.ui.models import QualityGatesRequest
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager
from codeframe.persistence.database import Database
from codeframe.lib.quality_gates import QualityGates
from codeframe.core.models import Task, TaskStatus, QualityGateResult, QualityGateFailure, QualityGateType, Severity
from pathlib import Path

# Module logger
logger = logging.getLogger(__name__)

# Create router without prefix since endpoints use full path
router = APIRouter(tags=["quality-gates"])


@router.get("/api/tasks/{task_id}/quality-gates")
async def get_quality_gate_status(task_id: int, db: Database = Depends(get_db)):
    """Get quality gate status for a task (T064).

    Sprint 10 - Phase 3: Quality Gates API

    Returns the quality gate status for a specific task, including which gates
    passed/failed and detailed failure information.

    Args:
        task_id: Task ID to get quality gate status for
        db: Database connection (injected)

    Returns:
        200 OK: Quality gate status
        {
            "task_id": int,
            "status": str,  # 'pending', 'running', 'passed', 'failed', or None
            "failures": [
                {
                    "gate": str,  # 'tests', 'type_check', 'coverage', 'code_review', 'linting'
                    "reason": str,  # Short failure reason
                    "details": str | null,  # Detailed output
                    "severity": str  # 'critical', 'high', 'medium', 'low'
                },
                ...
            ],
            "requires_human_approval": bool,
            "timestamp": str  # ISO timestamp
        }

        404 Not Found: Task not found

    Example:
        GET /api/tasks/42/quality-gates
    """
    # Check if task exists
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get quality gate status from database
    status_data = db.get_quality_gate_status(task_id)

    # Add task_id and timestamp to response
    return {
        "task_id": task_id,
        "status": status_data.get("status"),
        "failures": status_data.get("failures", []),
        "requires_human_approval": status_data.get("requires_human_approval", False),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post("/api/tasks/{task_id}/quality-gates", status_code=202)
async def trigger_quality_gates(
    task_id: int,
    background_tasks: BackgroundTasks,
    request: QualityGatesRequest = QualityGatesRequest(),
    db: Database = Depends(get_db)
):
    """Manually trigger quality gates for a task (T065).

    Sprint 10 - Phase 3: Quality Gates API

    Triggers quality gate execution for a specific task. Runs in background and
    returns immediately with job status. Optionally accepts gate_types to run
    specific gates only.

    Args:
        task_id: Task ID to run quality gates for
        background_tasks: FastAPI background tasks
        request: QualityGatesRequest with optional gate_types list
                Valid gate types: 'tests', 'type_check', 'coverage', 'code_review', 'linting'
        db: Database connection (injected)

    Returns:
        202 Accepted: Quality gates job started
        {
            "job_id": str,
            "task_id": int,
            "status": "running",
            "gate_types": list[str],  # Gates being executed
            "message": str
        }

        400 Bad Request: Invalid gate_types
        404 Not Found: Task not found
        500 Internal Server Error: Missing project workspace or API configuration

    Example:
        POST /api/tasks/42/quality-gates
        Body: {
            "gate_types": ["tests", "coverage"]  # Optional
        }
    """
    # Extract gate_types from request
    gate_types = request.gate_types

    # Validate gate_types if provided
    valid_gate_types = [
        "tests",
        "type_check",
        "coverage",
        "code_review",
        "linting",
    ]
    if gate_types:
        invalid_gates = [g for g in gate_types if g not in valid_gate_types]
        if invalid_gates:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gate types: {invalid_gates}. Valid types: {valid_gate_types}",
            )

    # Check if task exists
    task_data = db.get_task(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get project_id from task
    project_id = task_data.get("project_id")
    if not project_id:
        raise HTTPException(
            status_code=500, detail=f"Task {task_id} has no project_id"
        )

    # Get project workspace path
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=500, detail=f"Project {project_id} not found"
        )

    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Build Task object for quality gates
    task = Task(
        id=task_id,
        project_id=project_id,
        task_number=task_data.get("task_number", "unknown"),
        title=task_data.get("title", ""),
        description=task_data.get("description", ""),
        status=TaskStatus(task_data.get("status", "pending")),
    )

    # Determine which gates to run
    gates_to_run = gate_types if gate_types else ["all"]

    # Capture db_path for background task (don't capture request-scoped db instance)
    db_path = db.db_path

    # Background task to run quality gates
    async def run_quality_gates():
        """Background task to execute quality gates with fresh DB connection."""
        # Create fresh database connection for background task
        task_db = Database(db_path)
        task_db.initialize()

        try:
            logger.info(
                f"Quality gates job {job_id} started for task {task_id}, "
                f"gates={gates_to_run}"
            )

            # Update task status to 'running'
            task_db.update_quality_gate_status(
                task_id=task_id, status="running", failures=[]
            )

            # Broadcast quality_gates_started event
            try:
                await manager.broadcast(
                    {
                        "type": "quality_gates_started",
                        "task_id": task_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "gate_types": gates_to_run,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast quality_gates_started: {e}")

            # Create QualityGates instance
            quality_gates = QualityGates(
                db=task_db,
                project_id=project_id,
                project_root=Path(workspace_path),
            )

            # Run gates based on gate_types
            if not gate_types or "all" in gates_to_run:
                # Run all gates
                result = await quality_gates.run_all_gates(task)
            else:
                # Run specific gates
                all_failures = []
                execution_start = datetime.now(timezone.utc)

                gate_method_map = {
                    "tests": quality_gates.run_tests_gate,
                    "type_check": quality_gates.run_type_check_gate,
                    "coverage": quality_gates.run_coverage_gate,
                    "code_review": quality_gates.run_review_gate,
                    "linting": quality_gates.run_linting_gate,
                }

                for gate_type in gate_types:
                    gate_method = gate_method_map.get(gate_type)
                    if gate_method:
                        gate_result = await gate_method(task)
                        all_failures.extend(gate_result.failures)

                execution_time = (
                    datetime.now(timezone.utc) - execution_start
                ).total_seconds()
                status = "passed" if len(all_failures) == 0 else "failed"

                result = QualityGateResult(
                    task_id=task_id,
                    status=status,
                    failures=all_failures,
                    execution_time_seconds=execution_time,
                )

                # Update database with final result
                task_db.update_quality_gate_status(
                    task_id=task_id, status=status, failures=all_failures
                )

            # Broadcast completion event
            try:
                event_type = (
                    "quality_gates_passed"
                    if result.passed
                    else "quality_gates_failed"
                )
                await manager.broadcast(
                    {
                        "type": event_type,
                        "task_id": task_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "status": result.status,
                        "failures_count": len(result.failures),
                        "execution_time_seconds": result.execution_time_seconds,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast quality_gates_completed: {e}")

            logger.info(
                f"Quality gates job {job_id} completed: "
                f"status={result.status}, failures={len(result.failures)}"
            )

        except Exception as e:
            logger.error(
                f"Quality gates job {job_id} failed: {e}", exc_info=True
            )

            # Update status to 'failed' with error
            error_failure = QualityGateFailure(
                gate=QualityGateType.TESTS,  # Generic gate type for errors
                reason=f"Quality gates execution failed: {str(e)}",
                details=str(e),
                severity=Severity.CRITICAL,
            )

            task_db.update_quality_gate_status(
                task_id=task_id, status="failed", failures=[error_failure]
            )

            # Broadcast failure event
            try:
                await manager.broadcast(
                    {
                        "type": "quality_gates_error",
                        "task_id": task_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "error": str(e),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as broadcast_error:
                logger.warning(
                    f"Failed to broadcast quality_gates_error: {broadcast_error}"
                )

        finally:
            # Always close the database connection
            if task_db and task_db.conn:
                task_db.close()

    # Add background task
    background_tasks.add_task(run_quality_gates)

    # Return 202 Accepted immediately
    return {
        "job_id": job_id,
        "task_id": task_id,
        "status": "running",
        "gate_types": gates_to_run,
        "message": f"Quality gates execution started for task {task_id}",
    }
