"""Which environment variables came from the *repository* (issue #903).

``cf`` loads ``<cwd>/.env`` with ``override=True``, so a file committed inside a
cloned repo wins over what the operator exported. Anything downstream that
treats ``os.environ`` as "the operator's own configuration" is therefore wrong
for those keys — a repo can set them.

This module records which keys the workspace ``.env`` supplied, so a security
decision can tell the two apart. It deliberately holds *names only*: values stay
in ``os.environ`` and are never copied here.

Headless — no CLI or HTTP imports (architecture rule #1).

Note this is the narrow, base_url-shaped half of the problem. Stopping a repo
``.env`` from overriding the operator's environment in general is #904.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

#: Env var names supplied by the workspace's own ``.env``.
_repo_supplied: set[str] = set()


def record_repo_env_keys(keys: Iterable[str]) -> None:
    """Mark ``keys`` as having come from the repository."""
    _repo_supplied.update(keys)


def is_repo_supplied(name: str) -> bool:
    """Whether ``name``'s value in ``os.environ`` came from the repo's ``.env``."""
    return name in _repo_supplied


def reset() -> None:
    """Clear recorded provenance (tests)."""
    _repo_supplied.clear()


def keys_defined_in(env_file: Path) -> set[str]:
    """Names assigned in a ``.env`` file, without evaluating its values.

    A deliberately minimal parser: it only needs the left-hand sides, and
    reading values here would mean holding secrets in a second place.
    """
    names: set[str] = set()
    try:
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name = line.split("=", 1)[0].strip()
            if name.startswith("export "):
                name = name[len("export "):].strip()
            if name:
                names.add(name)
    except OSError:
        return set()
    return names
