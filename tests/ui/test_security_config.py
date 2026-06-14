"""Startup security validation for the JWT signing secret (issue #643).

``_validate_security_config()`` must refuse to start the server whenever auth
is enabled and the JWT secret is still the publicly-known default — otherwise
anyone can forge a valid JWT and bypass auth on every v2/WS/SSE route. The only
ways past the default secret are: a real ``AUTH_SECRET``, disabling auth, or an
explicit local-dev escape hatch (which must never apply in hosted mode).
"""

import pytest

from codeframe.auth.manager import DEFAULT_SECRET
from codeframe.ui import server

pytestmark = pytest.mark.v2


@pytest.fixture(autouse=True)
def clean_security_env(monkeypatch):
    """Start each case from a known env: self-hosted, no escape hatch.

    Individual tests opt into hosted mode / auth / escape hatch as needed. The
    module-level ``SECRET`` is patched per test so the default-vs-real branch is
    exercised without depending on the ambient ``AUTH_SECRET``.
    """
    monkeypatch.delenv("CODEFRAME_DEPLOYMENT_MODE", raising=False)
    monkeypatch.delenv("CODEFRAME_ALLOW_INSECURE_SECRET", raising=False)
    monkeypatch.delenv("CODEFRAME_AUTH_REQUIRED", raising=False)
    yield


def _set_secret(monkeypatch, value):
    # _validate_security_config re-imports SECRET from the manager at call time,
    # so patching the module attribute is enough (no reload required).
    monkeypatch.setattr("codeframe.auth.manager.SECRET", value)


def test_default_secret_with_auth_enabled_fails_hard(monkeypatch):
    """AC1: default secret + auth on (self-hosted default) → startup error."""
    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        server._validate_security_config()


def test_default_secret_with_escape_hatch_starts(monkeypatch, caplog):
    """AC2: escape hatch lets local dev run on the default secret (with a warning)."""
    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CODEFRAME_ALLOW_INSECURE_SECRET", "1")

    with caplog.at_level("WARNING"):
        server._validate_security_config()  # must not raise

    assert any("AUTH_SECRET" in rec.message for rec in caplog.records)


def test_real_secret_starts(monkeypatch):
    """AC2: a real secret + auth on → server starts (no error)."""
    _set_secret(monkeypatch, "a-real-and-very-secret-value")
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")

    server._validate_security_config()  # must not raise


def test_default_secret_with_auth_disabled_starts(monkeypatch, caplog):
    """Auth off → the secret is unused for enforcement, so only warn."""
    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")

    with caplog.at_level("WARNING"):
        server._validate_security_config()  # must not raise

    assert any("AUTH_SECRET" in rec.message for rec in caplog.records)


def test_hosted_mode_default_secret_fails_hard(monkeypatch):
    """Existing behavior preserved: hosted + default secret always fails."""
    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        server._validate_security_config()


def test_hosted_mode_default_secret_fails_even_with_auth_disabled(monkeypatch):
    """Hosted mode rejects the default secret regardless of auth — the hosted
    check fires before the auth_required() branch."""
    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        server._validate_security_config()


def test_hosted_mode_escape_hatch_still_fails(monkeypatch):
    """The dev escape hatch must never weaken hosted/production mode."""
    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CODEFRAME_ALLOW_INSECURE_SECRET", "1")

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        server._validate_security_config()


@pytest.mark.parametrize(
    "raw",
    ["", "   ", DEFAULT_SECRET + " ", "  " + DEFAULT_SECRET, f"\t{DEFAULT_SECRET}\n"],
)
@pytest.mark.parametrize("mode", ["self_hosted", "hosted"])
def test_blank_or_padded_default_secret_is_rejected(monkeypatch, raw, mode):
    """Blank/whitespace AUTH_SECRET — and a whitespace-padded copy of the known
    default — are as forgeable as the default, so they must hit the hard-fail
    path rather than be accepted as a custom secret."""
    import codeframe.auth.manager as manager

    _set_secret(monkeypatch, "stale-import-time-default")
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", mode)
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("AUTH_SECRET", raw)

    assert manager.refresh_secret() == DEFAULT_SECRET  # normalized to sentinel

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        server._validate_security_config()


def test_padded_custom_secret_is_preserved_verbatim(monkeypatch):
    """A genuinely custom secret keeps its exact bytes (incl. padding) for
    signing — only a padded copy of the *default* is normalized away."""
    import codeframe.auth.manager as manager

    _set_secret(monkeypatch, DEFAULT_SECRET)
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("AUTH_SECRET", "  my-real-secret  ")

    assert manager.refresh_secret() == "  my-real-secret  "  # not stripped
    server._validate_security_config()  # must not raise


def test_env_only_secret_is_honored_after_refresh(monkeypatch):
    """Regression (#643 review P2): AUTH_SECRET set only in .env must let the
    server start.

    The auth manager captures SECRET at import time — before the lifespan loads
    .env — so an operator who sets AUTH_SECRET only in .env would otherwise hit
    the new hard-fail. The lifespan calls refresh_secret() after load_environment
    so the real secret is seen. Simulate that: SECRET starts at the default, the
    env then gains a real value, and refresh_secret() must update it so
    validation passes and signing uses the configured secret.
    """
    import codeframe.auth.manager as manager

    _set_secret(monkeypatch, DEFAULT_SECRET)  # stale import-time default
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    monkeypatch.setenv("AUTH_SECRET", "secret-loaded-from-dotenv-at-startup")

    refreshed = manager.refresh_secret()

    assert refreshed == "secret-loaded-from-dotenv-at-startup"
    assert manager.SECRET == "secret-loaded-from-dotenv-at-startup"
    server._validate_security_config()  # must not raise
