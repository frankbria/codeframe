"""Per-workspace outbound webhook notification config (issue #560).

Stored alongside other workspace UI settings under ``.codeframe/`` as a JSON
file. Headless — no FastAPI or HTTP imports.

Schema (``.codeframe/notifications_config.json``):

    {
      "webhook_url": "https://hooks.example.com/...",  // or null
      "webhook_enabled": true
    }

Defense-in-depth: ``is_webhook_active`` re-validates the URL scheme/host
because the JSON file can be hand-edited or migrated from an older
deployment that didn't enforce validation at write time. The router PUT
endpoint validates too — never trust just one layer.
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

# Intentionally duplicated with codeframe/ui/routers/settings_v2.py's
# ``_ALLOWED_WEBHOOK_SCHEMES``: core cannot import from the UI layer
# (architecture rule #1 — core must be headless). Keep both values in
# sync if extended.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class NotificationsConfig(TypedDict):
    webhook_url: Optional[str]
    webhook_enabled: bool


_DEFAULT: NotificationsConfig = {"webhook_url": None, "webhook_enabled": False}


def _config_path(workspace: Workspace) -> Path:
    return workspace.state_dir / NOTIFICATIONS_CONFIG_FILENAME


def _is_safe_webhook_url(url: str) -> bool:
    """Defence-in-depth: scheme/host check on a stored URL before we POST.

    The router PUT validates too, but a hand-edited or pre-migration JSON
    file could carry a ``file://`` or schemeless URL. Used by
    ``is_webhook_active`` to fail-safe to ``None``.

    TODO: This does NOT block RFC-1918 (10/8, 172.16/12, 192.168/16) or
    loopback (127/8) addresses. For a self-hosted single-user tool that is
    intentional — users want to point at local receivers. If CodeFRAME ever
    runs as a shared / multi-tenant service, add a socket-level check here
    that resolves the host and rejects private/loopback ranges.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return False
    return parsed.scheme.lower() in _ALLOWED_SCHEMES and bool(parsed.netloc)


def load_notifications_config(workspace: Workspace) -> NotificationsConfig:
    """Read notifications config, returning defaults on missing/corrupt file.

    Never raises — a broken config should not break the triggering operation.
    Non-object JSON (``[]``, ``null``, a bare integer) is treated as corrupt
    and falls back to defaults rather than raising ``AttributeError`` from
    a downstream ``.get()`` call.
    """
    path = _config_path(workspace)
    if not path.exists():
        return dict(_DEFAULT)  # type: ignore[return-value]
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(
                f"Expected JSON object, got {type(data).__name__}"
            )
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
    """Return the webhook URL if URL is set, enabled flag is on, AND the URL
    passes basic safety checks (``http(s)`` scheme + non-empty host).

    Returns ``None`` otherwise — callers should short-circuit on ``None`` to
    avoid instantiating the webhook service for nothing. The safety check is
    intentionally redundant with the PUT-endpoint validation: it protects
    against hand-edited config files and pre-migration data.
    """
    cfg = load_notifications_config(workspace)
    url = (cfg["webhook_url"] or "").strip()
    if not url or not cfg["webhook_enabled"]:
        return None
    if not _is_safe_webhook_url(url):
        logger.warning(
            "Refusing to dispatch webhook to unsafe URL: %s",
            _redact_url_for_log(url),
        )
        return None
    return url


def _redact_url_for_log(url: str) -> str:
    """Return a logging-safe representation of a webhook URL.

    Slack/Discord/GitHub-style webhook URLs commonly embed secrets in:

    * the path or query (Slack's ``T*/B*/...`` token, signed Zapier hooks)
    * basic-auth credentials in ``user:password@host`` form

    ``parsed.netloc`` preserves the userinfo segment, so we use
    ``parsed.hostname`` (which strips auth and port) and re-attach the
    port explicitly. Returns ``scheme://host[:port]`` when parsable, else
    ``"<unparseable>"``.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return "<unparseable>"
    if not parsed.scheme or not parsed.hostname:
        return "<unparseable>"
    host = parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"
