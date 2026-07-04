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

import ipaddress
import json
import logging
import os
import socket
import tempfile
from pathlib import Path
from typing import Optional, TypedDict, Union

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


def allow_private_webhook_hosts() -> bool:
    """Opt-out for the SSRF host check (issues #656/#746).

    Off by default (block private/internal targets). Self-hosted operators
    who legitimately point webhooks at ``localhost`` or an internal service
    set ``CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1`` — read at call time so it can
    be toggled without a restart.
    """
    return os.getenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class UnsafeWebhookHostError(Exception):
    """A webhook host is (or resolves to) a private/internal/metadata IP."""

    def __init__(
        self,
        hostname: str,
        ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
    ):
        self.hostname = hostname
        self.ip = ip
        super().__init__(
            f"Webhook host {hostname!r} resolves to a private/internal "
            f"address ({ip}); refusing to avoid SSRF. Set "
            f"CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1 to allow internal targets."
        )


def _is_disallowed_ip(
    ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
) -> bool:
    # ::ffff:169.254.169.254 — judge by the embedded IPv4 address.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # ``not is_global`` is the primary rule: it covers private/loopback/
    # link-local/reserved/unspecified AND CGNAT 100.64.0.0/10, which none of
    # the individual flags report. Multicast (224.0.0.1) reports
    # ``is_global=True``, so check it explicitly.
    return (not ip.is_global) or ip.is_multicast


def vet_webhook_host(hostname: str) -> list[str]:
    """Check a webhook host against private/internal IP ranges (issue #746).

    IP literals are checked directly; DNS names are resolved (blocking —
    call off the event loop) and **every** returned address is checked.
    Returns the vetted IP strings so callers can pin them into the connector
    (closing the resolve-to-connect DNS-rebinding window), or ``[]`` when the
    host is unresolvable — the caller decides whether that blocks (save-time
    allows a not-yet-live URL; dispatch-time refuses).

    Raises ``UnsafeWebhookHostError`` on any private/loopback/link-local/
    metadata address. Does NOT consult ``allow_private_webhook_hosts()`` —
    callers gate on that first.
    """
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if _is_disallowed_ip(literal):
            raise UnsafeWebhookHostError(hostname, literal)
        return [str(literal)]

    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return []

    ips: list[str] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_disallowed_ip(ip):
            raise UnsafeWebhookHostError(hostname, ip)
        if str(ip) not in ips:
            ips.append(str(ip))
    return ips


def _is_safe_webhook_url(url: str) -> bool:
    """Defence-in-depth: scheme/host check on a stored URL before we POST.

    The router PUT validates too, but a hand-edited or pre-migration JSON
    file could carry a ``file://`` or schemeless URL. Used by
    ``is_webhook_active`` to fail-safe to ``None``.

    Private/loopback ranges are NOT checked here — dispatch-time enforcement
    (resolve-and-check + IP pinning, #746) lives in
    ``WebhookNotificationService.send_event``, the single choke point every
    outbound event webhook goes through.
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
    # ``parsed.port`` raises ValueError for malformed ports (e.g.
    # ``file://host:abc/x``). Without this guard the "fail-safe" branch
    # in ``is_webhook_active`` could end up raising instead of returning
    # None, which would bubble through every dispatch site's broad
    # ``except Exception``.
    try:
        port = parsed.port
    except ValueError:
        return "<unparseable>"
    if port is not None:
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"
