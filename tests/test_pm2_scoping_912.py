"""Staging pm2 operations never target `all` (#912).

Four independent staging paths ran `pm2 stop all` followed by `pm2 delete all`
and then restarted only `ecosystem.staging.config.js`. Staging and production
deploy to the **same host** — both `deploy.yml` jobs ssh to `secrets.HOST` and
drive pm2 — so an unattended staging health-check remediation stopped and
deleted the production backend and frontend, plus any unrelated app on the
shared VPS, and never restarted them. A silent production outage lasting until
the next production deploy.

Verified by hand against a real pm2 6.0.13 daemon:

    before:  codeframe-production-backend: online
             codeframe-staging-backend:    online
             codeframe-staging-frontend:   online

    pm2 stop/delete ecosystem.staging.config.js
    after:   codeframe-production-backend: online     # survives

    pm2 stop/delete all
    after:   nothing — production was deleted too
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[1]

#: `pm2 <verb> all` as an operational command. Matches the shell and systemd
#: forms; a line that merely *mentions* it inside a comment is excluded below.
_PM2_ALL = re.compile(r"pm2\s+(stop|delete|restart)\s+all\b")


def _operational_lines(path: Path) -> list[str]:
    """Lines that would actually run, ignoring comments."""
    offenders = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if _PM2_ALL.search(line):
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:  # a path outside the repo (the detector's own test)
                shown = path
            offenders.append(f"{shown}:{lineno}: {line}")
    return offenders


def _staging_files() -> list[Path]:
    files = sorted((REPO_ROOT / "scripts").glob("*.sh"))
    files += sorted((REPO_ROOT / "systemd").glob("*.service"))
    return [f for f in files if f.is_file()]


def test_no_staging_path_targets_every_pm2_process():
    """The acceptance criterion, made executable.

    `pm2 stop|delete all` on the shared VPS takes out production and every
    unrelated app. Scope to the ecosystem file, which pm2 accepts directly
    (`stop <id|name|namespace|all|json...>`), so there is no name list to drift.
    """
    offenders: list[str] = []
    for path in _staging_files():
        offenders.extend(_operational_lines(path))

    assert not offenders, "pm2 commands targeting `all`:\n" + "\n".join(offenders)


def test_the_scan_actually_reads_the_files():
    """Guards the test above from passing because it found nothing to check."""
    files = _staging_files()

    assert len(files) >= 3, f"expected the staging scripts, found {files}"
    assert any(f.name == "health-check.sh" for f in files)
    assert any(f.suffix == ".service" for f in files)


def test_the_detector_catches_the_original_form(tmp_path):
    """A regression guard is worthless if its pattern does not match the bug."""
    sample = tmp_path / "sample.sh"
    sample.write_text(
        "#!/usr/bin/env bash\n"
        "# pm2 delete all   <- a comment, not operational\n"
        "pm2 stop all 2>/dev/null || true\n"
        "pm2 delete all 2>/dev/null || true\n"
    )

    found = _operational_lines(sample)

    assert len(found) == 2, found
    assert all("pm2" in line for line in found)


def test_staging_stop_paths_name_the_ecosystem_file():
    """Not merely 'not all' — the stop must still target something."""
    stoppers = {
        "scripts/health-check.sh",
        "scripts/start-staging.sh",
        "scripts/deploy-staging.sh",
        "systemd/codeframe-staging.service",
    }
    for rel in stoppers:
        text = (REPO_ROOT / rel).read_text()
        if "pm2 stop" in text or "pm2 delete" in text:
            assert "ecosystem.staging.config.js" in text, (
                f"{rel} stops pm2 processes without naming the staging ecosystem"
            )
