"""`cf engines check` reports kilo as not ready when it is not logged in (#1353).

`check_ready()` reported only the binary, so a kilo 7.x that was never logged
in passed the check and then failed every task with "You need to sign in to
use this model". Like codex (#1010), readiness now includes `authenticated`.

A real 7.x login, for reference (keys only): `~/.local/share/kilo/auth.json`
is `{"<provider>": {"type": ..., "key": ...}, ...}`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeframe.core import credentials as credentials_module
from codeframe.core.adapters.kilocode import KilocodeAdapter

pytestmark = pytest.mark.v2


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """An empty HOME, no provider keys in the env or the credential store."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("CODEFRAME_DISABLE_KEYRING", "1")
    monkeypatch.setattr(credentials_module, "DEFAULT_STORAGE_DIR", tmp_path / "store")
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return h


def _auth(home: Path, payload) -> None:
    path = home / ".local" / "share" / "kilo" / "auth.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)


def test_a_7x_login_counts(home):
    _auth(home, {"anthropic": {"type": "api", "key": "k"}})
    assert KilocodeAdapter.is_authenticated()


def test_no_login_and_no_key_is_not_ready(home):
    assert not KilocodeAdapter.is_authenticated()
    assert KilocodeAdapter.check_ready()["authenticated"] is False


@pytest.mark.parametrize("payload", [{}, "", "not json"], ids=["empty-object", "empty-file", "garbage"])
def test_an_empty_or_broken_auth_file_is_not_a_login(home, payload):
    _auth(home, payload)
    assert not KilocodeAdapter.is_authenticated()


def test_a_skills_only_kilocode_dir_is_not_a_login(home):
    """~/.kilocode can hold only installed skills; that is not a 0.22 login."""
    (home / ".kilocode" / "skills").mkdir(parents=True)
    assert not KilocodeAdapter.is_authenticated()


@pytest.mark.parametrize("var", ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"])
def test_a_forwarded_provider_key_counts(home, monkeypatch, var):
    """kilo gets these through credential_env_vars (#1270) and uses them."""
    monkeypatch.setenv(var, "sk-test")
    assert KilocodeAdapter.is_authenticated()


def test_a_key_stored_with_cf_auth_setup_counts(home):
    from codeframe.core.credentials import CredentialManager, CredentialProvider

    CredentialManager(migrate=False).set_credential(CredentialProvider.LLM_ANTHROPIC, "sk-ant-stored-0000000000")
    assert KilocodeAdapter.is_authenticated()


def test_a_logged_in_kilo_on_path_is_reported_ready(home, monkeypatch):
    """KILOCODE_PATH was a 'requirement' documented as optional, so it always
    showed as unmet: kilo could never pass `cf engines check`."""
    from codeframe.core.engine_registry import check_requirements

    _auth(home, {"anthropic": {"type": "api", "key": "k"}})
    monkeypatch.setattr("codeframe.core.adapters.kilocode.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv("KILOCODE_PATH", raising=False)

    reqs = check_requirements("kilocode", Path.cwd())
    assert reqs and all(reqs.values()), reqs
