#!/usr/bin/env python3
"""Is a package-lock.json change surgical enough to merge without a human? (#1217)

Compares a base and a head ``package-lock.json`` (lockfileVersion 3) and exits 0
only when every property that made #1212's Dependabot lock diff safe holds:

- the set of packages is identical — nothing added, nothing removed;
- no entry newly declares an install script (``hasInstallScript``);
- every changed entry still resolves to ``https://registry.npmjs.org/`` and
  carries an ``integrity`` hash;
- every version change is patch-level (same major.minor).

Anything else exits 1 and prints why, one reason per line. The semver label on
the PR is not consulted: this checks the bytes that will be installed.

Usage: lock_diff_is_surgical.py BASE_LOCK HEAD_LOCK
"""

import json
import sys
from pathlib import Path

REGISTRY = "https://registry.npmjs.org/"


def _packages(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("lockfileVersion") != 3:
        sys.exit(f"{path}: expected lockfileVersion 3, got {data.get('lockfileVersion')!r}")
    return {k: v for k, v in data["packages"].items() if k}  # "" is the root project


def _major_minor(version: str) -> tuple[str, str] | None:
    parts = version.split(".")
    return (parts[0], parts[1]) if len(parts) >= 3 else None


def reasons_not_surgical(base: dict, head: dict) -> tuple[list[str], list[str]]:
    """``(reasons, changes)`` — refuse when ``reasons`` is non-empty."""
    reasons: list[str] = []
    changes: list[str] = []

    for key in sorted(set(head) - set(base)):
        reasons.append(f"package added: {key}")
    for key in sorted(set(base) - set(head)):
        reasons.append(f"package removed: {key}")

    for key in sorted(set(base) & set(head)):
        before, after = base[key], head[key]
        if before == after:
            continue
        name = key.rsplit("node_modules/", 1)[-1]
        changes.append(f"{name} {before.get('version')} -> {after.get('version')}")

        if after.get("hasInstallScript") and not before.get("hasInstallScript"):
            reasons.append(f"{key}: gains an install script")
        resolved = after.get("resolved", "")
        if not resolved.startswith(REGISTRY):
            reasons.append(f"{key}: resolved is not on {REGISTRY}: {resolved!r}")
        if not after.get("integrity"):
            reasons.append(f"{key}: no integrity hash")
        old, new = _major_minor(str(before.get("version"))), _major_minor(str(after.get("version")))
        if before.get("version") != after.get("version") and (old is None or old != new):
            reasons.append(
                f"{key}: {before.get('version')} -> {after.get('version')} is not patch-level"
            )

    if not changes and not reasons:
        reasons.append("no package changed — nothing to merge")
    return reasons, changes


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    base, head = _packages(Path(argv[1])), _packages(Path(argv[2]))
    reasons, changes = reasons_not_surgical(base, head)
    for line in changes:
        print(f"changed: {line}")
    for line in reasons:
        print(f"REFUSED: {line}")
    if reasons:
        return 1
    print(f"surgical: {len(changes)} package(s) patch-bumped, nothing added or removed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
