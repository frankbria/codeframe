"""Shared helpers for v2 routers."""

import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON via per-call unique temp-file + os.replace.

    A unique temp name is required so concurrent writers to the same target
    do not collide on a shared `.tmp` suffix.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
        os.replace(tmp_name, path)
    except Exception:
        # Clean up the temp file on failure so we don't leak it.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
