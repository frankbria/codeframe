"""Streaming errors get the same actionable mapping as complete() (#1434).

`map_provider_error` turns SDK exceptions into typed errors with readable text
(#1110, #1349, #1418), but the streaming path interactive chat uses bypassed
it: Anthropic's `async_stream` mapped nothing, OpenAI's only auth/rate/
connection with the raw SDK string. Chat then sent `str(exc)` to the browser,
e.g. ``Error code: 413 - {'type': 'error', ...}``. Real SDKs, mock transport.
"""

from __future__ import annotations

import asyncio

import pytest

from codeframe.adapters.llm.base import LLMModelNotFoundError, LLMRequestRejectedError

pytestmark = pytest.mark.v2

REASON = "prompt is too long for this model"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.delenv("CODEFRAME_VERBOSE", raising=False)


def _anthropic(status):
    import anthropic
    import httpx2

    from codeframe.adapters.llm.anthropic import AnthropicProvider

    def handler(request):
        return httpx2.Response(status, json={"type": "error", "error": {"type": "invalid_request_error", "message": REASON}})

    p = AnthropicProvider(api_key="test-key")
    p._async_client = anthropic.AsyncAnthropic(
        api_key="test-key", max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return p


def _openai(status):
    import httpx
    import openai

    from codeframe.adapters.llm.openai import OpenAIProvider

    def handler(request):
        return httpx.Response(status, json={"error": {"message": REASON, "type": "invalid_request_error"}})

    p = OpenAIProvider(api_key="test-key", model="gpt-5")
    p._async_client = openai.AsyncOpenAI(
        api_key="test-key", max_retries=0,
        http_client=openai.DefaultAsyncHttpxClient(transport=httpx.MockTransport(handler)),
    )
    return p


async def _drain(provider):
    async for _ in provider.async_stream(
        messages=[{"role": "user", "content": "hi"}], system="s", tools=[],
        model="m-1", max_tokens=100,
    ):
        pass


@pytest.mark.parametrize("build", [_anthropic, _openai], ids=["anthropic", "openai"])
@pytest.mark.parametrize("status, error", [(413, LLMRequestRejectedError), (404, LLMModelNotFoundError)])
def test_a_streaming_error_is_mapped_like_complete(build, status, error):
    with pytest.raises(error) as err:
        asyncio.run(_drain(build(status)))
    assert "Error code:" not in str(err.value), str(err.value)  # not the raw SDK string


def test_the_chat_error_event_carries_the_readable_text(monkeypatch, tmp_path):
    """What the browser gets: the mapped message, not the SDK's dict."""
    from codeframe.ui.routers import session_chat_ws as mod

    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: _anthropic(413))
    monkeypatch.setattr(mod.StreamingChatAdapter, "_load_history", lambda self: [])

    queue: asyncio.Queue = asyncio.Queue()
    asyncio.run(mod._run_streaming_adapter("s1", "Hi", queue, asyncio.Event(), None, tmp_path))
    errors = []
    while not queue.empty():
        e = queue.get_nowait()
        if e.get("type") == "error":
            errors.append(e)
    assert errors, "no error event"
    message = errors[0]["message"]
    assert "HTTP 413" in message and REASON in message, message
    assert "Error code:" not in message, message
