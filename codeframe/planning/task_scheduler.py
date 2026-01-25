"""Task Scheduler Component for Intelligent Task Scheduling.

This module provides scheduling capabilities for task management:
- schedule_tasks() - Assign start times based on dependencies and resources
- optimize_schedule() - Use heuristics to minimize project duration
- predict_completion_date() - Estimate project end date
- identify_bottlenecks() - Find tasks/agents causing delays
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from codeframe.agents.dependency_resolver import DependencyResolver

logger = logging.getLogger(__name__)


@dataclass
class TaskAssignment:
    """Assignment of a task to a time slot and agent."""

    task_id: int
    start_time: float  # Hours from project start
    end_time: float  # Hours from project start
    assigned_agent: Optional[int] = None


@dataclass
class TimelineEntry:
    """Entry in the project timeline."""

    time: float
    event_type: str  # "start", "end"
    task_id: int
    agent_id: Optional[int] = None


@dataclass
class ScheduleResult:
    """Result of task scheduling."""

    task_assignments: Dict[int, TaskAssignment]
    total_duration: float
    timeline: List[TimelineEntry]
    agents_used: int = 1


@dataclass
class ScheduleOptimization:
    """Result of schedule optimization."""

    optimized_schedule: "ScheduleResult"
    improvement_percentage: float
    changes_made: List[str]
    original_duration: float
    optimized_duration: float


@dataclass
class CompletionPrediction:
    """Prediction for project completion."""

    predicted_date: datetime
    confidence_interval: Dict[str, datetime]
    remaining_hours: float
    completed_percentage: float


@dataclass
class BottleneckInfo:
    """Information about a scheduling bottleneck."""

    task_id: int
    bottleneck_type: str  # "duration", "dependencies", "resource"
    impact_hours: float
    recommendation: str


class TaskScheduler:
    """
    Intelligent task scheduler using Critical Path Method (CPM).

    Capabilities:
    - Schedule tasks based on dependencies and resource constraints
    - Optimize schedules to minimize project duration
    - Predict completion dates with confidence intervals
    - Identify scheduling bottlenecks
    """

    def __init__(self):
        """Initialize the task scheduler."""
        # Default uncertainty factor for predictions (±20%)
        self.uncertainty_factor = 0.2

    def schedule_tasks(
        self,
        tasks: List[Any],
        task_durations: Dict[int, float],
        resolver: DependencyResolver,
        agents_available: int = 1,
    ) -> ScheduleResult:
        """
        Schedule tasks based on dependencies and available resources.

        Uses Critical Path Method to assign start/end times while
        respecting dependency constraints and agent availability.

        Args:
            tasks: List of Task objects
            task_durations: Dict mapping task_id to duration in hours
            resolver: DependencyResolver with built dependency graph
            agents_available: Number of parallel agents/workers

        Returns:
            ScheduleResult with task assignments and timeline
        """
        # Get parallel execution waves
        waves = resolver.identify_parallel_opportunities()

        # Build assignments
        task_assignments: Dict[int, TaskAssignment] = {}
        timeline: List[TimelineEntry] = []

        # Track agent availability
        agent_end_times = [0.0] * agents_available

        # Process tasks wave by wave
        for wave_num in sorted(waves.keys()):
            wave_tasks = waves[wave_num]

            # Sort by duration (longer tasks first for better packing)
            wave_tasks_sorted = sorted(
                wave_tasks,
                key=lambda tid: task_durations.get(tid, 0),
                reverse=True,
            )

            for task_id in wave_tasks_sorted:
                duration = task_durations.get(task_id, 0.0)

                # Find earliest start time based on dependencies
                deps = resolver.dependencies.get(task_id, set())
                earliest_start = 0.0
                if deps:
                    for dep_id in deps:
                        if dep_id in task_assignments:
                            earliest_start = max(
                                earliest_start,
                                task_assignments[dep_id].end_time,
                            )

                # Find the first available agent
                best_agent = 0
                best_start = max(earliest_start, agent_end_times[0])

                for agent_idx, agent_end in enumerate(agent_end_times):
                    potential_start = max(earliest_start, agent_end)
                    if potential_start < best_start:
                        best_start = potential_start
                        best_agent = agent_idx

                # Create assignment
                end_time = best_start + duration
                assignment = TaskAssignment(
                    task_id=task_id,
                    start_time=best_start,
                    end_time=end_time,
                    assigned_agent=best_agent,
                )
                task_assignments[task_id] = assignment

                # Update agent availability
                agent_end_times[best_agent] = end_time

                # Add timeline entries
                timeline.append(
                    TimelineEntry(
                        time=best_start,
                        event_type="start",
                        task_id=task_id,
                        agent_id=best_agent,
                    )
                )
                timeline.append(
                    TimelineEntry(
                        time=end_time,
                        event_type="end",
                        task_id=task_id,
                        agent_id=best_agent,
                    )
                )

        # Sort timeline by time
        timeline.sort(key=lambda e: (e.time, 0 if e.event_type == "start" else 1))

        # Warn if any tasks were not scheduled (e.g., due to unknown dependency IDs)
        expected_task_ids = set(task_durations.keys())
        scheduled_task_ids = set(task_assignments.keys())
        missing_task_ids = expected_task_ids - scheduled_task_ids
        if missing_task_ids:
            logger.warning(
                f"Tasks omitted from schedule (possibly due to unknown dependencies): "
                f"{sorted(missing_task_ids)}"
            )

        # Calculate total duration
        total_duration = max(
            (a.end_time for a in task_assignments.values()),
            default=0.0,
        )

        return ScheduleResult(
            task_assignments=task_assignments,
            total_duration=total_duration,
            timeline=timeline,
            agents_used=agents_available,
        )

    def optimize_schedule(
        self,
        schedule: ScheduleResult,
        resolver: DependencyResolver,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ScheduleOptimization:
        """
        Optimize a schedule to minimize project duration.

        Uses heuristics to identify parallelization opportunities
        and suggest task reordering within slack windows.

        Args:
            schedule: Current ScheduleResult to optimize
            resolver: DependencyResolver with dependency graph
            constraints: Optional constraints (max_parallel, etc.)

        Returns:
            ScheduleOptimization with optimized schedule and improvements
        """
        constraints = constraints or {}
        max_parallel = constraints.get("max_parallel", schedule.agents_used)

        changes_made: List[str] = []
        original_duration = schedule.total_duration

        # If we can use more agents than currently scheduled, re-schedule
        if max_parallel > schedule.agents_used:
            # Extract task durations from current assignments
            task_durations = {
                tid: assignment.end_time - assignment.start_time
                for tid, assignment in schedule.task_assignments.items()
            }

            # Get task list from assignments
            task_ids = list(schedule.task_assignments.keys())

            # Re-schedule with more agents
            optimized = self._reschedule_with_agents(
                task_ids=task_ids,
                task_durations=task_durations,
                resolver=resolver,
                agents_available=max_parallel,
            )

            if optimized.total_duration < original_duration:
                changes_made.append(
                    f"Increased parallelization from {schedule.agents_used} "
                    f"to {max_parallel} agents"
                )

            improvement = (
                (original_duration - optimized.total_duration) / original_duration * 100
                if original_duration > 0
                else 0
            )

            return ScheduleOptimization(
                optimized_schedule=optimized,
                improvement_percentage=improvement,
                changes_made=changes_made,
                original_duration=original_duration,
                optimized_duration=optimized.total_duration,
            )

        # No optimization possible
        return ScheduleOptimization(
            optimized_schedule=schedule,
            improvement_percentage=0.0,
            changes_made=["No optimizations found"],
            original_duration=original_duration,
            optimized_duration=original_duration,
        )

    def _reschedule_with_agents(
        self,
        task_ids: List[int],
        task_durations: Dict[int, float],
        resolver: DependencyResolver,
        agents_available: int,
    ) -> ScheduleResult:
        """Re-schedule tasks with a different number of agents."""
        # Get parallel waves
        waves = resolver.identify_parallel_opportunities()

        task_assignments: Dict[int, TaskAssignment] = {}
        timeline: List[TimelineEntry] = []
        agent_end_times = [0.0] * agents_available

        for wave_num in sorted(waves.keys()):
            wave_tasks = [tid for tid in waves[wave_num] if tid in task_ids]
            wave_tasks_sorted = sorted(
                wave_tasks,
                key=lambda tid: task_durations.get(tid, 0),
                reverse=True,
            )

            for task_id in wave_tasks_sorted:
                duration = task_durations.get(task_id, 0.0)

                # Find earliest start based on dependencies
                deps = resolver.dependencies.get(task_id, set())
                earliest_start = 0.0
                for dep_id in deps:
                    if dep_id in task_assignments:
                        earliest_start = max(
                            earliest_start,
                            task_assignments[dep_id].end_time,
                        )

                # Find best agent
                best_agent = 0
                best_start = max(earliest_start, agent_end_times[0])

                for agent_idx, agent_end in enumerate(agent_end_times):
                    potential_start = max(earliest_start, agent_end)
                    if potential_start < best_start:
                        best_start = potential_start
                        best_agent = agent_idx

                end_time = best_start + duration
                task_assignments[task_id] = TaskAssignment(
                    task_id=task_id,
                    start_time=best_start,
                    end_time=end_time,
                    assigned_agent=best_agent,
                )
                agent_end_times[best_agent] = end_time

                timeline.append(
                    TimelineEntry(
                        time=best_start,
                        event_type="start",
                        task_id=task_id,
                        agent_id=best_agent,
                    )
                )
                timeline.append(
                    TimelineEntry(
                        time=end_time,
                        event_type="end",
                        task_id=task_id,
                        agent_id=best_agent,
                    )
                )

        timeline.sort(key=lambda e: e.time)
        total_duration = max(
            (a.end_time for a in task_assignments.values()), default=0.0
        )

        return ScheduleResult(
            task_assignments=task_assignments,
            total_duration=total_duration,
            timeline=timeline,
            agents_used=agents_available,
        )

    def predict_completion_date(
        self,
        schedule: ScheduleResult,
        current_progress: Dict[int, str],
        start_date: datetime,
        hours_per_day: float = 8.0,
    ) -> CompletionPrediction:
        """
        Predict project completion date based on schedule and progress.

        Args:
            schedule: Current ScheduleResult
            current_progress: Dict mapping task_id to status ("completed", "in_progress")
            start_date: Project start date
            hours_per_day: Working hours per day (default 8)

        Returns:
            CompletionPrediction with predicted date and confidence interval
        """
        # Calculate remaining hours
        total_hours = schedule.total_duration
        completed_hours = 0.0

        for task_id, status in current_progress.items():
            if status == "completed" and task_id in schedule.task_assignments:
                assignment = schedule.task_assignments[task_id]
                completed_hours += assignment.end_time - assignment.start_time

        remaining_hours = max(0, total_hours - completed_hours)
        completed_percentage = (
            (completed_hours / total_hours * 100) if total_hours > 0 else 100
        )

        # Calculate working days needed
        days_needed = remaining_hours / hours_per_day

        # Apply uncertainty for confidence interval
        early_days = days_needed * (1 - self.uncertainty_factor)
        late_days = days_needed * (1 + self.uncertainty_factor)

        predicted_date = start_date + timedelta(days=days_needed)
        early_date = start_date + timedelta(days=early_days)
        late_date = start_date + timedelta(days=late_days)

        return CompletionPrediction(
            predicted_date=predicted_date,
            confidence_interval={
                "early": early_date,
                "late": late_date,
            },
            remaining_hours=remaining_hours,
            completed_percentage=completed_percentage,
        )

    def identify_bottlenecks(
        self,
        schedule: ScheduleResult,
        task_durations: Dict[int, float],
        resolver: DependencyResolver,
    ) -> List[BottleneckInfo]:
        """
        Identify scheduling bottlenecks in the project.

        Identifies:
        - Long duration tasks on critical path
        - Tasks with many dependents causing delays
        - Resource constraints limiting parallelization

        Args:
            schedule: Current ScheduleResult
            task_durations: Dict mapping task_id to duration
            resolver: DependencyResolver with dependency graph

        Returns:
            List of BottleneckInfo objects
        """
        bottlenecks: List[BottleneckInfo] = []

        # Get critical path
        cp_result = resolver.calculate_critical_path(task_durations)
        critical_set = set(cp_result.critical_task_ids)

        # Identify long duration tasks on critical path
        avg_duration = (
            sum(task_durations.values()) / len(task_durations)
            if task_durations
            else 0
        )
        duration_threshold = avg_duration * 2  # Tasks > 2x average

        for task_id in critical_set:
            duration = task_durations.get(task_id, 0)

            if duration > duration_threshold:
                dependent_count = len(resolver.dependents.get(task_id, set()))
                impact = duration - avg_duration

                bottlenecks.append(
                    BottleneckInfo(
                        task_id=task_id,
                        bottleneck_type="duration",
                        impact_hours=impact,
                        recommendation=(
                            f"Task {task_id} takes {duration:.1f}h (2x average). "
                            f"Consider splitting into smaller tasks. "
                            f"Blocks {dependent_count} downstream tasks."
                        ),
                    )
                )

        # Identify tasks with many dependents
        dependent_threshold = 3
        for task_id in resolver.all_tasks:
            dependent_count = len(resolver.dependents.get(task_id, set()))

            if dependent_count >= dependent_threshold and task_id in critical_set:
                duration = task_durations.get(task_id, 0)
                # Impact is duration times number of blocked tasks
                impact = duration * (dependent_count - 1)

                bottlenecks.append(
                    BottleneckInfo(
                        task_id=task_id,
                        bottleneck_type="dependencies",
                        impact_hours=impact,
                        recommendation=(
                            f"Task {task_id} blocks {dependent_count} tasks. "
                            f"Prioritize this task or consider parallelizing dependents."
                        ),
                    )
                )

        return bottlenecks
