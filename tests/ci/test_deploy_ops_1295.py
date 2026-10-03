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


def _run_script(volume, out: Path):
    return subprocess.run(
        ["bash", str(SCRIPT), str(out)],
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


@docker
def test_a_volume_without_its_database_fails_the_deploy(volume, tmp_path):
    _create(volume)
    out = tmp_path / "b.db"
    r = _run_script(volume, out)
    assert r.returncode == 1
    assert "database missing" in r.stderr
    assert not out.exists() and not (tmp_path / "b.db.partial").exists()


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
