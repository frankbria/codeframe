"""Tests for per-workspace GitHub integration config (issue #563).

The config holds only non-secret repo metadata — the PAT itself lives in the
machine-wide CredentialManager, never here.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from codeframe.core.github_integration_config import (
    clear_github_integration_config,
    load_github_integration_config,
    save_github_integration_config,
)

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    temp_dir = Path(tempfile.mkdtemp())
    ws_path = temp_dir / "ws"
    ws_path.mkdir(parents=True, exist_ok=True)
    from codeframe.core.workspace import create_or_load_workspace

    ws = create_or_load_workspace(ws_path)
    try:
        yield ws
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_load_returns_none_when_absent(workspace):
    assert load_github_integration_config(workspace) is None


def test_save_then_load_roundtrip(workspace):
    save_github_integration_config(
        workspace,
        {
            "repo": "acme/app",
            "owner_login": "acme",
            "owner_avatar_url": "https://avatars/1",
        },
    )
    cfg = load_github_integration_config(workspace)
    assert cfg is not None
    assert cfg["repo"] == "acme/app"
    assert cfg["owner_login"] == "acme"
    assert cfg["owner_avatar_url"] == "https://avatars/1"
    assert "connected_at" in cfg and cfg["connected_at"]


def test_clear_removes_config(workspace):
    save_github_integration_config(
        workspace,
        {"repo": "acme/app", "owner_login": "acme", "owner_avatar_url": ""},
    )
    assert load_github_integration_config(workspace) is not None
    clear_github_integration_config(workspace)
    assert load_github_integration_config(workspace) is None


def test_clear_is_idempotent(workspace):
    # No config present — clear must not raise.
    clear_github_integration_config(workspace)
    assert load_github_integration_config(workspace) is None


def test_corrupt_file_loads_as_none(workspace):
    from codeframe.core.github_integration_config import _config_path

    path = _config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json")
    assert load_github_integration_config(workspace) is None


def test_config_never_contains_pat(workspace):
    save_github_integration_config(
        workspace,
        {"repo": "acme/app", "owner_login": "acme", "owner_avatar_url": ""},
    )
    from codeframe.core.github_integration_config import _config_path

    raw = _config_path(workspace).read_text()
    assert "pat" not in raw.lower()
    assert "token" not in raw.lower()
