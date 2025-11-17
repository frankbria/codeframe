"""
Test that /api/projects endpoint returns progress metrics.

This test was created in response to production bug cf-46 where the frontend
Dashboard expected a `progress` field with `completed_tasks`, `total_tasks`,
and `percentage`, but the API was only returning raw database rows.

RED Phase: This test should FAIL initially, demonstrating the bug.
"""

import pytest
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus, TaskStatus, Issue


def test_list_projects_includes_progress_metrics():
    """
    Test that list_projects() returns progress field with task completion metrics.

    This is the RED phase test that demonstrates Bug 1 from cf-46.
    The test will FAIL because list_projects() currently doesn't calculate progress.
    """
    # Given: A database with a project
    db = Database(":memory:")
    db.initialize()

    project_id = db.create_project("Test Project", "Test Project project")

    # And: An issue for that project
    issue = Issue(
        project_id=project_id,
        issue_number="1.1",
        title="Test Issue",
        description="Test issue for progress calculation",
        status=TaskStatus.IN_PROGRESS,
        priority=2,
        workflow_step=1,
    )
    issue_id = db.create_issue(issue)

    # And: 5 tasks for the issue (3 completed, 2 pending)
    db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.1.1",
        parent_issue_number="1.1",
        title="Task 1",
        description="First task",
        status=TaskStatus.COMPLETED,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.1.2",
        parent_issue_number="1.1",
        title="Task 2",
        description="Second task",
        status=TaskStatus.COMPLETED,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.1.3",
        parent_issue_number="1.1",
        title="Task 3",
        description="Third task",
        status=TaskStatus.COMPLETED,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.1.4",
        parent_issue_number="1.1",
        title="Task 4",
        description="Fourth task",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    db.create_task_with_issue(
        project_id=project_id,
        issue_id=issue_id,
        task_number="1.1.5",
        parent_issue_number="1.1",
        title="Task 5",
        description="Fifth task",
        status=TaskStatus.IN_PROGRESS,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    # When: We fetch the project list
    projects = db.list_projects()

    # Then: Should return exactly one project
    assert len(projects) == 1
    project = projects[0]

    # And: Project should have basic fields
    assert project["id"] == project_id
    assert project["name"] == "Test Project"

    # And: Project MUST have a progress field (this will FAIL initially)
    assert "progress" in project, "Missing 'progress' field - this is Bug 1 from cf-46"

    # And: Progress field MUST have all required sub-fields
    assert "completed_tasks" in project["progress"], "Missing 'progress.completed_tasks'"
    assert "total_tasks" in project["progress"], "Missing 'progress.total_tasks'"
    assert "percentage" in project["progress"], "Missing 'progress.percentage'"

    # And: The metrics should be calculated correctly
    # 3 out of 5 tasks completed = 60%
    assert (
        project["progress"]["completed_tasks"] == 3
    ), f"Expected 3 completed tasks, got {project['progress']['completed_tasks']}"
    assert (
        project["progress"]["total_tasks"] == 5
    ), f"Expected 5 total tasks, got {project['progress']['total_tasks']}"
    assert (
        project["progress"]["percentage"] == 60.0
    ), f"Expected 60.0% completion, got {project['progress']['percentage']}"


def test_list_projects_progress_with_no_tasks():
    """
    Test progress calculation for a project with no tasks.

    Edge case: A new project with no issues or tasks should have 0/0 progress.
    """
    # Given: A database with a project that has no tasks
    db = Database(":memory:")
    db.initialize()

    project_id = db.create_project("Empty Project", "Empty Project project")

    # When: We fetch the project list
    projects = db.list_projects()

    # Then: Progress should show 0 tasks, 0% completion
    assert len(projects) == 1
    project = projects[0]

    assert "progress" in project
    assert project["progress"]["completed_tasks"] == 0
    assert project["progress"]["total_tasks"] == 0
    assert project["progress"]["percentage"] == 0.0


def test_list_projects_progress_with_all_completed():
    """
    Test progress calculation when all tasks are completed.

    Edge case: A project with all tasks completed should show 100%.
    """
    # Given: A database with a project
    db = Database(":memory:")
    db.initialize()

    project_id = db.create_project("Completed Project", "Completed Project project")

    # And: An issue with all tasks completed
    issue = Issue(
        project_id=project_id,
        issue_number="1.1",
        title="Completed Issue",
        description="All tasks done",
        status=TaskStatus.COMPLETED,
        priority=2,
        workflow_step=1,
    )
    issue_id = db.create_issue(issue)

    # And: 3 completed tasks
    for i in range(3):
        db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number=f"1.1.{i+1}",
            parent_issue_number="1.1",
            title=f"Task {i+1}",
            description=f"Task {i+1}",
            status=TaskStatus.COMPLETED,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
        )

    # When: We fetch the project list
    projects = db.list_projects()

    # Then: Progress should show 100% completion
    assert len(projects) == 1
    project = projects[0]

    assert "progress" in project
    assert project["progress"]["completed_tasks"] == 3
    assert project["progress"]["total_tasks"] == 3
    assert project["progress"]["percentage"] == 100.0


def test_list_projects_progress_multiple_projects():
    """
    Test that progress is calculated correctly for each project independently.
    """
    # Given: A database with two projects
    db = Database(":memory:")
    db.initialize()

    # Project 1: 50% complete (1 of 2 tasks)
    project1_id = db.create_project("Project Alpha", "Project Alpha project")
    issue1 = Issue(
        project_id=project1_id,
        issue_number="1.1",
        title="Issue 1",
        description="Test",
        status=TaskStatus.IN_PROGRESS,
        priority=2,
        workflow_step=1,
    )
    issue1_id = db.create_issue(issue1)

    db.create_task_with_issue(
        project_id=project1_id,
        issue_id=issue1_id,
        task_number="1.1.1",
        parent_issue_number="1.1",
        title="Task 1",
        description="Task 1",
        status=TaskStatus.COMPLETED,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    db.create_task_with_issue(
        project_id=project1_id,
        issue_id=issue1_id,
        task_number="1.1.2",
        parent_issue_number="1.1",
        title="Task 2",
        description="Task 2",
        status=TaskStatus.PENDING,
        priority=2,
        workflow_step=1,
        can_parallelize=False,
    )

    # Project 2: 75% complete (3 of 4 tasks)
    project2_id = db.create_project("Project Beta", "Project Beta project")
    issue2 = Issue(
        project_id=project2_id,
        issue_number="1.1",
        title="Issue 1",
        description="Test",
        status=TaskStatus.IN_PROGRESS,
        priority=2,
        workflow_step=1,
    )
    issue2_id = db.create_issue(issue2)

    for i in range(4):
        status = TaskStatus.COMPLETED if i < 3 else TaskStatus.PENDING
        db.create_task_with_issue(
            project_id=project2_id,
            issue_id=issue2_id,
            task_number=f"1.1.{i+1}",
            parent_issue_number="1.1",
            title=f"Task {i+1}",
            description=f"Task {i+1}",
            status=status,
            priority=2,
            workflow_step=1,
            can_parallelize=False,
        )

    # When: We fetch the project list
    projects = db.list_projects()

    # Then: Should have 2 projects with independent progress
    assert len(projects) == 2

    # Find projects by name (order may vary)
    alpha = next(p for p in projects if p["name"] == "Project Alpha")
    beta = next(p for p in projects if p["name"] == "Project Beta")

    # Project Alpha: 50% (1/2)
    assert alpha["progress"]["completed_tasks"] == 1
    assert alpha["progress"]["total_tasks"] == 2
    assert alpha["progress"]["percentage"] == 50.0

    # Project Beta: 75% (3/4)
    assert beta["progress"]["completed_tasks"] == 3
    assert beta["progress"]["total_tasks"] == 4
    assert beta["progress"]["percentage"] == 75.0
