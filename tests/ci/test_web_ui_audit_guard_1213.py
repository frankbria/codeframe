"""#1213 — the early signal for a new high advisory against `web-ui`.

`web-ui/Dockerfile`'s `deps` stage runs `npm ci` then
`npm audit --audit-level=high`. That gate is correct (#1131) but its failure mode
is disproportionate to its trigger: no commit is required — a newly published
advisory against any transitive dependency flips it — and the blast radius is the
whole `Deploy` workflow, both environments at once, since they build the same
image. #1210 was exactly that: staging un-deployable for a day, found by a human
noticing a red run, while both fixing Dependabot PRs sat green and unmerged.

`.github/workflows/web-ui-audit.yml` builds that same Dockerfile stage on a daily
schedule so a new advisory arrives as a targeted failure instead of as a deploy
outage. These assertions pin the properties that make it worth having — and, just
as importantly, that it neither *replaced* the gate it front-runs nor drifted into
checking something laxer.
"""

import re

import pytest
import yaml

from pathlib import Path

pytestmark = pytest.mark.v2

REPO = Path(__file__).resolve().parents[2]
AUDIT = REPO / ".github" / "workflows" / "web-ui-audit.yml"
DOCKERFILE = REPO / "web-ui" / "Dockerfile"
DEPLOY_README = REPO / "deploy" / "README.md"
CLAUDE_MD = REPO / "CLAUDE.md"

# The stage the workflow targets and the gate must both live in.
GATE_STAGE = "deps"


def _load(path: Path) -> dict:
    # PyYAML parses the bare `on:` key as the boolean True.
    return yaml.safe_load(path.read_text())


def _runs(workflow: dict) -> str:
    """Every executable line of every step, comment-only lines dropped.

    A shell comment cannot run anything, and this same scanner-vs-comment trap
    misfired twice while #1213 was written — once here and once in the #969
    guard. Only a line whose first non-space character is `#` is dropped, so an
    inline `#` inside a quoted string cannot hide a real command.
    """
    return " ".join(
        line
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        for line in step.get("run", "").splitlines()
        if not line.lstrip().startswith("#")
    )


def _stage_body(stage: str) -> str:
    """The executable lines of one Dockerfile stage, comments dropped.

    Scoped to the stage on purpose: a gate sitting in a stage no build target
    reaches is not a gate, and `--target deps` would silently stop running it.
    """
    body: list[str] = []
    inside = False
    for line in DOCKERFILE.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(r"^FROM\s", stripped, re.IGNORECASE):
            inside = bool(re.search(rf"\bAS\s+{re.escape(stage)}\b", stripped, re.IGNORECASE))
            continue
        if inside:
            body.append(stripped)
    return "\n".join(body)


def _gate_line() -> str:
    for line in _stage_body(GATE_STAGE).splitlines():
        if line.startswith("RUN") and "npm audit" in line:
            return line
    return ""


def test_it_runs_on_a_schedule():
    """The trigger is an upstream publication, not a commit of ours."""
    triggers = _load(AUDIT)[True]
    assert "schedule" in triggers, (
        "without a schedule the check only ever runs when someone pushes, which is "
        "exactly the blind spot that kept staging down for a day in #1210"
    )


def test_it_runs_the_real_gate_rather_than_its_own_copy_of_it():
    """A re-implemented audit is a second copy of the threshold, free to drift.

    It is also a different environment: `npm ci` on alpine/musl resolves
    different optional platform packages than glibc does (`sharp` is exactly
    such a dependency), so an advisory against the musl variant is invisible to
    an audit run on the bare runner.
    """
    runs = _runs(_load(AUDIT))
    assert "docker build" in runs, (
        "the workflow no longer builds the image stage that carries the gate, so "
        "whatever it checks instead can pass while the deploy still fails"
    )
    assert f"--target {GATE_STAGE}" in runs, (
        f"the workflow does not target the {GATE_STAGE!r} stage; a broader target "
        "builds the whole frontend for no added signal, a narrower one skips the gate"
    )
    assert "npm audit" not in runs, (
        "the workflow runs its own `npm audit` again — that is the duplicated "
        "threshold this check exists to prevent"
    )


def test_the_gate_lives_in_the_stage_the_workflow_targets():
    """`--target deps` only runs the gate while the gate is actually in `deps`."""
    assert _gate_line(), (
        f"no `RUN npm audit ...` in the Dockerfile's {GATE_STAGE!r} stage, so "
        f"`docker build --target {GATE_STAGE}` no longer exercises the gate at all"
    )
    assert "npm ci" in _stage_body(GATE_STAGE), (
        f"the {GATE_STAGE!r} stage no longer runs `npm ci`, so the scheduled build "
        "has stopped being the #1194 lockfile oracle as well"
    )


def test_the_gate_is_set_at_high_and_is_not_neutralised():
    """#1131: at `critical`, six high findings accumulated unnoticed.

    And a gate is only a gate while it can fail the build — `RUN npm audit ... ||
    true` type-checks as a gate and enforces nothing.
    """
    gate = _gate_line()
    assert re.search(r"--audit-level[= ]high\b", gate), (
        f"the audit gate is not set at `high`: {gate!r}. See #1131 — `critical` let "
        "six high-severity findings through."
    )
    for swallow in ("|| true", "|| :", "|| exit 0", "; true", "|| echo"):
        assert swallow not in gate, (
            f"the gate swallows its own failure ({swallow!r} in {gate!r}), so an "
            "image carrying a high advisory would build cleanly"
        )


def test_nothing_here_regenerates_the_lockfile():
    """#1194: any regenerated web-ui lock fails `npm ci` with a misleading error.

    `npm audit fix` is the reflex and it is wrong — a job that "fixes" the tree it
    is checking breaks the build it guards.
    """
    haystack = _runs(_load(AUDIT)) + "\n" + _stage_body(GATE_STAGE)
    for forbidden in ("npm audit fix", "npm install", "npm update"):
        assert forbidden not in haystack, (
            f"{forbidden!r} rewrites web-ui/package-lock.json into a state npm ci rejects (#1194)"
        )


@pytest.mark.parametrize("doc", [DEPLOY_README, CLAUDE_MD], ids=lambda p: p.name)
def test_the_recovery_procedure_is_written_down(doc: Path):
    """#1210's fix was non-obvious and the obvious move (`npm audit fix`) is wrong.

    Both places matter: `deploy/README.md` is where a human whose deploy went red
    looks, and `CLAUDE.md` is where an agent looks first.
    """
    text = doc.read_text()
    assert "npm audit fix" in text, (
        f"{doc.name} does not warn against `npm audit fix`, so the next person "
        "reaches for it first and lands a lockfile npm ci rejects (#1194)"
    )
    assert "#1194" in text, f"{doc.name} does not name #1194 as the reason"
