"""The proof report `cf pr create` appends to a PR body (#1273).

The README promised "Open a PR with proof report attached"; the body held only
commits and a diffstat. The report is built headlessly from the ledger.
"""

from datetime import datetime, timezone

import pytest

from codeframe.core.proof.ledger import init_proof_tables, save_requirement, save_run
from codeframe.core.proof.models import (
    Gate,
    Obligation,
    ProofRun,
    Requirement,
    RequirementScope,
    ReqStatus,
    Severity,
    Source,
)
from codeframe.core.proof.report import pr_proof_report
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    w = create_or_load_workspace(repo)
    init_proof_tables(w)
    return w


def _req(ws, req_id, title, status):
    save_requirement(ws, Requirement(
        id=req_id, title=title, description="d", severity=Severity.HIGH, source=Source.QA,
        scope=RequirementScope(), obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[], status=status, created_at=datetime.now(timezone.utc),
    ))


def _run(ws, passed, vacuous=False):
    now = datetime.now(timezone.utc)
    save_run(ws, ProofRun(
        run_id="run-1", workspace_id=ws.id, started_at=now, completed_at=now,
        triggered_by="human", overall_passed=passed, duration_ms=5, vacuous_pass=vacuous,
    ))


def test_an_empty_ledger_says_nothing_is_verified(ws):
    report = pr_proof_report(ws)
    assert report.startswith("## PROOF9")
    assert "No proof requirements" in report


def test_counts_and_open_requirements_are_listed(ws):
    _req(ws, "REQ-0001", "Login returns 500 on empty password", ReqStatus.OPEN)
    _req(ws, "REQ-0002", "Export drops the last row", ReqStatus.SATISFIED)
    _req(ws, "REQ-0003", "Legacy path", ReqStatus.WAIVED)

    report = pr_proof_report(ws)

    assert "1 open" in report and "1 satisfied" in report and "1 waived" in report
    assert "REQ-0001" in report and "Login returns 500 on empty password" in report
    assert "REQ-0002" not in report  # only the open ones are listed


def test_the_latest_run_is_reported(ws):
    _req(ws, "REQ-0001", "t", ReqStatus.SATISFIED)
    _run(ws, passed=True)
    assert "Latest run: passed" in pr_proof_report(ws)


def test_a_vacuous_pass_is_not_reported_as_a_pass(ws):
    """#1247: a pass that verified nothing must not read as green."""
    _req(ws, "REQ-0001", "t", ReqStatus.OPEN)
    _run(ws, passed=True, vacuous=True)
    report = pr_proof_report(ws)
    assert "verified nothing" in report
    assert "Latest run: passed" not in report


def test_no_run_yet_is_said(ws):
    _req(ws, "REQ-0001", "t", ReqStatus.OPEN)
    assert "No proof run yet" in pr_proof_report(ws)
