"""Schedule management for CodeFRAME v2.

This module provides v2-compatible wrappers around the scheduling functionality.
It bridges v2 Workspace/Task models with the v1 TaskScheduler.

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from codeframe.core.workspace import Workspace
from codeframe.core import tasks
from codeframe.planning.task_scheduler import TaskScheduler
from codeframe.agents.dependency_resolver import DependencyResolver

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# ============================================================================
# V2-Compatible Data Classes
# ============================================================================


@dataclass
class TaskAssignment:
    """Assignment of a task to a time slot and agent (v2 compatible)."""

    task_id: str  # v2 uses string UUIDs
    title: str
    start_time: float  # Hours from project start
    end_time: float  # Hours from project start
    assigned_agent: Optional[int] = None


@dataclass
class ScheduleResult:
    """Result of task scheduling (v2 compatible)."""

    task_assignments: list[TaskAssignment]
    total_duration: float
    agents_used: int


@dataclass
class CompletionPrediction:
    """Prediction for project completion (v2 compatible)."""

    predicted_date: datetime
    confidence_early: datetime
    confidence_late: datetime
    remaining_hours: float
    completed_percentage: float


@dataclass
class BottleneckInfo:
    """Information about a scheduling bottleneck (v2 compatible)."""

    task_id: str  # v2 uses string UUIDs
    task_title: str
    bottleneck_type: str  # "duration", "dependencies", "resource"
    impact_hours: float
    recommendation: str


# ============================================================================
# Schedule Functions
# ============================================================================


def get_schedule(
    workspace: Workspace,
    agents: int = 1,
) -> ScheduleResult:
    """Get the schedule for a workspace.

    Uses Critical Path Method to assign start/end times while
    respecting dependency constraints and agent availability.

    Args:
        workspace: Target workspace
        agents: Number of parallel agents/workers (default: 1)

    Returns:
        ScheduleResult with task assignments

    Raises:
        ValueError: If no tasks found in workspace
    """
    # Load tasks from workspace
    task_list = tasks.list_tasks(workspace, limit=1000)
    if not task_list:
        raise ValueError("No tasks found in workspace")

    # Build ID mapping (v2 string UUID -> v1 integer)
    # We use task index as the integer ID
    uuid_to_int: dict[str, int] = {}
    int_to_uuid: dict[int, str] = {}
    task_lookup: dict[str, tasks.Task] = {}

    for idx, task in enumerate(task_list):
        int_id = idx + 1  # 1-indexed for v1 compatibility
        uuid_to_int[task.id] = int_id
        int_to_uuid[int_id] = task.id
        task_lookup[task.id] = task

    # Build v1-compatible task structures
    v1_tasks = []
    task_durations: dict[int, float] = {}

    for task in task_list:
        int_id = uuid_to_int[task.id]
        # Create a simple object with required attributes
        v1_task = _V1TaskAdapter(
            id=int_id,
            title=task.title,
            status=task.status,
            estimated_hours=task.estimated_hours,
        )
        v1_tasks.append(v1_task)

        # Get duration (default to 1 hour if not specified)
        duration = task.estimated_hours if task.estimated_hours and task.estimated_hours > 0 else 1.0
        task_durations[int_id] = duration

    # Build dependency resolver with v1 integer IDs
    resolver = DependencyResolver()

    # Add dependencies (convert v2 depends_on to v1 format)
    for task in task_list:
        int_id = uuid_to_int[task.id]
        if task.depends_on:
            for dep_uuid in task.depends_on:
                if dep_uuid in uuid_to_int:
                    dep_int_id = uuid_to_int[dep_uuid]
                    resolver.dependencies.setdefault(int_id, set()).add(dep_int_id)
                    resolver.dependents.setdefault(dep_int_id, set()).add(int_id)
                    resolver.all_tasks.add(int_id)
                    resolver.all_tasks.add(dep_int_id)
        else:
            resolver.all_tasks.add(int_id)

    # Schedule tasks
    scheduler = TaskScheduler()
    v1_schedule = scheduler.schedule_tasks(
        tasks=v1_tasks,
        task_durations=task_durations,
        resolver=resolver,
        agents_available=agents,
    )

    # Convert back to v2 format
    assignments = []
    for int_id, v1_assignment in v1_schedule.task_assignments.items():
        uuid = int_to_uuid.get(int_id)
        if uuid:
            task = task_lookup[uuid]
            assignments.append(TaskAssignment(
                task_id=uuid,
                title=task.title,
                start_time=v1_assignment.start_time,
                end_time=v1_assignment.end_time,
                assigned_agent=v1_assignment.assigned_agent,
            ))

    # Sort by start time
    assignments.sort(key=lambda a: a.start_time)

    return ScheduleResult(
        task_assignments=assignments,
        total_duration=v1_schedule.total_duration,
        agents_used=v1_schedule.agents_used,
    )


def predict_completion(
    workspace: Workspace,
    hours_per_day: float = 8.0,
    start_date: Optional[datetime] = None,
) -> CompletionPrediction:
    """Predict project completion date.

    Args:
        workspace: Target workspace
        hours_per_day: Working hours per day (default: 8)
        start_date: Project start date (default: now)

    Returns:
        CompletionPrediction with predicted date and confidence interval

    Raises:
        ValueError: If no tasks found in workspace
    """
    if start_date is None:
        start_date = _utc_now()

    # Load tasks
    task_list = tasks.list_tasks(workspace, limit=1000)
    if not task_list:
        raise ValueError("No tasks found in workspace")

    # Build ID mapping
    uuid_to_int: dict[str, int] = {}
    int_to_uuid: dict[int, str] = {}

    for idx, task in enumerate(task_list):
        int_id = idx + 1
        uuid_to_int[task.id] = int_id
        int_to_uuid[int_id] = task.id

    # Build v1-compatible structures
    v1_tasks = []
    task_durations: dict[int, float] = {}
    current_progress: dict[int, str] = {}

    for task in task_list:
        int_id = uuid_to_int[task.id]
        v1_task = _V1TaskAdapter(
            id=int_id,
            title=task.title,
            status=task.status,
            estimated_hours=task.estimated_hours,
        )
        v1_tasks.append(v1_task)

        duration = task.estimated_hours if task.estimated_hours and task.estimated_hours > 0 else 1.0
        task_durations[int_id] = duration

        # Track completed tasks
        if task.status.value.upper() in ("DONE", "COMPLETED"):
            current_progress[int_id] = "completed"

    # Build dependency resolver
    resolver = DependencyResolver()
    for task in task_list:
        int_id = uuid_to_int[task.id]
        if task.depends_on:
            for dep_uuid in task.depends_on:
                if dep_uuid in uuid_to_int:
                    dep_int_id = uuid_to_int[dep_uuid]
                    resolver.dependencies.setdefault(int_id, set()).add(dep_int_id)
                    resolver.dependents.setdefault(dep_int_id, set()).add(int_id)
                    resolver.all_tasks.add(int_id)
                    resolver.all_tasks.add(dep_int_id)
        else:
            resolver.all_tasks.add(int_id)

    # Get schedule and prediction
    scheduler = TaskScheduler()
    v1_schedule = scheduler.schedule_tasks(
        tasks=v1_tasks,
        task_durations=task_durations,
        resolver=resolver,
        agents_available=1,
    )

    v1_prediction = scheduler.predict_completion_date(
        schedule=v1_schedule,
        current_progress=current_progress,
        start_date=start_date,
        hours_per_day=hours_per_day,
    )

    return CompletionPrediction(
        predicted_date=v1_prediction.predicted_date,
        confidence_early=v1_prediction.confidence_interval["early"],
        confidence_late=v1_prediction.confidence_interval["late"],
        remaining_hours=v1_prediction.remaining_hours,
        completed_percentage=v1_prediction.completed_percentage,
    )


def get_bottlenecks(workspace: Workspace) -> list[BottleneckInfo]:
    """Identify scheduling bottlenecks for a workspace.

    Identifies:
    - Long duration tasks on critical path
    - Tasks with many dependents causing delays
    - Resource constraints limiting parallelization

    Args:
        workspace: Target workspace

    Returns:
        List of BottleneckInfo objects

    Raises:
        ValueError: If no tasks found in workspace
    """
    # Load tasks
    task_list = tasks.list_tasks(workspace, limit=1000)
    if not task_list:
        raise ValueError("No tasks found in workspace")

    # Build ID mapping
    uuid_to_int: dict[str, int] = {}
    int_to_uuid: dict[int, str] = {}
    task_lookup: dict[str, tasks.Task] = {}

    for idx, task in enumerate(task_list):
        int_id = idx + 1
        uuid_to_int[task.id] = int_id
        int_to_uuid[int_id] = task.id
        task_lookup[task.id] = task

    # Build v1-compatible structures
    v1_tasks = []
    task_durations: dict[int, float] = {}

    for task in task_list:
        int_id = uuid_to_int[task.id]
        v1_task = _V1TaskAdapter(
            id=int_id,
            title=task.title,
            status=task.status,
            estimated_hours=task.estimated_hours,
        )
        v1_tasks.append(v1_task)

        duration = task.estimated_hours if task.estimated_hours and task.estimated_hours > 0 else 1.0
        task_durations[int_id] = duration

    # Build dependency resolver
    resolver = DependencyResolver()
    for task in task_list:
        int_id = uuid_to_int[task.id]
        if task.depends_on:
            for dep_uuid in task.depends_on:
                if dep_uuid in uuid_to_int:
                    dep_int_id = uuid_to_int[dep_uuid]
                    resolver.dependencies.setdefault(int_id, set()).add(dep_int_id)
                    resolver.dependents.setdefault(dep_int_id, set()).add(int_id)
                    resolver.all_tasks.add(int_id)
                    resolver.all_tasks.add(dep_int_id)
        else:
            resolver.all_tasks.add(int_id)

    # Get schedule and bottlenecks
    scheduler = TaskScheduler()
    v1_schedule = scheduler.schedule_tasks(
        tasks=v1_tasks,
        task_durations=task_durations,
        resolver=resolver,
        agents_available=1,
    )

    v1_bottlenecks = scheduler.identify_bottlenecks(
        schedule=v1_schedule,
        task_durations=task_durations,
        resolver=resolver,
    )

    # Convert to v2 format
    bottlenecks = []
    for v1_bn in v1_bottlenecks:
        uuid = int_to_uuid.get(v1_bn.task_id)
        if uuid:
            task = task_lookup[uuid]
            bottlenecks.append(BottleneckInfo(
                task_id=uuid,
                task_title=task.title,
                bottleneck_type=v1_bn.bottleneck_type,
                impact_hours=v1_bn.impact_hours,
                recommendation=v1_bn.recommendation,
            ))

    return bottlenecks


# ============================================================================
# Internal Helpers
# ============================================================================


class _V1TaskAdapter:
    """Adapter to make v2 tasks compatible with v1 TaskScheduler."""

    def __init__(
        self,
        id: int,
        title: str,
        status: Any,
        estimated_hours: Optional[float],
    ):
        self.id = id
        self.title = title
        self.status = status
        self.estimated_hours = estimated_hours
