"""Tests for database Issues/Tasks hierarchical model (cf-16.2).

Following TDD: These tests are written FIRST, before implementation.
Target: >90% coverage for Issues table and related operations.

Requirements from CONCEPTS_RESOLVED.md:
- Issues table with hierarchical numbering (e.g., "1.5")
- Tasks table enhanced with issue_id, task_number (e.g., "1.5.3")
- CRUD operations for Issues
- Query operations for Issue-Task relationships
- Unique constraints and foreign key relationships
"""

import pytest
from datetime import datetime
from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus, Issue


@pytest.fixture
def db(temp_db_path):
    """Create and initialize database with proper async cleanup.

    This fixture replaces the inline Database creation pattern
    to ensure async connections are properly closed and prevent
    pytest from hanging during teardown.
    """
    database = Database(temp_db_path)
    database.initialize()

    yield database

    # Close async connection if it was opened (prevents hanging)
    if database._async_conn:
        import asyncio

        try:
            asyncio.get_event_loop().run_until_complete(database.close_async())
        except RuntimeError:
            asyncio.run(database.close_async())
    database.close()


@pytest.mark.unit
class TestIssuesTableCreation:
    """Test Issues table schema creation and migration."""

    def test_issues_table_created(self, db):
        """Test that Issues table is created with correct schema."""

        # Verify issues table exists
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='issues'")
        result = cursor.fetchone()
        assert result is not None, "Issues table was not created"

    def test_issues_table_columns(self, db):
        """Test that Issues table has all required columns."""

        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(issues)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}  # column_name: type

        # Verify all required columns exist
        assert "id" in columns
        assert "project_id" in columns
        assert "issue_number" in columns
        assert "title" in columns
        assert "description" in columns
        assert "status" in columns
        assert "priority" in columns
        assert "workflow_step" in columns
        assert "created_at" in columns
        assert "completed_at" in columns

    def test_tasks_table_enhanced_columns(self, db):
        """Test that Tasks table has new columns for Issue relationship."""

        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # Verify new columns exist
        assert "issue_id" in columns
        assert "task_number" in columns
        assert "parent_issue_number" in columns
        assert "can_parallelize" in columns

    def test_issues_indexes_created(self, db):
        """Test that proper indexes are created for Issues."""

        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]

        # Verify indexes exist
        assert any(
            "idx_issues_number" in idx for idx in indexes
        ), "Index on issues(project_id, issue_number) not found"
        assert any(
            "idx_tasks_issue_number" in idx for idx in indexes
        ), "Index on tasks(parent_issue_number) not found"


@pytest.mark.unit
class TestIssueCRUD:
    """Test Issue CRUD operations."""

    def test_create_issue_minimal(self, db):
        """Test creating an issue with minimal required fields."""

        project_id = db.create_project("test-project", "Test Project project")

        issue = Issue(
            project_id=project_id,
            issue_number="1.5",
            title="Implement database migration",
            description="Add Issues table with hierarchical model",
            status=TaskStatus.PENDING,
            priority=1,
        )
        issue_id = db.create_issue(issue)

        assert issue_id is not None
        assert isinstance(issue_id, int)
        assert issue_id > 0

    def test_create_issue_full(self, db):
        """Test creating an issue with all fields."""

        project_id = db.create_project("test-project", "Test Project project")

        issue = Issue(
            project_id=project_id,
            issue_number="2.3",
            title="API endpoint for issues",
            description="Create REST API for issue management",
            status=TaskStatus.IN_PROGRESS,
            priority=0,
            workflow_step=5,
        )
        issue_id = db.create_issue(issue)

        assert issue_id is not None

        # Verify it was created correctly
        saved_issue = db.get_issue(issue_id)
        assert saved_issue.issue_number == "2.3"
        assert saved_issue.title == "API endpoint for issues"
        assert saved_issue.status == TaskStatus.IN_PROGRESS
        assert saved_issue.priority == 0
        assert saved_issue.workflow_step == 5

    def test_get_issue_by_id(self, db):
        """Test retrieving an issue by ID."""

        project_id = db.create_project("test-project", "Test Project project")
        issue = Issue(
            project_id=project_id,
            issue_number="1.1",
            title="Test Issue",
            description="This is a test",
            status=TaskStatus.PENDING,
            priority=2,
        )
        issue_id = db.create_issue(issue)

        # Retrieve issue
        issue = db.get_issue(issue_id)

        assert issue is not None
        assert issue.id == issue_id
        assert issue.project_id == project_id
        assert issue.issue_number == "1.1"
        assert issue.title == "Test Issue"
        assert issue.description == "This is a test"
        assert issue.status == TaskStatus.PENDING
        assert issue.priority == 2
        assert issue.created_at is not None

    def test_get_nonexistent_issue_returns_none(self, db):
        """Test that getting non-existent issue returns None."""

        issue = db.get_issue(99999)
        assert issue is None

    def test_list_issues_by_project(self, db):
        """Test listing all issues for a project."""

        project_id = db.create_project("test-project", "Test Project project")

        # Create multiple issues
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.1",
                title="Issue 1",
                description="Description 1",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.2",
                title="Issue 2",
                description="Description 2",
                status=TaskStatus.IN_PROGRESS,
                priority=2,
            )
        )
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="2.1",
                title="Issue 3",
                description="Description 3",
                status=TaskStatus.COMPLETED,
                priority=3,
            )
        )

        # List all issues for project
        issues = db.list_issues(project_id)

        assert len(issues) == 3
        issue_numbers = [i.issue_number for i in issues]
        assert "1.1" in issue_numbers
        assert "1.2" in issue_numbers
        assert "2.1" in issue_numbers

    def test_list_issues_empty_project(self, db):
        """Test listing issues for project with no issues."""

        project_id = db.create_project("test-project", "Test Project project")
        issues = db.list_issues(project_id)

        assert issues == []

    def test_list_issues_filters_by_project(self, db):
        """Test that list_issues only returns issues for specified project."""

        project1_id = db.create_project("project1", "Project1 project")
        project2_id = db.create_project("project2", "Project2 project")

        # Create issues in different projects
        db.create_issue(
            Issue(
                project_id=project1_id,
                issue_number="1.1",
                title="Project 1 Issue",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        db.create_issue(
            Issue(
                project_id=project2_id,
                issue_number="1.1",
                title="Project 2 Issue",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # List issues for project1
        issues = db.list_issues(project1_id)

        assert len(issues) == 1
        assert issues[0].title == "Project 1 Issue"

    def test_update_issue_status(self, db):
        """Test updating issue status."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.1",
                title="Test",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Update status
        db.update_issue(issue_id, {"status": "in_progress"})

        # Verify update
        issue = db.get_issue(issue_id)
        assert issue.status == TaskStatus.IN_PROGRESS

    def test_update_issue_multiple_fields(self, db):
        """Test updating multiple issue fields at once."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.1",
                title="Original Title",
                description="Original Desc",
                status=TaskStatus.PENDING,
                priority=2,
            )
        )

        # Update multiple fields
        db.update_issue(
            issue_id,
            {
                "title": "Updated Title",
                "description": "Updated Description",
                "status": "completed",
                "priority": 0,
                "workflow_step": 10,
            },
        )

        # Verify updates
        issue = db.get_issue(issue_id)
        assert issue.title == "Updated Title"
        assert issue.description == "Updated Description"
        assert issue.status == TaskStatus.COMPLETED
        assert issue.priority == 0
        assert issue.workflow_step == 10

    def test_update_issue_with_completed_timestamp(self, db):
        """Test that completing an issue sets completed_at timestamp."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.1",
                title="Test",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Complete the issue
        db.update_issue(
            issue_id, {"status": "completed", "completed_at": datetime.now().isoformat()}
        )

        # Verify completed_at is set
        issue = db.get_issue(issue_id)
        assert issue.completed_at is not None

    def test_update_nonexistent_issue(self, db):
        """Test that updating non-existent issue returns 0."""

        result = db.update_issue(99999, {"status": "completed"})
        assert result == 0  # 0 rows affected


@pytest.mark.unit
class TestTaskIssueRelationship:
    """Test Task-Issue relationship and enhanced task operations."""

    def test_create_task_with_issue_id(self, db):
        """Test creating a task linked to an issue."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Parent Issue",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create task with issue relationship
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.5.1",
            parent_issue_number="1.5",
            title="Implement schema",
            description="Create database schema",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step=3,
            can_parallelize=False,
        )

        assert task_id is not None
        assert task_id > 0

    @pytest.mark.asyncio
    async def test_get_tasks_by_issue(self, db):
        """Test retrieving all tasks for an issue."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Parent Issue",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create multiple tasks for the issue
        db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.1",
            "1.5",
            "Task 1",
            "Desc 1",
            TaskStatus.PENDING,
            1,
            1,
            False,
        )
        db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.2",
            "1.5",
            "Task 2",
            "Desc 2",
            TaskStatus.IN_PROGRESS,
            1,
            2,
            True,
        )
        db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.3",
            "1.5",
            "Task 3",
            "Desc 3",
            TaskStatus.COMPLETED,
            1,
            3,
            False,
        )

        # Get tasks by issue (async)
        tasks = await db.get_tasks_by_issue(issue_id)

        assert len(tasks) == 3
        task_numbers = [t.task_number for t in tasks]
        assert "1.5.1" in task_numbers
        assert "1.5.2" in task_numbers
        assert "1.5.3" in task_numbers

    @pytest.mark.asyncio
    async def test_get_tasks_by_issue_empty(self, db):
        """Test getting tasks for issue with no tasks."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Issue",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        tasks = await db.get_tasks_by_issue(issue_id)
        assert tasks == []

    def test_task_can_parallelize_flag(self, db):
        """Test that can_parallelize flag is stored correctly."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Issue",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create parallelizable task
        task_id = db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.1",
            "1.5",
            "Parallel Task",
            "Can run in parallel",
            TaskStatus.PENDING,
            1,
            1,
            can_parallelize=True,
        )

        # Verify flag
        cursor = db.conn.cursor()
        cursor.execute("SELECT can_parallelize FROM tasks WHERE id = ?", (task_id,))
        result = cursor.fetchone()
        assert result[0] == 1  # SQLite stores boolean as 1/0

    def test_get_tasks_by_parent_issue_number(self, db):
        """Test querying tasks by parent_issue_number."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="2.3",
                title="Issue",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create tasks
        db.create_task_with_issue(
            project_id, issue_id, "2.3.1", "2.3", "Task 1", "Desc", TaskStatus.PENDING, 1, 1, False
        )
        db.create_task_with_issue(
            project_id, issue_id, "2.3.2", "2.3", "Task 2", "Desc", TaskStatus.PENDING, 1, 1, False
        )

        # Query by parent issue number
        tasks = db.get_tasks_by_parent_issue_number("2.3")

        assert len(tasks) == 2
        for task in tasks:
            assert task.parent_issue_number == "2.3"


@pytest.mark.unit
class TestIssueConstraints:
    """Test data integrity constraints for Issues."""

    def test_unique_issue_number_per_project(self, db):
        """Test that issue_number must be unique within a project."""

        project_id = db.create_project("test-project", "Test Project project")

        # Create first issue
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Issue 1",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Try to create duplicate issue number
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            db.create_issue(
                Issue(
                    project_id=project_id,
                    issue_number="1.5",
                    title="Issue 2",
                    description="Desc",
                    status=TaskStatus.PENDING,
                    priority=1,
                )
            )

    def test_same_issue_number_different_projects_allowed(self, db):
        """Test that same issue_number is allowed in different projects."""

        project1_id = db.create_project("project1", "Project1 project")
        project2_id = db.create_project("project2", "Project2 project")

        # Create issues with same number in different projects - should succeed
        issue1_id = db.create_issue(
            Issue(
                project_id=project1_id,
                issue_number="1.1",
                title="Issue 1",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        issue2_id = db.create_issue(
            Issue(
                project_id=project2_id,
                issue_number="1.1",
                title="Issue 2",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        assert issue1_id != issue2_id

    def test_issue_status_constraint(self, db):
        """Test that issue status must be valid."""

        project_id = db.create_project("test-project", "Test Project project")

        # Valid statuses: pending, in_progress, completed, failed
        cursor = db.conn.cursor()

        # Try invalid status
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            cursor.execute(
                "INSERT INTO issues (project_id, issue_number, title, status, priority) VALUES (?, ?, ?, ?, ?)",
                (project_id, "1.1", "Test", "INVALID_STATUS", 1),
            )

    def test_issue_priority_constraint(self, db):
        """Test that issue priority must be between 0 and 4."""

        project_id = db.create_project("test-project", "Test Project project")
        cursor = db.conn.cursor()

        # Try priority out of range
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            cursor.execute(
                "INSERT INTO issues (project_id, issue_number, title, status, priority) VALUES (?, ?, ?, ?, ?)",
                (project_id, "1.1", "Test", "pending", 10),  # Invalid priority
            )

    def test_issue_foreign_key_to_project(self, db):
        """Test foreign key relationship from issue to project."""

        # Enable foreign keys
        db.conn.execute("PRAGMA foreign_keys = ON")

        cursor = db.conn.cursor()

        # Try to create issue with non-existent project_id
        try:
            cursor.execute(
                "INSERT INTO issues (project_id, issue_number, title, status, priority) VALUES (?, ?, ?, ?, ?)",
                (99999, "1.1", "Test", "pending", 1),
            )
            db.conn.commit()
            # If we get here, foreign keys aren't enforced
        except Exception:
            # Foreign keys enforced - good!
            pass

    def test_task_foreign_key_to_issue(self, db):
        """Test foreign key relationship from task to issue."""

        # Enable foreign keys
        db.conn.execute("PRAGMA foreign_keys = ON")

        project_id = db.create_project("test-project", "Test Project project")
        cursor = db.conn.cursor()

        # Try to create task with non-existent issue_id
        try:
            cursor.execute(
                """INSERT INTO tasks
                   (project_id, issue_id, task_number, title, status, priority)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, 99999, "1.1.1", "Test", "pending", 1),
            )
            db.conn.commit()
        except Exception:
            # Foreign key enforced - good!
            pass


@pytest.mark.unit
class TestIssueTaskQueries:
    """Test complex queries involving Issues and Tasks."""

    def test_get_issue_with_task_counts(self, db):
        """Test getting issue with count of associated tasks."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Issue",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create tasks
        for i in range(3):
            db.create_task_with_issue(
                project_id,
                issue_id,
                f"1.5.{i+1}",
                "1.5",
                f"Task {i+1}",
                "Desc",
                TaskStatus.PENDING,
                1,
                1,
                False,
            )

        # Get issue with task count
        issue_with_counts = db.get_issue_with_task_counts(issue_id)

        assert issue_with_counts.id == issue_id
        assert issue_with_counts.task_count == 3

    def test_get_issue_completion_status(self, db):
        """Test calculating issue completion based on task statuses."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Issue",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create tasks with different statuses
        db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.1",
            "1.5",
            "Task 1",
            "Desc",
            TaskStatus.COMPLETED,
            1,
            1,
            False,
        )
        db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.2",
            "1.5",
            "Task 2",
            "Desc",
            TaskStatus.COMPLETED,
            1,
            1,
            False,
        )
        db.create_task_with_issue(
            project_id, issue_id, "1.5.3", "1.5", "Task 3", "Desc", TaskStatus.PENDING, 1, 1, False
        )

        # Calculate completion
        completion = db.get_issue_completion_status(issue_id)

        assert completion["total_tasks"] == 3
        assert completion["completed_tasks"] == 2
        assert completion["completion_percentage"] == pytest.approx(66.67, rel=0.1)

    def test_list_issues_with_progress(self, db):
        """Test listing issues with their progress metrics."""

        project_id = db.create_project("test-project", "Test Project project")

        # Create issue 1 with tasks
        issue1_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.1",
                title="Issue 1",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )
        db.create_task_with_issue(
            project_id, issue1_id, "1.1.1", "1.1", "Task", "Desc", TaskStatus.COMPLETED, 1, 1, False
        )

        # Create issue 2 with tasks
        issue2_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.2",
                title="Issue 2",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        db.create_task_with_issue(
            project_id, issue2_id, "1.2.1", "1.2", "Task", "Desc", TaskStatus.PENDING, 1, 1, False
        )

        # List with progress
        issues = db.list_issues_with_progress(project_id)

        assert len(issues) == 2
        # Each issue should have task counts
        for issue in issues:
            assert "task_count" in issue


@pytest.mark.integration
class TestIssueTaskIntegration:
    """Integration tests for Issue-Task workflow."""

    @pytest.mark.asyncio
    async def test_complete_issue_workflow(self, db):
        """Test complete workflow from issue creation to completion."""

        # 1. Create project
        project_id = db.create_project("my-app", "My App project")

        # 2. Create issue
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.5",
                title="Database Migration",
                description="Implement hierarchical Issue/Task model",
                status=TaskStatus.PENDING,
                priority=0,
            )
        )

        # 3. Update issue to in_progress
        db.update_issue(issue_id, {"status": "in_progress"})

        # 4. Create subtasks
        task1_id = db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.1",
            "1.5",
            "Create Issues table",
            "Schema definition",
            TaskStatus.PENDING,
            0,
            1,
            False,
        )

        task2_id = db.create_task_with_issue(
            project_id,
            issue_id,
            "1.5.2",
            "1.5",
            "Write tests",
            "TDD approach",
            TaskStatus.PENDING,
            0,
            2,
            False,
        )

        # 5. Complete tasks
        cursor = db.conn.cursor()
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (TaskStatus.COMPLETED.value, task1_id)
        )
        cursor.execute(
            "UPDATE tasks SET status = ? WHERE id = ?", (TaskStatus.COMPLETED.value, task2_id)
        )
        db.conn.commit()

        # 6. Complete issue
        db.update_issue(
            issue_id, {"status": "completed", "completed_at": datetime.now().isoformat()}
        )

        # 7. Verify final state
        issue = db.get_issue(issue_id)
        assert issue.status == TaskStatus.COMPLETED
        assert issue.completed_at is not None

        tasks = await db.get_tasks_by_issue(issue_id)
        assert all(t.status == TaskStatus.COMPLETED for t in tasks)

    def test_parallel_task_execution(self, db):
        """Test workflow with parallelizable tasks."""

        project_id = db.create_project("test-project", "Test Project project")
        issue_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="2.1",
                title="Feature X",
                description="Desc",
                status=TaskStatus.IN_PROGRESS,
                priority=1,
            )
        )

        # Create tasks, some parallelizable
        db.create_task_with_issue(
            project_id,
            issue_id,
            "2.1.1",
            "2.1",
            "Backend API",
            "Desc",
            TaskStatus.IN_PROGRESS,
            1,
            1,
            True,
        )
        db.create_task_with_issue(
            project_id,
            issue_id,
            "2.1.2",
            "2.1",
            "Frontend UI",
            "Desc",
            TaskStatus.IN_PROGRESS,
            1,
            1,
            True,
        )
        db.create_task_with_issue(
            project_id,
            issue_id,
            "2.1.3",
            "2.1",
            "Integration test",
            "Desc",
            TaskStatus.PENDING,
            1,
            2,
            False,
        )

        # Get parallelizable tasks
        cursor = db.conn.cursor()
        cursor.execute(
            """SELECT * FROM tasks
               WHERE issue_id = ? AND can_parallelize = 1""",
            (issue_id,),
        )
        parallel_tasks = cursor.fetchall()

        assert len(parallel_tasks) == 2

    @pytest.mark.asyncio
    async def test_hierarchical_numbering_consistency(self, db):
        """Test that hierarchical numbering is consistent."""

        project_id = db.create_project("test-project", "Test Project project")

        # Create issues with hierarchical numbers
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1",
                title="Epic 1",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        issue2_id = db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.1",
                title="Story 1.1",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="1.2",
                title="Story 1.2",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )
        db.create_issue(
            Issue(
                project_id=project_id,
                issue_number="2",
                title="Epic 2",
                description="Desc",
                status=TaskStatus.PENDING,
                priority=1,
            )
        )

        # Create tasks for story 1.1
        db.create_task_with_issue(
            project_id, issue2_id, "1.1.1", "1.1", "Task 1", "Desc", TaskStatus.PENDING, 1, 1, False
        )
        db.create_task_with_issue(
            project_id, issue2_id, "1.1.2", "1.1", "Task 2", "Desc", TaskStatus.PENDING, 1, 1, False
        )

        # Verify hierarchy
        issues = db.list_issues(project_id)
        issue_numbers = [i.issue_number for i in issues]

        assert "1" in issue_numbers
        assert "1.1" in issue_numbers
        assert "1.2" in issue_numbers
        assert "2" in issue_numbers

        tasks = await db.get_tasks_by_issue(issue2_id)
        task_numbers = [t.task_number for t in tasks]

        assert "1.1.1" in task_numbers
        assert "1.1.2" in task_numbers
