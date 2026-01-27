"""
Tests for intervention context database methods.

Test coverage for supervisor intervention persistence:
- Setting intervention context on tasks
- Retrieving intervention context
- Clearing intervention context
- JSON serialization/deserialization

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus

pytestmark = pytest.mark.v2


class TestInterventionContextMethods:
    """Test intervention context database operations."""

    @pytest.fixture
    def db_with_task(self, tmp_path):
        """Create database with a test task."""
        db = Database(":memory:")
        db.initialize()

        # Create project
        project_id = db.create_project("test", "Test project")

        # Create issue
        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": "1.0",
            "title": "Test Issue",
            "status": "pending",
            "priority": 0,
            "workflow_step": 1,
        })

        # Create task
        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Test Task",
            description="Test task description",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        return db, task_id

    def test_update_intervention_context_sets_value(self, db_with_task):
        """Test that intervention context can be set on a task."""
        db, task_id = db_with_task

        context = {
            "intervention_applied": True,
            "pattern_matched": "file_already_exists",
            "existing_files": ["src/components/Button.tsx"],
            "instruction": "Use edit operations for existing files",
            "strategy": "convert_create_to_edit",
        }

        db.update_task_intervention_context(task_id, context)

        # Verify it was set
        result = db.get_task_intervention_context(task_id)
        assert result is not None
        assert result["intervention_applied"] is True
        assert result["pattern_matched"] == "file_already_exists"
        assert result["existing_files"] == ["src/components/Button.tsx"]

    def test_get_intervention_context_returns_none_when_not_set(self, db_with_task):
        """Test that get returns None when no context is set."""
        db, task_id = db_with_task

        result = db.get_task_intervention_context(task_id)

        assert result is None

    def test_clear_intervention_context_removes_value(self, db_with_task):
        """Test that intervention context can be cleared."""
        db, task_id = db_with_task

        # Set context first
        context = {
            "intervention_applied": True,
            "pattern_matched": "file_already_exists",
        }
        db.update_task_intervention_context(task_id, context)

        # Verify it was set
        assert db.get_task_intervention_context(task_id) is not None

        # Clear it
        db.clear_task_intervention_context(task_id)

        # Verify it was cleared
        assert db.get_task_intervention_context(task_id) is None

    def test_intervention_context_handles_complex_structure(self, db_with_task):
        """Test that complex nested structures are preserved."""
        db, task_id = db_with_task

        context = {
            "intervention_applied": True,
            "pattern_matched": "file_already_exists",
            "existing_files": [
                "src/components/Button.tsx",
                "src/components/Header.tsx",
                "src/utils/helpers.py",
            ],
            "instruction": "Use edit operations for existing files",
            "strategy": "convert_create_to_edit",
            "metadata": {
                "attempt_count": 2,
                "previous_errors": ["FileExistsError: Button.tsx"],
            },
        }

        db.update_task_intervention_context(task_id, context)

        result = db.get_task_intervention_context(task_id)

        assert result["existing_files"] == [
            "src/components/Button.tsx",
            "src/components/Header.tsx",
            "src/utils/helpers.py",
        ]
        assert result["metadata"]["attempt_count"] == 2
        assert "FileExistsError" in result["metadata"]["previous_errors"][0]

    def test_intervention_context_can_be_updated(self, db_with_task):
        """Test that intervention context can be overwritten."""
        db, task_id = db_with_task

        # Set initial context
        initial_context = {
            "intervention_applied": True,
            "existing_files": ["file1.py"],
        }
        db.update_task_intervention_context(task_id, initial_context)

        # Update with new context
        updated_context = {
            "intervention_applied": True,
            "existing_files": ["file1.py", "file2.py"],
            "retry_count": 2,
        }
        db.update_task_intervention_context(task_id, updated_context)

        result = db.get_task_intervention_context(task_id)

        assert result["existing_files"] == ["file1.py", "file2.py"]
        assert result["retry_count"] == 2

    def test_intervention_context_update_via_update_task(self, db_with_task):
        """Test that intervention_context can be set via generic update_task."""
        db, task_id = db_with_task
        import json

        context = {
            "intervention_applied": True,
            "pattern_matched": "file_already_exists",
        }

        # Update using the generic update_task method
        db.update_task(task_id, {"intervention_context": json.dumps(context)})

        # Verify it was set (need to parse JSON manually here since update_task
        # doesn't parse it)
        result = db.get_task_intervention_context(task_id)

        assert result is not None
        assert result["intervention_applied"] is True

    def test_get_intervention_context_nonexistent_task(self, db_with_task):
        """Test that get returns None for nonexistent task."""
        db, _ = db_with_task

        result = db.get_task_intervention_context(99999)

        assert result is None

    def test_get_task_includes_intervention_context(self, db_with_task):
        """Test that db.get_task() returns Task with intervention_context populated.

        This verifies the _row_to_task() deserialization round-trip, which is
        critical for LeadAgent re-fetching tasks after intervention is applied.
        """
        db, task_id = db_with_task

        context = {
            "intervention_applied": True,
            "pattern_matched": "file_already_exists",
            "existing_files": ["src/app.py"],
            "strategy": "convert_create_to_edit",
            "intervention_retry_count": 1,
        }
        db.update_task_intervention_context(task_id, context)

        # Re-fetch via get_task (uses _row_to_task internally)
        task = db.get_task(task_id)

        assert task is not None
        assert task.intervention_context is not None
        assert task.intervention_context["intervention_applied"] is True
        assert task.intervention_context["strategy"] == "convert_create_to_edit"
        assert task.intervention_context["existing_files"] == ["src/app.py"]
        assert task.intervention_context["intervention_retry_count"] == 1

    def test_get_task_returns_none_intervention_context_when_unset(self, db_with_task):
        """Task.intervention_context is None when no context has been set."""
        db, task_id = db_with_task

        task = db.get_task(task_id)

        assert task is not None
        assert task.intervention_context is None
