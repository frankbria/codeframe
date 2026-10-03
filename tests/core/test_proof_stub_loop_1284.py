"""#1284: following the generated stub must be able to satisfy every PROOF9 gate.

The runner enforces evidence as `pytest -k test_<gate>_<slug>`, but the E2E
stub was Playwright TypeScript (rename to `.spec.ts`) and the DEMO stub a
showboat markdown script: a developer who followed them to the letter got
FAILED on both gates, and E2E is required by five of the seven glitch types.
The PERF stub timed an empty block, so it passed the moment it was renamed,
recording evidence for work nobody did.

These tests run the real loop, unmocked: capture -> stub -> implement -> proof.
"Implement" means doing what each stub says: replace the placeholder with a
passing assertion and drop the `draft_` prefix.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import Gate, GlitchType, ReqStatus, Severity, Source
from codeframe.core.proof.obligations import OBLIGATION_MAP, classify_glitch
from codeframe.core.proof.runner import run_proof
from codeframe.core.proof.stubs import generate_stubs
from codeframe.core.workspace import create_or_load_workspace

pytestmark = [pytest.mark.v2, pytest.mark.timeout(600)]

#: A description that classifies as each glitch type.
DESCRIPTIONS: dict[GlitchType, str] = {
    GlitchType.LOGIC_BUG: "The total is computed wrong when the list is empty",
    GlitchType.INTEGRATION_BUG: "The api endpoint returns the wrong schema",
    GlitchType.UI_WIRING_BUG: "Clicking the submit button does nothing",
    GlitchType.UI_LAYOUT_BUG: "The sidebar layout overlaps the header on mobile",
    GlitchType.A11Y_BUG: "The dialog has no aria label for screen reader users",
    GlitchType.PERF_REGRESSION: "Search became slow, a latency regression",
    GlitchType.SECURITY_ISSUE: "A crafted value allows injection into the query",
}

_PLACEHOLDER = re.compile(r"^(\s*)assert False,.*$", re.MULTILINE)


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def total(xs):\n    return sum(xs)\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    w = create_or_load_workspace(repo)
    ledger.init_proof_tables(w)
    return w


def _implement(path):
    """Do what the stub says: make it a real test, then rename it."""
    text = path.read_text(encoding="utf-8")
    assert _PLACEHOLDER.search(text), f"{path.name} has no placeholder to implement"
    path.write_text(_PLACEHOLDER.sub(r"\1assert 1 + 1 == 2", text), encoding="utf-8")
    final = path.with_name(path.name.removeprefix("draft_"))
    path.rename(final)
    return final


def test_the_descriptions_cover_every_glitch_type():
    assert set(DESCRIPTIONS) == set(OBLIGATION_MAP)
    for glitch, text in DESCRIPTIONS.items():
        assert classify_glitch(text) == glitch, text


@pytest.mark.parametrize("glitch", list(OBLIGATION_MAP), ids=lambda g: g.value)
def test_following_every_stub_satisfies_the_requirement(ws, glitch):
    req, stub_paths = capture_requirement(
        ws, title=f"{glitch.value} repro", description=DESCRIPTIONS[glitch],
        where="app.py", severity=Severity.HIGH, source=Source.QA,
    )
    assert {o.gate for o in req.obligations} == set(OBLIGATION_MAP[glitch])

    for gate, path in stub_paths.items():
        if gate is not Gate.MANUAL:
            _implement(path)

    run_proof(ws, full=True)

    stored = ledger.get_requirement(ws, req.id)
    assert stored.status == ReqStatus.SATISFIED, (
        f"{glitch.value}: following the stubs did not satisfy "
        f"{[(o.gate.value, o.status) for o in stored.obligations]}"
    )


@pytest.mark.parametrize("gate", [Gate.E2E, Gate.DEMO, Gate.PERF])
def test_an_unimplemented_stub_cannot_pass(ws, gate):
    """Renamed but not implemented must fail: no evidence for work not done."""
    from codeframe.core.proof.models import Obligation, Requirement, RequirementScope

    req = Requirement(
        id="REQ-0099", title="stub check", description="d", severity=Severity.HIGH,
        source=Source.QA, scope=RequirementScope(), obligations=[Obligation(gate=gate)],
        evidence_rules=[], status=ReqStatus.OPEN,
    )
    source = generate_stubs(req)[gate]
    target = ws.repo_path / f"test_{gate.value}_check.py"
    target.write_text(source, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target)],
        cwd=ws.repo_path, capture_output=True, text=True,
    )

    assert result.returncode == 1, (gate.value, result.stdout[-800:])
