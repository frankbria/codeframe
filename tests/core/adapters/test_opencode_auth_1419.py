"""`cf engines check` reports opencode ready on one key or a login (#1419).

`requirements()` listed ANTHROPIC_API_KEY *and* OPENAI_API_KEY, and
`check_requirements` counts every unset entry as unmet, so opencode was only
ever "ready" with both keys set, although it needs one, or none when it is
logged in with `opencode auth login`. Same shape as codex (#1010) and kilo
(#1353): `requirements()` is empty and `check_ready` adds `authenticated`.

opencode keeps logins in `~/.local/share/opencode/auth.json` as
`{"<provider>": {"type": ..., "key": ...}}` (kilo is a fork of it).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeframe.core import credentials as credentials_module
from codeframe.core.engine_registry import check_requirements

pytestmark = pytest.mark.v2


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """An empty HOME, no provider keys in the env or the credential store,
    and an opencode binary on PATH."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("CODEFRAME_DISABLE_KEYRING", "1")
    monkeypatch.setattr(credentials_module, "DEFAULT_STORAGE_DIR", tmp_path / "store")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("codeframe.core.adapters.opencode.shutil.which", lambda name: f"/usr/bin/{name}")
    return h


def _ready(home) -> dict[str, bool]:
    return check_requirements("opencode", Path.cwd())


def _login(home: Path, payload) -> None:
    path = home / ".local" / "share" / "opencode" / "auth.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)


@pytest.mark.parametrize("var", ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"])
def test_one_provider_key_is_enough(home, monkeypatch, var):
    monkeypatch.setenv(var, "sk-test")
    reqs = _ready(home)
    assert reqs and all(reqs.values()), reqs


def test_an_opencode_login_alone_is_enough(home):
    _login(home, {"anthropic": {"type": "api", "key": "k"}})
    reqs = _ready(home)
    assert reqs and all(reqs.values()), reqs


def test_a_key_stored_with_cf_auth_setup_is_enough(home):
    from codeframe.core.credentials import CredentialManager, CredentialProvider

    CredentialManager(migrate=False).set_credential(CredentialProvider.LLM_OPENAI, "sk-stored-0000000000")
    reqs = _ready(home)
    assert reqs and all(reqs.values()), reqs


def test_neither_a_key_nor_a_login_is_not_ready(home):
    assert _ready(home).get("authenticated") is False


@pytest.mark.parametrize("payload", [{}, "not json", {"anthropic": {}}, {"anthropic": {"type": "api", "key": ""}}],
                         ids=["empty-object", "garbage", "empty-entry", "blank-key"])
def test_an_empty_or_broken_login_is_not_ready(home, payload):
    _login(home, payload)
    assert _ready(home).get("authenticated") is False


def test_a_missing_binary_is_not_ready(home, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr("codeframe.core.adapters.opencode.shutil.which", lambda name: None)
    assert _ready(home).get("opencode_binary") is False
