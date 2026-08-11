"""#1122 — the workflow-lint gate must stay wired in.

An uncompilable workflow produces a run with zero jobs and no logs, so it reads
as background noise rather than an outage. `deploy.yml` failed that way on every
push to main for a week, and `claude-review` (#1011) before it.

The `workflow-lint` job closes that hole, but only while it is actually reachable
and actually gates the summary — the CLAUDE.md rule about disabled gates exists
because that wiring has been quietly lost before. These tests pin it.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(TEST_WORKFLOW.read_text())


def test_the_workflow_lint_job_exists(workflow):
    assert "workflow-lint" in workflow["jobs"]


def test_it_is_a_dependency_of_test_summary(workflow):
    """Otherwise it can pass/fail without affecting the merge gate."""
    assert "workflow-lint" in workflow["jobs"]["test-summary"]["needs"]


def test_test_summary_actually_fails_on_it(workflow):
    """Being in `needs` is not enough — the summary's own check must name it.

    `if: always()` means test-summary runs regardless, so the exit-1 branch is
    what makes the gate real.
    """
    steps = workflow["jobs"]["test-summary"]["steps"]
    script = "\n".join(s.get("run", "") for s in steps)
    # Must be the exit-1 condition, not merely the summary table row — the table
    # also interpolates the result, so a looser check passes while the gate is
    # gone. (Caught by deliberately removing the condition and re-running.)
    assert '[ "${{ needs.workflow-lint.result }}" == "failure" ]' in script


def test_it_is_not_paths_filtered(workflow):
    """A skipped required check is the same silence this job removes.

    actionlint takes about a second, so running it on every PR costs nothing
    and avoids a gate that reports "skipped" exactly when a workflow changed.
    """
    job = workflow["jobs"]["workflow-lint"]
    assert "if" not in job, "workflow-lint must not be conditionally skipped"


def test_actionlint_is_pinned_with_a_checksum():
    """This job's purpose is stopping unverifiable CI config from landing."""
    raw = TEST_WORKFLOW.read_text()
    assert "ACTIONLINT_VERSION" in raw
    assert "ACTIONLINT_SHA256" in raw
    assert "sha256sum -c -" in raw


def test_every_workflow_file_still_parses():
    """A cheap local backstop; actionlint in CI is the real check."""
    for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict), f"{path.name} did not parse to a mapping"
        assert "jobs" in data, f"{path.name} declares no jobs"


def test_the_shellcheck_suppression_is_documented_and_tracked():
    """`-shellcheck=` is a deliberate scope limit, not a silent one (#1130).

    actionlint runs shellcheck whenever it is on PATH — which it is on GitHub
    runners but often not locally, so this class of check disappears without
    warning depending on where you run it. If the suppression is ever removed,
    this test should be deleted along with it; if it stays, it stays explained.
    """
    raw = TEST_WORKFLOW.read_text()
    assert "-shellcheck=" in raw
    assert "#1130" in raw, "the suppression must point at its follow-up issue"


def test_workflow_compilability_is_still_checked():
    """The suppression must not have disabled the thing the job exists for."""
    invocation = next(
        line for line in TEST_WORKFLOW.read_text().splitlines()
        if "./actionlint" in line
    )
    # -shellcheck= narrows the checks; it must not be paired with anything that
    # would also drop the expression/syntax pass. (Scoped to the invocation
    # line — `paths-ignore` appears elsewhere in this file.)
    assert "-ignore" not in invocation
    assert "-shellcheck=" in invocation


class TestEnvironmentSecretsAreReachable:
    """A job using an environment secret must declare that environment.

    GitHub exposes environment secrets ONLY to jobs with a matching
    `environment:` key. A job that references one without declaring it gets an
    empty string — silently, with no warning from actionlint, which cannot know
    where a secret lives.

    That is not hypothetical: release.yml's build job referenced
    ANTHROPIC_API_KEY without declaring `environment: staging`, so the
    model-default guard's MODEL_GUARD_REQUIRE_LIVE=1 would have failed every
    release. Caught by inspecting the repo's actual secrets, not by CI.
    """

    #: Secrets that live in an environment rather than at repo level. Keeping
    #: the list here means adding one to a job without its environment fails.
    ENVIRONMENT_SECRETS = {"ANTHROPIC_API_KEY": "staging"}

    #: (workflow, job) pairs knowingly referencing a secret their environment
    #: does not supply. Exempted with a pointer, not silenced: the `production`
    #: environment holds zero secrets, so deploy-production cannot work at all —
    #: tracked in #1143, which is an operator decision (populate it, or delete
    #: the job), not something a code change can fix.
    KNOWN_GAPS = {("deploy.yml", "deploy-production")}

    def _jobs(self, path: Path) -> dict:
        return (yaml.safe_load(path.read_text()) or {}).get("jobs", {}) or {}

    def test_every_job_using_an_environment_secret_declares_it(self):
        offenders: list[str] = []

        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
            raw_jobs = self._jobs(path)
            for job_name, job in raw_jobs.items():
                if not isinstance(job, dict):
                    continue
                body = yaml.safe_dump(job)
                for secret, environment in self.ENVIRONMENT_SECRETS.items():
                    if f"secrets.{secret}" not in body:
                        continue
                    declared = job.get("environment")
                    if isinstance(declared, dict):
                        declared = declared.get("name")
                    if (path.name, job_name) in self.KNOWN_GAPS:
                        continue
                    if declared != environment:
                        offenders.append(
                            f"{path.name}:{job_name} uses secrets.{secret} but "
                            f"declares environment={declared!r}, not {environment!r}"
                        )

        assert offenders == [], (
            "these jobs will receive an empty secret at runtime:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_release_build_job_can_see_the_key_it_requires(self):
        """Specific to the guard: it sets MODEL_GUARD_REQUIRE_LIVE, so an empty
        secret is a hard failure rather than a skipped check."""
        release = REPO_ROOT / ".github" / "workflows" / "release.yml"
        build = self._jobs(release)["build"]

        raw = yaml.safe_dump(build)
        assert "MODEL_GUARD_REQUIRE_LIVE" in raw
        assert build.get("environment") == "staging"
