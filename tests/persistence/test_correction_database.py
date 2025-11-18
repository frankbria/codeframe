"""
Unit tests for correction attempt database methods (cf-43) - TDD Implementation.

Tests written FIRST following RED-GREEN-REFACTOR methodology.
"""

import pytest
from codeframe.persistence.database import Database


class TestCorrectionAttemptDatabase:
    """Test database methods for correction attempts."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create an in-memory database for testing."""
        db = Database(":memory:")
        db.initialize()
        # Create a test project and task
        project_id = db.create_project("test-project", "Test Project project")
        # Note: create_task requires a Task object, so we'll use SQL directly for test
        cursor = db.conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (project_id, title, description, status, priority, workflow_step) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, "Test Task", "Test Description", "in_progress", 2, 1),
        )
        db.conn.commit()
        task_id = cursor.lastrowid
        db._test_task_id = task_id
        yield db
        db.close()

    def test_create_correction_attempt(self, db):
        """Test creating a correction attempt record."""
        attempt_id = db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=1,
            error_analysis="AssertionError: expected 5, got 3",
            fix_description="Added edge case handling",
            code_changes="+ if n == 0: return 1",
            test_result_id=None,
        )

        assert attempt_id is not None
        assert attempt_id > 0

    def test_create_correction_attempt_minimal(self, db):
        """Test creating correction attempt with minimal fields."""
        attempt_id = db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=2,
            error_analysis="ValueError: invalid input",
            fix_description="Added validation",
        )

        assert attempt_id is not None

    def test_get_correction_attempts_by_task(self, db):
        """Test retrieving correction attempts for a task."""
        # Create multiple attempts
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=1,
            error_analysis="Error 1",
            fix_description="Fix 1",
        )
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=2,
            error_analysis="Error 2",
            fix_description="Fix 2",
        )

        attempts = db.get_correction_attempts_by_task(db._test_task_id)

        assert len(attempts) == 2
        assert attempts[0]["attempt_number"] == 1
        assert attempts[1]["attempt_number"] == 2

    def test_get_latest_correction_attempt(self, db):
        """Test getting the most recent correction attempt."""
        # Create 3 attempts
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=1,
            error_analysis="Error 1",
            fix_description="Fix 1",
        )
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=2,
            error_analysis="Error 2",
            fix_description="Fix 2",
        )
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=3,
            error_analysis="Error 3",
            fix_description="Fix 3",
        )

        latest = db.get_latest_correction_attempt(db._test_task_id)

        assert latest is not None
        assert latest["attempt_number"] == 3
        assert latest["error_analysis"] == "Error 3"

    def test_get_latest_correction_attempt_none(self, db):
        """Test getting latest attempt when none exist."""
        latest = db.get_latest_correction_attempt(db._test_task_id)
        assert latest is None

    def test_count_correction_attempts(self, db):
        """Test counting correction attempts for a task."""
        # Initially 0
        assert db.count_correction_attempts(db._test_task_id) == 0

        # Add 2 attempts
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=1,
            error_analysis="Error 1",
            fix_description="Fix 1",
        )
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=2,
            error_analysis="Error 2",
            fix_description="Fix 2",
        )

        assert db.count_correction_attempts(db._test_task_id) == 2

    def test_correction_attempt_with_test_result(self, db):
        """Test creating correction attempt linked to test result."""
        # Create a test result first
        test_result_id = db.create_test_result(
            task_id=db._test_task_id, status="failed", passed=5, failed=2, errors=0
        )

        # Create correction attempt referencing test result
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=1,
            error_analysis="Tests failed",
            fix_description="Fixed assertions",
            test_result_id=test_result_id,
        )

        attempts = db.get_correction_attempts_by_task(db._test_task_id)
        assert len(attempts) == 1
        assert attempts[0]["test_result_id"] == test_result_id

    def test_correction_attempts_ordered_by_attempt_number(self, db):
        """Test that attempts are returned in order."""
        # Create out of order
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=3,
            error_analysis="Error 3",
            fix_description="Fix 3",
        )
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=1,
            error_analysis="Error 1",
            fix_description="Fix 1",
        )
        db.create_correction_attempt(
            task_id=db._test_task_id,
            attempt_number=2,
            error_analysis="Error 2",
            fix_description="Fix 2",
        )

        attempts = db.get_correction_attempts_by_task(db._test_task_id)

        assert len(attempts) == 3
        assert attempts[0]["attempt_number"] == 1
        assert attempts[1]["attempt_number"] == 2
        assert attempts[2]["attempt_number"] == 3
