"""The quickstart's PROVE step has to actually pass (#1173 / P2.34).

The README's Quick Start ended on ``cf proof run``, which on a fresh workspace
exits 2 — correct behaviour (#1118), documented in the wrong place. For a
product whose thesis is PROVE, the walkthrough demonstrated PROOF9's empty-state
guard rather than PROOF9.

The obvious fix — "just add ``cf proof capture`` before it" — does not work, and
that is what these tests pin. Capture writes ``draft_*`` stubs that pytest
deliberately does not collect, and each obligation carries a ``must_pass``
evidence rule, so a captured-but-unimplemented requirement moves the run from
exit 2 to exit **1**. Reaching exit 0 needs the third step the README now
documents: rename the draft stub and give it a real assertion.

So there are two failure modes to guard against, in opposite directions:

* the docs going back to capture-then-run and claiming a green run (test 2), and
* someone "fixing" test 2 by making the generated stub vacuously green, which
  would hand out proof for a test nobody wrote (test 1 and test 3).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.v2


REPO_ROOT_MARKERS = ("README.md", "docs/QUICKSTART.md")


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


@pytest.fixture
def captured(workspace):
    """The README's example glitch, captured exactly as documented."""
    from codeframe.core.proof.capture import capture_requirement
    from codeframe.core.proof.models import Severity, Source

    req, stubs = capture_requirement(
        workspace,
        title="add() returns the wrong sum for negative numbers",
        description="Calculation is wrong: add(-1, -1) returned 0 instead of -2",
        where="src/calc.py",
        severity=Severity.HIGH,
        source=Source.QA,
    )
    return req, stubs


@pytest.fixture
def local_pytest(monkeypatch):
    """Make the gate runner use the pytest on PATH instead of ``uv run pytest``.

    ``_run_pytest`` prefers ``uv run pytest`` whenever uv exists, which in a bare
    tmp workspace resolves no project and reports pytest missing. Hiding uv from
    that one lookup runs the *real* pytest against the *real* generated stubs,
    which is the whole point — a stubbed gate runner would prove nothing about
    whether a renamed stub is collectable.
    """
    if not shutil.which("pytest"):
        pytest.skip("pytest is not on PATH; the gate would be SKIPPED, not run")

    real_which = shutil.which

    def which(cmd, *args, **kwargs):
        if cmd == "uv":
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr("codeframe.core.gates.shutil.which", which)


def _implement(stub_path):
    """Do what the README tells the user to do with a generated stub.

    Drop the ``draft_`` prefix so pytest collects the file, and replace the
    placeholder assertion with a real one. The assertion is self-contained on
    purpose: this test is about the PROOF9 plumbing, not about a fixture's
    import path.
    """
    implemented = stub_path.with_name(stub_path.name.removeprefix("draft_"))
    original = stub_path.read_text(encoding="utf-8")
    body = original.replace(
        'assert False, "Not implemented yet — replace with real assertions"',
        "def add(a, b):\n        return a + b\n\n    assert add(-1, -1) == -2",
    )
    # Without this, a change to the stub template turns the replace into a no-op
    # and every test below would still pass — proving only that the *template*
    # is green, which is the exact thing this file exists to rule out.
    assert body != original, (
        f"{stub_path.name} no longer contains the placeholder assertion the "
        "README tells the reader to replace"
    )
    implemented.write_text(body, encoding="utf-8")
    stub_path.unlink()
    return implemented


# ---------------------------------------------------------------------------
# 1. The rename instruction in the generated stub has to be true
# ---------------------------------------------------------------------------


class TestTheDocumentedRenameIsCollectable:
    def test_stubs_are_written_as_uncollectable_drafts(self, captured):
        """If these were collectable, they would fail every run as ``assert False``."""
        _req, stubs = captured
        assert stubs, "capture produced no stubs — nothing for the docs to point at"
        for path in stubs.values():
            assert path.name.startswith("draft_"), path.name

    def test_the_evidence_rule_names_a_function_the_stub_defines(self, captured):
        """``pytest -k <test_id>`` is how the gate verifies; the stub must match it.

        The runner enforces each ``must_pass`` rule with a scoped pytest run, and
        exit 5 (nothing collected) is a FAILED obligation. So a stub whose
        function name drifted from its rule's ``test_id`` could never be
        satisfied, no matter how correctly the user implemented it.
        """
        req, stubs = captured
        for obligation in req.obligations:
            rules = [r for r in req.evidence_rules if r.gate == obligation.gate]
            assert rules, f"{obligation.gate.value} has no evidence rule"
            source = stubs[obligation.gate].read_text(encoding="utf-8")
            for rule in rules:
                assert f"def {rule.test_id}(" in source, (
                    f"{stubs[obligation.gate].name} defines no {rule.test_id}"
                )

    def test_renaming_makes_pytest_collect_it(self, workspace, captured, local_pytest):
        """The one thing the README's rename step depends on."""
        _req, stubs = captured
        implemented = _implement(next(iter(stubs.values())))

        collected = subprocess.run(
            ["pytest", "--collect-only", "-q", str(implemented)],
            cwd=workspace.repo_path,
            capture_output=True,
            text=True,
        )
        assert collected.returncode == 0, collected.stdout + collected.stderr


# ---------------------------------------------------------------------------
# 2. The documented sequence reaches a real, green run
# ---------------------------------------------------------------------------


class TestTheDocumentedSequencePasses:
    def test_capture_implement_run_satisfies_every_obligation(
        self, workspace, captured, local_pytest
    ):
        """README Step 7, end to end, against the real runner and real pytest."""
        from codeframe.core.proof.models import GateOutcome
        from codeframe.core.proof.runner import run_proof

        req, stubs = captured
        for path in stubs.values():
            _implement(path)

        results = run_proof(workspace, full=True)

        outcomes = results.get(req.id)
        assert outcomes, f"{req.id} produced no results — nothing was verified"
        assert all(o is GateOutcome.PASSED for _g, o in outcomes), outcomes


# ---------------------------------------------------------------------------
# 3. Capture alone is NOT enough — the reason the fix is three steps
# ---------------------------------------------------------------------------


class TestCaptureAloneDoesNotPass:
    def test_unimplemented_stubs_fail_their_obligations(
        self, workspace, captured, local_pytest
    ):
        """Adding only ``cf proof capture`` to the docs would still end non-zero.

        Guards the docs against reverting to the one-line "fix", and guards the
        generated stub against ever being made vacuously green.
        """
        from codeframe.core.proof.models import GateOutcome
        from codeframe.core.proof.runner import run_proof

        req, _stubs = captured
        results = run_proof(workspace, full=True)

        outcomes = results.get(req.id)
        assert outcomes, f"{req.id} produced no results"
        assert all(o is GateOutcome.FAILED for _g, o in outcomes), outcomes


# ---------------------------------------------------------------------------
# 4. The docs themselves
# ---------------------------------------------------------------------------


def _repo_root():
    from pathlib import Path

    here = Path(__file__).resolve()
    for parent in here.parents:
        if all((parent / marker).exists() for marker in REPO_ROOT_MARKERS):
            return parent
    pytest.skip("not running from a source checkout")


#: The step-by-step walkthrough in each doc, as (path, opening heading, closing
#: heading). Scoped deliberately: both files also carry a command *reference*
#: that lists every ``cf proof`` subcommand in alphabetical-ish order, and the
#: ordering rule below is about the guided path a new user types, not about a
#: lookup table.
WALKTHROUGHS = [
    ("README.md", "## Quick Start", "## Architecture"),
    ("docs/QUICKSTART.md", "## The Happy Path", "## Command Reference"),
]


def _walkthrough(doc, start_heading, end_heading):
    text = _repo_root().joinpath(doc).read_text(encoding="utf-8")
    start = text.find(start_heading)
    assert start != -1, f"{doc} no longer has a '{start_heading}' section"
    end = text.find(end_heading, start)
    assert end != -1, f"{doc} no longer has a '{end_heading}' section"
    return text[start:end]


class TestQuickstartDocsPrepareForTheProofRun:
    @pytest.mark.parametrize("doc,start,end", WALKTHROUGHS)
    def test_capture_is_documented_before_the_first_proof_run(self, doc, start, end):
        """A walkthrough that reaches ``proof run`` first ends on exit 2."""
        section = _walkthrough(doc, start, end)

        first_capture = section.find("proof capture")
        first_run = section.find("proof run")

        assert first_capture != -1, f"{doc}'s walkthrough never mentions `cf proof capture`"
        assert first_run != -1, f"{doc}'s walkthrough never mentions `cf proof run`"
        assert first_capture < first_run, (
            f"{doc}'s walkthrough reaches `cf proof run` before telling the "
            "reader to capture a requirement — on a fresh workspace that is a "
            "guaranteed exit 2"
        )

    @pytest.mark.parametrize("doc,start,end", WALKTHROUGHS)
    def test_the_stub_has_to_be_implemented_before_the_run(self, doc, start, end):
        """Capture writes a draft stub; the docs must say to implement it."""
        section = _walkthrough(doc, start, end)
        assert "draft_" in section, (
            f"{doc}'s walkthrough does not mention the generated draft_* stub, "
            "so a reader following it would run `cf proof run` against an "
            "unimplemented obligation and get exit 1"
        )
