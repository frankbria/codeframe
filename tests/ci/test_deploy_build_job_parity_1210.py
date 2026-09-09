"""#1210 — the two image-build jobs must stay equivalent apart from their tag.

`docker-build-staging` and `docker-build-production` build the same two
contexts from the same Dockerfiles. That equivalence is load-bearing: production
has never been deployed (it holds no secrets and has no host, so
`deploy-production` stops at its preflight), which means the *only* evidence
production's images are sound is that staging builds the identical thing.

#1210 leaned on exactly that. A high advisory failed the frontend image's
`npm audit --audit-level=high` and blocked every deploy; the fix was verified
against staging, and applies to production solely because the two jobs are the
same build. Nothing enforced that. Edit one job and not the other — bump a
pin, add a build-arg, change the context — and the inference silently stops
holding, with no signal until production's first real deploy.

The parity check compares the jobs' entire step lists rather than enumerating
fields or singling out the build steps. Anything that changes what gets built
lives in there: the `build-push-action` invocations, but equally the
`setup-buildx-action` pin above them, and any field or step that does not exist
yet.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

DEPLOY = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"

STAGING = "docker-build-staging"
PRODUCTION = "docker-build-production"

# (label, build context as written in the workflow)
IMAGES = (("backend", "."), ("frontend", "./web-ui"))


def _steps(job: str) -> list[dict]:
    return yaml.safe_load(DEPLOY.read_text())["jobs"][job]["steps"]


def _normalised_steps(job: str, environment: str) -> str:
    """The job's steps, serialised, with its own moving tag neutralised.

    Each side rewrites only its own environment token, which is what keeps a
    cross-tagged job (production pushing `:staging`) detectable instead of
    cancelling out.
    """
    return yaml.safe_dump(_steps(job), sort_keys=True).replace(f":{environment}", ":<env>")


def _build_step(job: str, context: str) -> dict:
    for step in _steps(job):
        if "build-push-action" in step.get("uses", ""):
            if step.get("with", {}).get("context") == context:
                return step
    raise AssertionError(f"{job} has no docker build step for context {context!r}")


def test_staging_and_production_run_the_same_build_steps() -> None:
    assert _normalised_steps(STAGING, "staging") == _normalised_steps(PRODUCTION, "production"), (
        "The staging and production image builds have drifted apart. Production "
        "has no deploy target, so staging is the only place these images are "
        "ever exercised — keep the two jobs' steps identical apart from the "
        "environment tag, or that evidence stops transferring (#1210)."
    )


@pytest.mark.parametrize(("label", "context"), IMAGES)
def test_each_job_pushes_its_own_moving_tag(label: str, context: str) -> None:
    """The failure the parity check alone would report confusingly: a
    copy-paste that leaves production tagging `:staging`, so a production
    deploy pulls staging's image.
    """
    for job, environment, wrong in (
        (STAGING, "staging", "production"),
        (PRODUCTION, "production", "staging"),
    ):
        tags = _build_step(job, context)["with"]["tags"]
        assert f":{environment}" in tags, f"{job} does not tag {label} :{environment}"
        assert f":{wrong}" not in tags, f"{job} tags {label} :{wrong}"
