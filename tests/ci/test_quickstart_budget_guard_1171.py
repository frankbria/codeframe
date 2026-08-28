"""#1171 — the README quickstart has to fit the 15-minute budget it claims.

`cf tasks generate` produced 25 tasks for a small todo API. The README then told
a new user to promote all of them and run `cf work batch run --all-ready`, which
is 25 agent runs serially: the cold-start harness cut it off at 925 s and the
walkthrough totalled 19m37s (`artifacts-pypi-0.9.3/timings.tsv`). Every other
step in that run sums to ~315 s, so the whole overrun is that one step.

The documented first run is now a single task. These assertions pin that, in
both places it has to hold — the README a user follows and the harness that
measures them — because the failure mode is a docs edit, which nothing else in
the suite would catch.
"""

import re

import pytest

from pathlib import Path

pytestmark = pytest.mark.v2

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
WALKTHROUGH = ROOT / "scripts" / "quickstart-cleanroom" / "walkthrough.sh"

# Promoting every BACKLOG task is what makes `--all-ready` unbounded. It stays a
# documented command — just not one the quickstart's first run reaches for.
PROMOTE_ALL = "--all --from BACKLOG"
BATCH_ALL_READY = "cf work batch run --all-ready"


def _quickstart_section() -> str:
    """The README from '## Quick Start' to the next top-level heading."""
    text = README.read_text()
    start = text.index("## Quick Start")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def test_quickstart_first_run_is_a_single_task():
    section = _quickstart_section()
    assert "cf work start" in section, (
        "The quickstart's execute step must be `cf work start <task-id> "
        "--execute` — one task demonstrates the loop inside the budget; the "
        "whole backlog does not (#1171)."
    )


def test_quickstart_does_not_lead_with_the_whole_backlog():
    section = _quickstart_section()
    if BATCH_ALL_READY not in section:
        return  # not mentioned at all is also fine

    # Mentioning it is fine; reaching it *before* the single-task run is what
    # put 25 serial agent runs on the documented happy path.
    assert section.index("cf work start") < section.index(BATCH_ALL_READY), (
        "`cf work batch run --all-ready` appears before `cf work start` in the "
        "Quick Start — that is the 19-minute path a new user follows (#1171)."
    )

    assert re.search(r"long[- ]running", section, re.IGNORECASE), (
        "The Quick Start offers `--all-ready` without saying it is "
        "long-running. Whatever it costs, the docs have to admit it (#1171)."
    )


def test_quickstart_promotes_one_task_not_every_backlog_task():
    section = _quickstart_section()
    if PROMOTE_ALL not in section:
        return

    single = re.search(r"cf tasks set status <?task[-_]?id>? READY", section)
    assert single, (
        "The Quick Start promotes every BACKLOG task without first showing how "
        "to promote one — that is what makes the next step unbounded (#1171)."
    )
    assert single.start() < section.index(PROMOTE_ALL), (
        "Bulk promotion is shown before single-task promotion, so the "
        "documented happy path is still the whole backlog (#1171)."
    )


def test_harness_does_not_run_the_whole_backlog():
    """The measured walkthrough has to follow the same path it measures."""
    script = WALKTHROUGH.read_text()
    steps = re.findall(r'^\s*step\s+"([^"]+)".*$', script, re.MULTILINE)
    body = "\n".join(
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    )

    assert BATCH_ALL_READY not in body, (
        "walkthrough.sh still runs the full backlog. It TIMEOUTs at 900 s, and "
        "no arrangement of 25 serial agent runs fits 15 minutes (#1171)."
    )
    assert any(s.endswith("work-start") for s in steps), (
        f"walkthrough.sh must still measure `cf work start`; steps: {steps}"
    )
    assert any(s.endswith("proof-run") for s in steps), (
        f"walkthrough.sh must still reach `cf proof run`; steps: {steps}"
    )
