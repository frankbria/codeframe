"""#1160 — the deploy pipeline stamps the build SHA into the image and checks it.

`/health` reported `commit: "unknown"` on every container for a full release
cycle. The reader was fine; the *input* had gone. #1121 moved the deploy into
Docker, `.dockerignore` excludes `.git`, and the `except` branch turned the
missing git metadata into a plausible-looking string. Nothing failed.

So testing `server.py` alone would not have caught it, and will not catch the
next one. These pin the chain end to end: the Dockerfile declares the arg, the
build passes it, and the verify step refuses a container whose reported commit
is not the one just built — which is also what makes a pull that silently left
the old container running fail the deploy instead of passing it.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DEPLOY = ROOT / ".github" / "workflows" / "deploy.yml"

BUILD_JOBS = ("docker-build-staging", "docker-build-production")
DEPLOY_JOBS = ("deploy-staging", "deploy-production")


def _steps(job: str) -> list[dict]:
    return yaml.safe_load(DEPLOY.read_text())["jobs"][job]["steps"]


def _backend_build_step(job: str) -> dict:
    for step in _steps(job):
        if "build-push-action" in step.get("uses", "") and step.get("with", {}).get(
            "context"
        ) in (".", "./"):
            return step
    raise AssertionError(f"{job} has no backend docker build step")


def _verify_step(job: str) -> dict:
    for step in _steps(job):
        if step.get("name") == "Verify deployment":
            return step
    raise AssertionError(f"{job} has no 'Verify deployment' step")


def test_dockerfile_declares_and_persists_git_commit():
    """ARG alone is build-time only — it must survive into the container env."""
    body = DOCKERFILE.read_text()

    assert "ARG GIT_COMMIT" in body, "Dockerfile does not accept a GIT_COMMIT build arg"
    assert "ENV GIT_COMMIT=" in body, "GIT_COMMIT is not persisted as a runtime env var"


@pytest.mark.parametrize("job", BUILD_JOBS)
def test_backend_build_passes_the_commit_sha(job: str):
    build_args = _backend_build_step(job).get("with", {}).get("build-args", "")

    assert "GIT_COMMIT=${{ github.sha }}" in build_args, (
        f"{job} builds the backend image without stamping github.sha into it"
    )


@pytest.mark.parametrize("job", DEPLOY_JOBS)
def test_verify_step_compares_the_running_commit(job: str):
    """A 200 from /health only proves *a* backend is up, not the new one."""
    run = _verify_step(job)["run"]

    assert ".commit" in run, f"{job} verify step never reads the reported commit"
    assert "${{ github.sha }}" in run, (
        f"{job} verify step never compares the reported commit to the deployed SHA"
    )
