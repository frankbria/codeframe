"""A rejected key's 401 message names where that key really came from (#1346).

`map_provider_error` guessed: "$ANTHROPIC_API_KEY, or when unset the stored
key", and for OpenAI-compatible providers it read `os.getenv` itself. But
`create_provider` may have used the principal's own stored key, the
machine-wide store, or — for a hosted tenant — no key at all, so the line
could point the user at the wrong thing to fix. The real path is driven here:
real stores, `create_provider`, and the adapter's own call raising a 401.
"""

from __future__ import annotations

import pytest

from codeframe.adapters.llm.base import Purpose
from codeframe.adapters.llm.errors import LLMAuthError
from codeframe.core.llm_resolution import LLMSettings, create_provider
from tests.core import test_stored_llm_keys_1264 as _keys

pytestmark = pytest.mark.v2

store_dir = _keys.store_dir


class _Rejected(Exception):
    status_code = 401


class _Client:
    """Stands in for the SDK client: every call is a 401."""

    def __getattr__(self, _name):
        return self

    def create(self, **_kw):
        raise _Rejected("invalid x-api-key")


def _rejection(settings, user_id=None):
    provider = create_provider(settings, user_id=user_id)
    provider._client = _Client()  # the lazy SDK client, pre-filled
    with pytest.raises(LLMAuthError) as err:
        provider.complete([{"role": "user", "content": "hi"}], purpose=Purpose.EXECUTION)
    return str(err.value)


def test_a_key_from_the_environment_says_so(store_dir, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", _keys.ENV)
    message = _rejection(LLMSettings(provider_type="anthropic"))
    assert "Key read from: $ANTHROPIC_API_KEY" in message
    assert "stored" not in message.split("Key read from:")[1].splitlines()[0]


def test_a_key_from_the_machine_wide_store_says_so(store_dir):
    _keys._store(_keys.STORED)
    message = _rejection(LLMSettings(provider_type="anthropic"))
    assert "Key read from: the machine-wide stored key" in message


def test_a_key_from_the_principals_own_store_says_so(store_dir):
    _keys._store(_keys.USER, user_id=7)
    message = _rejection(LLMSettings(provider_type="anthropic"), user_id=7)
    assert "Key read from: the key stored for your account" in message


def test_a_hosted_tenant_sent_no_key_is_told_so(store_dir, monkeypatch):
    """The issue's example: it used to report $OPENAI_API_KEY (or nothing),
    never that this server deliberately sent no key."""
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    message = _rejection(LLMSettings(provider_type="ollama", base_url="http://localhost:11434/v1"), user_id=7)
    assert "no key" in message.lower() and "hosted" in message.lower(), message


def test_a_stored_key_is_not_blamed_on_the_environment(store_dir):
    _keys._store(_keys.STORED)
    message = _rejection(LLMSettings(provider_type="anthropic"))
    assert "$ANTHROPIC_API_KEY" not in message, message
