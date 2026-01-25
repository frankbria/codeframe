"""Tests for TaskScheduler Component.

TDD tests for intelligent task scheduling:
- schedule_tasks() - Assign start times based on dependencies and resources
- optimize_schedule() - Use heuristics to minimize project duration
- predict_completion_date() - Estimate project end date
- identify_bottlenecks() - Find tasks/agents causing delays
"""

import pytest
from datetime import datetime

from codeframe.planning.task_scheduler import (
    TaskScheduler,
    ScheduleResult,
    ScheduleOptimization,
)
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.core.models import Task, TaskStatus

pytestmark = pytest.mark.v2


@pytest.fixture
def scheduler():
    """Fresh TaskScheduler instance."""
    return TaskScheduler()


@pytest.fixture
def resolver():
    """DependencyResolver instance for building task graphs."""
    return DependencyResolver()


@pytest.fixture
def linear_tasks():
    """Create a simple linear task chain: A -> B -> C -> D."""
    return [
        Task(id=1, task_number="1.1", title="Task A", status=TaskStatus.PENDING, depends_on=""),
        Task(id=2, task_number="1.2", title="Task B", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=3, task_number="1.3", title="Task C", status=TaskStatus.PENDING, depends_on="2"),
        Task(id=4, task_number="1.4", title="Task D", status=TaskStatus.PENDING, depends_on="3"),
    ]


@pytest.fixture
def parallel_tasks():
    """Create tasks with parallel opportunities: A -> (B, C) -> D."""
    return [
        Task(id=1, task_number="1.1", title="Task A", status=TaskStatus.PENDING, depends_on=""),
        Task(id=2, task_number="1.2", title="Task B", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=3, task_number="1.3", title="Task C", status=TaskStatus.PENDING, depends_on="1"),
        Task(id=4, task_number="1.4", title="Task D", status=TaskStatus.PENDING, depends_on="2,3"),
    ]


@pytest.mark.unit
class TestScheduleTasks:
    """Test schedule_tasks() method."""

    def test_schedule_tasks_returns_result_object(self, scheduler, resolver, linear_tasks):
        """Test that schedule_tasks returns ScheduleResult."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        assert isinstance(result, ScheduleResult)
        assert hasattr(result, "task_assignments")
        assert hasattr(result, "total_duration")
        assert hasattr(result, "timeline")

    def test_schedule_tasks_assigns_start_times(self, scheduler, resolver, linear_tasks):
        """Test that tasks are assigned valid start times."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        # All tasks should have assignments
        assert len(result.task_assignments) == 4

        # Task 1 starts at 0
        assert result.task_assignments[1].start_time == 0.0
        assert result.task_assignments[1].end_time == 2.0

        # Task 2 starts after Task 1 ends
        assert result.task_assignments[2].start_time >= 2.0

    def test_schedule_respects_dependencies(self, scheduler, resolver, parallel_tasks):
        """Test that scheduled tasks respect dependency constraints."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        # B and C should both start after A ends
        assert result.task_assignments[2].start_time >= result.task_assignments[1].end_time
        assert result.task_assignments[3].start_time >= result.task_assignments[1].end_time

        # D should start after both B and C end
        b_end = result.task_assignments[2].end_time
        c_end = result.task_assignments[3].end_time
        assert result.task_assignments[4].start_time >= max(b_end, c_end)

    def test_schedule_with_multiple_agents(self, scheduler, resolver, parallel_tasks):
        """Test that multiple agents can work in parallel."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        # With 2 agents, B and C can run in parallel
        # Total duration should be: A(2) + max(B(3), C(1)) + D(2) = 7
        assert result.total_duration <= 8.0  # Allow some scheduling overhead

    def test_schedule_single_agent_serializes(self, scheduler, resolver, parallel_tasks):
        """Test that single agent schedules tasks sequentially."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        # With 1 agent: A(2) + B(3) + C(1) + D(2) = 8
        # (B and C must be sequential)
        assert result.total_duration >= 8.0


@pytest.mark.unit
class TestOptimizeSchedule:
    """Test optimize_schedule() method."""

    def test_optimize_schedule_returns_optimization_result(
        self, scheduler, resolver, parallel_tasks
    ):
        """Test that optimize_schedule returns ScheduleOptimization."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        schedule = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        optimization = scheduler.optimize_schedule(
            schedule=schedule,
            resolver=resolver,
            constraints={"max_parallel": 4},
        )

        assert isinstance(optimization, ScheduleOptimization)
        assert hasattr(optimization, "optimized_schedule")
        assert hasattr(optimization, "improvement_percentage")
        assert hasattr(optimization, "changes_made")

    def test_optimize_suggests_parallelization(self, scheduler, resolver, parallel_tasks):
        """Test that optimization suggests parallel execution when possible."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        # First schedule with 1 agent
        schedule = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        # Optimize with more agents available
        optimization = scheduler.optimize_schedule(
            schedule=schedule,
            resolver=resolver,
            constraints={"max_parallel": 2},
        )

        # Optimization should suggest improvements
        assert optimization.improvement_percentage >= 0


@pytest.mark.unit
class TestPredictCompletionDate:
    """Test predict_completion_date() method."""

    def test_predict_completion_returns_datetime(self, scheduler, resolver, linear_tasks):
        """Test that prediction returns a datetime."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        schedule = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        prediction = scheduler.predict_completion_date(
            schedule=schedule,
            current_progress={},  # No tasks completed
            start_date=datetime.now(),
        )

        assert isinstance(prediction.predicted_date, datetime)
        assert hasattr(prediction, "confidence_interval")

    def test_predict_accounts_for_completed_tasks(self, scheduler, resolver, linear_tasks):
        """Test that completed tasks reduce remaining duration."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        schedule = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        now = datetime.now()

        # Prediction with no progress
        pred_full = scheduler.predict_completion_date(
            schedule=schedule,
            current_progress={},
            start_date=now,
        )

        # Prediction with task 1 completed
        pred_partial = scheduler.predict_completion_date(
            schedule=schedule,
            current_progress={1: "completed"},
            start_date=now,
        )

        # Partial should predict earlier completion
        assert pred_partial.predicted_date <= pred_full.predicted_date

    def test_predict_includes_confidence_interval(self, scheduler, resolver, linear_tasks):
        """Test that prediction includes confidence bounds."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        schedule = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        prediction = scheduler.predict_completion_date(
            schedule=schedule,
            current_progress={},
            start_date=datetime.now(),
        )

        # Confidence interval should have early and late bounds
        assert "early" in prediction.confidence_interval
        assert "late" in prediction.confidence_interval
        assert prediction.confidence_interval["early"] <= prediction.predicted_date
        assert prediction.confidence_interval["late"] >= prediction.predicted_date


@pytest.mark.unit
class TestIdentifyBottlenecks:
    """Test identify_bottlenecks() method."""

    def test_identify_bottlenecks_returns_list(self, scheduler, resolver, parallel_tasks):
        """Test that method returns list of BottleneckInfo."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 8.0, 2: 1.0, 3: 1.0, 4: 1.0}  # Task 1 is long

        schedule = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        bottlenecks = scheduler.identify_bottlenecks(
            schedule=schedule,
            task_durations=durations,
            resolver=resolver,
        )

        assert isinstance(bottlenecks, list)

    def test_identify_long_duration_bottleneck(self, scheduler, resolver, parallel_tasks):
        """Test that long duration tasks on critical path are identified."""
        resolver.build_dependency_graph(parallel_tasks)
        # Task 1 is very long (8 hours), making it a bottleneck
        durations = {1: 8.0, 2: 1.0, 3: 1.0, 4: 1.0}

        schedule = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        bottlenecks = scheduler.identify_bottlenecks(
            schedule=schedule,
            task_durations=durations,
            resolver=resolver,
        )

        # Task 1 should be identified as bottleneck
        bottleneck_ids = [b.task_id for b in bottlenecks]
        assert 1 in bottleneck_ids

    def test_bottleneck_includes_impact_info(self, scheduler, resolver, parallel_tasks):
        """Test that bottleneck info includes impact analysis."""
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 8.0, 2: 1.0, 3: 1.0, 4: 1.0}

        schedule = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        bottlenecks = scheduler.identify_bottlenecks(
            schedule=schedule,
            task_durations=durations,
            resolver=resolver,
        )

        if bottlenecks:
            bottleneck = bottlenecks[0]
            assert hasattr(bottleneck, "task_id")
            assert hasattr(bottleneck, "bottleneck_type")
            assert hasattr(bottleneck, "impact_hours")
            assert hasattr(bottleneck, "recommendation")


@pytest.mark.unit
class TestTaskAssignmentDataclass:
    """Test TaskAssignment dataclass structure."""

    def test_task_assignment_has_required_fields(self, scheduler, resolver, linear_tasks):
        """Test TaskAssignment dataclass fields."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        assignment = result.task_assignments[1]

        assert hasattr(assignment, "task_id")
        assert hasattr(assignment, "start_time")
        assert hasattr(assignment, "end_time")
        assert hasattr(assignment, "assigned_agent")


@pytest.mark.unit
class TestScheduleResultDataclass:
    """Test ScheduleResult dataclass structure."""

    def test_schedule_result_has_timeline(self, scheduler, resolver, linear_tasks):
        """Test ScheduleResult includes timeline information."""
        resolver.build_dependency_graph(linear_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        result = scheduler.schedule_tasks(
            tasks=linear_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=1,
        )

        assert hasattr(result, "timeline")
        assert isinstance(result.timeline, list)

        # Timeline should have entries
        assert len(result.timeline) > 0


@pytest.mark.integration
class TestSchedulerIntegration:
    """Integration tests for TaskScheduler with DependencyResolver."""

    def test_full_scheduling_workflow(self, scheduler, resolver, parallel_tasks):
        """Test complete scheduling workflow."""
        # Build dependency graph
        resolver.build_dependency_graph(parallel_tasks)
        durations = {1: 2.0, 2: 3.0, 3: 1.0, 4: 2.0}

        # Schedule tasks
        schedule = scheduler.schedule_tasks(
            tasks=parallel_tasks,
            task_durations=durations,
            resolver=resolver,
            agents_available=2,
        )

        # Optimize
        optimization = scheduler.optimize_schedule(
            schedule=schedule,
            resolver=resolver,
            constraints={"max_parallel": 2},
        )

        # Predict completion
        prediction = scheduler.predict_completion_date(
            schedule=optimization.optimized_schedule,
            current_progress={},
            start_date=datetime.now(),
        )

        # Identify bottlenecks
        bottlenecks = scheduler.identify_bottlenecks(
            schedule=optimization.optimized_schedule,
            task_durations=durations,
            resolver=resolver,
        )

        # Verify all components work together
        assert schedule.total_duration > 0
        assert optimization.improvement_percentage >= 0
        assert prediction.predicted_date is not None
        assert isinstance(bottlenecks, list)
