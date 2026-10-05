"""#1401: an evidence rule runs exactly the test it names.

The runner used to enforce a rule as ``pytest -k <test_id>``, and ``-k`` is
substring matching. #1397 made new ids unique, but an id that is a prefix of
another still selected both: a legacy title-only ``test_unit_total`` ran
``test_unit_total_wrong`` too, and ``test_unit_req_1000`` (empty title slug)
ran ``test_unit_req_10000``. Worse, a rule whose test does not exist passed
whenever a longer-named test containing it did. (The issue's own example,
``test_unit_total_wrong`` vs ``test_unit_req_0007_total_wrong``, is not a
substring pair; verified, so the tests use the prefix shapes that are.)

Through ``run_proof``, against a real pytest run.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codeframe.core.proof.ledger import init_proof_tables, save_requirement
from codeframe.core.proof.models import (
    EvidenceRule,
    Gate,
    GateOutcome,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)
from codeframe.core.proof.runner import run_proof
from codeframe.core.workspace import create_or_load_workspace

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

TESTS = '''\
import pytest


def test_unit_total():
    assert True


def test_unit_total_wrong():
    assert False, "a different requirement, still failing"


def test_unit_req_1000():
    assert True


def test_unit_req_10000():
    assert False, "REQ-10000, still failing"


def test_unit_absent_but_longer():
    assert True


@pytest.mark.parametrize("n", [1, 2])
def test_unit_param(n):
    assert n


@pytest.mark.parametrize("v", ["ok", "a::b"])
def test_unit_colons(v):
    assert v == "ok", "the case whose id contains :: still fails"
'''


@pytest.fixture(
    params=[None, "addopts = -v", "addopts = -qq", "verbosity_test_cases = 2", "addopts = tests"],
    ids=["no-config", "addopts-v", "addopts-qq", "verbosity-test-cases", "addopts-path"],
)
def ws(tmp_path, request):
    """A project's own pytest config must not change what runs: verbosity in
    addopts (or the per-test-case ini option) turned the node-id list into a
    tree, and a test path in addopts is collected on top of explicit node
    ids, so unrelated tests ran unfiltered (codex review)."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_rules.py").write_text(TESTS, encoding="utf-8")
    if request.param:
        (repo / "pytest.ini").write_text(f"[pytest]\n{request.param}\n", encoding="utf-8")
    w = create_or_load_workspace(repo)
    init_proof_tables(w)
    return w


def _unit_outcome(ws, test_id):
    save_requirement(ws, Requirement(
        id="REQ-0001", title="t", description="d",
        severity=Severity.MEDIUM, source=Source.QA,
        scope=RequirementScope(files=["app.py"]),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[EvidenceRule(test_id=test_id, gate=Gate.UNIT)],
        status=ReqStatus.OPEN, created_at=datetime.now(timezone.utc),
    ))
    return dict(run_proof(ws, full=True)["REQ-0001"])[Gate.UNIT]


def test_a_legacy_rule_does_not_run_another_test_its_name_prefixes(ws):
    assert _unit_outcome(ws, "test_unit_total") == GateOutcome.PASSED


def test_req_1000_does_not_run_req_10000(ws):
    assert _unit_outcome(ws, "test_unit_req_1000") == GateOutcome.PASSED


def test_a_missing_test_is_not_satisfied_by_a_longer_named_one(ws):
    assert _unit_outcome(ws, "test_unit_absent") == GateOutcome.FAILED


def test_a_parametrized_test_is_selected_by_its_name(ws):
    assert _unit_outcome(ws, "test_unit_param") == GateOutcome.PASSED


def test_a_failing_case_whose_param_id_contains_colons_is_not_skipped(ws):
    """Splitting on the last `::` before stripping `[...]` read `b]` as the
    name, dropped that case, and let the passing case satisfy the rule (codex)."""
    assert _unit_outcome(ws, "test_unit_colons") == GateOutcome.FAILED


def test_a_test_whose_node_id_prefixes_the_named_one_does_not_hide_it(tmp_path):
    """`--deselect` is prefix matching: deselecting `test_unit_total.py::test_unit`
    also removed the required `test_unit_total.py::test_unit_total` (codex)."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_unit_total.py").write_text(
        "def test_unit():\n    assert False\n\n\ndef test_unit_total():\n    assert True\n",
        encoding="utf-8",
    )
    w = create_or_load_workspace(repo)
    init_proof_tables(w)

    assert _unit_outcome(w, "test_unit_total") == GateOutcome.PASSED


@pytest.mark.parametrize("stop_early", ["-x", "--maxfail=1"])
def test_a_project_that_stops_early_cannot_leave_an_exact_case_unrun(tmp_path, stop_early):
    """With -x in addopts, a failing substring match stopped pytest before a
    later, failing exact case ran, and the report held only the passing one
    (codex review)."""
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "pytest.ini").write_text(f"[pytest]\naddopts = {stop_early}\n", encoding="utf-8")
    (repo / "tests" / "test_a.py").write_text(
        "def test_unit_total():\n    assert True\n\n\ndef test_unit_total_wrong():\n    assert False\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_b.py").write_text(
        "def test_unit_total():\n    assert False, 'the exact case that must decide'\n",
        encoding="utf-8",
    )
    w = create_or_load_workspace(repo)
    init_proof_tables(w)

    assert _unit_outcome(w, "test_unit_total") == GateOutcome.FAILED
