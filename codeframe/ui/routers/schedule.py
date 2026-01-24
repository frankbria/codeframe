"""Schedule management router.

This module provides API endpoints for:
- Viewing project schedules
- Predicting completion dates
- Identifying scheduling bottlenecks
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.planning.task_scheduler import TaskScheduler
from codeframe.agents.dependency_resolver import DependencyResolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


# ============================================================================
# Response Models
# ============================================================================


class TaskAssignmentResponse(BaseModel):
    """Response model for a single task assignment."""

    task_id: int
    start_time: float
    end_time: float
    assigned_agent: Optional[int] = None


class ScheduleResponse(BaseModel):
    """Response model for project schedule."""

    task_assignments: Dict[int, TaskAssignmentResponse]
    total_duration: float
    agents_used: int


class CompletionPredictionResponse(BaseModel):
    """Response model for completion prediction."""

    predicted_date: str
    remaining_hours: float
    completed_percentage: float
    confidence_interval: Dict[str, str]


class BottleneckResponse(BaseModel):
    """Response model for a scheduling bottleneck."""

    task_id: int
    task_title: str
    bottleneck_type: str
    impact_hours: float
    recommendation: str


# ============================================================================
# Schedule Endpoints
# ============================================================================


@router.get("/{project_id}", response_model=ScheduleResponse)
async def get_project_schedule(
    project_id: int,
    agents: int = 1,
    db: Database = Depends(get_db),
) -> Dict[str, Any]:
    """Get the schedule for a project.

    Args:
        project_id: Project ID
        agents: Number of parallel agents/workers (default: 1)
        db: Database connection

    Returns:
        Project schedule with task assignments
    """
    try:
        tasks = db.get_project_tasks(project_id)
        if not tasks:
            raise HTTPException(status_code=404, detail="No tasks found for project")

        # Build dependency graph and schedule
        resolver = DependencyResolver()
        resolver.build_dependency_graph(tasks)

        scheduler = TaskScheduler()

        # Extract durations
        task_durations = {}
        for task in tasks:
            duration = getattr(task, "estimated_hours", None)
            if duration is None or duration <= 0:
                duration = 1.0
            task_durations[task.id] = duration

        schedule = scheduler.schedule_tasks(
            tasks=tasks,
            task_durations=task_durations,
            resolver=resolver,
            agents_available=agents,
        )

        # Convert to response format
        assignments = {}
        for task_id, assignment in schedule.task_assignments.items():
            assignments[task_id] = {
                "task_id": task_id,
                "start_time": assignment.start_time,
                "end_time": assignment.end_time,
                "assigned_agent": assignment.assigned_agent,
            }

        return {
            "task_assignments": assignments,
            "total_duration": schedule.total_duration,
            "agents_used": schedule.agents_used,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/predict", response_model=CompletionPredictionResponse)
async def predict_completion(
    project_id: int,
    hours_per_day: float = 8.0,
    db: Database = Depends(get_db),
) -> Dict[str, Any]:
    """Predict project completion date.

    Args:
        project_id: Project ID
        hours_per_day: Working hours per day (default: 8)
        db: Database connection

    Returns:
        Completion prediction with confidence interval
    """
    try:
        tasks = db.get_project_tasks(project_id)
        if not tasks:
            raise HTTPException(status_code=404, detail="No tasks found for project")

        # Build schedule
        resolver = DependencyResolver()
        resolver.build_dependency_graph(tasks)
        scheduler = TaskScheduler()

        task_durations = {}
        for task in tasks:
            val = getattr(task, "estimated_hours", None)
            duration = val if val is not None and val > 0 else 1.0
            task_durations[task.id] = duration

        schedule = scheduler.schedule_tasks(
            tasks=tasks,
            task_durations=task_durations,
            resolver=resolver,
            agents_available=1,
        )

        # Get current progress
        current_progress = {}
        for task in tasks:
            status = task.status.value if hasattr(task.status, "value") else str(task.status)
            if status.upper() in ("DONE", "COMPLETED"):
                current_progress[task.id] = "completed"

        # Predict completion
        prediction = scheduler.predict_completion_date(
            schedule=schedule,
            current_progress=current_progress,
            start_date=datetime.now(),
            hours_per_day=hours_per_day,
        )

        return {
            "predicted_date": prediction.predicted_date.isoformat(),
            "remaining_hours": prediction.remaining_hours,
            "completed_percentage": prediction.completed_percentage,
            "confidence_interval": {
                "early": prediction.confidence_interval["early"].isoformat(),
                "late": prediction.confidence_interval["late"].isoformat(),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error predicting completion for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/bottlenecks", response_model=List[BottleneckResponse])
async def get_bottlenecks(
    project_id: int,
    db: Database = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Identify scheduling bottlenecks for a project.

    Args:
        project_id: Project ID
        db: Database connection

    Returns:
        List of identified bottlenecks with recommendations
    """
    try:
        tasks = db.get_project_tasks(project_id)
        if not tasks:
            raise HTTPException(status_code=404, detail="No tasks found for project")

        # Build schedule
        resolver = DependencyResolver()
        resolver.build_dependency_graph(tasks)
        scheduler = TaskScheduler()

        task_durations = {}
        for task in tasks:
            val = getattr(task, "estimated_hours", None)
            duration = val if val is not None and val > 0 else 1.0
            task_durations[task.id] = duration

        schedule = scheduler.schedule_tasks(
            tasks=tasks,
            task_durations=task_durations,
            resolver=resolver,
            agents_available=1,
        )

        bottlenecks = scheduler.identify_bottlenecks(
            schedule=schedule,
            task_durations=task_durations,
            resolver=resolver,
        )

        # Create task lookup for titles
        task_lookup = {t.id: t for t in tasks}

        result = []
        for bn in bottlenecks:
            task = task_lookup.get(bn.task_id)
            title = task.title if task else f"Task {bn.task_id}"
            result.append({
                "task_id": bn.task_id,
                "task_title": title,
                "bottleneck_type": bn.bottleneck_type,
                "impact_hours": bn.impact_hours,
                "recommendation": bn.recommendation,
            })

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bottlenecks for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
