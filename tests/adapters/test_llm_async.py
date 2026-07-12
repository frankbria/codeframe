"""Tests for async LLM provider methods."""
import pytest
from codeframe.adapters.llm import MockProvider, Purpose
from codeframe.adapters.llm.base import LLMRateLimitError, LLMAuthError, LLMConnectionError

pytestmark = pytest.mark.v2


class TestMockProviderAsync:
    """async_complete() tests using MockProvider (no real API)."""

    @pytest.mark.asyncio
    async def test_async_complete_returns_response(self):
        """async_complete returns an LLMResponse."""
        provider = MockProvider(default_response="async reply")
        response = await provider.async_complete(
            messages=[{"role": "user", "content": "hello"}]
        )
        assert response.content == "async reply"

    @pytest.mark.asyncio
    async def test_async_complete_accepts_purpose(self):
        """async_complete accepts purpose parameter."""
        provider = MockProvider(default_response="ok")
        response = await provider.async_complete(
            messages=[{"role": "user", "content": "hi"}],
            purpose=Purpose.PLANNING,
        )
        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_async_complete_accepts_system(self):
        """async_complete accepts system prompt."""
        provider = MockProvider(default_response="ok")
        response = await provider.async_complete(
            messages=[{"role": "user", "content": "hi"}],
            system="You are helpful",
        )
        assert response.content == "ok"

    @pytest.mark.asyncio
    async def test_async_complete_tracks_call(self):
        """async_complete counts toward call_count."""
        provider = MockProvider(default_response="ok")
        await provider.async_complete(messages=[{"role": "user", "content": "hi"}])
        await provider.async_complete(messages=[{"role": "user", "content": "hi"}])
        assert provider.call_count == 2


class TestMockProviderAsyncStream:
    """async_stream() tests using MockProvider."""

    @pytest.mark.asyncio
    async def test_async_stream_yields_default_chunks(self):
        """Default async_stream yields text_delta + message_stop."""
        provider = MockProvider(default_response="streamed reply")
        chunks = [
            chunk
            async for chunk in provider.async_stream(
                messages=[{"role": "user", "content": "hi"}],
                system="",
                tools=[],
                model="mock",
                max_tokens=100,
            )
        ]
        types = [c.type for c in chunks]
        assert "text_delta" in types
        assert "message_stop" in types
        text = next(c.text for c in chunks if c.type == "text_delta")
        assert text == "streamed reply"

    @pytest.mark.asyncio
    async def test_async_stream_uses_preconfigured_chunks(self):
        """add_stream_chunks() controls what async_stream yields."""
        from codeframe.adapters.llm.base import StreamChunk

        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="custom"),
            StreamChunk(type="message_stop", stop_reason="end_turn",
                        input_tokens=1, output_tokens=1, tool_inputs_by_id={}),
        ])
        chunks = [
            c
            async for c in provider.async_stream(
                messages=[], system="", tools=[], model="mock", max_tokens=10
            )
        ]
        assert chunks[0].text == "custom"
        assert chunks[1].type == "message_stop"

    @pytest.mark.asyncio
    async def test_async_stream_tracks_call(self):
        """async_stream records the call in provider.calls."""
        provider = MockProvider()
        _ = [
            c
            async for c in provider.async_stream(
                messages=[{"role": "user", "content": "hi"}],
                system="sys",
                tools=[],
                model="mock-model",
                max_tokens=50,
            )
        ]
        assert provider.call_count == 1
        assert provider.last_call["model"] == "mock-model"

    @pytest.mark.asyncio
    async def test_async_stream_honours_interrupt(self):
        """async_stream stops early when interrupt_event is set."""
        import asyncio
        from codeframe.adapters.llm.base import StreamChunk

        interrupt = asyncio.Event()
        provider = MockProvider()
        provider.add_stream_chunks([
            StreamChunk(type="text_delta", text="a"),
            StreamChunk(type="text_delta", text="b"),
            StreamChunk(type="message_stop", stop_reason="end_turn",
                        input_tokens=0, output_tokens=0, tool_inputs_by_id={}),
        ])
        interrupt.set()
        chunks = [
            c
            async for c in provider.async_stream(
                messages=[], system="", tools=[], model="m", max_tokens=10,
                interrupt_event=interrupt,
            )
        ]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_async_stream_supports_extended_thinking_param(self):
        """extended_thinking param is accepted and stored in call metadata."""
        provider = MockProvider()
        _ = [
            c
            async for c in provider.async_stream(
                messages=[], system="", tools=[], model="m", max_tokens=10,
                extended_thinking=True,
            )
        ]
        assert provider.last_call["extended_thinking"] is True


class _FakeStreamCtx:
    """Async ctx-manager + iterator that yields no SDK events."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _FakeMessages:
    def __init__(self, rec, name, raises=None):
        self._rec = rec
        self._name = name
        self._raises = raises

    def stream(self, **kwargs):
        self._rec.append((self._name, kwargs))
        if self._raises is not None:
            raise self._raises
        return _FakeStreamCtx()


class _FakeClient:
    """Stand-in for AsyncAnthropic with plain + beta message namespaces."""

    def __init__(self, rec, beta_raises=None):
        self.messages = _FakeMessages(rec, "plain")
        self.beta = type("_Beta", (), {"messages": _FakeMessages(rec, "beta", beta_raises)})()


class TestAnthropicExtendedThinkingRouting:
    """#766 — extended thinking must route to the beta namespace with thinking=."""

    def _provider(self, rec, beta_raises=None):
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="test-key")
        provider._async_client = _FakeClient(rec, beta_raises=beta_raises)
        return provider

    async def _drain(self, provider, **kw):
        async for _ in provider.async_stream(
            messages=[{"role": "user", "content": "hi"}],
            system="s", tools=[], model="claude-x", max_tokens=4096, **kw,
        ):
            pass

    @pytest.mark.asyncio
    async def test_extended_thinking_uses_beta_namespace(self):
        rec = []
        await self._drain(self._provider(rec), extended_thinking=True)
        name, kwargs = rec[-1]
        assert name == "beta"
        assert kwargs["betas"] == ["interleaved-thinking-2025-05-14"]
        assert kwargs["thinking"]["type"] == "enabled"
        assert 1024 <= kwargs["thinking"]["budget_tokens"] < 4096

    @pytest.mark.asyncio
    async def test_no_thinking_uses_plain_namespace(self):
        rec = []
        await self._drain(self._provider(rec), extended_thinking=False)
        name, kwargs = rec[-1]
        assert name == "plain"
        assert "betas" not in kwargs
        assert "thinking" not in kwargs

    @pytest.mark.asyncio
    async def test_small_max_tokens_skips_thinking(self):
        """budget_tokens needs >=1024 headroom; tiny caps fall back to plain."""
        rec = []
        async for _ in self._provider(rec).async_stream(
            messages=[{"role": "user", "content": "hi"}],
            system="s", tools=[], model="claude-x", max_tokens=512,
            extended_thinking=True,
        ):
            pass
        name, kwargs = rec[-1]
        assert name == "plain"
        assert "thinking" not in kwargs

    @pytest.mark.asyncio
    async def test_typeerror_degrades_to_plain_stream(self):
        """An SDK too old to accept betas=/thinking= degrades, not crashes."""
        rec = []
        await self._drain(
            self._provider(rec, beta_raises=TypeError("unexpected kwarg")),
            extended_thinking=True,
        )
        # First attempt hits beta (raises), fallback lands on plain without thinking.
        assert rec[0][0] == "beta"
        assert rec[-1][0] == "plain"
        assert "thinking" not in rec[-1][1]


class TestLLMExceptions:
    """Common LLM exception hierarchy."""

    def test_llm_rate_limit_is_exception(self):
        from codeframe.adapters.llm.base import LLMError
        assert issubclass(LLMRateLimitError, LLMError)

    def test_llm_auth_is_exception(self):
        from codeframe.adapters.llm.base import LLMError
        assert issubclass(LLMAuthError, LLMError)

    def test_llm_connection_is_exception(self):
        from codeframe.adapters.llm.base import LLMError
        assert issubclass(LLMConnectionError, LLMError)
