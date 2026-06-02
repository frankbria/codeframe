"""Per-workspace GitHub integration config (issue #563).

Stores only **non-secret** repo metadata for a connected GitHub repository under
``.codeframe/github_integration.json``. The PAT itself is stored in the
machine-wide ``CredentialManager`` (``CredentialProvider.GIT_GITHUB``) — never
in this file.

Headless — no FastAPI or HTTP imports (architecture rule #1). Mirrors the
shape of ``codeframe/core/notifications_config.py``.

Schema (``.codeframe/github_integration.json``):

    {
      "repo": "owner/repo",
      "owner_login": "owner",
      "owner_avatar_url": "https://avatars.githubusercontent.com/...",
      "connected_at": "2026-06-01T12:00:00+00:00"
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

GITHUB_INTEGRATION_CONFIG_FILENAME = "github_integration.json"


class GitHubIntegrationConfig(TypedDict):
    repo: str
    owner_login: str
    owner_avatar_url: str
    connected_at: str


def _config_path(workspace: Workspace) -> Path:
    return workspace.state_dir / GITHUB_INTEGRATION_CONFIG_FILENAME


def load_github_integration_config(
    workspace: Workspace,
) -> Optional[GitHubIntegrationConfig]:
    """Read the integration config, returning ``None`` when absent or corrupt.

    Never raises — a broken config should read as "not connected" rather than
    breaking the status endpoint.
    """
    path = _config_path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not data.get("repo"):
            raise ValueError("missing required 'repo' field")
        return {
            "repo": str(data["repo"]),
            "owner_login": str(data.get("owner_login") or ""),
            "owner_avatar_url": str(data.get("owner_avatar_url") or ""),
            "connected_at": str(data.get("connected_at") or ""),
        }
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Invalid github_integration.json — treating as not connected: %s", e
        )
        return None


def save_github_integration_config(
    workspace: Workspace,
    config: dict,
) -> GitHubIntegrationConfig:
    """Atomically persist integration config to disk.

    ``connected_at`` is stamped here (UTC) if not supplied by the caller.
    Returns the normalized config that was written.
    """
    payload: GitHubIntegrationConfig = {
        "repo": str(config["repo"]),
        "owner_login": str(config.get("owner_login") or ""),
        "owner_avatar_url": str(config.get("owner_avatar_url") or ""),
        "connected_at": str(
            config.get("connected_at") or datetime.now(timezone.utc).isoformat()
        ),
    }
    path = _config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return payload


def clear_github_integration_config(workspace: Workspace) -> None:
    """Remove the integration config. Idempotent — absence is a no-op."""
    path = _config_path(workspace)
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Failed to remove github_integration.json: %s", e)
