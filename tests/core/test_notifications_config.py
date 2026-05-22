"""Tests for per-workspace notifications config (issue #560)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from codeframe.core.notifications_config import (
    NOTIFICATIONS_CONFIG_FILENAME,
    is_webhook_active,
    load_notifications_config,
    save_notifications_config,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    temp_dir = Path(tempfile.mkdtemp())
    ws_path = temp_dir / "ws"
    ws_path.mkdir(parents=True, exist_ok=True)
    ws = create_or_load_workspace(ws_path)
    try:
        yield ws
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_load_returns_defaults_when_file_missing(workspace):
    cfg = load_notifications_config(workspace)
    assert cfg == {"webhook_url": None, "webhook_enabled": False}


def test_save_then_load_roundtrip(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/hook", "webhook_enabled": True},
    )
    cfg = load_notifications_config(workspace)
    assert cfg["webhook_url"] == "https://example.com/hook"
    assert cfg["webhook_enabled"] is True


def test_save_writes_to_state_dir(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://x.test/hook", "webhook_enabled": False},
    )
    expected = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    assert expected.exists()


def test_load_handles_corrupt_json(workspace):
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text("{ not valid json")
    cfg = load_notifications_config(workspace)
    assert cfg == {"webhook_url": None, "webhook_enabled": False}


def test_empty_url_is_normalized_to_none(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "", "webhook_enabled": True},
    )
    cfg = load_notifications_config(workspace)
    assert cfg["webhook_url"] is None


def test_is_webhook_active_returns_url_when_enabled(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": True},
    )
    assert is_webhook_active(workspace) == "https://example.com/h"


def test_is_webhook_active_returns_none_when_disabled(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://example.com/h", "webhook_enabled": False},
    )
    assert is_webhook_active(workspace) is None


def test_is_webhook_active_returns_none_when_url_missing(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": None, "webhook_enabled": True},
    )
    assert is_webhook_active(workspace) is None


def test_is_webhook_active_trims_whitespace(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "   ", "webhook_enabled": True},
    )
    assert is_webhook_active(workspace) is None


def test_load_handles_non_object_json_list(workspace):
    """A valid-JSON-but-not-object payload (e.g. ``[]``) must not crash."""
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text("[]")
    cfg = load_notifications_config(workspace)
    assert cfg == {"webhook_url": None, "webhook_enabled": False}


def test_load_handles_non_object_json_null(workspace):
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text("null")
    cfg = load_notifications_config(workspace)
    assert cfg == {"webhook_url": None, "webhook_enabled": False}


def test_load_handles_non_object_json_integer(workspace):
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text("42")
    cfg = load_notifications_config(workspace)
    assert cfg == {"webhook_url": None, "webhook_enabled": False}


def test_is_webhook_active_rejects_file_scheme_in_stored_config(workspace):
    """Defence-in-depth: hand-edited config with ``file://`` must not be dispatched."""
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    # Write directly, bypassing save's normalization, to simulate hand edit.
    path.write_text(
        '{"webhook_url": "file:///etc/passwd", "webhook_enabled": true}'
    )
    assert is_webhook_active(workspace) is None


def test_is_webhook_active_rejects_schemeless_url_in_stored_config(workspace):
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text(
        '{"webhook_url": "example.com/hook", "webhook_enabled": true}'
    )
    assert is_webhook_active(workspace) is None


def test_is_webhook_active_accepts_valid_https(workspace):
    save_notifications_config(
        workspace,
        {"webhook_url": "https://hooks.example.com/h", "webhook_enabled": True},
    )
    assert is_webhook_active(workspace) == "https://hooks.example.com/h"


def test_unsafe_url_log_does_not_leak_basic_auth(workspace, caplog):
    """Basic-auth credentials in the URL must be stripped before logging.
    ``parsed.netloc`` preserves ``user:password@host``, so we use
    ``parsed.hostname`` to drop the auth segment.
    """
    import logging

    # Unsafe scheme so we hit the warning branch.
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text(
        '{"webhook_url": "file://admin:SuperSecret@private.host/x", '
        '"webhook_enabled": true}'
    )

    with caplog.at_level(logging.WARNING):
        assert is_webhook_active(workspace) is None

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "SuperSecret" not in log_text
    assert "admin:" not in log_text


def test_redact_url_for_log_preserves_port():
    """Port is non-secret and useful in logs (which environment), so keep it."""
    from codeframe.core.notifications_config import _redact_url_for_log

    assert _redact_url_for_log("https://hooks.example.com:8443/path/x?q=1") == (
        "https://hooks.example.com:8443"
    )


def test_unsafe_url_log_does_not_leak_path_or_query(workspace, caplog):
    """Logs must NOT echo the full URL — webhook URLs often embed secrets
    in the path or query (e.g. Slack token in path, signed Zapier hook)."""
    import logging

    # Write directly to bypass save's PUT-style normalization (which would
    # reject this URL).
    secret_path = (
        "https://example.com/services/T123456/B999/SUPER_SECRET_TOKEN_xyz?sig=abc"
    )
    # Use an unsafe scheme so the unsafe-URL branch fires.
    path = workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME
    path.write_text(
        f'{{"webhook_url": "file://{secret_path}", "webhook_enabled": true}}'
    )

    with caplog.at_level(logging.WARNING):
        assert is_webhook_active(workspace) is None

    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    # The redacted form (scheme://host) is fine; the secret path/token is not.
    assert "SUPER_SECRET_TOKEN" not in log_text
    assert "T123456" not in log_text
    assert "sig=abc" not in log_text
