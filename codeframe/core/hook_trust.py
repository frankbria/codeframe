"""Per-workspace trust decisions for repo-committed hooks (issue #905).

Hook commands come from files a repository can commit — ``.codeframe/config.yaml``
and CODEFRAME.md front matter — and ``cf init`` fires ``after_init`` immediately.
Cloning an untrusted repository and running any ``cf`` command was therefore
equivalent to running its code.

A hook now runs only if the operator has recorded a decision for *these exact
commands* in *this workspace*. The record lives in ``~/.codeframe`` — outside the
repository tree — so a repo cannot grant itself trust by committing the file, and
it is keyed by a hash of the commands so editing a hook revokes the old approval
rather than inheriting it.

Headless — no CLI or HTTP imports (architecture rule #1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from codeframe.core.config import HooksConfig

logger = logging.getLogger(__name__)

#: Opt-in for non-interactive runs, mirroring the CLI's ``--allow-hooks``.
ALLOW_HOOKS_ENV = "CODEFRAME_ALLOW_HOOKS"

_TRUSTED_HOOKS_FILE = "trusted_hooks.json"


def _trust_store_path() -> Path:
    """``~/.codeframe/trusted_hooks.json`` — deliberately outside any repo."""
    return Path.home() / ".codeframe" / _TRUSTED_HOOKS_FILE


def hooks_fingerprint(hooks: "HooksConfig") -> str:
    """Stable hash of the hook commands themselves.

    Keyed on the commands, not merely the workspace, so editing a hook after it
    was approved requires a fresh decision instead of inheriting the old one.
    """
    from dataclasses import fields

    payload = {
        f.name: getattr(hooks, f.name)
        for f in fields(hooks)
        if isinstance(getattr(hooks, f.name, None), str) and getattr(hooks, f.name)
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_store() -> dict:
    path = _trust_store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        # A corrupt store must read as "nothing is trusted", never as a pass.
        logger.warning("Could not read %s; treating all hooks as untrusted", path)
        return {}


def is_trusted(workspace_path: Path, hooks: "HooksConfig") -> bool:
    """Whether these exact hook commands are approved for this workspace."""
    key = str(Path(workspace_path).resolve())
    return _load_store().get(key) == hooks_fingerprint(hooks)


def record_trust(workspace_path: Path, hooks: "HooksConfig") -> None:
    """Approve these exact hook commands for this workspace."""
    path = _trust_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    store = _load_store()
    store[str(Path(workspace_path).resolve())] = hooks_fingerprint(hooks)

    # Atomic write with owner-only permissions: this file decides whether code
    # runs, so a partial write must not be readable as a decision.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(store, handle, indent=2)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def allow_hooks_requested() -> bool:
    """Whether the operator passed the non-interactive opt-in."""
    return os.getenv(ALLOW_HOOKS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def describe_hooks(hooks: "HooksConfig") -> str:
    """The exact commands, for showing the operator before anything runs."""
    from dataclasses import fields

    lines = []
    for f in fields(hooks):
        value = getattr(hooks, f.name, None)
        if isinstance(value, str) and value:
            lines.append(f"  {f.name}: {value}")
    return "\n".join(lines)
