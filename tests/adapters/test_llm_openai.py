"""Tests for OpenAI LLM adapter."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Helpers to build mock ChatCompletion objects
# ---------------------------------------------------------------------------


def _make_choice(content=None, tool_calls=None, finish_reason="stop"):
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls or []
    choice.finish_reason = finish_reason
    return choice


def _make_tool_call(id, name, arguments: dict):
    tc = MagicMock()
    tc.id = id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_completion(content=None, tool_calls=None, finish_reason="stop", model="gpt-4o"):
    resp = MagicMock()
    resp.choices = [_make_choice(content, tool_calls, finish_reason)]
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 20
    resp.model = model
    return resp


def _make_stream_chunk(content):
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = content
    return chunk


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOpenAIProviderInit:
    """Initialisation and key resolution."""

    def test_no_api_key_raises(self):
        """Raises ValueError when no API key available."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIProvider()
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original

    def test_direct_api_key_accepted(self):
        """Direct api_key parameter is stored."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        assert provider.api_key == "sk-test"

    def test_env_var_fallback(self):
        """Falls back to OPENAI_API_KEY env var."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env"}):
            provider = OpenAIProvider()
        assert provider.api_key == "sk-env"

    def test_base_url_stored(self):
        """base_url is stored on the provider."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:11434/v1")
        assert provider.base_url == "http://localhost:11434/v1"

    def test_default_model_stored(self):
        """Default model is gpt-4o."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        assert provider.model == "gpt-4o"

    def test_custom_model_stored(self):
        """Custom model is accepted."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test", model="gpt-3.5-turbo")
        assert provider.model == "gpt-3.5-turbo"

    def test_credential_manager_used(self):
        """Retrieves key from CredentialManager when provided."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        credential_manager = MagicMock()
        credential_manager.get_credential.return_value = "sk-from-manager"

        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            provider = OpenAIProvider(credential_manager=credential_manager)
            assert provider.api_key == "sk-from-manager"
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original


class TestOpenAIProviderComplete:
    """complete() method."""

    def test_simple_text_response(self):
        """Returns LLMResponse with text content."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        mock_resp = _make_completion(content="Hello!")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_resp

                response = provider.complete([{"role": "user", "content": "Hi"}])

        assert response.content == "Hello!"
        assert response.stop_reason == "end_turn"
        assert response.input_tokens == 10
        assert response.output_tokens == 20

    def test_stop_reason_tool_calls(self):
        """finish_reason 'tool_calls' maps to 'tool_use'."""
        from codeframe.adapters.llm.openai import OpenAIProvider
        from codeframe.adapters.llm.base import Tool

        provider = OpenAIProvider(api_key="sk-test")
        tc = _make_tool_call("id1", "read_file", {"path": "/foo.py"})
        mock_resp = _make_completion(tool_calls=[tc], finish_reason="tool_calls")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_resp

                tools = [Tool(name="read_file", description="Read a file", input_schema={"type": "object"})]
                response = provider.complete(
                    [{"role": "user", "content": "Read /foo.py"}],
                    tools=tools,
                )

        assert response.stop_reason == "tool_use"
        assert response.has_tool_calls
        assert response.tool_calls[0].name == "read_file"
        assert response.tool_calls[0].input == {"path": "/foo.py"}

    def test_system_prompt_prepended(self):
        """System prompt is prepended as system role message."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        mock_resp = _make_completion(content="OK")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_resp

                provider.complete(
                    [{"role": "user", "content": "Hi"}],
                    system="You are a helpful assistant.",
                )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a helpful assistant."}

    def test_temperature_forwarded(self):
        """temperature > 0 is forwarded to the API."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        mock_resp = _make_completion(content="OK")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_resp

                provider.complete([{"role": "user", "content": "Hi"}], temperature=0.7)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("temperature") == 0.7

    def test_uses_provider_model(self):
        """get_model() returns self.model (not a Claude model name)."""
        from codeframe.adapters.llm.openai import OpenAIProvider
        from codeframe.adapters.llm.base import Purpose

        provider = OpenAIProvider(api_key="sk-test", model="gpt-4-turbo")
        assert provider.get_model(Purpose.PLANNING) == "gpt-4-turbo"
        assert provider.get_model(Purpose.EXECUTION) == "gpt-4-turbo"
        assert provider.get_model(Purpose.GENERATION) == "gpt-4-turbo"


class TestOpenAIProviderStream:
    """stream() method."""

    def test_yields_content_chunks(self):
        """Yields text content from streaming response."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        chunks = [_make_stream_chunk("Hello"), _make_stream_chunk(" world")]

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = iter(chunks)

                result = list(provider.stream([{"role": "user", "content": "Hi"}]))

        assert "".join(result) == "Hello world"

    def test_handles_none_delta_content(self):
        """None delta content is skipped gracefully."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        chunks = [
            _make_stream_chunk(None),
            _make_stream_chunk("Hello"),
            _make_stream_chunk(None),
        ]

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = iter(chunks)

                result = list(provider.stream([{"role": "user", "content": "Hi"}]))

        assert "".join(result) == "Hello"


class TestOpenAIProviderBaseUrl:
    """base_url routing."""

    def test_client_created_with_base_url(self):
        """openai.OpenAI is constructed with the custom base_url."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:11434/v1")
        mock_resp = _make_completion(content="Hi")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_resp

                # Access the client to trigger lazy init
                _ = provider.client

        mock_cls.assert_called_once_with(
            api_key="sk-test", base_url="http://localhost:11434/v1"
        )

    def test_default_base_url_is_none(self):
        """base_url defaults to None (OpenAI production)."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_cls.return_value = MagicMock()
                _ = provider.client

        mock_cls.assert_called_once_with(api_key="sk-test", base_url=None)


class TestOpenAIProviderErrors:
    """Error handling."""

    def test_authentication_error_surfaced(self):
        """AuthenticationError becomes a ValueError."""
        import openai
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-bad")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
                    "bad key", response=MagicMock(), body={}
                )

                with pytest.raises((ValueError, openai.AuthenticationError)):
                    provider.complete([{"role": "user", "content": "hi"}])

    def test_rate_limit_error_surfaced(self):
        """RateLimitError is raised."""
        import openai
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.side_effect = openai.RateLimitError(
                    "rate limit", response=MagicMock(), body={}
                )

                with pytest.raises((ValueError, openai.RateLimitError)):
                    provider.complete([{"role": "user", "content": "hi"}])


class TestOpenAIProviderToolRoundTrip:
    """Multi-turn tool call round-trip."""

    def test_tool_call_to_result_to_answer(self):
        """Tool call → tool result message → final answer (multi-turn)."""
        from codeframe.adapters.llm.openai import OpenAIProvider
        from codeframe.adapters.llm.base import Tool

        provider = OpenAIProvider(api_key="sk-test")
        tool = Tool(name="read_file", description="Read a file", input_schema={"type": "object", "properties": {"path": {"type": "string"}}})

        tc = _make_tool_call("call_abc", "read_file", {"path": "/foo.py"})
        first_resp = _make_completion(tool_calls=[tc], finish_reason="tool_calls")
        final_resp = _make_completion(content="The file contains: hello", finish_reason="stop")

        with patch.object(provider, "_client", None):
            with patch("openai.OpenAI") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.chat.completions.create.side_effect = [first_resp, final_resp]

                # First turn: model requests tool call
                r1 = provider.complete(
                    [{"role": "user", "content": "What's in /foo.py?"}],
                    tools=[tool],
                )
                assert r1.has_tool_calls
                assert r1.tool_calls[0].id == "call_abc"

                # Second turn: send back tool result
                messages = [
                    {"role": "user", "content": "What's in /foo.py?"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {"id": "call_abc", "name": "read_file", "input": {"path": "/foo.py"}}
                        ],
                    },
                    {
                        "role": "user",
                        "content": "",
                        "tool_results": [
                            {"tool_call_id": "call_abc", "content": "hello", "is_error": False}
                        ],
                    },
                ]
                r2 = provider.complete(messages, tools=[tool])
                assert r2.content == "The file contains: hello"
                assert not r2.has_tool_calls


class TestOpenAIMessageConversion:
    """_convert_messages() helper."""

    def test_simple_messages_pass_through(self):
        """Simple role/content messages are unchanged."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = provider._convert_messages(msgs)
        assert result == msgs

    def test_tool_results_become_tool_role_messages(self):
        """tool_results on a user message expand to role='tool' messages."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        msgs = [
            {
                "role": "user",
                "content": "",
                "tool_results": [
                    {"tool_call_id": "id1", "content": "result1", "is_error": False},
                    {"tool_call_id": "id2", "content": "result2", "is_error": True},
                ],
            }
        ]
        result = provider._convert_messages(msgs)
        assert len(result) == 2
        assert result[0] == {"role": "tool", "tool_call_id": "id1", "content": "result1"}
        assert result[1] == {"role": "tool", "tool_call_id": "id2", "content": "result2"}

    def test_assistant_tool_calls_converted(self):
        """Assistant message with tool_calls is converted to OpenAI format."""
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-test")
        msgs = [
            {
                "role": "assistant",
                "content": "I'll use a tool",
                "tool_calls": [{"id": "id1", "name": "my_tool", "input": {"key": "val"}}],
            }
        ]
        result = provider._convert_messages(msgs)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "I'll use a tool"
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "id1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "my_tool"
        assert json.loads(tc["function"]["arguments"]) == {"key": "val"}
