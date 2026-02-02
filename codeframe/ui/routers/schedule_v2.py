"""V2 Schedule router - delegates to core modules.

This module provides v2-style API endpoints for schedule management that
delegate to core/schedule.py. It uses the v2 Workspace model.

The v1 router (schedule.py) remains for backwards compatibility.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from codeframe.core.workspace import Workspace
from codeframe.core import schedule
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/schedule", tags=["schedule-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class TaskAssignmentResponse(BaseModel):
    """Response model for a single task assignment."""

    task_id: str
    title: str
    start_time: float
    end_time: float
    assigned_agent: Optional[int] = None


class ScheduleResponse(BaseModel):
    """Response model for project schedule."""

    task_assignments: list[TaskAssignmentResponse]
    total_duration: float
    agents_used: int


class CompletionPredictionResponse(BaseModel):
    """Response model for completion prediction."""

    predicted_date: str
    remaining_hours: float
    completed_percentage: float
    confidence_interval: dict[str, str]


class BottleneckResponse(BaseModel):
    """Response model for a scheduling bottleneck."""

    task_id: str
    task_title: str
    bottleneck_type: str
    impact_hours: float
    recommendation: str


# ============================================================================
# Schedule Endpoints
# ============================================================================


@router.get("", response_model=ScheduleResponse)
async def get_schedule(
    agents: int = Query(1, ge=1, le=10, description="Number of parallel agents/workers"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> ScheduleResponse:
    """Get the schedule for a workspace.

    Uses Critical Path Method to assign start/end times while
    respecting dependency constraints and agent availability.

    This is the v2 equivalent of `cf schedule show`.

    Args:
        agents: Number of parallel agents/workers (default: 1)
        workspace: v2 Workspace

    Returns:
        Schedule with task assignments
    """
    try:
        result = schedule.get_schedule(workspace, agents=agents)

        return ScheduleResponse(
            task_assignments=[
                TaskAssignmentResponse(
                    task_id=a.task_id,
                    title=a.title,
                    start_time=a.start_time,
                    end_time=a.end_time,
                    assigned_agent=a.assigned_agent,
                )
                for a in result.task_assignments
            ],
            total_duration=result.total_duration,
            agents_used=result.agents_used,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=api_error("Schedule not found", ErrorCodes.NOT_FOUND, str(e)),
        )
    except Exception as e:
        logger.error(f"Failed to get schedule: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get schedule", ErrorCodes.INTERNAL_ERROR, str(e)),
        )


@router.get("/predict", response_model=CompletionPredictionResponse)
async def predict_completion(
    hours_per_day: float = Query(8.0, gt=0, le=24, description="Working hours per day"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> CompletionPredictionResponse:
    """Predict project completion date.

    This is the v2 equivalent of `cf schedule predict`.

    Args:
        hours_per_day: Working hours per day (default: 8)
        workspace: v2 Workspace

    Returns:
        Completion prediction with confidence interval
    """
    try:
        result = schedule.predict_completion(workspace, hours_per_day=hours_per_day)

        return CompletionPredictionResponse(
            predicted_date=result.predicted_date.isoformat(),
            remaining_hours=result.remaining_hours,
            completed_percentage=result.completed_percentage,
            confidence_interval={
                "early": result.confidence_early.isoformat(),
                "late": result.confidence_late.isoformat(),
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=api_error("Prediction failed", ErrorCodes.NOT_FOUND, str(e)),
        )
    except Exception as e:
        logger.error(f"Failed to predict completion: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to predict completion", ErrorCodes.INTERNAL_ERROR, str(e)),
        )


@router.get("/bottlenecks", response_model=list[BottleneckResponse])
async def get_bottlenecks(
    workspace: Workspace = Depends(get_v2_workspace),
) -> list[BottleneckResponse]:
    """Identify scheduling bottlenecks for a workspace.

    Identifies:
    - Long duration tasks on critical path
    - Tasks with many dependents causing delays
    - Resource constraints limiting parallelization

    This is the v2 equivalent of `cf schedule bottlenecks`.

    Args:
        workspace: v2 Workspace

    Returns:
        List of identified bottlenecks with recommendations
    """
    try:
        bottlenecks = schedule.get_bottlenecks(workspace)

        return [
            BottleneckResponse(
                task_id=bn.task_id,
                task_title=bn.task_title,
                bottleneck_type=bn.bottleneck_type,
                impact_hours=bn.impact_hours,
                recommendation=bn.recommendation,
            )
            for bn in bottlenecks
        ]

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=api_error("Bottlenecks not found", ErrorCodes.NOT_FOUND, str(e)),
        )
    except Exception as e:
        logger.error(f"Failed to get bottlenecks: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get bottlenecks", ErrorCodes.INTERNAL_ERROR, str(e)),
        )
