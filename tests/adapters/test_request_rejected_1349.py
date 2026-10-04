"""A 400 is a rejected request, not a connection failure (#1349).

`map_provider_error` sent every status it did not special-case through
`LLMConnectionError("The … API call failed.")`, with the provider's reason
shown only under CODEFRAME_VERBOSE. A model rejecting `temperature` (#1267)
therefore told users to check their network. Driven through the real SDKs
with a mock transport, like the #1267 wire tests.
"""

from __future__ import annotations

import pytest

from codeframe.adapters.llm.base import LLMConnectionError, LLMRequestRejectedError

pytestmark = pytest.mark.v2

REASON = "temperature is not supported for this model"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.delenv("CODEFRAME_VERBOSE", raising=False)


def _anthropic(handler):
    import anthropic
    import httpx2

    from codeframe.adapters.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="test-key")
    provider._client = anthropic.Anthropic(
        api_key="test-key", max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return provider


def _openai(handler):
    import httpx
    import openai

    from codeframe.adapters.llm.openai import OpenAIProvider

    provider = OpenAIProvider(api_key="test-key", model="gpt-5")
    provider._client = openai.OpenAI(
        api_key="test-key", max_retries=0,
        http_client=openai.DefaultHttpxClient(transport=httpx.MockTransport(handler)),
    )
    return provider


def _anthropic_400(request):
    import httpx2

    return httpx2.Response(400, json={
        "type": "error", "error": {"type": "invalid_request_error", "message": REASON},
    })


def _openai_400(request):
    import httpx

    return httpx.Response(400, json={
        "error": {"message": REASON, "type": "invalid_request_error", "param": "temperature", "code": None},
    })


@pytest.mark.parametrize("build, handler", [(_anthropic, _anthropic_400), (_openai, _openai_400)], ids=["anthropic", "openai"])
def test_a_400_names_the_rejection_and_the_providers_reason(build, handler):
    with pytest.raises(LLMRequestRejectedError) as err:
        build(handler).complete([{"role": "user", "content": "hi"}])
    message = str(err.value)
    assert "HTTP 400" in message, message
    assert REASON in message, message  # without CODEFRAME_VERBOSE
    assert not isinstance(err.value, LLMConnectionError)


def test_a_transport_failure_is_still_a_connection_error():
    import httpx2

    def refused(request):
        raise httpx2.ConnectError("connection refused")

    with pytest.raises(LLMConnectionError):
        _anthropic(refused).complete([{"role": "user", "content": "hi"}])
