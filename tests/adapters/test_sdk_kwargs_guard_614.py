"""#614 — the guard that stops an SDK major bump silently killing every fresh install.

`anthropic` was pinned `>=0.18.0` with no ceiling. anthropic 1.0.0 removed
`temperature` (and the other sampling kwargs) from `Messages.create()`, so every
`uv tool install codeframe-ai` resolved to an SDK the adapter cannot call and
published 0.9.2 was dead on arrival — the same shape of failure as #1112, and
invisible to CI, which resolves the locked 0.70.0 and never sees 1.x.

Since #1170 the project was on 1.x with `temperature` travelling in `extra_body`;
since the 2.x migration it sends no sampling parameter at all, because 2.x pins
API version 2026-10-21, which rejects them on every model. That is the point of
keeping the guard keyed to what the adapter actually sends: the set moves with
the adapter, and the assertion keeps meaning "the installed SDK accepts every
kwarg we send".

This asserts the contract that actually matters: every keyword the adapter passes
unconditionally is one the *installed* SDK accepts. It fails the moment the lock
moves to an SDK whose signature has drifted, whatever the pin says.

Covers both entry points the adapter uses. `messages.stream()` is a separate
signature from `messages.create()`, so one passing says nothing about the other.

Deliberately NOT asserted: `betas` and `thinking`, which `async_stream` sends only
for interleaved extended thinking and already guards with a `TypeError` fallback
(#766). Those are allowed to be absent; the kwargs below are not.

The signature check alone is weak: `extra_body` is generic SDK plumbing that
will never vanish. The wire-level tests at the bottom carry the other half, and
since the 2.x migration they assert two things over the real installed client:

- no sampling parameter (`temperature`, `top_p`, `top_k`) reaches the request
  body on any entry point, for any model — the Claude 3 / 4.x models that used
  to take them included, because API 2026-10-21 rejects them on all of them;
- the SDK still sends an `anthropic-version` the request shape has been
  checked against. A new SDK minor that moves the API version is exactly the
  silent change that broke 0.9.2, so this trips first and names what to check.

Both live here because this file (with test_model_defaults_guard_1112.py) is
what the Unlocked Resolution workflow runs against a no-lockfile resolution of
the pyproject ranges — the one place that sees what a fresh `uv tool install`
would get.
"""

import inspect
import json

import pytest

from codeframe.adapters.llm.base import ModelSelector

#: A model on the legacy request shape (#1267): it took temperature before the
#: 2.x migration, so it is the case most likely to regress into sending one.
LEGACY_MODEL = "claude-haiku-4-5"

#: API versions the adapter's request shape has been checked against. Adding one
#: is a claim that someone read its changelog for request-shape changes
#: (sampling, thinking, content blocks) and updated the adapter to match.
CHECKED_API_VERSIONS = {"2026-10-21"}

#: Rejected by API 2026-10-21 on every model; none may reach the wire.
SAMPLING_PARAMS = ("temperature", "top_p", "top_k")

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


def _message_reply(request):
    import httpx2

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


def _provider_over(handler, model=None):
    """An AnthropicProvider whose sync client is the real SDK on a mock transport."""
    import anthropic
    import httpx2

    from codeframe.adapters.llm.anthropic import AnthropicProvider

    selector = ModelSelector(execution_model=model) if model else None
    provider = AnthropicProvider(api_key="test-key", model_selector=selector)
    provider._client = anthropic.Anthropic(
        api_key="test-key",
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )
    return provider


@pytest.mark.parametrize("temperature", [0.0, 0.7])
def test_no_sampling_parameter_reaches_the_request_body(temperature):
    """API 2026-10-21 rejects sampling parameters on every model.

    The kwarg tests in test_llm_anthropic.py mock ``messages.create`` and so
    only prove what the adapter *hands* the SDK. This one drives the real
    installed client through a mock transport and decodes the JSON it would
    have put on the wire. It uses a legacy model on purpose: those took
    ``temperature`` until the 2.x migration (#767), so they are where a
    regression would reappear.
    """
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _message_reply(request)

    _provider_over(handler, LEGACY_MODEL).complete(
        messages=[{"role": "user", "content": "hi"}], temperature=temperature
    )

    sent = set(SAMPLING_PARAMS) & set(captured["body"])
    assert not sent, f"API 2026-10-21 returns 400 on {sorted(sent)}"


def test_the_sdk_sends_an_api_version_we_have_checked():
    """The tripwire for the next silent request-shape change.

    anthropic 2.x moved to API 2026-10-21, which turned every ``temperature``
    the adapter sent into a 400 without any signature change the guards above
    could see. If a later SDK release sends another version, this fails before
    a fresh install does: read that version's changelog, fix the adapter, then
    add it to ``CHECKED_API_VERSIONS``.
    """
    captured = {}

    def handler(request):
        captured["version"] = request.headers.get("anthropic-version")
        return _message_reply(request)

    _provider_over(handler).complete(messages=[{"role": "user", "content": "hi"}])

    assert captured["version"] in CHECKED_API_VERSIONS, (
        f"installed anthropic SDK sends anthropic-version {captured['version']!r}; "
        f"the adapter's request shape was checked against {sorted(CHECKED_API_VERSIONS)}."
    )


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
def test_no_sampling_parameter_reaches_the_stream_request_body_either(temperature):
    """Same wire assertion for ``messages.stream()``, which is its own method.

    ``stream()`` is a different SDK entry point from ``create()`` with its own
    signature and its own manager, so "create sends no temperature" is not
    evidence that stream does not.
    """
    import httpx2

    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_STREAM_SSE.encode(),
        )

    chunks = list(
        _provider_over(handler, LEGACY_MODEL).stream(
            messages=[{"role": "user", "content": "hi"}], temperature=temperature
        )
    )

    assert chunks == ["hi"], chunks
    sent = set(SAMPLING_PARAMS) & set(captured["body"])
    assert not sent, f"API 2026-10-21 returns 400 on {sorted(sent)}"


def test_the_default_model_sends_no_temperature_over_the_wire():
    """claude-sonnet-5-5 (the default since #1348) rejected temperature even
    before the 2.x migration; it must still get none."""
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _message_reply(request)

    _provider_over(handler).complete(
        messages=[{"role": "user", "content": "hi"}], temperature=0.7
    )

    assert captured["body"]["model"] == "claude-sonnet-5-5"
    assert "temperature" not in captured["body"]
