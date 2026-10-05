"""A lapsed waiver is not presented as plainly "waived" (#1360).

Since #1276 the merge gate blocks on a WAIVED requirement whose waiver expired,
read-only; reverting the status to OPEN is `check_expired_waivers`'s job. The
status readers kept counting it as waived, so the /proof page could show
"0 open" while a merge was refused for that very requirement.
"""

from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from codeframe.core.proof import ledger
from codeframe.core.proof.models import (
    Gate, Obligation, Requirement, RequirementScope, ReqStatus, Severity, Source, Waiver,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _req(rid, expires):
    return Requirement(
        id=rid, title=rid, description="d", severity=Severity.HIGH, source=Source.QA, scope=RequirementScope(),
        obligations=[Obligation(gate=Gate.UNIT)], evidence_rules=[], status=ReqStatus.WAIVED,
        waiver=Waiver(reason="r", expires=expires),
    )


@pytest.fixture
def ws(tmp_path):
    w = create_or_load_workspace(tmp_path)
    ledger.init_proof_tables(w)
    ledger.save_requirement(w, _req("REQ-0001", date.today() - timedelta(days=2)))  # lapsed
    ledger.save_requirement(w, _req("REQ-0002", date.today() + timedelta(days=30)))  # live
    return w


@pytest.fixture
def client(ws):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import proof_v2

    app = FastAPI()
    app.include_router(proof_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: ws
    return TestClient(app)


def test_status_counts_a_lapsed_waiver_separately(client):
    body = client.get("/api/v2/proof/status").json()
    assert body["waived"] == 1, body
    assert body["waiver_expired"] == 1, body
    flags = {r["id"]: r["waiver_expired"] for r in body["requirements"]}
    assert flags == {"REQ-0001": True, "REQ-0002": False}


def test_the_requirements_list_the_proof_page_reads_agrees(client):
    body = client.get("/api/v2/proof/requirements").json()
    assert body["by_status"]["waived"] == 1, body["by_status"]
    assert body["by_status"]["waiver_expired"] == 1, body["by_status"]


def test_reading_status_writes_nothing(client, ws):
    """Read-only, like the merge gate: reverting stays check_expired_waivers's job."""
    client.get("/api/v2/proof/status")
    assert ledger.get_requirement(ws, "REQ-0001").status == ReqStatus.WAIVED


def test_cf_proof_status_already_reverts_it(ws):
    """The CLI half of the issue: `cf proof status` runs check_expired_waivers
    first, so it reports the lapsed one as open, not waived."""
    from codeframe.cli.app import app

    result = CliRunner().invoke(app, ["proof", "status", "-w", str(ws.repo_path)])
    assert result.exit_code == 0, result.output
    assert "Expired 1 waivers" in result.output
    assert ledger.get_requirement(ws, "REQ-0001").status == ReqStatus.OPEN
