"""Opt-in anonymous telemetry + crash reporting (issue #616).

Headless core module — no FastAPI/UI imports. The CLI layer decides *when* to
record; this module owns consent resolution, payload construction, and
transport.

Privacy guarantees (see PRIVACY.md):
- Default OFF; nothing is ever sent unless the user opts in.
- Resolution order: ``CODEFRAME_TELEMETRY`` env var > ``DO_NOT_TRACK`` >
  ``~/.codeframe/telemetry.json`` > default off.
- Events carry only: command name (validated against the registered command
  tree by the caller), duration, exit code, version, OS, Python version, and a
  random anonymous id. Never args, paths, prompts, or project content.
- Crash reports carry the exception class and traceback frames *inside the
  codeframe package only* (paths relativized); exception messages are omitted
  because they frequently embed user file paths.
- Sends are fire-and-forget with a short timeout; failures are always silent.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://telemetry.codeframe.dev/v1/events"
CONFIG_FILENAME = "telemetry.json"
SCHEMA_VERSION = 1
SEND_TIMEOUT_SECONDS = 3.0

_TRUE_VALUES = {"on", "1", "true", "yes"}
_FALSE_VALUES = {"off", "0", "false", "no"}


@dataclass
class TelemetryConfig:
    """Machine-wide telemetry consent state, stored at ~/.codeframe/telemetry.json."""

    enabled: bool = False
    prompted: bool = False
    anonymous_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    endpoint: Optional[str] = None


def default_storage_dir() -> Path:
    """Machine-wide config dir (same convention as CredentialManager)."""
    return Path.home() / ".codeframe"


def config_path(storage_dir: Optional[Path] = None) -> Path:
    return (storage_dir or default_storage_dir()) / CONFIG_FILENAME


def load_config(storage_dir: Optional[Path] = None) -> TelemetryConfig:
    """Load config; a missing or corrupted file yields safe defaults (off)."""
    path = config_path(storage_dir)
    try:
        data = json.loads(path.read_text())
        return TelemetryConfig(
            enabled=bool(data.get("enabled", False)),
            prompted=bool(data.get("prompted", False)),
            anonymous_id=str(data.get("anonymous_id") or uuid.uuid4()),
            endpoint=data.get("endpoint") or None,
        )
    except FileNotFoundError:
        return TelemetryConfig()
    except (OSError, ValueError, TypeError):
        logger.debug("Unreadable telemetry config at %s; using defaults", path)
        return TelemetryConfig()


def save_config(config: TelemetryConfig, storage_dir: Optional[Path] = None) -> None:
    """Atomically persist config (unique temp file + os.replace)."""
    import tempfile

    path = config_path(storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "enabled": config.enabled,
        "prompted": config.prompted,
        "anonymous_id": config.anonymous_id,
    }
    if config.endpoint:
        payload["endpoint"] = config.endpoint
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
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


def ensure_config(storage_dir: Optional[Path] = None) -> TelemetryConfig:
    """Load config, persisting defaults on first call so the anonymous id is stable."""
    config = load_config(storage_dir)
    if not config_path(storage_dir).exists():
        save_config(config, storage_dir)
    return config


def env_override() -> Optional[bool]:
    """Explicit CODEFRAME_TELEMETRY=on|off override, or None if unset/unrecognized."""
    value = os.environ.get("CODEFRAME_TELEMETRY", "").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def is_enabled(storage_dir: Optional[Path] = None) -> bool:
    """Resolve consent: env var > DO_NOT_TRACK > config file > default off."""
    override = env_override()
    if override is not None:
        return override
    dnt = os.environ.get("DO_NOT_TRACK", "").strip().lower()
    if dnt not in ("", "0", "false"):
        return False
    return load_config(storage_dir).enabled


def resolve_endpoint(storage_dir: Optional[Path] = None) -> str:
    """Resolve collector URL: env var > config file > built-in default."""
    env_endpoint = os.environ.get("CODEFRAME_TELEMETRY_ENDPOINT", "").strip()
    if env_endpoint:
        return env_endpoint
    return load_config(storage_dir).endpoint or DEFAULT_ENDPOINT


def _base_event(event: str, anonymous_id: str) -> dict:
    from codeframe import __version__

    return {
        "event": event,
        "schema": SCHEMA_VERSION,
        "anonymous_id": anonymous_id,
        "version": __version__,
        "os": platform.system().lower(),
        "python": platform.python_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_command_event(
    command: str, duration_ms: int, exit_code: int, anonymous_id: str
) -> dict:
    """Usage event: command name, duration, outcome — nothing else."""
    payload = _base_event("command", anonymous_id)
    payload.update(
        {
            "command": command,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "success": exit_code == 0,
        }
    )
    return payload


def _sanitize_frames(exc: BaseException) -> list[dict]:
    """Keep only traceback frames inside the codeframe package, relativized.

    Exception messages and out-of-package frames (user code, stdlib, deps) are
    dropped entirely — they can embed user file paths.
    """
    package_root = Path(__file__).resolve().parent.parent  # .../codeframe
    base = package_root.parent
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            relative = Path(frame.filename).resolve().relative_to(base)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] == package_root.name:
            frames.append(
                {"file": str(relative), "line": frame.lineno, "function": frame.name}
            )
    return frames


def build_crash_event(exc: BaseException, anonymous_id: str) -> dict:
    """Crash report: exception class + sanitized in-package frames only."""
    payload = _base_event("crash", anonymous_id)
    payload.update(
        {"exception_type": type(exc).__name__, "frames": _sanitize_frames(exc)}
    )
    return payload


def send_events(
    events: list[dict],
    endpoint: str,
    timeout: float = SEND_TIMEOUT_SECONDS,
    client: Optional[httpx.Client] = None,
) -> bool:
    """POST a batch of events. Never raises — telemetry must not break the CLI."""
    try:
        if client is not None:
            response = client.post(endpoint, json={"events": events})
        else:
            with httpx.Client(timeout=timeout) as own_client:
                response = own_client.post(endpoint, json={"events": events})
        return 200 <= response.status_code < 300
    except Exception:
        logger.debug("Telemetry send to %s failed", endpoint, exc_info=True)
        return False


def send_events_background(events: list[dict], endpoint: str) -> threading.Thread:
    """Fire-and-forget send on a daemon thread. Caller may join() with a bound."""
    thread = threading.Thread(
        target=send_events, args=(events, endpoint), daemon=True, name="telemetry-send"
    )
    thread.start()
    return thread
