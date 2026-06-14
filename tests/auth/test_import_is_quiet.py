"""Regression: importing auth must not warn, and the CLI must stay quiet.

The default-AUTH_SECRET warning used to fire at *import* time in
``codeframe.auth.manager``. Because Python's last-resort logging handler prints
WARNING records to stderr, that leaked onto every ``cf`` command (the Golden
Path never uses auth). The warning now lives only in the server's startup
validation. These tests pin that behavior.
"""
import subprocess
import sys

import pytest

pytestmark = pytest.mark.v2


def test_importing_auth_manager_emits_no_warning():
    """A fresh interpreter importing auth.manager prints nothing to stderr."""
    result = subprocess.run(
        [sys.executable, "-c", "import codeframe.auth.manager"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "AUTH_SECRET" not in result.stderr
    assert "DO NOT USE IN PRODUCTION" not in result.stderr


def test_server_validation_still_raises_in_hosted_mode(monkeypatch):
    """The check that matters did not disappear — hosted + default secret fails."""
    import codeframe.auth.manager as manager
    from codeframe.ui.server import _validate_security_config

    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setattr(manager, "SECRET", manager.DEFAULT_SECRET)

    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        _validate_security_config()


def test_server_validation_warns_but_allows_in_self_hosted_mode(monkeypatch, caplog):
    """Self-hosted + default secret + auth OFF is allowed, with a warning.

    Post-#643 the default secret is only tolerated when auth is not enforced;
    set CODEFRAME_AUTH_REQUIRED=false explicitly so this test states its intent
    rather than relying on the suite-wide conftest default. The auth-ON branch
    (which now hard-fails) is covered in tests/ui/test_security_config.py.
    """
    import logging

    import codeframe.auth.manager as manager
    from codeframe.ui.server import _validate_security_config

    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    monkeypatch.setattr(manager, "SECRET", manager.DEFAULT_SECRET)

    with caplog.at_level(logging.WARNING):
        _validate_security_config()  # must not raise

    assert any("default AUTH_SECRET" in r.message for r in caplog.records)
