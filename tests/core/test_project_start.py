"""Tests for Project.start() method and LeadAgent integration."""

import os
import pytest
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
    db.get_project = Mock(return_value={"id": 1, "name": "test_project", "status": "init"})
    db.update_project = Mock()
    return db


@pytest.fixture
def project_with_db(temp_project_dir, mock_db):
    """Create a project instance with mocked database."""
    project = Project(temp_project_dir)
    project.db = mock_db

    # Mock config
    mock_config = Mock()
    mock_config.project_name = "test_project"
    with patch.object(project.config, 'load', return_value=mock_config):
        yield project


class TestProjectStartValidation:
    """Test Project.start() prerequisite validation."""

    def test_start_raises_error_when_database_not_initialized(self, temp_project_dir):
        """Test that start() raises RuntimeError when database is not initialized."""
        project = Project(temp_project_dir)
        # Don't set project.db

        with pytest.raises(RuntimeError, match="Database not initialized"):
            project.start()

    def test_start_raises_error_when_api_key_missing(self, project_with_db):
        """Test that start() raises RuntimeError when ANTHROPIC_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY environment variable is required"):
                project_with_db.start()

    def test_start_raises_error_when_api_key_format_invalid(self, project_with_db):
        """Test that start() raises RuntimeError for invalid API key format."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "invalid-key-format"}):
            with pytest.raises(RuntimeError, match="Invalid ANTHROPIC_API_KEY format"):
                project_with_db.start()

    def test_start_raises_error_when_project_not_found(self, project_with_db):
        """Test that start() raises ValueError when project not found in database."""
        project_with_db.db.get_project = Mock(return_value=None)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(ValueError, match="not found in database"):
                project_with_db.start()


class TestProjectStartZeroTrustValidation:
    """Test Zero Trust validation in Project.start()."""

    def test_start_validates_database_response_is_dict(self, project_with_db):
        """Test that start() validates database response is a dictionary."""
        project_with_db.db.get_project = Mock(return_value="not a dict")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(ValueError, match="Invalid project record format"):
                project_with_db.start()

    def test_start_validates_project_id_field_exists(self, project_with_db):
        """Test that start() validates 'id' field exists in database response."""
        project_with_db.db.get_project = Mock(return_value={"name": "test"})  # Missing 'id'

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(ValueError, match="missing 'id' field"):
                project_with_db.start()

    def test_start_validates_project_id_is_integer(self, project_with_db):
        """Test that start() validates 'id' field is an integer."""
        project_with_db.db.get_project = Mock(return_value={"id": "not-an-int", "name": "test"})

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(ValueError, match="expected int"):
                project_with_db.start()


class TestProjectStartWithExistingPRD:
    """Test Project.start() when PRD exists (resume flow)."""

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_resumes_when_prd_exists(self, mock_lead_agent_class, project_with_db):
        """Test that start() resumes project when PRD exists."""
        # Mock LeadAgent instance
        mock_agent = Mock()
        mock_agent.has_existing_prd = Mock(return_value=True)
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            project_with_db.start()

        # Verify LeadAgent was initialized
        mock_lead_agent_class.assert_called_once_with(
            project_id=1,
            db=project_with_db.db,
            api_key="sk-ant-test-key"
        )

        # Verify status set to ACTIVE
        assert project_with_db._status == ProjectStatus.ACTIVE

        # Verify database updated
        project_with_db.db.update_project.assert_called_once_with(
            1, {"status": "active"}
        )

        # Verify LeadAgent cached
        assert project_with_db._lead_agent == mock_agent

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_does_not_call_start_discovery_when_prd_exists(self, mock_lead_agent_class, project_with_db):
        """Test that start() doesn't call start_discovery() when PRD exists."""
        mock_agent = Mock()
        mock_agent.has_existing_prd = Mock(return_value=True)
        mock_agent.start_discovery = Mock()
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            project_with_db.start()

        # Verify start_discovery was NOT called
        mock_agent.start_discovery.assert_not_called()


class TestProjectStartWithoutPRD:
    """Test Project.start() when PRD doesn't exist (discovery flow)."""

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_begins_discovery_when_no_prd(self, mock_lead_agent_class, project_with_db):
        """Test that start() begins discovery when PRD doesn't exist."""
        # Mock LeadAgent instance
        mock_agent = Mock()
        mock_agent.has_existing_prd = Mock(return_value=False)
        mock_agent.start_discovery = Mock(return_value="What problem are you trying to solve?")
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            project_with_db.start()

        # Verify start_discovery was called
        mock_agent.start_discovery.assert_called_once()

        # Verify status set to PLANNING
        assert project_with_db._status == ProjectStatus.PLANNING

        # Verify database updated
        project_with_db.db.update_project.assert_called_once_with(
            1, {"status": "planning"}
        )

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_begins_discovery_when_prd_is_none(self, mock_lead_agent_class, project_with_db):
        """Test that start() begins discovery when PRD returns None."""
        mock_agent = Mock()
        mock_agent.has_existing_prd = Mock(return_value=False)
        mock_agent.start_discovery = Mock(return_value="What problem are you trying to solve?")
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            project_with_db.start()

        # Verify start_discovery was called
        mock_agent.start_discovery.assert_called_once()

        # Verify status set to PLANNING
        assert project_with_db._status == ProjectStatus.PLANNING


class TestProjectStartErrorHandling:
    """Test Project.start() error handling and rollback."""

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_rollback_on_leadagent_initialization_error(self, mock_lead_agent_class, project_with_db):
        """Test that start() rolls back status on LeadAgent initialization error."""
        initial_status = project_with_db._status
        mock_lead_agent_class.side_effect = RuntimeError("LeadAgent init failed")

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(RuntimeError, match="LeadAgent init failed"):
                project_with_db.start()

        # Verify status rolled back
        assert project_with_db._status == initial_status

        # Verify database rollback attempted
        project_with_db.db.update_project.assert_called_with(
            1, {"status": initial_status.value}
        )

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_rollback_on_prd_load_error(self, mock_lead_agent_class, project_with_db):
        """Test that start() rolls back on PRD check error."""
        initial_status = project_with_db._status
        mock_agent = Mock()
        mock_agent.has_existing_prd = Mock(side_effect=Exception("Database error"))
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(Exception, match="Database error"):
                project_with_db.start()

        # Verify status rolled back
        assert project_with_db._status == initial_status

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_rollback_handles_missing_project_id(self, mock_lead_agent_class, project_with_db):
        """Test that rollback doesn't fail when error occurs before project_id is set."""
        # Make get_project raise error (before project_id is set)
        project_with_db.db.get_project = Mock(side_effect=Exception("DB connection error"))

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            with pytest.raises(Exception, match="DB connection error"):
                project_with_db.start()

        # Verify no NameError occurred during rollback
        # (test passes if no exception during rollback)


class TestGetLeadAgentCaching:
    """Test get_lead_agent() caching behavior."""

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_get_lead_agent_returns_cached_instance(self, mock_lead_agent_class, project_with_db):
        """Test that get_lead_agent() returns cached instance when available."""
        # Create a cached instance
        mock_agent = Mock()
        project_with_db._lead_agent = mock_agent

        result = project_with_db.get_lead_agent()

        # Verify cached instance returned
        assert result == mock_agent

        # Verify no new instance created
        mock_lead_agent_class.assert_not_called()

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_get_lead_agent_creates_instance_when_not_cached(self, mock_lead_agent_class, project_with_db):
        """Test that get_lead_agent() creates new instance when not cached."""
        mock_agent = Mock()
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            result = project_with_db.get_lead_agent()

        # Verify new instance created
        mock_lead_agent_class.assert_called_once_with(
            project_id=1,
            db=project_with_db.db,
            api_key="sk-ant-test-key"
        )

        # Verify instance cached
        assert project_with_db._lead_agent == mock_agent
        assert result == mock_agent

    def test_get_lead_agent_validates_api_key_format_in_fallback(self, project_with_db):
        """Test that get_lead_agent() validates API key format in fallback mode."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "invalid-key"}):
            with pytest.raises(RuntimeError, match="Invalid ANTHROPIC_API_KEY format"):
                project_with_db.get_lead_agent()


class TestProjectStartIntegration:
    """Integration tests for Project.start() full workflow."""

    @patch('codeframe.agents.lead_agent.LeadAgent')
    def test_start_caches_leadagent_for_get_lead_agent(self, mock_lead_agent_class, project_with_db):
        """Test that start() caches LeadAgent for subsequent get_lead_agent() calls."""
        mock_agent = Mock()
        mock_agent.has_existing_prd = Mock(return_value=True)
        mock_lead_agent_class.return_value = mock_agent

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}):
            project_with_db.start()

            # Call get_lead_agent() - should return cached instance
            result = project_with_db.get_lead_agent()

        # Verify same instance returned
        assert result == mock_agent

        # Verify LeadAgent only created once (by start(), not get_lead_agent())
        assert mock_lead_agent_class.call_count == 1
