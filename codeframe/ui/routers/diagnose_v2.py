"""V2 Diagnose router - delegates to core/diagnostic_agent module.

This module provides v2-style API endpoints for task diagnosis.
Diagnosis analyzes failed runs to identify root causes and recommendations.

Routes:
    POST /api/v2/tasks/{id}/diagnose - Diagnose a failed task
    GET  /api/v2/tasks/{id}/diagnose - Get existing diagnostic report
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.core import tasks, runtime
from codeframe.core.diagnostics import (
    DiagnosticReport,
    get_latest_diagnostic_report,
)
from codeframe.core.diagnostic_agent import DiagnosticAgent
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tasks", tags=["diagnose-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class RecommendationResponse(BaseModel):
    """Response for a diagnostic recommendation."""

    title: str
    description: str
    action: str  # RemediationAction value
    priority: int
    command: Optional[str]


class DiagnosticReportResponse(BaseModel):
    """Response for a diagnostic report."""

    id: str
    task_id: str
    run_id: str
    failure_category: str
    severity: str
    root_cause: str
    log_summary: str
    error_messages: list[str]
    recommendations: list[RecommendationResponse]
    has_blocker: bool
    analyzed_at: str


class DiagnoseRequest(BaseModel):
    """Request for running diagnosis."""

    force: bool = Field(False, description="Force re-analysis even if report exists")


# ============================================================================
# Helper Functions
# ============================================================================


def _report_to_response(report: DiagnosticReport) -> DiagnosticReportResponse:
    """Convert a DiagnosticReport to a DiagnosticReportResponse."""
    return DiagnosticReportResponse(
        id=report.id,
        task_id=report.task_id,
        run_id=report.run_id,
        failure_category=report.failure_category.value,
        severity=report.severity.value,
        root_cause=report.root_cause,
        log_summary=report.log_summary,
        error_messages=report.error_messages,
        recommendations=[
            RecommendationResponse(
                title=rec.title,
                description=rec.description,
                action=rec.action.value,
                priority=rec.priority,
                command=rec.command,
            )
            for rec in report.recommendations
        ],
        has_blocker=report.has_blocker,
        analyzed_at=report.analyzed_at.isoformat(),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/{task_id}/diagnose", response_model=DiagnosticReportResponse)
async def diagnose_task(
    task_id: str,
    request: DiagnoseRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
) -> DiagnosticReportResponse:
    """Diagnose a failed task and generate recommendations.

    Analyzes run logs to identify the root cause of failure and
    provides actionable recommendations to fix the issue.

    Args:
        task_id: Task ID to diagnose
        request: Diagnosis options
        workspace: v2 Workspace

    Returns:
        Diagnostic report with analysis and recommendations

    Raises:
        HTTPException:
            - 404: Task not found or no failed run
            - 400: Task has no failed runs
    """
    force = request.force if request else False

    try:
        # Find task
        task = tasks.get(workspace, task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
            )

        # Find the most recent failed run
        runs = runtime.list_runs(workspace, task_id=task.id)
        failed_runs = [r for r in runs if r.status == runtime.RunStatus.FAILED]

        if not failed_runs:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    "No failed runs",
                    ErrorCodes.INVALID_STATE,
                    f"Task '{task.title}' has no failed runs to diagnose",
                ),
            )

        latest_run = failed_runs[0]  # Most recent failed run

        # Check for existing report
        existing_report = get_latest_diagnostic_report(workspace, run_id=latest_run.id)

        if existing_report and not force:
            return _report_to_response(existing_report)

        # Run diagnostic analysis
        agent = DiagnosticAgent(workspace)
        report = agent.analyze(task.id, latest_run.id)

        return _report_to_response(report)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to diagnose task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Diagnosis failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/{task_id}/diagnose", response_model=DiagnosticReportResponse)
async def get_diagnostic_report(
    task_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> DiagnosticReportResponse:
    """Get the latest diagnostic report for a task.

    Returns the most recent diagnostic report without running new analysis.
    Use POST to run a new analysis.

    Args:
        task_id: Task ID to get report for
        workspace: v2 Workspace

    Returns:
        Latest diagnostic report

    Raises:
        HTTPException:
            - 404: Task not found or no diagnostic report exists
    """
    # Find task
    task = tasks.get(workspace, task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=api_error("Task not found", ErrorCodes.NOT_FOUND, f"No task with id {task_id}"),
        )

    # Get latest report for this task
    report = get_latest_diagnostic_report(workspace, task_id=task.id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "No diagnostic report",
                ErrorCodes.NOT_FOUND,
                f"No diagnostic report exists for task '{task.title}'. Run POST /diagnose first.",
            ),
        )

    return _report_to_response(report)
