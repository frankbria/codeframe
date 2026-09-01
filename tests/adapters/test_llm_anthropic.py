"""Tests for AnthropicProvider request construction."""

from unittest.mock import MagicMock

import pytest

from codeframe.adapters.llm.anthropic import AnthropicProvider
from codeframe.adapters.llm.base import LLMResponse

pytestmark = pytest.mark.v2


def _provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="test-key")


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_complete_passes_temperature_unconditionally(monkeypatch, temperature):
    """temperature=0.0 must reach the API, not be dropped (#767, #1170).

    On the 1.x SDK the kwarg is gone from ``Messages.create()``, so the adapter
    sends it in ``extra_body`` — which the SDK merges into the request JSON
    verbatim. The invariant is unchanged: 0.0 is a request for deterministic
    sampling, never "unset".
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
    assert "temperature" not in kwargs, "1.x rejects the top-level kwarg"
    assert kwargs["extra_body"]["temperature"] == temperature


@pytest.mark.parametrize("temperature", [0.0, 0.7])
async def test_async_complete_passes_temperature_unconditionally(monkeypatch, temperature):
    """Async path must also pass temperature=0.0 (#767, #1170)."""

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
    assert _create.captured["extra_body"]["temperature"] == temperature


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_stream_passes_temperature_unconditionally(temperature):
    """Sync streaming path must also pass temperature=0.0 (#767, #1170)."""
    provider = _provider()
    fake_client = MagicMock()
    stream_cm = MagicMock()
    stream_cm.__enter__.return_value.text_stream = iter(["hi"])
    fake_client.messages.stream.return_value = stream_cm
    provider._client = fake_client

    list(provider.stream(messages=[{"role": "user", "content": "hi"}], temperature=temperature))

    kwargs = fake_client.messages.stream.call_args.kwargs
    assert "temperature" not in kwargs, "1.x rejects the top-level kwarg"
    assert kwargs["extra_body"]["temperature"] == temperature
