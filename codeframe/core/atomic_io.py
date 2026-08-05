"""Atomic, crash-safe file writes.

Headless by construction — stdlib only, no FastAPI/UI imports, so every layer
(core, CLI, routers) can share one implementation.

Why this exists: `open(path, "w")` truncates the target *first*. A crash, a
full disk or a killed process between that truncation and the last byte leaves
the file empty or half-written, and the previous contents are gone. For
`config.yaml`, `environment.json` and the encrypted credential store, that is
silent data loss on the user's machine (#954).

The sequence here is the standard durable-replace dance:

1. write into a temp file **in the same directory** (``os.replace`` is only
   atomic within a filesystem),
2. ``fsync`` it so the bytes are on disk before anything points at them,
3. ``os.replace`` onto the target — atomic, so a reader sees either the whole
   old file or the whole new one, never a mixture,
4. best-effort ``fsync`` of the directory so the rename itself survives a crash.

The temp name is unique per call: a shared ``.tmp`` suffix let two concurrent
writers collide, with the loser's cleanup deleting the winner's in-flight file
(#920).
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union

__all__ = [
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
    "fsync_directory",
]


def fsync_directory(path: Union[str, Path]) -> None:
    """Best-effort ``fsync`` of a directory so a rename inside it is durable.

    ``os.replace`` is atomic but not automatically durable: on POSIX
    filesystems a power loss right after the rename can lose the new directory
    entry even though the file's own contents were synced. Anything that
    renames a finished file into place — including the workspace ``state.db``
    swap, which does not go through ``atomic_write_bytes`` — needs this.

    Silently does nothing where directories cannot be opened (Windows).
    """
    try:
        dir_fd = os.open(path, os.O_RDONLY)
    except OSError:  # pragma: no cover - platform dependent
        return
    try:
        os.fsync(dir_fd)
    except OSError:  # pragma: no cover - platform dependent
        pass
    finally:
        os.close(dir_fd)


def atomic_write_bytes(path: Union[str, Path], data: bytes, mode: int | None = None) -> None:
    """Durably replace ``path`` with ``data``.

    Args:
        path: Target file. Parent directories are created if missing.
        data: Bytes to write.
        mode: Optional permission bits applied to the file before it is moved
            into place, so it is never briefly world-readable at the target
            name (used for the credential store's 0600).

    Raises:
        OSError: If the write, fsync or rename fails. The existing file at
            ``path`` is left untouched in that case.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        # Never leak the temp file — a failed save must not litter the
        # workspace with .config.yaml.*.tmp droppings.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    # Persist the directory entry too, or the rename itself can be lost on a
    # hard crash even though the file contents were synced.
    fsync_directory(path.parent)


def atomic_write_text(
    path: Union[str, Path], text: str, encoding: str = "utf-8", mode: int | None = None
) -> None:
    """Durably replace ``path`` with ``text``.

    The encoding is explicit and defaults to UTF-8 rather than the locale
    default, which would otherwise write cp1252 on stock Windows and then be
    rejected by our own UTF-8 readers (#931/#1029).
    """
    atomic_write_bytes(path, text.encode(encoding), mode=mode)


def atomic_write_json(path: Union[str, Path], payload: Any, mode: int | None = None) -> None:
    """Durably replace ``path`` with ``payload`` serialized as indented JSON."""
    atomic_write_text(path, json.dumps(payload, indent=2), mode=mode)
