"""Current-generation models accept our request shape (#1267).

Opus 4.7+, Opus 5/5.5, Sonnet 5/5.5 and Fable reject ``temperature`` (and a
``thinking.budget_tokens``) with a 400; OpenAI's gpt-5 and o-series reject
``max_tokens`` and ``temperature``. Every test here drives the real installed SDK
through a mock transport and decodes the JSON body it would have sent — the
same standard as the #767 wire tests in ``test_sdk_kwargs_guard_614.py``.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from codeframe.adapters.llm.base import ModelSelector

pytestmark = pytest.mark.v2

#: Reject sampling and thinking budgets (claude-api skill, model table 2026-09).
NO_SAMPLING = [
    "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-sonnet-5-5", "claude-sonnet-5", "claude-fable-5-1", "claude-fable-5",
    "anthropic.claude-opus-5-5",  # Bedrock prefix
]
#: Still accept both (the current defaults among them).
SAMPLING = [
    "claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-6", "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929", "claude-opus-4-1", "claude-opus-4-20250514",
    "claude-3-5-haiku-20241022", "claude-opus-4-5@20251101",  # Vertex snapshot
]

_MESSAGE = {
    "id": "msg_1", "type": "message", "role": "assistant", "model": "m",
    "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
    "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
}


def _selector(model: str) -> ModelSelector:
    return ModelSelector(
        planning_model=model, execution_model=model, generation_model=model,
        correction_model=model, supervision_model=model,
    )


def _anthropic(model: str, captured: dict, sse: bool = False):
    import anthropic
    import httpx2

    from codeframe.adapters.llm.anthropic import AnthropicProvider
    from tests.adapters.test_sdk_kwargs_guard_614 import _STREAM_SSE

    def handler(request):
        captured["body"] = json.loads(request.content)
        if sse:
            return httpx2.Response(
                200, headers={"content-type": "text/event-stream"},
                content=_STREAM_SSE.encode(),
            )
        return httpx2.Response(200, json=_MESSAGE)

    provider = AnthropicProvider(api_key="test-key", model_selector=_selector(model))
    transport = httpx2.MockTransport(handler)
    provider._client = anthropic.Anthropic(
        api_key="test-key", http_client=anthropic.DefaultHttpxClient(transport=transport)
    )
    provider._async_client = anthropic.AsyncAnthropic(
        api_key="test-key",
        http_client=anthropic.DefaultAsyncHttpxClient(transport=transport),
    )
    return provider


class TestAnthropicSampling:
    @pytest.mark.parametrize("model", NO_SAMPLING)
    def test_complete_omits_temperature(self, model):
        captured: dict = {}
        _anthropic(model, captured).complete(
            messages=[{"role": "user", "content": "hi"}], temperature=0.0
        )
        assert "temperature" not in captured["body"], captured["body"]

    @pytest.mark.parametrize("model", SAMPLING)
    def test_complete_keeps_temperature(self, model):
        """The #767 invariant: temperature=0.0 still reaches models that take it."""
        captured: dict = {}
        _anthropic(model, captured).complete(
            messages=[{"role": "user", "content": "hi"}], temperature=0.0
        )
        assert captured["body"]["temperature"] == 0.0

    @pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5"])
    def test_async_complete_omits_temperature(self, model):
        captured: dict = {}
        asyncio.run(
            _anthropic(model, captured).async_complete(
                messages=[{"role": "user", "content": "hi"}], temperature=0.0
            )
        )
        assert "temperature" not in captured["body"]

    @pytest.mark.parametrize("model, sent", [("claude-opus-5", False), ("claude-sonnet-4-5", True)])
    def test_stream_follows_the_same_rule(self, model, sent):
        captured: dict = {}
        list(_anthropic(model, captured, sse=True).stream(
            messages=[{"role": "user", "content": "hi"}], temperature=0.0
        ))
        assert ("temperature" in captured["body"]) is sent


class TestAnthropicThinking:
    """``async_stream(extended_thinking=True)`` sent a fixed budget, which the
    current generation rejects; it must ask for adaptive thinking instead."""

    def _thinking(self, model):
        captured: dict = {}
        provider = _anthropic(model, captured, sse=True)

        async def _drain():
            async for _ in provider.async_stream(
                messages=[{"role": "user", "content": "hi"}], system="s", tools=[],
                model=model, max_tokens=8000, extended_thinking=True,
            ):
                pass

        asyncio.run(_drain())
        return captured["body"].get("thinking")

    @pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5", "claude-opus-4-7"])
    def test_current_models_get_adaptive_thinking(self, model):
        assert self._thinking(model) == {"type": "adaptive"}

    @pytest.mark.parametrize("model", ["claude-sonnet-4-5", "claude-haiku-4-5"])
    def test_older_models_keep_a_budget(self, model):
        assert self._thinking(model) == {"type": "enabled", "budget_tokens": 4000}


def _openai(model: str, captured: dict, provider_name: str = "openai", base_url=None):
    import httpx
    import openai

    from codeframe.adapters.llm.openai import OpenAIProvider

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "c", "object": "chat.completion", "created": 0, "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })

    provider = OpenAIProvider(
        api_key="test-key", model=model, provider_name=provider_name, base_url=base_url
    )
    provider._client = openai.OpenAI(
        api_key="test-key",
        http_client=openai.DefaultHttpxClient(transport=httpx.MockTransport(handler)),
    )
    return provider


class TestOpenAIShape:
    @pytest.mark.parametrize("model", ["gpt-5", "gpt-5-mini", "o3", "o4-mini"])
    def test_reasoning_models_get_max_completion_tokens_and_no_temperature(self, model):
        captured: dict = {}
        _openai(model, captured).complete(
            messages=[{"role": "user", "content": "hi"}], max_tokens=123, temperature=0.0
        )
        body = captured["body"]
        assert body["max_completion_tokens"] == 123
        assert "max_tokens" not in body and "temperature" not in body

    def test_gpt_4o_keeps_temperature_with_max_completion_tokens(self):
        captured: dict = {}
        _openai("gpt-4o", captured).complete(
            messages=[{"role": "user", "content": "hi"}], max_tokens=123, temperature=0.0
        )
        body = captured["body"]
        assert body["max_completion_tokens"] == 123 and body["temperature"] == 0.0
        assert "max_tokens" not in body

    @pytest.mark.parametrize("name", ["ollama", "vllm", "compatible"])
    def test_compatible_providers_keep_max_tokens(self, name):
        """Many OpenAI-compatible servers predate max_completion_tokens."""
        captured: dict = {}
        _openai("qwen2.5-coder:7b", captured, provider_name=name).complete(
            messages=[{"role": "user", "content": "hi"}], max_tokens=123, temperature=0.0
        )
        body = captured["body"]
        assert body["max_tokens"] == 123 and body["temperature"] == 0.0
        assert "max_completion_tokens" not in body


    def test_provider_openai_pointed_at_a_local_server_keeps_max_tokens(self):
        """CLAUDE.md documents provider: openai + base_url: localhost:11434."""
        captured: dict = {}
        _openai(
            "qwen2.5-coder:7b", captured, base_url="http://localhost:11434/v1"
        ).complete(messages=[{"role": "user", "content": "hi"}], max_tokens=123)
        assert captured["body"]["max_tokens"] == 123
        assert "max_completion_tokens" not in captured["body"]

    def test_an_explicit_api_openai_com_base_url_is_still_openai(self):
        captured: dict = {}
        _openai("gpt-5", captured, base_url="https://api.openai.com/v1").complete(
            messages=[{"role": "user", "content": "hi"}], max_tokens=123
        )
        assert captured["body"]["max_completion_tokens"] == 123
