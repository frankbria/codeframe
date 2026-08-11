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


def test_the_shellcheck_suppression_is_gone():
    """#1130 cleared the 44 pre-existing findings, so the opt-out came out.

    It was never cosmetic: with it in place, an unquoted heredoc delimiter in
    deploy.yml let the runner command-substitute lines inside the ssh block
    that only looked like comments. Nothing but shellcheck catches that.
    """
    assert "-shellcheck=" not in TEST_WORKFLOW.read_text()


def test_the_job_fails_when_shellcheck_is_missing_rather_than_passing_vacuously():
    """actionlint SKIPS every shell finding when the binary is absent from
    PATH — it does not warn. Without this guard the gate would go quietly
    hollow the day the runner image drops shellcheck."""
    raw = TEST_WORKFLOW.read_text()

    assert "command -v shellcheck" in raw
    assert "::error::" in raw


def test_workflow_compilability_is_still_checked():
    """The suppression must not have disabled the thing the job exists for."""
    invocation = next(
        line for line in TEST_WORKFLOW.read_text().splitlines()
        if "./actionlint" in line
    )
    # Nothing on the invocation line may drop the expression/syntax pass, which
    # is what the job was created for. (Scoped to the invocation line —
    # `paths-ignore` appears elsewhere in this file.)
    assert "-ignore" not in invocation
    assert "-shellcheck=" not in invocation


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

    #: (workflow, job) pairs that reference a secret their environment does not
    #: supply AND guard against it. The bare exemption these replace was a
    #: promise nobody checked; #1143 turned it into a preflight step, so the
    #: entry is now conditional on that step still being there.
    #:
    #: `production` holds zero secrets while deploy-production references two
    #: dozen. Populating it is an operator decision; failing loudly first is not.
    GUARDED = {("deploy.yml", "deploy-production")}

    def _jobs(self, path: Path) -> dict:
        return (yaml.safe_load(path.read_text()) or {}).get("jobs", {}) or {}

    @staticmethod
    def _has_preflight(job: dict) -> bool:
        """A first step that refuses to continue when a secret is empty."""
        for step in job.get("steps", []):
            if "preflight" in step.get("name", "").lower() and "exit 1" in step.get(
                "run", ""
            ):
                return True
        return False

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
                    if (path.name, job_name) in self.GUARDED:
                        # Only exempt while the guard actually exists.
                        assert self._has_preflight(job), (
                            f"{path.name}:{job_name} is exempt because it "
                            "preflights its secrets — that step is now gone"
                        )
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

    def test_the_production_guard_runs_before_anything_uses_a_secret(self):
        """#1143: the preflight is only useful as the FIRST step. Behind the SSH
        setup it reports nothing the SSH failure had not already reported."""
        job = self._jobs(REPO_ROOT / ".github" / "workflows" / "deploy.yml")[
            "deploy-production"
        ]
        names = [s.get("name", "") for s in job["steps"]]

        assert "preflight" in names[0].lower(), names[:3]

    def test_the_production_guard_covers_every_secret_it_claims_to(self):
        """The failure mode this replaces was a missing secret resolving to an
        empty string in silence, so a guard that omits one is worse than none —
        it says "configured" while a blank AUTH_SECRET goes to the remote .env.
        """
        import re

        job = self._jobs(REPO_ROOT / ".github" / "workflows" / "deploy.yml")[
            "deploy-production"
        ]
        preflight = next(
            s for s in job["steps"] if "preflight" in s.get("name", "").lower()
        )
        checked = set(re.findall(r"[A-Z0-9_]{3,}", preflight["run"]))

        # Every secret the step wires into its own env must be in the list it
        # iterates — otherwise it is declared and never looked at.
        for name in preflight.get("env", {}):
            assert name in checked, f"{name} is passed to the guard but never checked"

    def test_the_production_environment_has_no_fictional_url(self):
        """It pointed at codeframe.example.com, which the GitHub deployments
        page renders as a live link to a target that does not exist (#1143)."""
        job = self._jobs(REPO_ROOT / ".github" / "workflows" / "deploy.yml")[
            "deploy-production"
        ]
        environment = job.get("environment")

        url = environment.get("url", "") if isinstance(environment, dict) else ""
        assert "example.com" not in url, url

    def test_the_release_build_job_can_see_the_key_it_requires(self):
        """Specific to the guard: it sets MODEL_GUARD_REQUIRE_LIVE, so an empty
        secret is a hard failure rather than a skipped check."""
        release = REPO_ROOT / ".github" / "workflows" / "release.yml"
        build = self._jobs(release)["build"]

        raw = yaml.safe_dump(build)
        assert "MODEL_GUARD_REQUIRE_LIVE" in raw
        assert build.get("environment") == "staging"
