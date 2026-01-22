"""Tests for LLM adapters."""

import pytest

from codeframe.adapters.llm import (
    AnthropicProvider,
    LLMResponse,
    MockProvider,
    ModelSelector,
    Purpose,
    ToolCall,
    get_provider,
)


class TestModelSelector:
    """Tests for ModelSelector."""

    def test_default_models(self):
        """Default models are set correctly."""
        selector = ModelSelector()
        assert "sonnet" in selector.planning_model
        assert "sonnet" in selector.execution_model
        assert "haiku" in selector.generation_model

    def test_for_purpose_planning(self):
        """Planning purpose returns planning model."""
        selector = ModelSelector()
        model = selector.for_purpose(Purpose.PLANNING)
        assert model == selector.planning_model

    def test_for_purpose_execution(self):
        """Execution purpose returns execution model."""
        selector = ModelSelector()
        model = selector.for_purpose(Purpose.EXECUTION)
        assert model == selector.execution_model

    def test_for_purpose_generation(self):
        """Generation purpose returns generation model."""
        selector = ModelSelector()
        model = selector.for_purpose(Purpose.GENERATION)
        assert model == selector.generation_model

    def test_custom_models(self):
        """Custom models can be specified."""
        selector = ModelSelector(
            planning_model="custom-opus",
            execution_model="custom-sonnet",
            generation_model="custom-haiku",
        )
        assert selector.for_purpose(Purpose.PLANNING) == "custom-opus"
        assert selector.for_purpose(Purpose.EXECUTION) == "custom-sonnet"
        assert selector.for_purpose(Purpose.GENERATION) == "custom-haiku"


class TestMockProvider:
    """Tests for MockProvider."""

    def test_default_response(self):
        """Returns default response when no queue."""
        provider = MockProvider(default_response="Hello")
        response = provider.complete([{"role": "user", "content": "Hi"}])
        assert response.content == "Hello"

    def test_tracks_calls(self):
        """Tracks all calls made."""
        provider = MockProvider()
        provider.complete([{"role": "user", "content": "First"}])
        provider.complete([{"role": "user", "content": "Second"}])
        assert provider.call_count == 2
        assert provider.calls[0]["messages"][0]["content"] == "First"
        assert provider.calls[1]["messages"][0]["content"] == "Second"

    def test_last_call(self):
        """Returns the most recent call."""
        provider = MockProvider()
        provider.complete(
            [{"role": "user", "content": "Test"}],
            purpose=Purpose.PLANNING,
        )
        assert provider.last_call is not None
        assert provider.last_call["purpose"] == Purpose.PLANNING

    def test_queued_responses(self):
        """Returns queued responses in order."""
        provider = MockProvider()
        provider.add_text_response("First")
        provider.add_text_response("Second")
        provider.add_text_response("Third")

        r1 = provider.complete([])
        r2 = provider.complete([])
        r3 = provider.complete([])
        r4 = provider.complete([])  # Falls back to default

        assert r1.content == "First"
        assert r2.content == "Second"
        assert r3.content == "Third"
        assert r4.content == "Mock response"  # Default

    def test_tool_call_response(self):
        """Can return responses with tool calls."""
        provider = MockProvider()
        tool_calls = [
            ToolCall(id="tc1", name="read_file", input={"path": "/test.py"})
        ]
        provider.add_tool_response(tool_calls, content="I'll read that file")

        response = provider.complete([])
        assert response.has_tool_calls
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "read_file"
        assert response.content == "I'll read that file"

    def test_custom_handler(self):
        """Custom handler generates dynamic responses."""
        provider = MockProvider()

        def handler(messages):
            last_msg = messages[-1]["content"]
            return LLMResponse(content=f"Echo: {last_msg}")

        provider.set_response_handler(handler)

        r1 = provider.complete([{"role": "user", "content": "Hello"}])
        r2 = provider.complete([{"role": "user", "content": "World"}])

        assert r1.content == "Echo: Hello"
        assert r2.content == "Echo: World"

    def test_reset(self):
        """Reset clears all state."""
        provider = MockProvider()
        provider.add_text_response("Queued")
        provider.complete([{"role": "user", "content": "Test"}])

        provider.reset()

        assert provider.call_count == 0
        assert len(provider.responses) == 0

    def test_model_selection(self):
        """Correct model is selected based on purpose."""
        provider = MockProvider()

        provider.complete([], purpose=Purpose.PLANNING)
        provider.complete([], purpose=Purpose.GENERATION)

        assert "sonnet" in provider.calls[0]["model"]
        assert "haiku" in provider.calls[1]["model"]

    def test_stream(self):
        """Stream yields response words."""
        provider = MockProvider(default_response="Hello world test")
        chunks = list(provider.stream([]))
        assert "".join(chunks).strip() == "Hello world test"


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_requires_api_key(self):
        """Raises ValueError if no API key."""
        # Clear env var temporarily
        import os
        original = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicProvider()
        finally:
            if original:
                os.environ["ANTHROPIC_API_KEY"] = original

    def test_accepts_api_key_parameter(self):
        """Can pass API key directly."""
        provider = AnthropicProvider(api_key="test-key")
        assert provider.api_key == "test-key"

    def test_model_selection(self):
        """Model selection works correctly."""
        provider = AnthropicProvider(api_key="test-key")
        assert "sonnet" in provider.get_model(Purpose.EXECUTION)
        assert "haiku" in provider.get_model(Purpose.GENERATION)

    def test_custom_model_selector(self):
        """Can use custom model selector."""
        selector = ModelSelector(planning_model="custom-model")
        provider = AnthropicProvider(api_key="test-key", model_selector=selector)
        assert provider.get_model(Purpose.PLANNING) == "custom-model"


class TestGetProvider:
    """Tests for get_provider factory function."""

    def test_get_mock_provider(self):
        """Returns MockProvider for 'mock' type."""
        provider = get_provider("mock")
        assert isinstance(provider, MockProvider)

    def test_unknown_provider_raises(self):
        """Raises ValueError for unknown provider type."""
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("unknown")


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_has_tool_calls_false(self):
        """has_tool_calls is False when empty."""
        response = LLMResponse(content="Hello")
        assert not response.has_tool_calls

    def test_has_tool_calls_true(self):
        """has_tool_calls is True when tools present."""
        response = LLMResponse(
            content="",
            tool_calls=[ToolCall(id="1", name="test", input={})],
        )
        assert response.has_tool_calls

    def test_default_values(self):
        """Default values are set correctly."""
        response = LLMResponse(content="Test")
        assert response.stop_reason == "end_turn"
        assert response.model == ""
        assert response.input_tokens == 0
        assert response.output_tokens == 0
        assert response.tool_calls == []
