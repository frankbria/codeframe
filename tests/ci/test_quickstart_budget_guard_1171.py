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
QUICKSTART = ROOT / "docs" / "QUICKSTART.md"
WALKTHROUGH = ROOT / "scripts" / "quickstart-cleanroom" / "walkthrough.sh"

# Promoting every BACKLOG task is what makes `--all-ready` unbounded. It stays a
# documented command — just not one the quickstart's first run reaches for.
PROMOTE_ALL = "--all --from BACKLOG"
BATCH_ALL_READY = "cf work batch run --all-ready"

# Deliberately loose: the point is that *some* warning is present, not that it is
# phrased the way it is today. A guard that fails on a reworded sentence gets
# deleted; one that fails on a missing warning gets fixed.
SAYS_IT_IS_SLOW = r"long[- ]running|takes? a long time|can take (hours|a while)|not (quick|fast)"


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

    assert re.search(SAYS_IT_IS_SLOW, section, re.IGNORECASE), (
        "The Quick Start offers `--all-ready` without warning that it is "
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


def test_the_long_form_quickstart_leads_with_one_task_too():
    """docs/QUICKSTART.md is the other document a new user follows.

    It spells the command `codeframe`, not `cf`. Same trap, same fix — and
    without this it could regress to recommending the whole backlog first while
    every other assertion here still passed.
    """
    text = QUICKSTART.read_text()
    start = text.index("### Step 5: Execute Tasks")
    end = text.index("### Step 6", start)
    section = text[start:end]

    single = section.index("codeframe work start")
    batch = section.index("codeframe work batch run --all-ready")
    assert single < batch, (
        "docs/QUICKSTART.md offers the full backlog before the single-task run "
        "(#1171)."
    )
    assert re.search(SAYS_IT_IS_SLOW, section, re.IGNORECASE), (
        "docs/QUICKSTART.md recommends `--all-ready` without saying it is "
        "long-running (#1171)."
    )


def test_harness_never_promotes_an_empty_task_id():
    """An unresolvable ID must not produce a fast, plausible-looking total.

    `walkthrough.sh` runs under `set -uo pipefail` with no `-e`. Outside a
    non-empty guard, a failed ID extraction runs `cf tasks set status '' READY`,
    silently skips the agent run, still reaches `cf proof run`, and reports a
    total that measures a path nobody walked.
    """
    script = WALKTHROUGH.read_text()

    guard = re.search(r'if \[ -z "\$TASK_ID" \]; then', script)
    assert guard, (
        "walkthrough.sh no longer checks for an empty TASK_ID before promoting "
        "(#1171)."
    )
    else_branch = script.index("else", guard.end())
    # The block's own `fi`, at column 0. Checking only that the steps come after
    # `else` is not enough: `else :; fi` followed by the steps would satisfy that
    # while leaving them unguarded again.
    closing_fi = re.search(r"^fi$", script[else_branch:], re.MULTILINE)
    assert closing_fi, "The TASK_ID guard block is never closed (#1171)."
    block = script[else_branch : else_branch + closing_fi.start()]

    for step in ('step "5-promote-one"', 'step "6-work-start"'):
        assert step in block, (
            f"{step} is outside the non-empty TASK_ID branch — an unresolved ID "
            "would promote an empty ID and still report a total measuring "
            "nothing (#1171)."
        )
    assert "P-NO-TASK-ID" in script, (
        "The unresolvable-ID path must still file a finding, or the run looks "
        "clean (#1171)."
    )
