"""#1397: a requirement's evidence selects only its own tests.

The runner enforces a rule as `pytest -k <test_id>` over the whole project.
Two captures of one glitch shared a title, so they shared a test_id
(`test_<gate>_<slug(title)>`), and each requirement's rule also ran the other
one's test: a still-failing re-capture failed the requirement that was
already fixed, and the merge gate blocked on it.

The real loop, unmocked, as in test_proof_stub_loop_1284.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import Gate, ReqStatus, Severity, Source
from codeframe.core.proof.runner import run_proof
from codeframe.core.workspace import create_or_load_workspace
from tests.core.test_proof_stub_loop_1284 import _implement

pytestmark = [pytest.mark.v2, pytest.mark.timeout(600)]

TITLE = "Total wrong"
DESCRIPTION = "The total is computed wrong when the list is empty"


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def total(xs):\n    return sum(xs)\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    w = create_or_load_workspace(repo)
    ledger.init_proof_tables(w)
    return w


def _capture(ws):
    return capture_requirement(
        ws, title=TITLE, description=DESCRIPTION, where="app.py",
        severity=Severity.HIGH, source=Source.QA,
    )


def _implement_failing(path):
    """Implemented, but the regression it guards is not fixed yet."""
    final = _implement(path)
    final.write_text(final.read_text().replace("assert 1 + 1 == 2", "assert 1 + 1 == 3"))
    return final


def test_same_title_requirements_get_distinct_test_ids(ws):
    first, _ = _capture(ws)
    second, _ = _capture(ws)
    ids = [r.test_id for r in (*first.evidence_rules, *second.evidence_rules)]
    assert len(ids) == len(set(ids)), ids


def test_each_generated_test_function_matches_its_rule(ws):
    req, paths = _capture(ws)
    for rule in req.evidence_rules:
        source = paths[rule.gate].read_text()
        assert re.search(rf"^def {re.escape(rule.test_id)}\(", source, re.M), rule.test_id


def test_a_failing_recapture_does_not_fail_the_fixed_requirement(ws):
    fixed, fixed_paths = _capture(ws)
    for gate, path in fixed_paths.items():
        if gate is not Gate.MANUAL:
            _implement(path)
    recurring, recurring_paths = _capture(ws)
    for gate, path in recurring_paths.items():
        if gate is not Gate.MANUAL:
            _implement_failing(path)

    run_proof(ws, full=True)

    assert ledger.get_requirement(ws, fixed.id).status == ReqStatus.SATISFIED
    assert ledger.get_requirement(ws, recurring.id).status != ReqStatus.SATISFIED


def test_a_title_quoting_another_requirements_test_id_does_not_select_it(ws):
    """pytest -k is substring matching: a re-capture titled with the earlier
    requirement's test name (pasted from CI output) made the earlier rule
    select the new test too (GLM review)."""
    first, _ = _capture(ws)
    second, _ = capture_requirement(
        ws, title=f"{first.evidence_rules[0].test_id} failing again", description=DESCRIPTION,
        where="app.py", severity=Severity.HIGH, source=Source.QA,
    )
    for older in first.evidence_rules:
        for newer in second.evidence_rules:
            assert older.test_id not in newer.test_id, (older.test_id, newer.test_id)
