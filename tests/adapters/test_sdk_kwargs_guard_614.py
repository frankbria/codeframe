"""#614 — the guard that stops an SDK major bump silently killing every fresh install.

`anthropic` was pinned `>=0.18.0` with no ceiling. anthropic 1.0.0 removed
`temperature` (and the other sampling kwargs) from `Messages.create()`, so every
`uv tool install codeframe-ai` resolved to an SDK the adapter cannot call and
published 0.9.2 was dead on arrival — the same shape of failure as #1112, and
invisible to CI, which resolves the locked 0.70.0 and never sees 1.x.

This asserts the contract that actually matters: every keyword the adapter passes
unconditionally is one the *installed* SDK accepts. It fails the moment the lock
moves to an SDK whose signature has drifted, whatever the pin says.

Covers both entry points the adapter uses. `messages.stream()` is a separate
signature from `messages.create()`, and the sync `stream()` also sends
`temperature`, so it was exposed to this same break.

Deliberately NOT asserted: `betas` and `thinking`, which `async_stream` sends only
for interleaved extended thinking and already guards with a `TypeError` fallback
(#766). Those are allowed to be absent; the kwargs below are not.
"""

import inspect

import pytest

pytestmark = pytest.mark.v2

# Every key AnthropicProvider puts into `kwargs` unconditionally, across
# complete / async_complete (-> messages.create) and stream / async_stream
# (-> messages.stream). The union is the same set for both.
ADAPTER_KWARGS = {"model", "max_tokens", "messages", "temperature", "system", "tools"}


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
