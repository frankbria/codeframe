"""No staging path takes out unrelated apps on the shared VPS (#912, #1121).

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

#: The same invariant after #1121 replaced PM2 with compose. Docker's blunt
#: instruments are host-wide by construction: a prune or a `$(docker ps -q)`
#: expansion hits every container on the box, which on this shared VPS means
#: autoauthor, narrative and podcastfy. Compose scoped to the project's own
#: files is fine; these are not.
_DOCKER_HOST_WIDE = re.compile(
    r"docker\s+(system|container|image|volume)\s+prune"
    r"|docker\s+(stop|rm|kill)\s+.*\$\(\s*docker\s+ps"
)


def _operational_lines(path: Path) -> list[str]:
    """Lines that would actually run, ignoring comments."""
    offenders = []
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if _PM2_ALL.search(line) or _DOCKER_HOST_WIDE.search(line):
            try:
                shown = path.relative_to(REPO_ROOT)
            except ValueError:  # a path outside the repo (the detector's own test)
                shown = path
            offenders.append(f"{shown}:{lineno}: {line}")
    return offenders


def _staging_files() -> list[Path]:
    files = sorted((REPO_ROOT / "scripts").glob("*.sh"))
    files += sorted((REPO_ROOT / "systemd").glob("*.service"))
    files += sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    files += [
        REPO_ROOT / name
        for name in (
            "docker-compose.yml",
            "docker-compose.staging.yml",
            "docker-compose.production.yml",
        )
    ]
    return [f for f in files if f.is_file()]


def test_no_staging_path_targets_every_process_on_the_box():
    """The acceptance criterion, made executable — and carried across #1121.

    `pm2 stop|delete all` on the shared VPS took out production and every
    unrelated app. Containers do not remove the hazard, they rename it: a
    `docker system prune` or `docker stop $(docker ps -q)` is the same blunt
    instrument. Compose scoped to this project's own files is safe; anything
    host-wide is not.
    """
    offenders: list[str] = []
    for path in _staging_files():
        offenders.extend(_operational_lines(path))

    assert not offenders, (
        "commands that would hit unrelated apps on the shared VPS:\n"
        + "\n".join(offenders)
    )


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


def test_every_stop_path_names_what_it_stops():
    """Not merely 'not all' — a stop must still target something specific.

    #1121 deleted the PM2-only scripts and the ecosystem files they named, so
    this now checks whatever survives: a remaining `pm2 stop` must name the
    ecosystem file, and a `docker compose down` must carry the -f flags that
    scope it to this project. An unscoped `docker compose down` in the wrong
    directory is the modern `pm2 delete all`.
    """
    for path in _staging_files():
        text = path.read_text()
        rel = path.relative_to(REPO_ROOT)

        if "pm2 stop" in text or "pm2 delete" in text:
            assert "ecosystem" in text, f"{rel}: pm2 stop without naming a target"

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "compose down" not in stripped:
                continue
            assert "-f " in stripped or "$COMPOSE" in stripped, (
                f"{rel}: `{stripped}` is not scoped to this project's compose "
                "files — in the wrong cwd it stops whatever it finds"
            )
