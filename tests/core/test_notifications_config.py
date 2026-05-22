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
