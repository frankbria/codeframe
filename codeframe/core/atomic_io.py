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
    "DEFAULT_FILE_MODE",
]

# ``tempfile.mkstemp`` forces 0600 and ``os.replace`` carries that onto the
# target, so writing through this module would silently tighten config.yaml /
# environment.json from the umask-derived mode ``open(path, "w")`` gave them.
# Default to what a plain create would produce instead; callers that want
# something stricter (the credential store) pass ``mode`` explicitly.
#
# Read once at import, not per call: ``os.umask`` is a read-modify-write of a
# process-global, so doing it on every write opens a window where another
# thread creates a world-writable file (raised by the GLM reviewer).
_UMASK = os.umask(0)
os.umask(_UMASK)
DEFAULT_FILE_MODE = 0o666 & ~_UMASK


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


def atomic_write_bytes(
    path: Union[str, Path], data: bytes, mode: int | None = None
) -> None:
    """Durably replace ``path`` with ``data``.

    Args:
        path: Target file. Parent directories are created if missing.
        data: Bytes to write.
        mode: Permission bits applied to the file before it is moved into
            place, so it never briefly carries the wrong mode at the target
            name (the credential store passes 0600). When omitted, the target's
            existing permissions are preserved, and a file that does not exist
            yet gets ``DEFAULT_FILE_MODE`` — matching ``open(path, "w")`` in
            both cases, rather than mkstemp's 0600.

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
            file_mode = mode
        else:
            # os.replace points the target name at the temp *inode*, carrying
            # its mode along, whereas `open(path, "w")` truncated the existing
            # inode and left its mode alone. So a fixed default would silently
            # undo an operator's `chmod 600 .codeframe/config.yaml` on the next
            # save. Preserve what is already there; only a file that does not
            # exist yet gets the umask default.
            try:
                file_mode = path.stat().st_mode & 0o777
            except OSError:
                file_mode = DEFAULT_FILE_MODE
        os.chmod(tmp_name, file_mode)
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
