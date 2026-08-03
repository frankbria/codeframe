"""The claude-review job failed on every PR for want of one permission (#1011).

It died ~15 seconds in with

    Could not fetch an OIDC token. Did you remember to add `id-token: write`
    to your workflow permissions?

on every PR regardless of content — reproduced identically on two unrelated PRs
opened minutes apart. The action exchanges a GitHub OIDC token for the
installation token it posts with, and the job's `permissions:` block granted
only reads.

Because it is not a required status check it never blocked a merge, which is the
actual damage: the repo silently lost one of its two bot reviewers behind a red X
everyone learned to ignore.

These tests pin the permission and the two diagnostics that make a
configuration failure distinguishable from a review that found nothing.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "claude-code-review.yml"


@pytest.fixture(scope="module")
def job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["claude-review"]


def _step(job: dict, name: str) -> dict:
    for step in job["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r}")


class TestOidcIsAvailableToTheJob:
    """AC2. The error message names the fix; the log confirms the credential
    itself was present (`CLAUDE_CODE_OAUTH_TOKEN: ***`), which rules out the
    other candidate cause."""

    def test_the_job_can_mint_an_oidc_token(self, job):
        assert job["permissions"].get("id-token") == "write", (
            "without id-token: write the action cannot fetch an OIDC token and "
            "the job fails ~15s in on every PR"
        )

    def test_nothing_else_was_widened_to_get_there(self, job):
        """A review bot needs no write access to the repository. Granting
        `contents: write` to fix an auth error would be a much worse trade."""
        perms = job["permissions"]

        assert perms["contents"] == "read"
        assert perms["pull-requests"] == "read"
        assert perms["issues"] == "read"

    def test_the_action_is_still_sha_pinned(self, job):
        """The version is immutable, which is how the issue ruled out an action
        change and left the permissions block as the cause."""
        uses = _step(job, "Run Claude Code Review")["uses"]

        ref = uses.split("@", 1)[1]
        assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), (
            f"the action is pinned to {ref!r}, not an immutable SHA"
        )


class TestAConfigurationFailureIsDistinguishable:
    """AC3. A red X that means "the secret expired" and a red X that means
    "the reviewer disliked your code" must not look the same."""

    def test_a_missing_credential_is_caught_before_the_action_runs(self, job):
        step = _step(job, "Verify the review credential is present")

        assert "CLAUDE_CODE_OAUTH_TOKEN" in yaml.safe_dump(step["env"])
        assert "exit 1" in step["run"]

    def test_it_says_the_failure_is_not_about_the_pr(self, job):
        step = _step(job, "Verify the review credential is present")

        assert "not a finding about this PR" in step["run"]

    def test_the_preflight_runs_before_the_review(self, job):
        names = [s.get("name") for s in job["steps"]]

        assert names.index("Verify the review credential is present") < names.index(
            "Run Claude Code Review"
        )

    def test_the_preflight_is_unconditional(self, job):
        """The review steps are gated on PR size. The credential check must not
        be, or a small PR would report success having checked nothing."""
        step = _step(job, "Verify the review credential is present")

        assert "if" not in step

    def test_a_failed_review_explains_itself(self, job):
        step = _step(job, "Explain a failed review")

        assert "GITHUB_STEP_SUMMARY" in step["run"]
        assert "not a review finding" in step["run"]

    def test_the_explainer_only_fires_on_a_real_review_failure(self, job):
        """`if: failure()` alone would also fire when the preflight failed,
        printing the wrong diagnosis for the case it already explained."""
        condition = _step(job, "Explain a failed review")["if"]

        assert "failure()" in condition
        assert "steps.claude-review.outcome == 'failure'" in condition

    def test_the_review_step_has_the_id_that_condition_references(self, job):
        assert _step(job, "Run Claude Code Review")["id"] == "claude-review"


class TestTheJobStillTriggersOnCodeChanges:
    """Guard on the premise: none of the above matters if the job stops running.
    `paths-ignore` covers `.github/**`, so a workflow-only PR does not trigger
    it — this PR carries this test file precisely so the fix is exercised."""

    @pytest.fixture(scope="class")
    def workflow(self) -> dict:
        # `on:` parses as the boolean True under YAML 1.1.
        parsed = yaml.safe_load(WORKFLOW.read_text())
        return parsed.get("on", parsed.get(True))

    def test_it_runs_on_pull_requests(self, workflow):
        assert set(workflow["pull_request"]["types"]) == {"opened", "synchronize"}

    def test_python_and_typescript_changes_are_not_ignored(self, workflow):
        ignored = workflow["pull_request"]["paths-ignore"]

        assert not any(pattern.endswith((".py", ".ts", ".tsx")) for pattern in ignored)

    def test_workflow_only_changes_are_ignored(self, workflow):
        """Which is why this file exists — so the fix gets a real run."""
        assert ".github/**" in workflow["pull_request"]["paths-ignore"]
