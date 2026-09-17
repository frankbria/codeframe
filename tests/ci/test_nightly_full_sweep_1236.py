"""#1236 — the nightly cross-browser sweep must be reproducible on demand.

`e2e-browser-full` in `test.yml` is the only job that runs every Playwright spec
in every browser, and it was `schedule`-only. It went red on 2026-08-09 and
stayed red for 40 nights before anyone looked: nothing gated a merge on it, and
the only way to reproduce CI's failure was to wait for the 02:00 UTC cron. A
`workflow_dispatch` trigger lets the sweep run against a branch before merge.
These assertions pin that the trigger exists and that the nightly-only jobs
actually honour it — a dispatch that skips the very job it exists for is worse
than none.
"""

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

TEST_YML = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "test.yml"


def _workflow() -> dict:
    return yaml.safe_load(TEST_YML.read_text())


def test_the_suite_can_be_dispatched_by_hand():
    # PyYAML parses the bare `on:` key as the boolean True.
    triggers = _workflow()[True]
    assert "workflow_dispatch" in triggers, (
        "test.yml has no workflow_dispatch trigger, so the full browser sweep "
        "can only be reproduced by waiting for the nightly cron (#1236)"
    )


@pytest.mark.parametrize("job", ["e2e-browser-full", "e2e-backend-tests"])
def test_the_nightly_only_jobs_also_run_on_a_dispatch(job: str):
    condition = _workflow()["jobs"][job].get("if", "")
    assert "github.event_name == 'schedule'" in condition, (
        f"{job} no longer runs on the nightly schedule"
    )
    assert "github.event_name == 'workflow_dispatch'" in condition, (
        f"{job} skips itself on a manual run, so a dispatch cannot reproduce "
        "the nightly failure it exists to reproduce (#1236)"
    )
