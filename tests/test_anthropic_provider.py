"""Tests for Anthropic provider integration.

Following TDD: These tests are written FIRST, before implementation.
Target: >90% coverage for anthropic.py module.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from codeframe.providers.anthropic import AnthropicProvider


@pytest.mark.unit
class TestAnthropicProviderInitialization:
    """Test Anthropic provider initialization."""

    def test_provider_initialization_with_api_key(self):
        """Test that provider initializes with valid API key."""
        provider = AnthropicProvider(api_key="sk-ant-test-key")

        assert provider.api_key == "sk-ant-test-key"
        assert provider.model is not None
        assert provider.client is not None

    def test_provider_initialization_without_api_key_raises_error(self):
        """Test that provider fails fast when API key is missing."""
        with pytest.raises(ValueError) as exc_info:
            AnthropicProvider(api_key=None)

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_provider_initialization_with_empty_api_key_raises_error(self):
        """Test that provider fails fast when API key is empty."""
        with pytest.raises(ValueError) as exc_info:
            AnthropicProvider(api_key="")

        assert "ANTHROPIC_API_KEY" in str(exc_info.value)

    def test_provider_initialization_with_custom_model(self):
        """Test that provider accepts custom model."""
        provider = AnthropicProvider(
            api_key="sk-ant-test-key",
            model="claude-3-opus-20240229"
        )

        assert provider.model == "claude-3-opus-20240229"

    def test_provider_default_model(self):
        """Test that provider uses default model when not specified."""
        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # Default should be claude-sonnet-4 or similar
        assert provider.model in ["claude-sonnet-4", "claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022"]


@pytest.mark.unit
class TestAnthropicProviderMessageSending:
    """Test sending messages to Anthropic API."""

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_with_simple_conversation(self, mock_anthropic_class):
        """Test sending a simple message."""
        # ARRANGE: Mock Anthropic client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Hello! How can I help you?")]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 8

        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT: Send message
        conversation = [
            {"role": "user", "content": "Hello!"}
        ]
        response = provider.send_message(conversation)

        # ASSERT: Verify response
        assert response["content"] == "Hello! How can I help you?"
        assert response["stop_reason"] == "end_turn"
        assert response["usage"]["input_tokens"] == 10
        assert response["usage"]["output_tokens"] == 8

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_with_multi_turn_conversation(self, mock_anthropic_class):
        """Test sending multi-turn conversation."""
        # ARRANGE
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Yes, I remember your question.")]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 12

        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT
        conversation = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "2+2 equals 4."},
            {"role": "user", "content": "Can you explain that?"}
        ]
        response = provider.send_message(conversation)

        # ASSERT
        assert response["content"] == "Yes, I remember your question."
        assert mock_client.messages.create.called

        # Verify conversation was passed correctly
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert len(call_kwargs["messages"]) == 3

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_handles_api_error(self, mock_anthropic_class):
        """Test that API errors are handled gracefully."""
        # ARRANGE
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error: Rate limit exceeded")
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(Exception) as exc_info:
            conversation = [{"role": "user", "content": "Hello"}]
            provider.send_message(conversation)

        assert "Rate limit" in str(exc_info.value) or "API Error" in str(exc_info.value)

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_handles_timeout(self, mock_anthropic_class):
        """Test that timeout errors are handled."""
        # ARRANGE
        mock_client = Mock()
        mock_client.messages.create.side_effect = TimeoutError("Request timeout")
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(TimeoutError):
            conversation = [{"role": "user", "content": "Hello"}]
            provider.send_message(conversation)

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_with_empty_conversation_raises_error(self, mock_anthropic_class):
        """Test that empty conversation raises error."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            provider.send_message([])

        assert "empty" in str(exc_info.value).lower() or "conversation" in str(exc_info.value).lower()

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_with_invalid_role_raises_error(self, mock_anthropic_class):
        """Test that invalid message role raises error."""
        mock_client = Mock()
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(ValueError) as exc_info:
            conversation = [{"role": "invalid", "content": "Hello"}]
            provider.send_message(conversation)

        assert "role" in str(exc_info.value).lower()


@pytest.mark.unit
class TestAnthropicProviderTokenUsage:
    """Test token usage tracking."""

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_returns_token_usage(self, mock_anthropic_class):
        """Test that token usage is returned."""
        # ARRANGE
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Response")]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT
        conversation = [{"role": "user", "content": "Test"}]
        response = provider.send_message(conversation)

        # ASSERT
        assert "usage" in response
        assert response["usage"]["input_tokens"] == 100
        assert response["usage"]["output_tokens"] == 50

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_handles_missing_usage_data(self, mock_anthropic_class):
        """Test that missing usage data is handled gracefully."""
        # ARRANGE
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = [Mock(text="Response")]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None  # No usage data

        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT
        conversation = [{"role": "user", "content": "Test"}]
        response = provider.send_message(conversation)

        # ASSERT
        # Should handle gracefully, maybe return 0 or None
        assert "usage" in response or response is not None


@pytest.mark.unit
class TestAnthropicProviderErrorHandling:
    """Test error handling and recovery."""

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_handles_authentication_error(self, mock_anthropic_class):
        """Test handling of authentication errors."""
        # ARRANGE
        from anthropic import AuthenticationError

        mock_client = Mock()
        # Create a properly formatted AuthenticationError
        mock_response = Mock()
        mock_response.status_code = 401
        error = AuthenticationError("Invalid API key", response=mock_response, body=None)
        mock_client.messages.create.side_effect = error
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-invalid-key")

        # ACT & ASSERT
        with pytest.raises(AuthenticationError):
            conversation = [{"role": "user", "content": "Test"}]
            provider.send_message(conversation)

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_handles_rate_limit_error(self, mock_anthropic_class):
        """Test handling of rate limit errors."""
        # ARRANGE
        from anthropic import RateLimitError

        mock_client = Mock()
        # Create a properly formatted RateLimitError
        mock_response = Mock()
        mock_response.status_code = 429
        error = RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        mock_client.messages.create.side_effect = error
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(RateLimitError):
            conversation = [{"role": "user", "content": "Test"}]
            provider.send_message(conversation)

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_send_message_handles_api_connection_error(self, mock_anthropic_class):
        """Test handling of connection errors."""
        # ARRANGE
        from anthropic import APIConnectionError
        import httpx

        mock_client = Mock()
        # APIConnectionError requires request parameter
        mock_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        error = APIConnectionError(message="Connection failed", request=mock_request)
        mock_client.messages.create.side_effect = error
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT & ASSERT
        with pytest.raises(APIConnectionError):
            conversation = [{"role": "user", "content": "Test"}]
            provider.send_message(conversation)


@pytest.mark.integration
class TestAnthropicProviderIntegration:
    """Integration tests for Anthropic provider."""

    @patch("codeframe.providers.anthropic.Anthropic")
    def test_complete_conversation_flow(self, mock_anthropic_class):
        """Test complete conversation workflow."""
        # ARRANGE
        mock_client = Mock()

        # First response
        mock_response_1 = Mock()
        mock_response_1.content = [Mock(text="Hello! How can I help?")]
        mock_response_1.stop_reason = "end_turn"
        mock_response_1.usage.input_tokens = 10
        mock_response_1.usage.output_tokens = 8

        # Second response
        mock_response_2 = Mock()
        mock_response_2.content = [Mock(text="Sure, I can help with that.")]
        mock_response_2.stop_reason = "end_turn"
        mock_response_2.usage.input_tokens = 30
        mock_response_2.usage.output_tokens = 12

        mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]
        mock_anthropic_class.return_value = mock_client

        provider = AnthropicProvider(api_key="sk-ant-test-key")

        # ACT - First message
        conversation = [{"role": "user", "content": "Hello"}]
        response_1 = provider.send_message(conversation)

        # ACT - Second message
        conversation.append({"role": "assistant", "content": response_1["content"]})
        conversation.append({"role": "user", "content": "Can you help me?"})
        response_2 = provider.send_message(conversation)

        # ASSERT
        assert response_1["content"] == "Hello! How can I help?"
        assert response_2["content"] == "Sure, I can help with that."
        assert mock_client.messages.create.call_count == 2
