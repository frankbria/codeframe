"""#614 — the guard that stops an SDK major bump silently killing every fresh install.

`anthropic` was pinned `>=0.18.0` with no ceiling. anthropic 1.0.0 removed
`temperature` (and the other sampling kwargs) from `Messages.create()`, so every
`uv tool install codeframe-ai` resolved to an SDK the adapter cannot call and
published 0.9.2 was dead on arrival — the same shape of failure as #1112, and
invisible to CI, which resolves the locked 0.70.0 and never sees 1.x.

This asserts the contract that actually matters: every keyword the adapter
passes is one the *installed* SDK accepts. It fails the moment the lock moves to
an SDK whose signature has drifted, whatever the pin says.
"""

import inspect

import pytest

pytestmark = pytest.mark.v2

# Every key AnthropicProvider.complete / async_complete put into `kwargs`.
ADAPTER_KWARGS = {"model", "max_tokens", "messages", "temperature", "system", "tools"}


def _create_params(create) -> set[str]:
    return set(inspect.signature(create).parameters)


def test_sync_client_accepts_every_kwarg_the_adapter_sends():
    from anthropic import Anthropic

    missing = ADAPTER_KWARGS - _create_params(Anthropic(api_key="x").messages.create)
    assert not missing, (
        f"installed anthropic SDK no longer accepts {sorted(missing)} on "
        "Messages.create(); AnthropicProvider still sends them. Migrate the "
        "adapter before raising the pin in pyproject.toml."
    )


def test_async_client_accepts_every_kwarg_the_adapter_sends():
    from anthropic import AsyncAnthropic

    missing = ADAPTER_KWARGS - _create_params(
        AsyncAnthropic(api_key="x").messages.create
    )
    assert not missing, (
        f"installed anthropic SDK no longer accepts {sorted(missing)} on async "
        "Messages.create(); AnthropicProvider.async_complete still sends them."
    )
