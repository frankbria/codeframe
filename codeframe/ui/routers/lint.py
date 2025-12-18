"""Linting endpoints for CodeFRAME.

This module provides API endpoints for running linters (ruff, eslint),
viewing lint results, trends, and configuration.

Sprint 9 Phase 5: T115-T119
"""

from datetime import datetime, UTC
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Depends

from codeframe.persistence.database import Database
from codeframe.testing.lint_runner import LintRunner
from codeframe.ui.dependencies import get_db
from codeframe.ui.shared import manager

router = APIRouter(prefix="/api/lint", tags=["lint"])


@router.get("/results")
async def get_lint_results(task_id: int, db: Database = Depends(get_db)):
    """Get lint results for a specific task (T116).

    Args:
        task_id: Task ID to get lint results for
        db: Database connection (injected)

    Returns:
        List of lint results with error/warning counts and full output

    Example:
        GET /api/lint/results?task_id=123
    """
    results = db.get_lint_results_for_task(task_id)
    return {"task_id": task_id, "results": results}


@router.get("/trend")
async def get_lint_trend(project_id: int, days: int = 7, db: Database = Depends(get_db)):
    """Get lint error trend for project over time (T117).

    Args:
        project_id: Project ID
        days: Number of days to look back (default: 7)
        db: Database connection (injected)

    Returns:
        List of {date, linter, error_count, warning_count} dictionaries

    Example:
        GET /api/lint/trend?project_id=1&days=7
    """
    trend = db.get_lint_trend(project_id, days=days)
    return {"project_id": project_id, "days": days, "trend": trend}


@router.get("/config")
async def get_lint_config(project_id: int, db: Database = Depends(get_db)):
    """Get current lint configuration for project (T118).

    Args:
        project_id: Project ID
        db: Database connection (injected)

    Returns:
        Lint configuration from pyproject.toml and .eslintrc.json

    Example:
        GET /api/lint/config?project_id=1
    """
    # Get project workspace path
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    workspace_path = Path(project.get("workspace_path", "."))

    # Load config using LintRunner
    lint_runner = LintRunner(workspace_path)

    return {
        "project_id": project_id,
        "config": lint_runner.config,
        "has_ruff_config": "ruff" in lint_runner.config,
        "has_eslint_config": "eslint" in lint_runner.config,
    }


@router.post("/run", status_code=202)
async def run_lint_manual(request: Request, db: Database = Depends(get_db)):
    """Trigger manual lint run for specific files or task (T115).

    Args:
        request: FastAPI request object
        db: Database connection (injected)

    Request Body:
        - project_id: int
        - task_id: int (optional)
        - files: list[str] (optional, if not using task_id)

    Returns:
        202 Accepted: Lint results with error/warning counts

    Example:
        POST /api/lint/run
        {
            "project_id": 1,
            "task_id": 123
        }
    """
    data = await request.json()
    project_id = data.get("project_id")
    task_id = data.get("task_id")
    files = data.get("files", [])

    if not project_id:
        raise HTTPException(status_code=422, detail="project_id is required")

    # Get project workspace
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    workspace_path = Path(project.get("workspace_path", "."))

    # Get files to lint
    if task_id:
        # Verify task exists
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        # TODO: Implement task-based file discovery. The Task model doesn't currently
        # track modified files. Options: (1) add files_modified field to Task model,
        # (2) query git diff for commits associated with task, (3) track via changelog.
        # For now, require explicit files list when using task_id.
        if not files:
            raise HTTPException(
                status_code=422,
                detail="Task-based file discovery not yet implemented. Please provide explicit 'files' list."
            )
    elif not files:
        raise HTTPException(status_code=422, detail="Either task_id or files must be provided")

    # Convert to Path objects
    file_paths = [Path(workspace_path) / f for f in files]

    # Broadcast lint started (T119)
    await manager.broadcast(
        {
            "type": "lint_started",
            "project_id": project_id,
            "task_id": task_id,
            "file_count": len(file_paths),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # Run lint
    lint_runner = LintRunner(workspace_path)
    try:
        results = await lint_runner.run_lint(file_paths)
    except Exception as e:
        # Broadcast lint failed (T119)
        await manager.broadcast(
            {
                "type": "lint_failed",
                "project_id": project_id,
                "task_id": task_id,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        raise HTTPException(status_code=500, detail=str(e))

    # Store results if task_id provided
    if task_id:
        for result in results:
            result.task_id = task_id
            db.create_lint_result(
                task_id=result.task_id,
                linter=result.linter,
                error_count=result.error_count,
                warning_count=result.warning_count,
                files_linted=result.files_linted,
                output=result.output,
            )

    # Check quality gate
    has_errors = lint_runner.has_critical_errors(results)

    # Broadcast lint completed (T119)
    total_errors = sum(r.error_count for r in results)
    total_warnings = sum(r.warning_count for r in results)

    await manager.broadcast(
        {
            "type": "lint_completed",
            "project_id": project_id,
            "task_id": task_id,
            "has_errors": has_errors,
            "error_count": total_errors,
            "warning_count": total_warnings,
            "results": [r.to_dict() for r in results],
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # Prepare response
    return {
        "status": "completed",
        "project_id": project_id,
        "task_id": task_id,
        "has_errors": has_errors,
        "results": [
            {
                "linter": r.linter,
                "error_count": r.error_count,
                "warning_count": r.warning_count,
                "files_linted": r.files_linted,
            }
            for r in results
        ],
    }
