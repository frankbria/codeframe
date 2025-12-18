"""Tests for typed database returns and async operations.

These tests verify:
1. Project.to_dict() serialization works correctly
2. Async connection cleanup via context manager
3. IssueWithTaskCount composition pattern
4. NULL created_at raises ValueError after migration 011
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from codeframe.core.models import (
    Issue,
    IssueWithTaskCount,
    Project,
    ProjectPhase,
    ProjectStatus,
    SourceType,
    TaskStatus,
    VALID_TASK_STATUSES,
)
from codeframe.persistence.database import Database


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def db(temp_db_path):
    """Create an initialized database."""
    database = Database(temp_db_path)
    database.initialize()
    yield database
    database.close()


class TestValidTaskStatuses:
    """Tests for VALID_TASK_STATUSES constant."""

    def test_valid_task_statuses_is_frozenset(self):
        """VALID_TASK_STATUSES should be a frozenset."""
        assert isinstance(VALID_TASK_STATUSES, frozenset)

    def test_valid_task_statuses_contains_all_enum_values(self):
        """VALID_TASK_STATUSES should contain all TaskStatus enum values."""
        for status in TaskStatus:
            assert status.value in VALID_TASK_STATUSES

    def test_valid_task_statuses_has_expected_values(self):
        """VALID_TASK_STATUSES should contain known status values."""
        expected = {"pending", "assigned", "in_progress", "blocked", "completed", "failed"}
        assert VALID_TASK_STATUSES == expected


class TestProjectToDict:
    """Tests for Project.to_dict() serialization."""

    def test_project_to_dict_basic(self):
        """Test basic Project.to_dict() serialization."""
        project = Project(
            id=1,
            name="Test Project",
            description="A test project",
            source_type=SourceType.GIT_REMOTE,
            source_location="https://github.com/test/repo",
            source_branch="main",
            workspace_path="/tmp/workspace",
            status=ProjectStatus.ACTIVE,
            phase=ProjectPhase.PLANNING,
        )

        result = project.to_dict()

        assert result["id"] == 1
        assert result["name"] == "Test Project"
        assert result["description"] == "A test project"
        assert result["source_type"] == "git_remote"
        assert result["source_location"] == "https://github.com/test/repo"
        assert result["source_branch"] == "main"
        assert result["workspace_path"] == "/tmp/workspace"
        assert result["status"] == "active"
        assert result["phase"] == "planning"
        assert result["created_at"] is not None

    def test_project_to_dict_with_none_values(self):
        """Test Project.to_dict() handles None values correctly."""
        project = Project(
            name="Test",
            description="Test",
            workspace_path="/tmp",
        )

        result = project.to_dict()

        assert result["id"] is None
        assert result["source_location"] is None
        assert result["current_commit"] is None
        assert result["paused_at"] is None
        assert result["config"] is None

    def test_project_to_dict_serializes_datetime(self):
        """Test Project.to_dict() serializes datetime to ISO format."""
        created = datetime(2025, 1, 15, 10, 30, 0)
        project = Project(
            name="Test",
            description="Test",
            workspace_path="/tmp",
            created_at=created,
        )

        result = project.to_dict()

        assert result["created_at"] == "2025-01-15T10:30:00"


class TestIssueWithTaskCountComposition:
    """Tests for IssueWithTaskCount composition pattern."""

    def test_issue_with_task_count_wraps_issue(self):
        """IssueWithTaskCount should wrap an Issue object."""
        issue = Issue(
            id=1,
            project_id=1,
            issue_number="1.0",
            title="Test Issue",
            status=TaskStatus.IN_PROGRESS,
        )

        issue_with_count = IssueWithTaskCount(issue=issue, task_count=5)

        assert issue_with_count.issue is issue
        assert issue_with_count.task_count == 5

    def test_issue_with_task_count_convenience_accessors(self):
        """IssueWithTaskCount should expose Issue fields via properties."""
        issue = Issue(
            id=42,
            project_id=7,
            issue_number="2.1",
            title="Feature X",
            status=TaskStatus.COMPLETED,
        )

        issue_with_count = IssueWithTaskCount(issue=issue, task_count=3)

        assert issue_with_count.id == 42
        assert issue_with_count.project_id == 7
        assert issue_with_count.issue_number == "2.1"
        assert issue_with_count.title == "Feature X"
        assert issue_with_count.status == TaskStatus.COMPLETED

    def test_issue_with_task_count_to_dict(self):
        """IssueWithTaskCount.to_dict() should include task_count."""
        issue = Issue(
            id=1,
            project_id=1,
            issue_number="1.0",
            title="Test",
        )

        issue_with_count = IssueWithTaskCount(issue=issue, task_count=10)
        result = issue_with_count.to_dict()

        # Should have all Issue fields plus task_count
        assert "id" in result
        assert "issue_number" in result
        assert "title" in result
        assert "task_count" in result
        assert result["task_count"] == 10


class TestAsyncConnectionCleanup:
    """Tests for async connection cleanup."""

    @pytest.mark.asyncio
    async def test_async_context_manager_closes_connection(self, db):
        """Async context manager should close async connection on exit."""
        async with db:
            # Connection should be created/available
            pass

        # After context exit, async connection should be closed
        assert db._async_conn is None

    @pytest.mark.asyncio
    async def test_async_context_manager_initializes_sync_connection(self, temp_db_path):
        """Async context manager should initialize sync connection if not already done."""
        db = Database(temp_db_path)

        async with db:
            # Sync connection should be initialized
            assert db.conn is not None

        db.close()

    @pytest.mark.asyncio
    async def test_close_async_is_idempotent(self, db):
        """Calling close_async() multiple times should be safe."""
        async with db:
            pass

        # Should not raise
        await db.close_async()
        await db.close_async()

        assert db._async_conn is None


class TestNullCreatedAtValidation:
    """Tests for NULL created_at validation.

    Note: After migration 011, the database schema enforces NOT NULL on created_at.
    These tests use a custom database without migrations to test the validation logic.
    """

    @pytest.fixture
    def db_no_migrations(self, temp_db_path):
        """Create a database without running migrations (allows NULL created_at)."""
        db = Database(temp_db_path)
        db.initialize(run_migrations=False)
        yield db
        db.close()

    def test_row_to_task_raises_on_null_created_at(self, db_no_migrations):
        """_row_to_task should raise ValueError for NULL created_at."""
        db = db_no_migrations
        cursor = db.conn.cursor()

        # Create project and issue first
        cursor.execute(
            "INSERT INTO projects (name, description, workspace_path, status) "
            "VALUES ('Test', 'Test', '/tmp', 'active')"
        )
        project_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO issues (project_id, issue_number, title, status, created_at) "
            "VALUES (?, '1.0', 'Test Issue', 'pending', datetime('now'))",
            (project_id,),
        )
        issue_id = cursor.lastrowid

        # Insert task with NULL created_at (possible without migration 011)
        cursor.execute(
            "INSERT INTO tasks (project_id, issue_id, title, status, created_at) "
            "VALUES (?, ?, 'Test Task', 'pending', NULL)",
            (project_id, issue_id),
        )
        task_id = cursor.lastrowid
        db.conn.commit()

        # Attempting to get this task should raise ValueError
        with pytest.raises(ValueError, match="NULL created_at"):
            db.get_task(task_id)

    def test_row_to_issue_raises_on_null_created_at(self, db_no_migrations):
        """_row_to_issue should raise ValueError for NULL created_at."""
        db = db_no_migrations
        cursor = db.conn.cursor()

        # Create project first
        cursor.execute(
            "INSERT INTO projects (name, description, workspace_path, status) "
            "VALUES ('Test', 'Test', '/tmp', 'active')"
        )
        project_id = cursor.lastrowid

        # Insert issue with NULL created_at (possible without migration 011)
        cursor.execute(
            "INSERT INTO issues (project_id, issue_number, title, status, created_at) "
            "VALUES (?, '1.0', 'Test Issue', 'pending', NULL)",
            (project_id,),
        )
        issue_id = cursor.lastrowid
        db.conn.commit()

        # Attempting to get this issue should raise ValueError
        with pytest.raises(ValueError, match="NULL created_at"):
            db.get_issue(issue_id)


class TestGetIssueWithTaskCounts:
    """Tests for get_issue_with_task_counts with composition.

    Note: Uses database without migrations to avoid foreign key reference issues
    from migration 011 (backup table references).
    """

    @pytest.fixture
    def db_no_migrations(self, temp_db_path):
        """Database without migrations (avoids FK issues from migration 011)."""
        db = Database(temp_db_path)
        db.initialize(run_migrations=False)
        yield db
        db.close()

    @pytest.fixture
    def db_with_data(self, db_no_migrations):
        """Database with project and issue created."""
        db = db_no_migrations
        project_id = db.create_project(
            name="Test Project",
            description="Test",
            workspace_path="/tmp/test",
        )

        issue = Issue(
            project_id=project_id,
            issue_number="1.0",
            title="Test Issue",
            status=TaskStatus.PENDING,
        )
        issue_id = db.create_issue(issue)

        return db, project_id, issue_id

    def test_get_issue_with_task_counts_returns_typed_object(self, db_with_data):
        """get_issue_with_task_counts should return IssueWithTaskCount."""
        db, project_id, issue_id = db_with_data

        # Create tasks
        cursor = db.conn.cursor()
        for i in range(3):
            cursor.execute(
                """
                INSERT INTO tasks (
                    project_id, issue_id, task_number, parent_issue_number,
                    title, description, status, priority, workflow_step,
                    can_parallelize, requires_mcp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    project_id,
                    issue_id,
                    f"1.0.{i+1}",
                    "1.0",
                    f"Task {i+1}",
                    "Test task",
                    "pending",
                    2,
                    1,
                    False,
                    False,
                ),
            )
        db.conn.commit()

        result = db.get_issue_with_task_counts(issue_id)

        assert isinstance(result, IssueWithTaskCount)
        assert result.task_count == 3
        assert result.issue_number == "1.0"
        assert result.title == "Test Issue"

    def test_get_issue_with_task_counts_returns_none_for_nonexistent(self, db_no_migrations):
        """get_issue_with_task_counts should return None for nonexistent issue."""
        result = db_no_migrations.get_issue_with_task_counts(99999)
        assert result is None

    def test_get_issue_with_task_counts_zero_tasks(self, db_with_data):
        """get_issue_with_task_counts should return 0 for issue with no tasks."""
        db, project_id, issue_id = db_with_data

        result = db.get_issue_with_task_counts(issue_id)

        assert result.task_count == 0
