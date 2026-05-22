"""Per-workspace outbound webhook notification config (issue #560).

Stored alongside other workspace UI settings under ``.codeframe/`` as a JSON
file. Headless — no FastAPI or HTTP imports.

Schema (``.codeframe/notifications_config.json``):

    {
      "webhook_url": "https://hooks.example.com/...",  // or null
      "webhook_enabled": true
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, TypedDict

from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

NOTIFICATIONS_CONFIG_FILENAME = "notifications_config.json"


class NotificationsConfig(TypedDict):
    webhook_url: Optional[str]
    webhook_enabled: bool


_DEFAULT: NotificationsConfig = {"webhook_url": None, "webhook_enabled": False}


def _config_path(workspace: Workspace) -> Path:
    return workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME


def load_notifications_config(workspace: Workspace) -> NotificationsConfig:
    """Read notifications config, returning defaults on missing/corrupt file.

    Never raises — a broken config should not break the triggering operation.
    """
    path = _config_path(workspace)
    if not path.exists():
        return dict(_DEFAULT)  # type: ignore[return-value]
    try:
        data = json.loads(path.read_text())
        return {
            "webhook_url": data.get("webhook_url") or None,
            "webhook_enabled": bool(data.get("webhook_enabled", False)),
        }
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning(
            "Invalid notifications_config.json — falling back to defaults: %s", e
        )
        return dict(_DEFAULT)  # type: ignore[return-value]


def save_notifications_config(
    workspace: Workspace, config: NotificationsConfig
) -> None:
    """Atomically persist notifications config to disk."""
    path = _config_path(workspace)
    payload = {
        "webhook_url": config.get("webhook_url") or None,
        "webhook_enabled": bool(config.get("webhook_enabled", False)),
    }
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


def is_webhook_active(workspace: Workspace) -> Optional[str]:
    """Return the webhook URL if both URL is set AND enabled flag is on.

    Returns ``None`` otherwise — callers should short-circuit on ``None`` to
    avoid instantiating the webhook service for nothing.
    """
    cfg = load_notifications_config(workspace)
    url = (cfg["webhook_url"] or "").strip()
    if not url or not cfg["webhook_enabled"]:
        return None
    return url
