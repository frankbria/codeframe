"""API tests for discovery progress endpoint (cf-17.2).

Following TDD: These tests are written FIRST before API implementation.
Tests verify GET /api/projects/{id}/discovery/progress endpoint.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from codeframe.ui.server import app
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus


@pytest.fixture
def test_db_path(tmp_path):
    """Create temporary test database."""
    db_path = tmp_path / "test.db"
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def test_client(test_db_path):
    """Create test client with initialized database."""
    # Initialize database
    db = Database(test_db_path)
    db.initialize()

    # Set database path in app state
    app.state.db = db

    # Create test client
    client = TestClient(app)

    yield client

    # Cleanup
    db.close()


class TestDiscoveryProgressEndpoint:
    """Test GET /api/projects/{id}/discovery/progress endpoint (cf-17.2)."""

    def test_get_discovery_progress_returns_404_for_nonexistent_project(self, test_client):
        """Test endpoint returns 404 for non-existent project."""
        # ACT
        response = test_client.get("/api/projects/99999/discovery/progress")

        # ASSERT
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_progress_returns_null_when_discovery_not_started(
        self, mock_provider_class, test_client
    ):
        """Test endpoint returns null for discovery when in idle state."""
        # ARRANGE
        # Create project
        project_id = app.state.db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        # ACT
        response = test_client.get(f"/api/projects/{project_id}/discovery/progress")

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert data["project_id"] == project_id
        assert data["phase"] == "discovery"  # Default phase
        assert data["discovery"] is None  # Discovery not started

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_progress_returns_progress_when_discovering(
        self, mock_provider_class, test_client
    ):
        """Test endpoint returns discovery progress when in discovering state."""
        # ARRANGE
        # Create project
        project_id = app.state.db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # Start discovery and answer 3 questions
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=app.state.db, api_key="test-key")
        agent.start_discovery()
        agent.process_discovery_answer("Answer 1 with sufficient content")
        agent.process_discovery_answer("Answer 2 with sufficient content")
        agent.process_discovery_answer("Answer 3 with sufficient content")

        # ACT
        response = test_client.get(f"/api/projects/{project_id}/discovery/progress")

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert data["project_id"] == project_id
        assert data["phase"] == "discovery"
        assert data["discovery"] is not None

        discovery = data["discovery"]
        assert discovery["state"] == "discovering"
        assert discovery["progress_percentage"] == 60.0  # 3/5 * 100
        assert discovery["answered_count"] == 3
        assert discovery["total_required"] == 5
        assert discovery["remaining_count"] == 2
        assert "current_question" in discovery
        assert discovery["current_question"] is not None

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_progress_returns_100_percent_when_completed(
        self, mock_provider_class, test_client
    ):
        """Test endpoint returns 100% progress when discovery completed."""
        # ARRANGE
        # Create project
        project_id = app.state.db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # Complete discovery
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=app.state.db, api_key="test-key")
        agent.start_discovery()

        for i in range(5):
            agent.process_discovery_answer(f"Answer {i + 1} with sufficient content")

        # ACT
        response = test_client.get(f"/api/projects/{project_id}/discovery/progress")

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert data["project_id"] == project_id
        assert data["phase"] == "discovery"
        assert data["discovery"] is not None

        discovery = data["discovery"]
        assert discovery["state"] == "completed"
        assert discovery["progress_percentage"] == 100.0
        assert discovery["answered_count"] == 5
        assert discovery["total_required"] == 5
        assert "structured_data" in discovery

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_progress_matches_project_phase(self, mock_provider_class, test_client):
        """Test endpoint returns correct phase field matching project.phase."""
        # ARRANGE
        # Create project with specific phase
        project_id = app.state.db.create_project("test-project", "Test Project project")

        # Update project phase to "planning"
        app.state.db.update_project(project_id, {"phase": "planning"})

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        # ACT
        response = test_client.get(f"/api/projects/{project_id}/discovery/progress")

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert data["phase"] == "planning"
        assert data["project_id"] == project_id

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_progress_excludes_answers_field(self, mock_provider_class, test_client):
        """Test endpoint does not include the raw answers field for security."""
        # ARRANGE
        # Create project
        project_id = app.state.db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # Start discovery
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=app.state.db, api_key="test-key")
        agent.start_discovery()
        agent.process_discovery_answer("Answer 1 with sufficient content")

        # ACT
        response = test_client.get(f"/api/projects/{project_id}/discovery/progress")

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        discovery = data["discovery"]
        # Should not include raw answers dictionary
        assert "answers" not in discovery
