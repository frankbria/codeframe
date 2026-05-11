"""Shared helpers for v2 routers."""

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON via temp-file + os.replace so a crash mid-write cannot
    leave a truncated file at `path`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
