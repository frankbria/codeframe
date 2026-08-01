"""`--engine codex` must run when the codex CLI is logged in (#1010 / P0.28).

`cf work start --engine codex --execute` and `cf work batch run --engine codex`
both called `require_openai_api_key()`, which exits when `OPENAI_API_KEY` is
unset. But codex does not need that variable — `codex login` writes ChatGPT-plan
credentials to `~/.codex/auth.json`, and the #914 end-to-end demo drove a real
`codex app-server` to completion with no `OPENAI_API_KEY` at all.

A real logged-in auth.json on this machine, for reference:

    auth_mode      = 'chatgpt'
    OPENAI_API_KEY = None          # literally null
    tokens         = {access_token, account_id, id_token, refresh_token}

So the env var is not merely an incomplete proof of auth — the logged-in file
explicitly records it as absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def codex_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return home


def _write_auth(home: Path, payload: dict) -> None:
    (home / "auth.json").write_text(json.dumps(payload))


def _chatgpt_login() -> dict:
    """The shape `codex login` actually writes for a ChatGPT-plan account."""
    return {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "last_refresh": "2026-08-01T00:00:00.000000000Z",
        "tokens": {
            "access_token": "at",
            "account_id": "acct",
            "id_token": "it",
            "refresh_token": "rt",
        },
    }


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_a_chatgpt_login_counts_as_authenticated(codex_home):
    """The headline case: `codex login`, no OPENAI_API_KEY anywhere."""
    from codeframe.core.adapters.codex import CodexAdapter

    _write_auth(codex_home, _chatgpt_login())

    assert CodexAdapter.is_authenticated()


def test_the_env_key_still_counts(codex_home, monkeypatch):
    """codex honours OPENAI_API_KEY too — it stays a valid alternative."""
    from codeframe.core.adapters.codex import CodexAdapter

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    assert CodexAdapter.is_authenticated()


def test_an_api_key_stored_in_auth_json_counts(codex_home):
    """`codex login --api-key` writes the key into the file instead."""
    from codeframe.core.adapters.codex import CodexAdapter

    _write_auth(codex_home, {"auth_mode": "apikey", "OPENAI_API_KEY": "sk-stored"})

    assert CodexAdapter.is_authenticated()


def test_neither_is_not_authenticated(codex_home):
    from codeframe.core.adapters.codex import CodexAdapter

    assert not CodexAdapter.is_authenticated()


def test_a_logged_out_auth_json_is_not_authenticated(codex_home):
    """`codex logout` can leave the file behind with nothing in it — presence
    alone must not be the test."""
    from codeframe.core.adapters.codex import CodexAdapter

    _write_auth(codex_home, {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
                             "tokens": {}})

    assert not CodexAdapter.is_authenticated()


def test_a_corrupt_auth_json_is_not_authenticated(codex_home):
    (codex_home / "auth.json").write_text("{not json")

    from codeframe.core.adapters.codex import CodexAdapter

    assert not CodexAdapter.is_authenticated()


def test_codex_home_is_honoured(tmp_path, monkeypatch):
    """codex documents $CODEX_HOME; hard-coding ~/.codex would miss a relocated
    install."""
    from codeframe.core.adapters.codex import CodexAdapter

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    elsewhere = tmp_path / "relocated"
    elsewhere.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    monkeypatch.setenv("CODEX_HOME", str(elsewhere))
    _write_auth(elsewhere, _chatgpt_login())

    assert CodexAdapter.is_authenticated()


def test_check_ready_reports_the_login(codex_home):
    """AC3: `cf engines check` must not flag a missing key when logged in."""
    from codeframe.core.adapters.codex import CodexAdapter

    _write_auth(codex_home, _chatgpt_login())

    assert CodexAdapter.check_ready().get("authenticated") is True


def test_check_ready_reports_the_absence(codex_home):
    from codeframe.core.adapters.codex import CodexAdapter

    assert CodexAdapter.check_ready().get("authenticated") is False


# ---------------------------------------------------------------------------
# The CLI gate — the actual user-visible bug
# ---------------------------------------------------------------------------


def test_the_cli_does_not_refuse_a_logged_in_codex(codex_home, monkeypatch):
    """AC1: `--engine codex` runs with no OPENAI_API_KEY when codex is logged in."""
    from codeframe.cli.validators import require_codex_auth

    _write_auth(codex_home, _chatgpt_login())

    require_codex_auth()  # must not raise


def test_the_cli_still_fails_fast_when_unauthenticated(codex_home, capsys, monkeypatch):
    """AC2: and the message names *both* ways to authenticate."""
    import typer

    import codeframe.cli.validators as validators
    from codeframe.cli.validators import require_codex_auth

    # The validator falls back to .env files, and this machine (like CI) may
    # have a real OPENAI_API_KEY in one. Pin the unauthenticated case.
    monkeypatch.setattr(validators, "load_env_files", lambda: None)

    with pytest.raises(typer.Exit):
        require_codex_auth()

    message = capsys.readouterr().out
    assert "codex login" in message
    assert "OPENAI_API_KEY" in message


def test_work_start_uses_the_codex_check_not_the_openai_one(monkeypatch, codex_home):
    """The gate at the call site is what actually blocked the user."""
    import codeframe.cli.validators as validators

    _write_auth(codex_home, _chatgpt_login())

    called: list[str] = []
    monkeypatch.setattr(
        validators, "require_openai_api_key",
        lambda: called.append("openai") or "k",
    )

    from codeframe.cli.app import app  # noqa: F401  (import side effects only)

    validators.require_codex_auth()
    assert called == [], "the codex path must not go through require_openai_api_key"


def test_engines_check_calls_codex_ready_when_logged_in(codex_home):
    """AC3, at the surface the user actually sees.

    `cf engines check` marks *any* unsatisfied entry as an unmet requirement and
    exits 1, so listing OPENAI_API_KEY under `requirements()` reported a working
    logged-in codex as broken.
    """
    from codeframe.core.engine_registry import check_requirements

    _write_auth(codex_home, _chatgpt_login())

    reqs = check_requirements("codex")

    assert reqs["authenticated"] is True
    # The specific claim: no *credential* entry is reported unmet. Not
    # `all(reqs.values())` — codex_binary is legitimately False wherever the CLI
    # is not installed, which is every CI runner.
    assert "OPENAI_API_KEY" not in reqs, (
        f"a logged-in codex is still flagged for a missing key: {reqs}"
    )


def test_engines_check_still_flags_an_unauthenticated_codex(codex_home):
    from codeframe.core.engine_registry import check_requirements

    reqs = check_requirements("codex")

    # `not all(...)` would pass trivially wherever the binary is absent.
    assert reqs["authenticated"] is False
