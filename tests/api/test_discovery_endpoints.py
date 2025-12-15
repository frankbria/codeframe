"""API tests for discovery answer submission endpoint (012-discovery-answer-ui).

Following TDD: These tests are written FIRST before API implementation.
Tests verify POST /api/projects/{id}/discovery/answer endpoint.
"""

from unittest.mock import Mock, patch


def get_db_from_client(api_client):
    """Get database instance from test client's app."""
    from codeframe.ui import server

    return server.app.state.db


class TestDiscoveryAnswerEndpoint:
    """Test POST /api/projects/{id}/discovery/answer endpoint (US5)."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_post_discovery_answer_returns_200_with_valid_answer(
        self, mock_provider_class, api_client
    ):
        """Test endpoint returns 200 with valid answer (T030)."""
        # ARRANGE
        # Create project
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # Start discovery
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")
        agent.start_discovery()

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer",
            json={"answer": "This is a valid answer to the discovery question."},
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "next_question" in data
        assert "is_complete" in data
        assert "current_index" in data
        assert "total_questions" in data
        assert "progress_percentage" in data

    def test_post_with_empty_answer_returns_400(self, api_client):
        """Test endpoint returns 422 with empty answer (T031) - Pydantic validation."""
        # ARRANGE
        # Create project
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        # ACT - empty string
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer", json={"answer": ""}
        )

        # ASSERT - Pydantic returns 422 for validation errors
        assert response.status_code == 422
        assert "detail" in response.json()

        # ACT - whitespace only
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer", json={"answer": "   "}
        )

        # ASSERT - Pydantic returns 422 for validation errors
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_post_with_answer_exceeding_5000_chars_returns_400(self, api_client):
        """Test endpoint returns 422 when answer exceeds 5000 characters (T032) - Pydantic validation."""
        # ARRANGE
        # Create project
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        # ACT
        long_answer = "a" * 5001
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer", json={"answer": long_answer}
        )

        # ASSERT - Pydantic returns 422 for validation errors
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_post_with_invalid_project_id_returns_404(self, api_client):
        """Test endpoint returns 404 with invalid project_id (T033)."""
        # ACT
        response = api_client.post(
            "/api/projects/99999/discovery/answer",
            json={"answer": "This is a valid answer."},
        )

        # ASSERT
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_post_when_not_in_discovery_phase_returns_400(self, mock_provider_class, api_client):
        """Test endpoint returns 400 when project not in discovery phase (T034)."""
        # ARRANGE
        # Create project
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        # Update project phase to "planning" (not discovery)
        db.update_project(project_id, {"phase": "planning"})

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer",
            json={"answer": "This is a valid answer."},
        )

        # ASSERT
        assert response.status_code == 400
        assert "not in discovery phase" in response.json()["detail"].lower()

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_not_started_returns_400(self, mock_provider_class, api_client):
        """Test endpoint returns 400 when discovery state is 'idle' (not started)."""
        # ARRANGE
        # Create project in discovery phase but DON'T start discovery
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "discovery"})

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer",
            json={"answer": "This is a valid answer."},
        )

        # ASSERT
        assert response.status_code == 400
        response_data = response.json()
        assert "discovery is not active" in response_data["detail"].lower()
        assert "idle" in response_data["detail"].lower()

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_lead_agent_process_discovery_answer_called_correctly(
        self, mock_provider_class, api_client
    ):
        """Test LeadAgent.process_discovery_answer() called with trimmed answer (T035)."""
        # ARRANGE
        # Create project
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # Start discovery
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")
        agent.start_discovery()

        # ACT - submit answer with leading/trailing whitespace
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer",
            json={"answer": "  This is a valid answer with whitespace.  "},
        )

        # ASSERT
        assert response.status_code == 200

        # Verify the answer was processed (current_index advanced from 0 to 1)
        data = response.json()
        assert data["current_index"] == 1  # Should have advanced after first answer
        assert data["progress_percentage"] == 20.0  # 1/5 questions = 20%

        # Verify answer was persisted by creating new agent and checking state
        new_agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")
        new_status = new_agent.get_discovery_status()
        assert new_status["answered_count"] == 1  # Answer should be persisted

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_response_includes_required_fields(self, mock_provider_class, api_client):
        """Test response includes next_question, is_complete, current_index (T036)."""
        # ARRANGE
        # Create project
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # Start discovery
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")
        agent.start_discovery()

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/answer",
            json={"answer": "This is a valid answer."},
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        # Verify all required fields exist
        assert "success" in data
        assert "next_question" in data
        assert "is_complete" in data
        assert "current_index" in data
        assert "total_questions" in data
        assert "progress_percentage" in data

        # Verify data types
        assert isinstance(data["success"], bool)
        assert data["success"] is True
        assert isinstance(data["is_complete"], bool)
        assert isinstance(data["current_index"], int)
        assert isinstance(data["total_questions"], int)
        assert isinstance(data["progress_percentage"], (int, float))

        # Verify values are reasonable
        assert data["current_index"] >= 0
        assert data["total_questions"] > 0
        assert 0 <= data["progress_percentage"] <= 100

        # When not complete, next_question should be a string
        if not data["is_complete"]:
            assert isinstance(data["next_question"], str)
            assert len(data["next_question"]) > 0
