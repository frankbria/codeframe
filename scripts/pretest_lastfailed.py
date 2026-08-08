#!/usr/bin/env python3
"""Re-run previously-failed tests, without ever expanding to the full suite.

``pytest --lf --lfnf none`` looks like it covers this, but ``--lfnf none``
guards only the *empty* cache. When ``lastfailed`` is non-empty and its node IDs
no longer resolve — a test that was renamed, moved or deleted — pytest falls
back to its documented behaviour of running **everything** (issue #984).

That made the pre-commit hook self-triggering in the most ordinary workflow:
rename a test, and because the old name is still in the cache from the run where
it failed, the very next commit runs the whole suite. With the pre-#979 suite
that was hours, and the hook carries ``-x``, so it also aborted the commit on the
first unrelated failure it happened to hit.

So the selection is computed here instead: drop node IDs that can no longer be
collected, and run only what is left. A cache full of stale entries selects
nothing, which is what ``--lfnf none`` promised in the first place.

Usage:
    pretest_lastfailed.py                  # run the surviving failures
    pretest_lastfailed.py --print-selection # print them, run nothing
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CACHE_RELATIVE = Path(".pytest_cache") / "v" / "cache" / "lastfailed"


def read_lastfailed(root: Path) -> list[str]:
    """Node IDs pytest recorded as failing, or [] if there is nothing usable.

    Fails safe: an unreadable or malformed cache yields no selection. The one
    outcome this must never produce is "I could not tell, so run everything".
    """
    path = root / CACHE_RELATIVE
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    return [key for key in data if isinstance(key, str) and key]


def _file_of(node_id: str) -> str:
    """The file part of a node ID (the whole thing for a collection-error key)."""
    return node_id.split("::", 1)[0]


def collectible(root: Path, files: list[str]) -> set[str]:
    """Node IDs that still resolve, collected from *files* only.

    Deliberately scoped to the files named in the cache — a handful — so this
    can never become the full-suite collection it exists to prevent.
    """
    if not files:
        return set()

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--no-header", "-p", "no:cacheprovider", *files],
        cwd=root,
        capture_output=True,
        text=True,
    )
    # Collection errors are fine: whatever did collect is still trustworthy,
    # and anything that did not is exactly what we mean to drop.
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith(("ERROR", "E "))
    }


def select(root: Path) -> list[str]:
    """The node IDs the hook should run: previously failed AND still present."""
    recorded = read_lastfailed(root)
    if not recorded:
        return []

    live_files = sorted({
        f for f in (_file_of(n) for n in recorded) if (root / f).exists()
    })
    if not live_files:
        return []

    resolvable = collectible(root, live_files)

    surviving = []
    for node_id in recorded:
        if "::" in node_id:
            if node_id in resolvable:
                surviving.append(node_id)
        elif (root / node_id).exists():
            # A whole-file key comes from a collection error; the file existing
            # is the most we can check, and re-running it is the point.
            surviving.append(node_id)
    return surviving


def main(argv: list[str]) -> int:
    root = Path.cwd()
    selection = select(root)

    if "--print-selection" in argv:
        print("\n".join(selection))
        return 0

    if not selection:
        return 0

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "--no-header", *selection],
        cwd=root,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
