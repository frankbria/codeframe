"""#1485 — judge every pytest evidence rule of a run from ONE pytest process.

`_run_gate` used to start `pytest -k <test_id>` per `must_pass` rule (#1401).
A ratchet of an N-test suite creates N requirements, so `cf proof run --full`
launched N pytest processes, each collecting the whole suite. Now the run's
enforced rules are judged from one JUnit report with the shared
`gates.cases_verdict`, keeping the exact-name semantics: parameters stripped, a
missing name fails, a skip is not evidence.

The process count is measured, not mocked: the fixture project's conftest
appends a line per pytest session.
"""

from datetime import datetime, timezone
from pathlib import Path

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

TESTS = '''import pytest


def test_unit_a():
    assert True


def test_unit_b():
    assert False


def test_unit_c():
    assert True


def test_unit_total():
    assert True


def test_unit_total_wrong():
    assert False


@pytest.mark.skip(reason="not evidence")
def test_unit_skipped():
    pass


@pytest.mark.parametrize("n", [1, 2])
def test_unit_param(n):
    assert n
'''

CONFTEST = '''import pathlib


def pytest_sessionstart(session):
    with open(pathlib.Path(__file__).parent / "sessions.log", "a") as f:
        f.write("session\\n")
'''


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_rules.py").write_text(TESTS, encoding="utf-8")
    (repo / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    w = create_or_load_workspace(repo)
    init_proof_tables(w)
    return w


def _sessions(ws) -> int:
    log = Path(ws.repo_path) / "sessions.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


def _require(ws, n: int, *test_ids: str) -> str:
    req_id = f"REQ-{n:04d}"
    save_requirement(ws, Requirement(
        id=req_id, title=req_id, description="d",
        severity=Severity.MEDIUM, source=Source.RATCHET,
        scope=RequirementScope(files=["."]),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[EvidenceRule(test_id=t, gate=Gate.UNIT) for t in test_ids],
        status=ReqStatus.OPEN, created_at=datetime.now(timezone.utc),
    ))
    return req_id


def _unit(results, req_id) -> GateOutcome:
    return dict(results[req_id])[Gate.UNIT]


def test_n_rules_are_judged_by_one_pytest_process(ws):
    ids = [_require(ws, i, t) for i, t in enumerate(["test_unit_a", "test_unit_b", "test_unit_c"], 1)]

    results = run_proof(ws, full=True)

    assert _sessions(ws) == 1
    assert [_unit(results, r) for r in ids] == [
        GateOutcome.PASSED, GateOutcome.FAILED, GateOutcome.PASSED,
    ]


def test_a_missing_test_fails_its_own_rule_and_no_other(ws):
    present = _require(ws, 1, "test_unit_a")
    missing = _require(ws, 2, "test_unit_missing")

    results = run_proof(ws, full=True)

    assert _sessions(ws) == 1
    assert _unit(results, present) == GateOutcome.PASSED
    assert _unit(results, missing) == GateOutcome.FAILED


def test_exact_name_semantics_hold_in_the_shared_run(ws):
    """#1401: a longer name that `-k` drags in cannot decide a rule.
    #1430: a skip is not evidence. Parameters are stripped."""
    exact = _require(ws, 1, "test_unit_total")
    skipped = _require(ws, 2, "test_unit_skipped")
    param = _require(ws, 3, "test_unit_param")

    results = run_proof(ws, full=True)

    assert _sessions(ws) == 1
    assert _unit(results, exact) == GateOutcome.PASSED
    assert _unit(results, skipped) == GateOutcome.FAILED
    assert _unit(results, param) == GateOutcome.PASSED


def test_one_requirement_with_several_rules_needs_all_of_them(ws):
    req = _require(ws, 1, "test_unit_a", "test_unit_b")

    results = run_proof(ws, full=True)

    assert _sessions(ws) == 1
    assert _unit(results, req) == GateOutcome.FAILED


def test_a_collection_error_fails_every_rule(ws):
    (Path(ws.repo_path) / "tests" / "test_broken.py").write_text("import nope_not_a_module\n")
    ids = [_require(ws, 1, "test_unit_a"), _require(ws, 2, "test_unit_c")]

    results = run_proof(ws, full=True)

    assert [_unit(results, r) for r in ids] == [GateOutcome.FAILED, GateOutcome.FAILED]


def test_pytest_verdicts_reports_each_name(ws):
    from codeframe.core.gates import pytest_verdicts

    got = pytest_verdicts(Path(ws.repo_path), ["test_unit_a", "test_unit_b", "test_unit_skipped", "test_unit_gone"])

    assert got.problem is None
    assert got.verdicts == {
        "test_unit_a": "passed",
        "test_unit_b": "failed",
        "test_unit_skipped": "skipped",
        "test_unit_gone": None,
    }
