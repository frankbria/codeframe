"""#1239 — a red scheduled run must produce a signal outside the Actions tab.

`e2e-browser-full` in `test.yml` is `schedule`/`workflow_dispatch`-only and
`test-summary` deliberately does not need it, so nothing gates a merge on it. It
failed 40 nights in a row (2026-08-09 → 2026-09-17) before anyone looked (#1236).
The daily `Web UI Audit` had the same blind spot by design (#1213).

Both workflows now end a red scheduled run by calling the shared
`scheduled-failure-issue.yml`, which opens one issue per workflow or comments on
the existing open one. These assertions pin the shape that makes it worth
having: the job exists, it fires only on a failed *scheduled* run, it calls the
shared workflow with the scope that workflow needs, and the shared workflow
looks before it creates.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SHARED = "scheduled-failure-issue.yml"
JOB = "report-scheduled-failure"
CALLERS = {
    "test.yml": ["test-summary", "e2e-browser-full", "e2e-backend-tests"],
    "web-ui-audit.yml": ["npm-audit"],
}


def _jobs(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())["jobs"]


@pytest.mark.parametrize("caller", CALLERS)
def test_the_reporting_job_exists_and_fires_only_on_a_failed_scheduled_run(caller: str):
    job = _jobs(caller).get(JOB)
    assert job, f"{caller} has no {JOB!r} job: a red scheduled run is invisible again (#1239)"
    condition = job.get("if", "")
    assert "failure()" in condition, f"{caller}:{JOB} is not gated on failure()"
    assert (
        "github.event_name == 'schedule'" in condition
    ), f"{caller}:{JOB} is not gated on the schedule event, so it would fire on push/PR"
    for other in ("push", "pull_request", "workflow_dispatch"):
        assert f"'{other}'" not in condition, f"{caller}:{JOB} also fires on {other}"
    assert (
        job.get("uses") == f"./.github/workflows/{SHARED}"
    ), f"{caller}:{JOB} does not call the shared {SHARED}; two copies drift"


@pytest.mark.parametrize("caller,terminal_jobs", CALLERS.items())
def test_it_needs_every_job_that_ends_a_scheduled_run(caller: str, terminal_jobs: list):
    """`failure()` only sees jobs in `needs`; a nightly-only job left out fails silently."""
    needs = _jobs(caller)[JOB].get("needs", [])
    missing = set(terminal_jobs) - set(needs)
    assert (
        not missing
    ), f"{caller}:{JOB} does not need {sorted(missing)}, so their failure is invisible"


@pytest.mark.parametrize("caller", CALLERS)
def test_the_caller_grants_the_scope_the_shared_workflow_declares(caller: str):
    """A caller granting less than the callee declares is a startup_failure with no log
    (see check-workflow-calls.yml)."""
    declared = yaml.safe_load((WORKFLOWS / SHARED).read_text()).get("permissions", {})
    assert declared.get("issues") == "write", f"{SHARED} no longer declares issues: write"
    granted = _jobs(caller)[JOB].get("permissions", {})
    assert granted.get("issues") == "write", f"{caller}:{JOB} does not grant issues: write"


def test_the_shared_workflow_updates_before_it_creates():
    """One open issue per workflow, not one per night."""
    shared = yaml.safe_load((WORKFLOWS / SHARED).read_text())
    # PyYAML parses the bare `on:` key as the boolean True.
    assert "workflow_call" in shared[True], f"{SHARED} is not callable"
    run = " ".join(
        line
        for job in shared["jobs"].values()
        for step in job.get("steps", [])
        for line in step.get("run", "").splitlines()
        if not line.lstrip().startswith("#")
    )
    for verb in ("gh issue list", "gh issue comment", "gh issue create"):
        assert verb in run, f"{SHARED} no longer runs `{verb}`"
    assert run.index("gh issue list") < run.index(
        "gh issue create"
    ), f"{SHARED} creates before it looks for an existing issue (not idempotent)"
