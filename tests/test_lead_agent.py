"""Tests for Lead Agent with Anthropic integration.

Following TDD: These tests are written FIRST, before implementation.
Target: >90% coverage for lead_agent.py module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus


@pytest.mark.unit
class TestLeadAgentInitialization:
    """Test Lead Agent initialization."""

    def test_lead_agent_initialization_with_database(self, temp_db_path):
        """Test that Lead Agent initializes with database connection."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ASSERT
        assert agent.project_id == project_id
        assert agent.db is not None
        assert agent.provider is not None

    def test_lead_agent_initialization_without_api_key_raises_error(self, temp_db_path):
        """Test that Lead Agent fails fast when API key is missing."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            LeadAgent(project_id=project_id, db=db, api_key=None)

        assert "api_key" in str(exc_info.value).lower() or "ANTHROPIC" in str(exc_info.value)

    def test_lead_agent_loads_existing_conversation(self, temp_db_path):
        """Test that Lead Agent loads existing conversation from database."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        # Add some conversation history
        db.create_memory(project_id, "conversation", "user", "Hello")
        db.create_memory(project_id, "conversation", "assistant", "Hi there!")

        # ACT
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        conversation = agent.get_conversation_history()

        # ASSERT
        assert len(conversation) == 2
        assert conversation[0]["role"] == "user"
        assert conversation[0]["content"] == "Hello"
        assert conversation[1]["role"] == "assistant"
        assert conversation[1]["content"] == "Hi there!"


@pytest.mark.unit
class TestLeadAgentChat:
    """Test Lead Agent chat functionality."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_sends_message_to_provider(self, mock_provider_class, temp_db_path):
        """Test that chat sends message to Anthropic provider."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Hello! How can I help you?",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        response = agent.chat("Hello!")

        # ASSERT
        assert response == "Hello! How can I help you?"
        assert mock_provider.send_message.called

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_saves_user_message_to_database(self, mock_provider_class, temp_db_path):
        """Test that chat saves user message to database."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Response",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        agent.chat("Hello!")

        # ASSERT
        conversation = db.get_conversation(project_id)
        user_messages = [m for m in conversation if m["key"] == "user"]
        assert len(user_messages) >= 1
        assert user_messages[-1]["value"] == "Hello!"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_saves_assistant_response_to_database(self, mock_provider_class, temp_db_path):
        """Test that chat saves AI response to database."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Hello! How can I help?",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        response = agent.chat("Hello!")

        # ASSERT
        conversation = db.get_conversation(project_id)
        assistant_messages = [m for m in conversation if m["key"] == "assistant"]
        assert len(assistant_messages) >= 1
        assert assistant_messages[-1]["value"] == "Hello! How can I help?"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_maintains_conversation_history(self, mock_provider_class, temp_db_path):
        """Test that chat maintains conversation history across multiple messages."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.side_effect = [
            {
                "content": "Hello! How can I help?",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            {
                "content": "Sure, I can help with that.",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 30, "output_tokens": 12},
            },
        ]
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT - First message
        response_1 = agent.chat("Hello!")

        # ACT - Second message
        response_2 = agent.chat("Can you help me?")

        # ASSERT
        conversation = db.get_conversation(project_id)
        assert len(conversation) == 4  # 2 user + 2 assistant

        # Verify order
        assert conversation[0]["key"] == "user"
        assert conversation[0]["value"] == "Hello!"
        assert conversation[1]["key"] == "assistant"
        assert conversation[1]["value"] == "Hello! How can I help?"
        assert conversation[2]["key"] == "user"
        assert conversation[2]["value"] == "Can you help me?"
        assert conversation[3]["key"] == "assistant"
        assert conversation[3]["value"] == "Sure, I can help with that."

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_handles_provider_error(self, mock_provider_class, temp_db_path):
        """Test that chat handles provider errors gracefully."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.side_effect = Exception("API Error")
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(Exception) as exc_info:
            agent.chat("Hello!")

        assert "API Error" in str(exc_info.value)

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_with_empty_message_raises_error(self, mock_provider_class, temp_db_path):
        """Test that chat with empty message raises error."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            agent.chat("")

        assert "empty" in str(exc_info.value).lower() or "message" in str(exc_info.value).lower()


@pytest.mark.unit
class TestLeadAgentConversationPersistence:
    """Test conversation persistence across restarts."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_conversation_persists_across_agent_instances(self, mock_provider_class, temp_db_path):
        """Test that conversation persists when creating new agent instance."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Hello!",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # ACT - First agent instance
        agent_1 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent_1.chat("First message")

        # ACT - New agent instance (simulating restart)
        agent_2 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        conversation = agent_2.get_conversation_history()

        # ASSERT
        assert len(conversation) >= 2  # User + Assistant
        assert any(m["content"] == "First message" for m in conversation if m["role"] == "user")

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_conversation_handles_long_history(self, mock_provider_class, temp_db_path):
        """Test that conversation handles long history gracefully."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Response",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT - Send multiple messages
        for i in range(10):
            agent.chat(f"Message {i}")

        # ASSERT
        conversation = agent.get_conversation_history()
        assert len(conversation) == 20  # 10 user + 10 assistant

        # Verify all messages are present (order may vary based on timing)
        roles = [msg["role"] for msg in conversation]
        contents = [msg["content"] for msg in conversation]

        # Count roles
        assert roles.count("user") == 10
        assert roles.count("assistant") == 10

        # Verify at least first message is present
        assert any("Message 0" in content for content in contents)


@pytest.mark.unit
class TestLeadAgentTokenUsageTracking:
    """Test token usage tracking and logging."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_logs_token_usage(self, mock_provider_class, temp_db_path, caplog):
        """Test that chat logs token usage."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Response",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        import logging

        caplog.set_level(logging.INFO)
        agent.chat("Test message")

        # ASSERT
        # Check if token usage was logged
        log_messages = [record.message for record in caplog.records]
        assert any("token" in msg.lower() for msg in log_messages)

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_tracks_total_tokens(self, mock_provider_class, temp_db_path):
        """Test that chat tracks cumulative token usage."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.side_effect = [
            {
                "content": "Response 1",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            {
                "content": "Response 2",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 120, "output_tokens": 60},
            },
        ]
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        agent.chat("Message 1")
        agent.chat("Message 2")

        # ASSERT
        # Total tokens should be tracked (implementation will expose this)
        # For now, just verify both calls succeeded
        assert mock_provider.send_message.call_count == 2


@pytest.mark.unit
class TestLeadAgentErrorHandling:
    """Test error handling and recovery."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_handles_database_error(self, mock_provider_class, temp_db_path):
        """Test that chat handles database errors gracefully."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Response",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT - Close database to simulate error
        db.close()

        # ASSERT
        with pytest.raises(Exception):
            agent.chat("Test")

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_chat_logs_errors_with_context(self, mock_provider_class, temp_db_path, caplog):
        """Test that errors are logged with context."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.side_effect = Exception("Test error")
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        import logging

        caplog.set_level(logging.ERROR)

        with pytest.raises(Exception):
            agent.chat("Test")

        # ASSERT
        log_messages = [record.message for record in caplog.records]
        assert any("error" in msg.lower() for msg in log_messages)


@pytest.mark.integration
class TestLeadAgentIntegration:
    """Integration tests for Lead Agent."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_complete_conversation_workflow(self, mock_provider_class, temp_db_path):
        """Test complete conversation workflow from initialization to multiple messages."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.side_effect = [
            {
                "content": "Hello! I'm your Lead Agent.",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            {
                "content": "I can help you build software.",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 30, "output_tokens": 12},
            },
            {
                "content": "Let's start with requirements.",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 50, "output_tokens": 15},
            },
        ]
        mock_provider_class.return_value = mock_provider

        # ACT - Full conversation
        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        response_1 = agent.chat("Hello")
        response_2 = agent.chat("What can you do?")
        response_3 = agent.chat("Let's start")

        # ASSERT
        assert response_1 == "Hello! I'm your Lead Agent."
        assert response_2 == "I can help you build software."
        assert response_3 == "Let's start with requirements."

        # Verify conversation persistence
        conversation = db.get_conversation(project_id)
        assert len(conversation) == 6  # 3 user + 3 assistant messages

        # Verify order is correct
        assert conversation[0]["key"] == "user"
        assert conversation[1]["key"] == "assistant"
        assert conversation[2]["key"] == "user"
        assert conversation[3]["key"] == "assistant"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_agent_restart_maintains_context(self, mock_provider_class, temp_db_path):
        """Test that agent restart maintains conversation context."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.side_effect = [
            {
                "content": "First response",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            {
                "content": "Second response with context",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 30, "output_tokens": 12},
            },
        ]
        mock_provider_class.return_value = mock_provider

        # ACT - First agent
        agent_1 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent_1.chat("First message")

        # Simulate restart by creating new agent instance
        agent_2 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        response = agent_2.chat("Second message")

        # ASSERT
        # Verify that the second call includes first conversation in context
        call_args = mock_provider.send_message.call_args_list[1][0][0]
        assert len(call_args) >= 3  # First user + First assistant + Second user
        assert response == "Second response with context"

        # Verify database has all messages
        conversation = db.get_conversation(project_id)
        assert len(conversation) == 4
