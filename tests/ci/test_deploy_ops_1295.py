"""#1295 — container deploy operations.

The pre-deploy backup copied `.codeframe/state.db`, which does not exist on a
container host (the live DB is /data/codeframe.db in a named volume), so it
skipped silently and reported success; staging had no backup at all. And the
deploy regenerated each env file from a fixed secret list without
CODEFRAME_BOOTSTRAP_TOKEN, erasing the token deploy/README.md tells operators to
set, so a fresh instance could not create its first account.

The docker cases run deploy/backup-db.sh for real against throwaway volumes.
"""

import shutil
import sqlite3
import subprocess
import uuid
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / ".github" / "workflows" / "deploy.yml"
SCRIPT = REPO / "deploy" / "backup-db.sh"
IMAGE = "python:3.12-alpine"


def _steps(job: str) -> list[dict]:
    return yaml.safe_load(DEPLOY.read_text())["jobs"][job]["steps"]


def _deploy_jobs() -> list[str]:
    jobs = yaml.safe_load(DEPLOY.read_text())["jobs"]
    return [j for j in jobs if j.startswith("deploy-")]


def test_there_are_two_deploy_jobs():
    assert sorted(_deploy_jobs()) == ["deploy-production", "deploy-staging"]


@pytest.mark.parametrize("job", ["deploy-staging", "deploy-production"])
def test_env_generator_carries_the_bootstrap_token(job):
    step = next(s for s in _steps(job) if s.get("name") == "Create environment file")
    assert step["env"]["ENV_BOOTSTRAP_TOKEN"] == "${{ secrets.CODEFRAME_BOOTSTRAP_TOKEN }}"
    assert "CODEFRAME_BOOTSTRAP_TOKEN=${ENV_BOOTSTRAP_TOKEN}" in step["run"]


@pytest.mark.parametrize("job", ["deploy-staging", "deploy-production"])
def test_every_deploy_backs_up_the_volume_db_before_deploying(job):
    names = [s.get("name") for s in _steps(job)]
    backup = names.index("Create pre-deployment backup")
    deploy = next(i for i, n in enumerate(names) if n and n.startswith("Deploy to"))
    assert backup < deploy
    run = _steps(job)[backup]["run"]
    assert "deploy/backup-db.sh" in run
    assert "cp .codeframe/state.db" not in run


# --- the script itself, against real volumes -----------------------------

docker = pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker")


def _docker(*args, check=True, **kw):
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True, **kw)


@pytest.fixture
def volume():
    name = f"cf-backup-test-{uuid.uuid4().hex[:10]}"
    yield name
    _docker("rm", "-f", f"{name}-writer", check=False)
    _docker("volume", "rm", "-f", name, check=False)


def _create(volume):
    _docker("volume", "create", volume)
    # Owned by the backend's uid, as compose leaves it.
    _docker("run", "--rm", "-v", f"{volume}:/data", IMAGE, "chown", "10001:10001", "/data")


def _run_script(volume, out: Path, state: Path | None = None):
    return subprocess.run(
        ["bash", str(SCRIPT), str(out), str(state or out.parent / "state")],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CODEFRAME_DATA_VOLUME": volume},
        capture_output=True,
        text=True,
    )


@docker
def test_no_volume_is_a_first_deploy_and_succeeds(volume, tmp_path):
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 0, r.stderr
    assert not out.exists()


def _make_db(volume, rows=3):
    _docker(
        "run", "--rm", "--user", "10001:10001", "-v", f"{volume}:/data", IMAGE, "python", "-c",
        "import sqlite3\n"
        "c = sqlite3.connect('/data/codeframe.db')\n"
        "c.execute('CREATE TABLE users (email TEXT)')\n"
        f"c.executemany('INSERT INTO users VALUES (?)', [('u',)] * {rows})\n"
        "c.commit()\n",
    )


@docker
def test_a_volume_never_given_a_database_is_still_a_first_deploy(volume, tmp_path):
    """A first deploy that crashed before creating the DB leaves an empty
    volume; that must not block the deploy that fixes the config (review)."""
    _create(volume)
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not out.exists() and not (tmp_path / "b.db.partial").exists()


@docker
def test_a_backup_records_that_this_host_has_a_database(volume, tmp_path):
    _create(volume)
    _make_db(volume)
    assert _run_script(volume, tmp_path / "b.db").returncode == 0
    assert (tmp_path / "state" / ".database-backed-up").exists()


@docker
def test_a_lost_database_on_a_host_that_had_one_fails_the_deploy(volume, tmp_path):
    _create(volume)
    _make_db(volume)
    assert _run_script(volume, tmp_path / "first.db").returncode == 0
    _docker("run", "--rm", "-v", f"{volume}:/data", IMAGE, "sh", "-c", "rm -f /data/codeframe.db*")
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 1
    assert "data loss" in r.stdout
    assert not out.exists() and not (tmp_path / "b.db.partial").exists()


@docker
def test_a_lost_volume_on_a_host_that_had_a_database_fails_the_deploy(volume, tmp_path):
    _create(volume)
    _make_db(volume)
    assert _run_script(volume, tmp_path / "first.db").returncode == 0
    _docker("volume", "rm", "-f", volume)
    r = _run_script(volume, tmp_path / "b.db")
    assert r.returncode == 1
    assert "data loss" in r.stdout


# --- the deploy steps as ssh runs them ------------------------------------


def _remote_script(job: str, project: Path) -> str:
    """The step's `ssh host "bash -s" << ENDSSH` body, as the runner hands it
    to the remote shell: secrets substituted, then the unquoted heredoc's
    client-side unescaping of \\$."""
    run = next(s for s in _steps(job) if s.get("name") == "Create pre-deployment backup")["run"]
    body = run.split("<< ENDSSH\n", 1)[1].rsplit("ENDSSH", 1)[0]
    body = body.replace("${{ secrets.PROJECT_PATH }}", str(project))
    assert "${{" not in body, "an unsubstituted expression would reach the shell"
    return body.replace("\\$", "$")


def _run_step(job: str, project: Path, volume: str):
    project.mkdir(exist_ok=True)
    shutil.copy(SCRIPT, project / "backup-db.sh")  # the step scp's it there
    return subprocess.run(
        ["bash", "-s"],
        input=_remote_script(job, project),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "CODEFRAME_DATA_VOLUME": volume},
        capture_output=True,
        text=True,
    )


@docker
def test_staging_step_lets_a_fresh_host_deploy(volume, tmp_path):
    """No volume, no backups yet: ls finds nothing and exits 2, which
    pipefail turned into a failed first deploy (codex)."""
    r = _run_step("deploy-staging", tmp_path / "proj", volume)
    assert r.returncode == 0, r.stdout + r.stderr


@docker
def test_staging_step_runs_to_completion_after_the_backup(volume, tmp_path):
    """`docker run -i` read the rest of the ssh heredoc as its stdin, so
    nothing after the backup ran and the step still exited 0 (review)."""
    _create(volume)
    _make_db(volume)
    project = tmp_path / "proj"
    r = _run_step("deploy-staging", project, volume)
    assert r.returncode == 0, r.stdout + r.stderr
    archives = list((project / "backups").glob("codeframe-*.db.gz"))
    assert len(archives) == 1, r.stdout + r.stderr  # gzip ran: lines after the backup executed


@docker
def test_production_step_archives_the_database(volume, tmp_path):
    import tarfile

    _create(volume)
    _make_db(volume, rows=7)
    project = tmp_path / "proj"
    r = _run_step("deploy-production", project, volume)
    assert r.returncode == 0, r.stdout + r.stderr
    archives = list((project / "backups").glob("backup-*.tar.gz"))
    assert len(archives) == 1, r.stdout + r.stderr
    with tarfile.open(archives[0]) as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("/codeframe.db"))
        tar.extract(member, tmp_path / "x", filter="data")
    db = tmp_path / "x" / member.name
    assert sqlite3.connect(db).execute("SELECT count(*) FROM users").fetchone()[0] == 7


@docker
def test_backup_includes_rows_still_in_the_wal_of_a_live_writer(volume, tmp_path):
    """A plain cp of the main file misses committed rows that are still in the
    -wal file; an online backup does not."""
    _create(volume)
    _docker(
        "run", "-d", "--name", f"{volume}-writer", "--user", "10001:10001",
        "-v", f"{volume}:/data", IMAGE, "python", "-c",
        "import sqlite3, time\n"
        "c = sqlite3.connect('/data/codeframe.db')\n"
        "c.execute('PRAGMA journal_mode=wal')\n"
        "c.execute('PRAGMA wal_autocheckpoint=0')\n"
        "c.execute('CREATE TABLE users (email TEXT)')\n"
        "c.executemany('INSERT INTO users VALUES (?)', [(f'u{i}',) for i in range(25)])\n"
        "c.commit()\n"
        "open('/data/ready', 'w').close()\n"
        "time.sleep(120)\n",
    )
    for _ in range(60):
        if _docker("run", "--rm", "-v", f"{volume}:/data", IMAGE, "test", "-f", "/data/ready", check=False).returncode == 0:
            break
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 0, r.stderr
    assert sqlite3.connect(out).execute("SELECT count(*) FROM users").fetchone()[0] == 25


@docker
def test_a_corrupt_database_fails_and_leaves_no_file(volume, tmp_path):
    _create(volume)
    _docker(
        "run", "--rm", "--user", "10001:10001", "-v", f"{volume}:/data", IMAGE,
        "sh", "-c", "head -c 8192 /dev/urandom > /data/codeframe.db",
    )
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 1
    assert not out.exists() and not (tmp_path / "b.db.partial").exists()


@docker
def test_a_database_with_corrupt_pages_fails_the_integrity_check(volume, tmp_path):
    """A valid header with damaged pages copies cleanly — only the check after
    the backup catches it, so a deploy does not proceed on a bad backup."""
    _create(volume)
    _docker(
        "run", "--rm", "--user", "10001:10001", "-v", f"{volume}:/data", IMAGE, "python", "-c",
        "import sqlite3\n"
        "c = sqlite3.connect('/data/codeframe.db')\n"
        "c.execute('CREATE TABLE t (x TEXT)')\n"
        "c.execute('CREATE INDEX ix ON t (x)')\n"
        "c.executemany('INSERT INTO t VALUES (?)', [('v' * 200,)] * 400)\n"
        "c.commit(); c.close()\n"
        "f = open('/data/codeframe.db', 'r+b'); f.seek(4096 * 3); f.write(b'\\xff' * 4096); f.close()\n",
    )
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 1
    assert "integrity_check" in r.stderr
    assert not out.exists()


def test_backups_are_never_readable_by_other_users_while_written():
    """Shared host: the 600 applied after the fact left the streaming partial
    file, and production's /tmp staging dir, readable meanwhile (codex)."""
    script = SCRIPT.read_text()
    assert script.index("umask 077") < script.index("docker run")
    run = next(s for s in _steps("deploy-production") if s.get("name") == "Create pre-deployment backup")["run"]
    assert "mkdir -m 700 \\${TMP_BACKUP}" in run


@docker
def test_a_truncated_database_on_a_host_that_had_one_fails_the_deploy(volume, tmp_path):
    """SQLite opens a zero-byte file as a valid empty database, so 'exists'
    was not 'still there': the backup succeeded over the loss (GLM)."""
    _create(volume)
    _make_db(volume)
    assert _run_script(volume, tmp_path / "first.db").returncode == 0
    _docker("run", "--rm", "--user", "10001:10001", "-v", f"{volume}:/data", IMAGE,
            "sh", "-c", "rm -f /data/codeframe.db-wal /data/codeframe.db-shm; : > /data/codeframe.db")
    r = _run_script(volume, tmp_path / "b.db")
    assert r.returncode == 1
    assert "data loss" in r.stdout


def test_the_production_archive_is_never_world_readable_while_written():
    """The tar.gz lands at the top of /tmp with the ssh shell's umask and was
    chmod 600 only after the mv (GLM)."""
    run = next(s for s in _steps("deploy-production") if s.get("name") == "Create pre-deployment backup")["run"]
    assert run.index("umask 077") < run.index("tar -czf")
