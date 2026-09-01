"""#614 — the guard that stops an SDK major bump silently killing every fresh install.

`anthropic` was pinned `>=0.18.0` with no ceiling. anthropic 1.0.0 removed
`temperature` (and the other sampling kwargs) from `Messages.create()`, so every
`uv tool install codeframe-ai` resolved to an SDK the adapter cannot call and
published 0.9.2 was dead on arrival — the same shape of failure as #1112, and
invisible to CI, which resolves the locked 0.70.0 and never sees 1.x.

Since #1170 the project is *on* 1.x and `temperature` travels in `extra_body`
instead — so it is no longer in this set. That is the point of keeping the guard
keyed to what the adapter actually sends: the set moves with the adapter, and the
assertion keeps meaning "the installed SDK accepts every kwarg we send".

This asserts the contract that actually matters: every keyword the adapter passes
unconditionally is one the *installed* SDK accepts. It fails the moment the lock
moves to an SDK whose signature has drifted, whatever the pin says.

Covers both entry points the adapter uses. `messages.stream()` is a separate
signature from `messages.create()`, and the sync `stream()` also sends
`temperature` in `extra_body`, so it was exposed to this same break.

Deliberately NOT asserted: `betas` and `thinking`, which `async_stream` sends only
for interleaved extended thinking and already guards with a `TypeError` fallback
(#766). Those are allowed to be absent; the kwargs below are not.

The signature check alone got weaker at #1170: `extra_body` is generic SDK
plumbing that will never vanish, whereas `temperature` was a real bet on the
signature. So the wire-level test at the bottom carries the other half — that
`extra_body` is still *merged into the request body*, which is the only reason
routing `temperature` through it is acceptable. Both live here because this file
(with test_model_defaults_guard_1112.py) is what the Unlocked Resolution workflow
runs against a no-lockfile resolution of the pyproject ranges — the one place
that sees what a fresh `uv tool install` would get.
"""

import inspect
import json

import pytest

pytestmark = pytest.mark.v2

# Every key AnthropicProvider puts into `kwargs` unconditionally, across
# complete / async_complete (-> messages.create) and stream / async_stream
# (-> messages.stream). The union is the same set for both.
ADAPTER_KWARGS = {"model", "max_tokens", "messages", "extra_body", "system", "tools"}


def _missing(method) -> set[str]:
    return ADAPTER_KWARGS - set(inspect.signature(method).parameters)


def _clients():
    from anthropic import Anthropic, AsyncAnthropic

    return Anthropic(api_key="x"), AsyncAnthropic(api_key="x")


@pytest.mark.parametrize("call", ["create", "stream"])
def test_sync_client_accepts_every_kwarg_the_adapter_sends(call):
    sync, _ = _clients()

    missing = _missing(getattr(sync.messages, call))
    assert not missing, (
        f"installed anthropic SDK no longer accepts {sorted(missing)} on "
        f"Messages.{call}(); AnthropicProvider still sends them. Migrate the "
        "adapter before raising the pin in pyproject.toml."
    )


@pytest.mark.parametrize("call", ["create", "stream"])
def test_async_client_accepts_every_kwarg_the_adapter_sends(call):
    _, async_ = _clients()

    missing = _missing(getattr(async_.messages, call))
    assert not missing, (
        f"installed anthropic SDK no longer accepts {sorted(missing)} on async "
        f"Messages.{call}(); AnthropicProvider still sends them."
    )


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_temperature_reaches_the_request_body_over_the_wire(temperature):
    """The #767 invariant, asserted where it actually matters: the HTTP body.

    The kwarg tests in test_llm_anthropic.py mock ``messages.create`` and so
    only prove what the adapter *hands* the SDK. This one drives the real
    installed client through a mock transport and decodes the JSON it would
    have put on the wire — so it fails if ``extra_body`` ever stops being
    merged into the request, which is the half the signature check above can
    no longer see.
    """
    import anthropic
    import httpx2

    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    from codeframe.adapters.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="test-key")
    provider._client = anthropic.Anthropic(
        api_key="test-key",
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )

    provider.complete(
        messages=[{"role": "user", "content": "hi"}], temperature=temperature
    )

    assert captured["body"]["temperature"] == temperature


#: A minimal well-formed SSE stream, enough for ``messages.stream()`` to build a
#: final message. Only the request matters here; this is just a valid reply.
_STREAM_SSE = "\n".join(
    [
        "event: message_start",
        'data: {"type":"message_start","message":{"id":"m","type":"message",'
        '"role":"assistant","model":"claude-sonnet-4-5","content":[],'
        '"stop_reason":null,"stop_sequence":null,'
        '"usage":{"input_tokens":1,"output_tokens":0}}}',
        "",
        "event: content_block_start",
        'data: {"type":"content_block_start","index":0,'
        '"content_block":{"type":"text","text":""}}',
        "",
        "event: content_block_delta",
        'data: {"type":"content_block_delta","index":0,'
        '"delta":{"type":"text_delta","text":"hi"}}',
        "",
        "event: content_block_stop",
        'data: {"type":"content_block_stop","index":0}',
        "",
        "event: message_delta",
        'data: {"type":"message_delta",'
        '"delta":{"stop_reason":"end_turn","stop_sequence":null},'
        '"usage":{"output_tokens":1}}',
        "",
        "event: message_stop",
        'data: {"type":"message_stop"}',
        "",
    ]
)


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_temperature_reaches_the_stream_request_body_too(temperature):
    """Same wire assertion for ``messages.stream()``, which is its own method.

    ``stream()`` is a different SDK entry point from ``create()`` with its own
    signature and its own manager, so "create merges extra_body" is not
    evidence that stream does. Without this, the sync streaming path would rest
    on exactly the signature-only check this file already says proves nothing
    for a generic kwarg like ``extra_body``.
    """
    import anthropic
    import httpx2

    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_STREAM_SSE.encode(),
        )

    from codeframe.adapters.llm.anthropic import AnthropicProvider

    provider = AnthropicProvider(api_key="test-key")
    provider._client = anthropic.Anthropic(
        api_key="test-key",
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )

    chunks = list(
        provider.stream(
            messages=[{"role": "user", "content": "hi"}], temperature=temperature
        )
    )

    assert chunks == ["hi"], chunks
    assert captured["body"]["temperature"] == temperature
