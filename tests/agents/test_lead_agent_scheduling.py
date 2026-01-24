"""Tests for LeadAgent task scheduling integration.

TDD tests for integrating TaskScheduler with LeadAgent:
- schedule_project_tasks() - Create project schedule from tasks
- Integration with effort estimation and dependency resolver
"""

import pytest

from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.core.models import Issue, TaskStatus
from codeframe.planning.task_scheduler import ScheduleResult


@pytest.fixture
def temp_db(temp_db_path):
    """Create initialized database for testing."""
    db = Database(temp_db_path)
    db.initialize()
    return db


@pytest.fixture
def project_with_tasks(temp_db):
    """Create a project with tasks that have dependencies and effort estimates."""
    project_id = temp_db.create_project("test-project", "Test scheduling project")

    # Create an issue for the tasks
    issue = Issue(
        project_id=project_id,
        issue_number="1",
        title="Test Issue",
        description="Test issue for scheduling",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
    )
    issue_id = temp_db.create_issue(issue)

    # Create tasks with dependencies and estimated_hours
    # Task structure: A -> (B, C) -> D
    task_a = temp_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.1",
        parent_issue_number="1",
        title="Task A - Foundation",
        description="Foundation task",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
        estimated_hours=2.0,
        complexity_score=2,
    )

    task_b = temp_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.2",
        parent_issue_number="1",
        title="Task B - Feature",
        description="Feature task",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=True,
        estimated_hours=3.0,
        complexity_score=3,
    )
    # Add dependency: B depends on A
    temp_db.add_task_dependency(task_b, task_a)

    task_c = temp_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.3",
        parent_issue_number="1",
        title="Task C - Integration",
        description="Integration task",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=True,
        estimated_hours=1.0,
        complexity_score=2,
    )
    # Add dependency: C depends on A
    temp_db.add_task_dependency(task_c, task_a)

    task_d = temp_db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.4",
        parent_issue_number="1",
        title="Task D - Finalization",
        description="Final task",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
        estimated_hours=2.0,
        complexity_score=2,
    )
    # Add dependencies: D depends on B and C
    temp_db.add_task_dependency(task_d, task_b)
    temp_db.add_task_dependency(task_d, task_c)

    return {
        "project_id": project_id,
        "issue_id": issue_id,
        "task_ids": [task_a, task_b, task_c, task_d],
        "db": temp_db,
    }


@pytest.mark.unit
class TestScheduleProjectTasks:
    """Test schedule_project_tasks() method."""

    def test_schedule_project_tasks_returns_schedule_result(self, project_with_tasks):
        """Test that schedule_project_tasks returns a ScheduleResult."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        assert isinstance(result, ScheduleResult)
        assert hasattr(result, "task_assignments")
        assert hasattr(result, "total_duration")
        assert hasattr(result, "timeline")

    def test_schedule_project_tasks_includes_all_tasks(self, project_with_tasks):
        """Test that schedule includes all project tasks."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]
        task_ids = project_with_tasks["task_ids"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        # All 4 tasks should be scheduled
        assert len(result.task_assignments) == 4
        for task_id in task_ids:
            assert task_id in result.task_assignments

    def test_schedule_uses_estimated_hours(self, project_with_tasks):
        """Test that schedule uses estimated_hours from tasks."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]
        task_ids = project_with_tasks["task_ids"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        # Task A duration should be 2.0 hours (as set in fixture)
        task_a_id = task_ids[0]
        assignment = result.task_assignments[task_a_id]
        duration = assignment.end_time - assignment.start_time
        assert duration == 2.0

    def test_schedule_respects_dependencies(self, project_with_tasks):
        """Test that schedule respects task dependencies."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]
        task_ids = project_with_tasks["task_ids"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        task_a_id, task_b_id, task_c_id, task_d_id = task_ids

        # B and C must start after A ends
        a_end = result.task_assignments[task_a_id].end_time
        b_start = result.task_assignments[task_b_id].start_time
        c_start = result.task_assignments[task_c_id].start_time

        assert b_start >= a_end
        assert c_start >= a_end

        # D must start after both B and C end
        b_end = result.task_assignments[task_b_id].end_time
        c_end = result.task_assignments[task_c_id].end_time
        d_start = result.task_assignments[task_d_id].start_time

        assert d_start >= max(b_end, c_end)

    def test_schedule_with_multiple_agents(self, project_with_tasks):
        """Test scheduling with multiple agents reduces duration."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # Schedule with 1 agent (serial)
        result_1_agent = agent.schedule_project_tasks(agents_available=1)

        # Schedule with 2 agents (parallel B and C)
        result_2_agents = agent.schedule_project_tasks(agents_available=2)

        # 2 agents should be faster or equal
        assert result_2_agents.total_duration <= result_1_agent.total_duration

    def test_schedule_with_default_duration_for_missing_estimates(self, temp_db):
        """Test that tasks without estimated_hours use default duration."""
        project_id = temp_db.create_project("test-project", "Test project")

        # Create an issue
        issue = Issue(
            project_id=project_id,
            issue_number="1",
            title="Test Issue",
            description="Test",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
        )
        issue_id = temp_db.create_issue(issue)

        # Create task without estimated_hours
        task_id = temp_db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.1",
            parent_issue_number="1",
            title="Task without estimate",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
            # No estimated_hours
        )

        agent = LeadAgent(project_id=project_id, db=temp_db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        # Task should be scheduled with default duration (1.0 hour)
        assert task_id in result.task_assignments
        duration = result.task_assignments[task_id].end_time - result.task_assignments[task_id].start_time
        assert duration == 1.0  # Default duration

    def test_schedule_empty_project_returns_empty_schedule(self, temp_db):
        """Test scheduling project with no tasks returns empty schedule."""
        project_id = temp_db.create_project("empty-project", "No tasks")

        agent = LeadAgent(project_id=project_id, db=temp_db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        assert isinstance(result, ScheduleResult)
        assert len(result.task_assignments) == 0
        assert result.total_duration == 0.0


@pytest.mark.unit
class TestGetProjectScheduleInfo:
    """Test helper methods for scheduling information."""

    def test_get_project_duration_hours(self, project_with_tasks):
        """Test getting total project duration in hours."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks(agents_available=2)

        # With 2 agents: A(2) + max(B(3), C(1)) + D(2) = 7 hours
        assert result.total_duration == 7.0

    def test_schedule_timeline_has_events(self, project_with_tasks):
        """Test that schedule timeline contains start/end events."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        result = agent.schedule_project_tasks()

        # Should have start and end events for each task
        assert len(result.timeline) == 8  # 4 tasks * 2 events each

        event_types = [e.event_type for e in result.timeline]
        assert event_types.count("start") == 4
        assert event_types.count("end") == 4


@pytest.mark.unit
class TestScheduleWithProgress:
    """Test scheduling with partially completed tasks."""

    def test_schedule_excludes_completed_tasks_duration(self, project_with_tasks):
        """Test that completed tasks affect remaining schedule correctly."""
        db = project_with_tasks["db"]
        project_id = project_with_tasks["project_id"]
        task_ids = project_with_tasks["task_ids"]

        # Mark task A as completed
        db.update_task(task_ids[0], {"status": TaskStatus.COMPLETED.value})

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # Schedule should still include all tasks for planning purposes
        # but completed tasks can be handled by predict_completion_date
        result = agent.schedule_project_tasks()

        assert len(result.task_assignments) == 4
