"""Tests for Project.pause() and Project.resume() methods."""

import pytest
from datetime import datetime, UTC
from unittest.mock import Mock, patch
from codeframe.core.project import Project
from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = Mock(spec=Database)
    db.conn = Mock()
    db.conn.cursor = Mock()

    # Mock cursor with fetchone returning project_id
    mock_cursor = Mock()
    mock_cursor.fetchone = Mock(return_value={"id": 1})
    db.conn.cursor.return_value = mock_cursor

    db.update_project = Mock()
    db.get_agents_for_project = Mock(return_value=[])
    return db


@pytest.fixture
def project_with_db(temp_project_dir, mock_db):
    """Create a project instance with mocked database."""
    project = Project(temp_project_dir)
    project.db = mock_db
    project._status = ProjectStatus.ACTIVE

    # Mock config
    mock_config = Mock()
    mock_config.project_name = "test_project"
    project.config.load = Mock(return_value=mock_config)

    return project


class TestProjectPauseValidation:
    """Test Project.pause() prerequisite validation."""

    def test_pause_raises_error_when_database_not_initialized(self, temp_project_dir):
        """Test that pause() raises RuntimeError when database is not initialized."""
        project = Project(temp_project_dir)
        # Don't set project.db

        with pytest.raises(RuntimeError, match="Database not initialized"):
            project.pause()

    def test_pause_raises_error_when_project_not_found(self, project_with_db):
        """Test that pause() raises ValueError when project not found in database."""
        # Mock cursor to return None (project not found)
        mock_cursor = Mock()
        mock_cursor.fetchone = Mock(return_value=None)
        project_with_db.db.conn.cursor.return_value = mock_cursor

        with pytest.raises(ValueError, match="not found in database"):
            project_with_db.pause()


class TestProjectPauseSuccessPath:
    """Test successful Project.pause() execution."""

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_with_no_active_agents(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test pause with no active agents (no flash save needed)."""
        # Setup mocks
        mock_context_mgr = Mock()
        mock_context_mgr_class.return_value = mock_context_mgr

        mock_checkpoint_mgr = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.git_commit = "abc123def456"
        mock_checkpoint.name = "Project paused"
        mock_checkpoint_mgr.create_checkpoint.return_value = mock_checkpoint
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        # No active agents
        project_with_db.db.get_agents_for_project.return_value = []

        # Execute
        result = project_with_db.pause(reason="test pause")

        # Verify
        assert result["success"] is True
        assert result["checkpoint_id"] == 42
        assert result["tokens_before"] == 0
        assert result["tokens_after"] == 0
        assert result["reduction_percentage"] == 0.0
        assert result["items_archived"] == 0
        assert "paused_at" in result

        # Verify status updated
        project_with_db.db.update_project.assert_called_once()
        call_args = project_with_db.db.update_project.call_args[0]
        assert call_args[0] == 1  # project_id
        assert call_args[1]["status"] == ProjectStatus.PAUSED.value
        assert "paused_at" in call_args[1]

        # Verify checkpoint created
        mock_checkpoint_mgr.create_checkpoint.assert_called_once()
        checkpoint_call = mock_checkpoint_mgr.create_checkpoint.call_args[1]
        assert checkpoint_call["trigger"] == "pause"
        assert "test pause" in checkpoint_call["name"]

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_with_flash_save_success(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test pause with successful flash save for active agents."""
        # Setup mocks
        mock_context_mgr = Mock()
        mock_context_mgr.should_flash_save.return_value = True
        mock_context_mgr.flash_save.return_value = {
            "tokens_before": 150000,
            "tokens_after": 75000,
            "reduction_percentage": 50.0,
            "items_archived": 120
        }
        mock_context_mgr_class.return_value = mock_context_mgr

        mock_checkpoint_mgr = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.git_commit = "abc123"
        mock_checkpoint.name = "Project paused"
        mock_checkpoint_mgr.create_checkpoint.return_value = mock_checkpoint
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        # Active agents
        project_with_db.db.get_agents_for_project.return_value = [
            {"agent_id": "backend-001"},
            {"agent_id": "frontend-001"}
        ]

        # Execute
        result = project_with_db.pause()

        # Verify flash save called for each agent
        assert mock_context_mgr.flash_save.call_count == 2

        # Verify aggregated results
        assert result["success"] is True
        assert result["tokens_before"] == 300000  # 150k × 2
        assert result["tokens_after"] == 150000   # 75k × 2
        assert result["reduction_percentage"] == 50.0
        assert result["items_archived"] == 240    # 120 × 2

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_with_flash_save_failures_continues(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test pause continues even if individual flash saves fail."""
        # Setup mocks
        mock_context_mgr = Mock()
        mock_context_mgr.should_flash_save.return_value = True

        # First agent succeeds, second fails
        mock_context_mgr.flash_save.side_effect = [
            {
                "tokens_before": 100000,
                "tokens_after": 50000,
                "reduction_percentage": 50.0,
                "items_archived": 80
            },
            Exception("Flash save failed for agent 2")
        ]
        mock_context_mgr_class.return_value = mock_context_mgr

        mock_checkpoint_mgr = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.git_commit = "abc123"
        mock_checkpoint.name = "Project paused"
        mock_checkpoint_mgr.create_checkpoint.return_value = mock_checkpoint
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        # Two active agents
        project_with_db.db.get_agents_for_project.return_value = [
            {"agent_id": "backend-001"},
            {"agent_id": "frontend-001"}
        ]

        # Execute (should not raise exception)
        result = project_with_db.pause()

        # Verify partial success
        assert result["success"] is True
        assert result["tokens_before"] == 100000  # Only first agent
        assert result["tokens_after"] == 50000
        assert result["items_archived"] == 80

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_with_reason_included_in_checkpoint(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test pause reason is included in checkpoint name and description."""
        # Setup mocks
        mock_context_mgr_class.return_value = Mock()

        mock_checkpoint_mgr = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.git_commit = "abc123"
        mock_checkpoint.name = "Project paused: resource limit"
        mock_checkpoint_mgr.create_checkpoint.return_value = mock_checkpoint
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        project_with_db.db.get_agents_for_project.return_value = []

        # Execute with reason
        result = project_with_db.pause(reason="resource_limit")

        # Verify checkpoint call includes reason
        checkpoint_call = mock_checkpoint_mgr.create_checkpoint.call_args[1]
        assert "resource_limit" in checkpoint_call["name"]
        assert "resource_limit" in checkpoint_call["description"]

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_timestamp_consistency(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test that same paused_at timestamp is used in DB and result."""
        # Setup mocks
        mock_context_mgr_class.return_value = Mock()

        mock_checkpoint_mgr = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.git_commit = "abc123"
        mock_checkpoint.name = "Project paused"
        mock_checkpoint_mgr.create_checkpoint.return_value = mock_checkpoint
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        project_with_db.db.get_agents_for_project.return_value = []

        # Execute
        result = project_with_db.pause()

        # Get timestamp from database update call
        db_call_args = project_with_db.db.update_project.call_args[0]
        db_timestamp = db_call_args[1]["paused_at"]

        # Get timestamp from result
        result_timestamp = result["paused_at"]

        # Verify they match
        assert db_timestamp == result_timestamp

        # Verify format is ISO 8601 with Z suffix
        assert result_timestamp.endswith("Z")
        assert "T" in result_timestamp


class TestProjectPauseErrorHandling:
    """Test Project.pause() error handling and rollback."""

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_rollback_on_checkpoint_failure(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test that status is rolled back if checkpoint creation fails."""
        # Setup mocks
        mock_context_mgr_class.return_value = Mock()

        mock_checkpoint_mgr = Mock()
        mock_checkpoint_mgr.create_checkpoint.side_effect = Exception("Git commit failed")
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        project_with_db.db.get_agents_for_project.return_value = []
        original_status = project_with_db._status

        # Execute and expect exception
        with pytest.raises(Exception, match="Git commit failed"):
            project_with_db.pause()

        # Verify status was rolled back
        assert project_with_db._status == original_status

        # Verify rollback was attempted on database
        # Note: update_project is called AFTER checkpoint creation in pause(),
        # so if checkpoint fails, update_project is never called initially.
        # Rollback attempts to call update_project once.
        assert project_with_db.db.update_project.call_count == 1  # Rollback only

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_handles_rollback_failure_gracefully(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test that rollback failures don't mask original error."""
        # Setup mocks
        mock_context_mgr_class.return_value = Mock()

        mock_checkpoint_mgr = Mock()
        mock_checkpoint_mgr.create_checkpoint.side_effect = Exception("Original error")
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        # Make rollback also fail
        project_with_db.db.update_project.side_effect = [
            None,  # First call (in pause)
            Exception("Rollback failed")  # Second call (rollback)
        ]
        project_with_db.db.get_agents_for_project.return_value = []

        # Execute - should raise original error, not rollback error
        with pytest.raises(Exception, match="Original error"):
            project_with_db.pause()


class TestProjectResumeWithPausedAt:
    """Test Project.resume() clears paused_at timestamp."""

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    def test_resume_clears_paused_at_timestamp(
        self, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test that resume() clears paused_at field in database."""
        # Setup mocks
        mock_checkpoint_mgr = Mock()

        # Mock checkpoint
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.name = "Test checkpoint"
        mock_checkpoint.created_at = datetime.now(UTC)
        mock_checkpoint.git_commit = "abc123def456"

        # Mock list_checkpoints to return checkpoint
        mock_checkpoint_mgr.list_checkpoints.return_value = [mock_checkpoint]

        # Mock restore_checkpoint to return success
        mock_checkpoint_mgr.restore_checkpoint.return_value = {
            "success": True,
            "items_restored": 150
        }
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        # Mock database methods
        project_with_db.db.get_checkpoint_by_id = Mock(return_value=mock_checkpoint)

        # Execute resume
        project_with_db.resume()

        # Verify paused_at was cleared
        assert project_with_db.db.update_project.call_count == 1
        call_args = project_with_db.db.update_project.call_args[0]
        assert call_args[0] == 1  # project_id
        assert call_args[1] == {"paused_at": None}

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    def test_resume_from_specific_checkpoint(
        self, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test resume from specific checkpoint by ID."""
        # Setup mocks
        mock_checkpoint_mgr = Mock()

        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.name = "Specific checkpoint"
        mock_checkpoint.created_at = datetime.now(UTC)
        mock_checkpoint.git_commit = "abc123"

        mock_checkpoint_mgr.restore_checkpoint.return_value = {
            "success": True,
            "items_restored": 200
        }
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        project_with_db.db.get_checkpoint_by_id = Mock(return_value=mock_checkpoint)

        # Execute resume with specific checkpoint_id
        project_with_db.resume(checkpoint_id=42)

        # Verify correct checkpoint was used
        project_with_db.db.get_checkpoint_by_id.assert_called_once_with(42)

        # Verify paused_at cleared
        call_args = project_with_db.db.update_project.call_args[0]
        assert call_args[1] == {"paused_at": None}

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    def test_resume_raises_error_when_no_checkpoints_exist(
        self, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test resume raises ValueError when no checkpoints exist."""
        mock_checkpoint_mgr = Mock()
        mock_checkpoint_mgr.list_checkpoints.return_value = []
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        with pytest.raises(ValueError, match="No checkpoints available"):
            project_with_db.resume()

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    def test_resume_raises_error_when_checkpoint_not_found(
        self, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test resume raises ValueError when specific checkpoint not found."""
        mock_checkpoint_mgr = Mock()
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        project_with_db.db.get_checkpoint_by_id = Mock(return_value=None)

        with pytest.raises(ValueError, match="Checkpoint 999 not found"):
            project_with_db.resume(checkpoint_id=999)


class TestProjectPauseIdempotency:
    """Test Project.pause() idempotency and duplicate pause handling."""

    @patch('codeframe.lib.checkpoint_manager.CheckpointManager')
    @patch('codeframe.lib.context_manager.ContextManager')
    def test_pause_when_already_paused(
        self, mock_context_mgr_class, mock_checkpoint_mgr_class, project_with_db
    ):
        """Test that pausing an already paused project creates duplicate checkpoint.

        Note: Current implementation allows duplicate pause. This test documents
        the behavior. Future enhancement could add idempotency check.
        """
        # Setup mocks
        mock_context_mgr_class.return_value = Mock()

        mock_checkpoint_mgr = Mock()
        mock_checkpoint = Mock()
        mock_checkpoint.id = 42
        mock_checkpoint.git_commit = "abc123"
        mock_checkpoint.name = "Project paused"
        mock_checkpoint_mgr.create_checkpoint.return_value = mock_checkpoint
        mock_checkpoint_mgr_class.return_value = mock_checkpoint_mgr

        project_with_db.db.get_agents_for_project.return_value = []

        # Set status to already paused
        project_with_db._status = ProjectStatus.PAUSED

        # Execute - currently allows duplicate pause
        result = project_with_db.pause()

        # Verify it succeeded (documents current behavior)
        assert result["success"] is True

        # Note: Recommendation from code review is to add idempotency check
        # to prevent duplicate pause operations
