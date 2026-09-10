"""#1216 — the frontend image's audit gate must actually execute on the deploy path.

`web-ui/Dockerfile`'s `deps` stage runs `npm ci` then
`npm audit --audit-level=high`, and the gate's stated guarantee is that "an image
carrying a high advisory does not get built at all". `deploy.yml` builds that
image with `cache-from: type=gha`, and a BuildKit layer's cache key is its parent
layers plus the command string — neither of which changes when an advisory is
published upstream. So an unchanged `package-lock.json` makes the audit layer a
cache hit and the audit never runs: the deploy pushes an image carrying the
advisory and the gate reports nothing.

Note this is the *opposite* failure from #1210, where the gate fired and took both
deploys down. Same gate, both directions, because it had no execution guarantee of
its own.

These assertions pin that the deploy build re-runs the gate stage, and that the
daily cacheless check (#1213) that front-runs it has not quietly grown a cache.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / ".github" / "workflows" / "deploy.yml"
AUDIT = REPO / ".github" / "workflows" / "web-ui-audit.yml"

BUILD_JOBS = ("docker-build-staging", "docker-build-production")
FRONTEND_CONTEXT = "./web-ui"
# The Dockerfile stage carrying `npm ci` + the audit gate, per #1213's guard.
GATE_STAGE = "deps"


def _frontend_build_step(job: str) -> dict:
    steps = yaml.safe_load(DEPLOY.read_text())["jobs"][job]["steps"]
    for step in steps:
        with_ = step.get("with", {})
        if "build-push-action" in step.get("uses", "") and with_.get("context") == FRONTEND_CONTEXT:
            return with_
    raise AssertionError(f"{job} has no frontend build step (context {FRONTEND_CONTEXT!r})")


@pytest.mark.parametrize("job", BUILD_JOBS)
def test_the_deploy_build_cannot_serve_the_gate_stage_from_cache(job: str) -> None:
    with_ = _frontend_build_step(job)
    if "type=gha" not in str(with_.get("cache-from", "")):
        pytest.skip("frontend build no longer reads the GHA cache; nothing to bust")

    filters = [f.strip() for f in str(with_.get("no-cache-filters", "")).splitlines() if f.strip()]
    assert GATE_STAGE in filters, (
        f"{job}'s frontend build reads the GHA layer cache but does not exclude the "
        f"{GATE_STAGE!r} stage from it. An unchanged lockfile makes `npm audit` a cache "
        "hit, so a high advisory published since the last build ships unreported (#1216)."
    )


def test_the_scheduled_check_stays_cacheless() -> None:
    """#1213's daily run is the only other place the gate re-executes.

    It builds the stage on a fresh runner with no `--cache-from`. Give it one and
    both executions of the gate become cache hits at the same time.
    """
    runs = " ".join(
        line
        for job in yaml.safe_load(AUDIT.read_text())["jobs"].values()
        for step in job.get("steps", [])
        for line in step.get("run", "").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "docker build" in runs, "the scheduled check no longer builds the image stage (#1213)"
    assert "--cache-from" not in runs, (
        "the scheduled audit build has grown a cache, so it can hit the same stale "
        "`npm audit` layer the deploy path does — then neither place runs the gate (#1216)"
    )
