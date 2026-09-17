"""#1189 — claude-review skips bot PRs instead of failing on them.

GitHub withholds regular `secrets.*` from `pull_request` runs on Dependabot PRs
(they live in the separate Dependabot secrets scope), so the #1011 credential
preflight — correct on a human PR — flagged a permanent, unfixable condition as
a failure on every dependency bump. A check that is always red and never
blocking trains everyone to ignore the check column.

Both halves matter, so both are pinned here: the gate must be present, and the
preflight it protects must NOT have been deleted to achieve it.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "claude-code-review.yml"
)


def _review_job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["claude-review"]


def test_bot_authored_and_bot_pushed_prs_are_gated_out():
    """`github.actor` alone is too narrow — it is the pusher on `synchronize`.

    That is the mistake #1167 fixed in glm-review.yml; this workflow uses the
    same condition so the two reviewers cannot drift apart.
    """
    condition = _review_job()["if"]
    assert "github.event.pull_request.user.type == 'User'" in condition
    assert "github.event.sender.type == 'User'" in condition


def test_the_dead_dependabot_opt_in_is_gone():
    """`allowed_bots` opted in PRs that can never authenticate."""
    assert "allowed_bots" not in WORKFLOW.read_text()


def test_the_credential_preflight_still_fails_loudly():
    """A human PR with a rotated secret must still go red (#1011 AC3)."""
    preflight = next(
        step
        for step in _review_job()["steps"]
        if step["name"] == "Verify the review credential is present"
    )
    assert "CLAUDE_CODE_OAUTH_TOKEN" in preflight["env"]["OAUTH_TOKEN"]
    assert "exit 1" in preflight["run"]


def test_fork_prs_are_gated_out():
    """#1221: `secrets.*` are withheld from `pull_request` runs on fork PRs for
    the same structural reason as on Dependabot PRs, so a human fork PR passed
    the #1189 gate and then failed the preflight with a misdiagnosis ("unset
    or rotated"). Same-repo head only; a fork PR skips, like a bot PR does.
    """
    condition = _review_job()["if"]
    assert "github.event.pull_request.head.repo.full_name == github.repository" in condition


def test_the_fork_rationale_is_recorded_next_to_the_bot_one():
    text = WORKFLOW.read_text()
    assert "#1221" in text and "fork" in text.lower()
