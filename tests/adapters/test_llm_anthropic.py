"""Tests for AnthropicProvider request construction."""

from unittest.mock import MagicMock

import pytest

from codeframe.adapters.llm.anthropic import AnthropicProvider
from codeframe.adapters.llm.base import LLMResponse, ModelSelector

pytestmark = pytest.mark.v2


def _provider() -> AnthropicProvider:
    # A legacy-shape model (#1267): it took temperature until the SDK 2.x
    # migration, so it is where a regression back to sending one would show.
    return AnthropicProvider(
        api_key="test-key", model_selector=ModelSelector(execution_model="claude-haiku-4-5")
    )


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_complete_sends_no_temperature(monkeypatch, temperature):
    """No temperature, top-level or in ``extra_body``, for any model.

    anthropic 2.x pins API 2026-10-21, which rejects sampling parameters on
    every model; this retired the #767 "0.0 must reach the API" invariant for
    Anthropic. The wire-level version is in test_sdk_kwargs_guard_614.py.
    """
    provider = _provider()
    fake_client = MagicMock()
    fake_client.messages.create.return_value = MagicMock()
    provider._client = fake_client
    monkeypatch.setattr(
        provider, "_parse_response", lambda r: LLMResponse(content="ok")
    )

    provider.complete(messages=[{"role": "user", "content": "hi"}], temperature=temperature)

    kwargs = fake_client.messages.create.call_args.kwargs
    assert "temperature" not in kwargs
    assert "temperature" not in kwargs.get("extra_body", {})


@pytest.mark.parametrize("temperature", [0.0, 0.7])
async def test_async_complete_sends_no_temperature(monkeypatch, temperature):
    """Async path must not send temperature either (API 2026-10-21)."""

    async def _create(**kwargs):
        _create.captured = kwargs
        return MagicMock()

    provider = _provider()
    fake_async = MagicMock()
    fake_async.messages.create = _create
    provider._async_client = fake_async
    monkeypatch.setattr(
        provider, "_parse_response", lambda r: LLMResponse(content="ok")
    )

    await provider.async_complete(
        messages=[{"role": "user", "content": "hi"}], temperature=temperature
    )

    assert "temperature" not in _create.captured
    assert "temperature" not in _create.captured.get("extra_body", {})


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_stream_sends_no_temperature(temperature):
    """Sync streaming path must not send temperature either (API 2026-10-21)."""
    provider = _provider()
    fake_client = MagicMock()
    stream_cm = MagicMock()
    stream_cm.__enter__.return_value.text_stream = iter(["hi"])
    fake_client.messages.stream.return_value = stream_cm
    provider._client = fake_client

    list(provider.stream(messages=[{"role": "user", "content": "hi"}], temperature=temperature))

    kwargs = fake_client.messages.stream.call_args.kwargs
    assert "temperature" not in kwargs
    assert "temperature" not in kwargs.get("extra_body", {})
