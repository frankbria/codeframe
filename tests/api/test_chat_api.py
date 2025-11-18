"""
Tests for Chat API Endpoints (cf-14.1)

Test Coverage:
1. POST /api/projects/{id}/chat - Send message and get response
2. GET /api/projects/{id}/chat/history - Retrieve conversation history
3. Error handling:
   - 404: Project not found
   - 400: Empty message
   - 500: Agent communication failure
4. WebSocket broadcasting integration
5. Message persistence

Test Approach: TDD (RED-GREEN-REFACTOR)
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from codeframe.ui.server import app
from codeframe.core.models import AgentMaturity


def get_app():
    """Get the current app instance after module reload."""

    return app


@pytest.fixture
def test_project(api_client):
    """Create a test project with running Lead Agent."""
    project_id = get_app().state.db.create_project(
        name="Test Chat Project", description="Test Chat Project project"
    )

    # Create Lead Agent record
    get_app().state.db.create_agent(
        agent_id=f"lead-{project_id}",
        agent_type="lead",
        provider="anthropic",
        maturity_level=AgentMaturity.D4,  # Expert level
    )

    return project_id


class TestChatEndpoint:
    """Test POST /api/projects/{id}/chat endpoint (cf-14.1)"""

    def test_send_message_success(self, api_client, test_project):
        """
        RED Test: Send message and get AI response

        Expected behavior:
        - Accept user message
        - Route to Lead Agent
        - Return AI response
        - Broadcast via WebSocket
        - Store message in database
        """
        # Arrange
        user_message = "Hello, I want to build a web app"

        # Import the server module to access running_agents
        from codeframe.ui import server

        # Mock Lead Agent
        mock_agent = Mock()
        mock_agent.chat.return_value = "Hi! Let's discuss your project. What features do you need?"

        # Add mock agent to running_agents dictionary
        server.running_agents[test_project] = mock_agent

        try:
            # Mock WebSocket broadcast
            with patch(
                "codeframe.ui.server.manager.broadcast", new_callable=AsyncMock
            ) as mock_broadcast:
                # Act
                response = api_client.post(
                    f"/api/projects/{test_project}/chat", json={"message": user_message}
                )

                # Assert
                assert response.status_code == 200
                data = response.json()

                # Check response structure
                assert "response" in data
                assert "timestamp" in data
                assert (
                    data["response"] == "Hi! Let's discuss your project. What features do you need?"
                )

                # Verify Lead Agent was called
                mock_agent.chat.assert_called_once_with(user_message)

                # Verify WebSocket broadcast was attempted
                assert mock_broadcast.called
        finally:
            # Clean up
            server.running_agents.pop(test_project, None)

    def test_send_message_empty_validation(self, api_client, test_project):
        """
        RED Test: Reject empty message with 400 Bad Request
        """
        # Act
        response = api_client.post(f"/api/projects/{test_project}/chat", json={"message": ""})

        # Assert
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_send_message_project_not_found(self, api_client):
        """
        RED Test: Return 404 for non-existent project
        """
        # Act
        response = api_client.post("/api/projects/99999/chat", json={"message": "Hello"})

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_send_message_agent_not_started(self, api_client):
        """
        RED Test: Return 400 if Lead Agent not started for project
        """
        # Arrange: Create project without starting agent
        project_id = get_app().state.db.create_project(name="Project Without Agent", description="Project Without Agent project")

        # Act
        response = api_client.post(f"/api/projects/{project_id}/chat", json={"message": "Hello"})

        # Assert
        assert response.status_code == 400
        assert "agent not started" in response.json()["detail"].lower()

    def test_send_message_agent_failure(self, api_client, test_project):
        """
        RED Test: Handle agent communication failure with 500
        """
        # Arrange
        with patch("codeframe.ui.server.running_agents") as mock_agents:
            mock_agent = Mock()
            mock_agent.chat.side_effect = Exception("API connection failed")
            mock_agents.get.return_value = mock_agent

            # Act
            response = api_client.post(f"/api/projects/{test_project}/chat", json={"message": "Hello"})

        # Assert
        assert response.status_code == 500
        assert "error" in response.json()["detail"].lower()


class TestChatHistoryEndpoint:
    """Test GET /api/projects/{id}/chat/history endpoint (cf-14.1)"""

    def test_get_history_success(self, api_client, test_project):
        """
        RED Test: Retrieve conversation history from database
        """
        # Arrange: Create conversation history
        get_app().state.db.create_memory(
            project_id=test_project, category="conversation", key="user", value="Hello"
        )
        get_app().state.db.create_memory(
            project_id=test_project,
            category="conversation",
            key="assistant",
            value="Hi! How can I help?",
        )
        get_app().state.db.create_memory(
            project_id=test_project,
            category="conversation",
            key="user",
            value="I want to build an app",
        )

        # Act
        response = api_client.get(f"/api/projects/{test_project}/chat/history")

        # Assert
        assert response.status_code == 200
        data = response.json()

        assert "messages" in data
        assert len(data["messages"]) == 3

        # Check chronological order
        messages = data["messages"]
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi! How can I help?"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "I want to build an app"

        # Check timestamps exist
        for msg in messages:
            assert "timestamp" in msg

    def test_get_history_pagination(self, api_client, test_project):
        """
        RED Test: Support pagination with limit and offset
        """
        # Arrange: Create 10 messages
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            get_app().state.db.create_memory(
                project_id=test_project, category="conversation", key=role, value=f"Message {i}"
            )

        # Act: Get first 5 messages
        response = api_client.get(
            f"/api/projects/{test_project}/chat/history", params={"limit": 5, "offset": 0}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 5
        assert data["messages"][0]["content"] == "Message 0"

        # Act: Get next 5 messages
        response = api_client.get(
            f"/api/projects/{test_project}/chat/history", params={"limit": 5, "offset": 5}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 5
        assert data["messages"][0]["content"] == "Message 5"

    def test_get_history_project_not_found(self, api_client):
        """
        RED Test: Return 404 for non-existent project
        """
        # Act
        response = api_client.get("/api/projects/99999/chat/history")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_history_empty(self, api_client, test_project):
        """
        RED Test: Return empty list for project with no conversation
        """
        # Act
        response = api_client.get(f"/api/projects/{test_project}/chat/history")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert data["messages"] == []


class TestChatWebSocketIntegration:
    """Test WebSocket broadcasting for chat messages (cf-14.1)"""

    @pytest.mark.asyncio
    async def test_chat_broadcasts_message(self, api_client, test_project):
        """
        RED Test: Verify chat message broadcasts via WebSocket
        """
        # Arrange
        from codeframe.ui import server

        # Mock Lead Agent
        mock_agent = Mock()
        mock_agent.chat.return_value = "AI response"

        # Add mock agent to running_agents dictionary
        server.running_agents[test_project] = mock_agent

        try:
            with patch(
                "codeframe.ui.server.manager.broadcast", new_callable=AsyncMock
            ) as mock_broadcast:
                # Act
                response = api_client.post(
                    f"/api/projects/{test_project}/chat", json={"message": "Hello"}
                )

                # Assert
                assert response.status_code == 200

                # Verify broadcast was called with correct message structure
                assert mock_broadcast.call_count >= 1

                # Check broadcast message contains chat data
                broadcast_call = mock_broadcast.call_args_list[0]
                broadcast_message = broadcast_call[0][0]

                assert broadcast_message["type"] == "chat_message"
                assert broadcast_message["project_id"] == test_project
                assert "role" in broadcast_message
                assert "content" in broadcast_message
        finally:
            # Clean up
            server.running_agents.pop(test_project, None)

    @pytest.mark.asyncio
    async def test_chat_continues_when_broadcast_fails(self, api_client, test_project):
        """
        Test: Chat continues working even if WebSocket broadcast fails

        Covers edge case where broadcast exception is caught and ignored (line 512-514)
        """
        # Arrange
        from codeframe.ui import server

        mock_agent = Mock()
        mock_agent.chat.return_value = "Response despite broadcast failure"
        server.running_agents[test_project] = mock_agent

        try:
            # Mock broadcast to raise exception
            with patch(
                "codeframe.ui.server.manager.broadcast", new_callable=AsyncMock
            ) as mock_broadcast:
                mock_broadcast.side_effect = Exception("WebSocket connection lost")

                # Act
                response = api_client.post(
                    f"/api/projects/{test_project}/chat", json={"message": "Test message"}
                )

                # Assert - Chat should still work despite broadcast failure
                assert response.status_code == 200
                data = response.json()
                assert data["response"] == "Response despite broadcast failure"
                assert "timestamp" in data

                # Verify broadcast was attempted
                assert mock_broadcast.called
        finally:
            server.running_agents.pop(test_project, None)
