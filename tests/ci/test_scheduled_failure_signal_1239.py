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

import os
import subprocess

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
    "unlocked-resolution.yml": ["unlocked-install"],
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


# The shape checks above are a proxy; this runs the real step script with `gh`
# stubbed, which is the only thing that actually fails if the idempotency logic
# breaks (a wrong flag, a search that misses, create-before-list).
_STUB_GH = """#!/bin/bash
echo "gh $1 $2" >> "$GH_CALLS"
case "$1 $2" in
  "issue list") cat "$GH_OPEN" ;;
  "issue create") echo "https://example.test/issues/999" ;;
esac
"""


def _run_step(tmp_path: Path, open_issues: str) -> str:
    shared = yaml.safe_load((WORKFLOWS / SHARED).read_text())
    (step,) = [s for j in shared["jobs"].values() for s in j["steps"] if "run" in s]
    (tmp_path / "bin").mkdir(exist_ok=True)
    (tmp_path / "bin" / "gh").write_text(_STUB_GH)
    (tmp_path / "bin" / "gh").chmod(0o755)
    (tmp_path / "open.json").write_text(open_issues)
    calls = tmp_path / "calls.txt"
    calls.write_text("")
    env = {
        **os.environ,
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "GH_CALLS": str(calls),
        "GH_OPEN": str(tmp_path / "open.json"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "WORKFLOW": "Test Suite",
        "RUN_URL": "https://example.test/run/1",
    }
    subprocess.run(["bash", "-c", step["run"]], env=env, check=True, capture_output=True)
    return calls.read_text()


def test_the_first_red_night_opens_an_issue(tmp_path: Path):
    calls = _run_step(tmp_path, "[]")
    assert "gh issue create" in calls and "gh issue comment" not in calls, calls


def test_the_next_red_night_updates_it_instead(tmp_path: Path):
    title = "[P1.0] Scheduled `Test Suite` run is failing"
    other = "[P1.0] Scheduled `Web UI Audit` run is failing"
    open_issues = f'[{{"number": 7, "title": "{other}"}}, {{"number": 42, "title": "{title}"}}]'
    calls = _run_step(tmp_path, open_issues)
    assert "gh issue comment" in calls and "gh issue create" not in calls, calls
