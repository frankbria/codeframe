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
