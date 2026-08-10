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
