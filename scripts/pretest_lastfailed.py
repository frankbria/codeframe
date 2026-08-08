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
import re
import subprocess
import sys
from pathlib import Path

CACHE_RELATIVE = Path(".pytest_cache") / "v" / "cache" / "lastfailed"

#: pytest banners a collection failure as "ERROR collecting <path>".
_COLLECT_ERROR = re.compile(r"ERROR collecting (\S+)")

#: pytest reports the count either as the padded summary rule
#: "===== 2 tests collected in 0.06s =====" or, at higher verbosity, as
#: "collected 2 items" near the top. Deliberately not anchored to the line
#: start — the summary is surrounded by "=" padding.
_COLLECTED_COUNT = re.compile(r"(\d+) tests? collected|collected (\d+) items?")


class CollectFormatError(RuntimeError):
    """pytest collected tests in a shape this script could not parse."""


def _collected_something(stdout: str) -> bool:
    for match in _COLLECTED_COUNT.finditer(stdout):
        count = match.group(1) or match.group(2)
        if count and int(count) > 0:
            return True
    return False


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


def collectible(root: Path, files: list[str]) -> tuple[set[str], set[str]]:
    """Inspect *files*, returning (node IDs that resolve, files that error).

    Deliberately scoped to the files named in the cache — a handful — so this
    can never become the full-suite collection it exists to prevent.

    The two return values are different things and must not be conflated. A
    node ID that simply stopped resolving is *stale*: the test was renamed, and
    there is nothing to run. A file that raises during collection is *broken*:
    you just made it un-importable, which is exactly what a pre-commit hook
    should catch. Pruning the second along with the first would let the hook
    pass on the change it exists to stop.
    """
    if not files:
        return set(), set()

    result = subprocess.run(
        # `-o addopts=` is load-bearing, not tidiness. Verbosity is a single
        # counter: this repo's pytest.ini starts addopts with `-v`, so ini -v
        # plus our -q nets to DEFAULT verbosity, and --collect-only then prints
        # an indented <Module>/<Function> tree with no "::" on any line. Every
        # node ID would parse as unresolvable and the hook would silently
        # select nothing, forever. Clearing addopts also drops -m filters and
        # coverage flags, none of which belong in a collection probe.
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--no-header", "-p", "no:cacheprovider", "-o", "addopts=", *files],
        cwd=root,
        capture_output=True,
        text=True,
    )

    resolved = {
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.lstrip().startswith(("ERROR", "E "))
    }
    errored = set(_COLLECT_ERROR.findall(result.stdout))

    # Not `and not errored`: a broken file coexisting with a healthy one still
    # populates `errored` (that regex is verbosity-independent) while `resolved`
    # stays empty, which would slip past the guard and prune the healthy file's
    # live failure as stale.
    if not resolved and _collected_something(result.stdout):
        # pytest found tests but we could not read them — a format we do not
        # understand. Do not silently conclude "everything is stale": say so
        # and let the caller fall back to running the files themselves.
        raise CollectFormatError(result.stdout[-400:])

    return resolved, errored


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

    try:
        resolvable, errored = collectible(root, live_files)
    except CollectFormatError as exc:
        # Bounded and loud: run the cached files rather than guess. Still only
        # the handful named in the cache, never the whole suite.
        print(
            "pretest_lastfailed: could not parse pytest collection output; "
            f"falling back to running {len(live_files)} cached file(s).\n{exc}",
            file=sys.stderr,
        )
        return live_files

    surviving: list[str] = []
    for node_id in recorded:
        file_part = _file_of(node_id)
        if file_part in errored:
            # Broken, not stale — run the file so pytest re-raises the error
            # and the commit is blocked. Once, however many of its node IDs
            # are in the cache.
            if file_part not in surviving:
                surviving.append(file_part)
        elif "::" in node_id:
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

    # Two invocations, node IDs first. A single `pytest -x broken.py
    # live.py::test_x` aborts the whole session on the collection error before
    # running anything, so the failure you came to see never reports — you get
    # "1 error during collection" and debug the wrong thing. Running the
    # resolvable node IDs first means the expected failure is what you see.
    #
    # -x applies ACROSS the groups, not just within them: if a live test fails
    # we stop and never reach the broken file. That is the fail-fast contract,
    # not an oversight — the broken neighbour surfaces on the next attempt,
    # once the thing you were just shown is fixed. Either group blocks the
    # commit on its own.
    node_ids = [item for item in selection if "::" in item]
    whole_files = [item for item in selection if "::" not in item]

    for group in (node_ids, whole_files):
        if not group:
            continue
        code = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "--no-header", *group],
            cwd=root,
        ).returncode
        # 5 == "no tests collected", the deselect-all no-op; not a failure.
        if code not in (0, 5):
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
