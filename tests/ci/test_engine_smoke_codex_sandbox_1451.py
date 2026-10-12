"""#1451 — the Engine Task Smoke job must let codex's sandbox start.

codex sandboxes every command with a bundled bubblewrap, which needs unprivileged
user namespaces. GitHub's Ubuntu 24.04 runners ship
`kernel.apparmor_restrict_unprivileged_userns=1`, so bwrap cannot start there.
The adapter declines codex's escalation requests (an approval runs the command
unsandboxed, #1278), so the agent ends with "The sandbox failed to start" and
writes nothing — the false-completion shape the smoke tier exists to catch.

It went unseen until 2026-10-11 because the codex task leg had been *skipped*
for weeks on an invalid OPENAI_API_KEY (#1355). The first run with a working key
failed on the sandbox instead.

The fix lifts the restriction on the throwaway runner before the tier runs.
These assertions pin that the step exists, runs before the tier, and is not
quietly dropped from the job that needs it.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.v2

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "engine-smoke.yml"
SYSCTL = "kernel.apparmor_restrict_unprivileged_userns=0"


def _steps(job: str) -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]


def _index(steps: list[dict], predicate) -> int:
    return next((i for i, s in enumerate(steps) if predicate(s)), -1)


def test_the_task_job_lifts_the_userns_restriction_before_the_tier_runs():
    steps = _steps("task")
    lift = _index(steps, lambda s: SYSCTL in s.get("run", ""))
    tier = _index(steps, lambda s: "test_engine_smoke_tier.py" in s.get("run", ""))

    assert tier != -1, "the Engine Task Smoke job no longer runs the smoke tier"
    assert lift != -1, (
        f"no step sets {SYSCTL}: codex's bubblewrap sandbox cannot start on "
        "ubuntu-24.04 runners and the codex leg fails with no file written (#1451)"
    )
    assert lift < tier, "the userns restriction is lifted after the tier already ran"


def test_the_lift_uses_sudo_on_the_runner_not_a_container():
    """sysctl needs root; without sudo the step fails before anything runs."""
    step = next(s for s in _steps("task") if SYSCTL in s.get("run", ""))
    assert "sudo sysctl -w" in step["run"]
