"""`vacuous_pass` is carried across the proof API surface (#1247 AC2).

The flag is only useful if it survives the trip to the client that renders the
run. It has to appear on the synchronous POST response, on the cached GET, on
the ledger-recovered GET after that cache expires, and on the run list the
history panel reads — four paths that build their responses separately.
"""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.proof.ledger import init_proof_tables, save_requirement
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    Gate,
    GateOutcome,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)

pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "ws"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)
    init_proof_tables(workspace)
    yield workspace
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import proof_v2

    app = FastAPI()
    app.include_router(proof_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: test_workspace
    return TestClient(app)


def _seed(workspace, *, disable_all_gates: bool) -> None:
    save_requirement(
        workspace,
        Requirement(
            id="REQ-1",
            title="Test REQ-1",
            description="test",
            severity=Severity.MEDIUM,
            source=Source.QA,
            scope=RequirementScope(files=["x.py"]),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
            status=ReqStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        ),
    )
    if disable_all_gates:
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": [], "strictness": "strict"})
        )


def _run(test_client):
    with patch(
        "codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "")
    ):
        resp = test_client.post("/api/v2/proof/run", json={"full": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestVacuousPassOverTheApi:
    def test_post_run_reports_vacuous_pass(self, test_client, test_workspace):
        _seed(test_workspace, disable_all_gates=True)
        assert _run(test_client)["vacuous_pass"] is True

    def test_post_run_reports_a_real_pass_as_not_vacuous(self, test_client, test_workspace):
        _seed(test_workspace, disable_all_gates=False)
        assert _run(test_client)["vacuous_pass"] is False

    def test_cached_get_carries_the_flag(self, test_client, test_workspace):
        _seed(test_workspace, disable_all_gates=True)
        run_id = _run(test_client)["run_id"]

        resp = test_client.get(f"/api/v2/proof/runs/{run_id}")

        assert resp.status_code == 200
        assert resp.json()["vacuous_pass"] is True

    def test_ledger_recovered_get_carries_the_flag(self, test_client, test_workspace):
        """The in-process cache expires; the durable row must still say so."""
        from codeframe.ui.routers import proof_v2

        _seed(test_workspace, disable_all_gates=True)
        run_id = _run(test_client)["run_id"]
        proof_v2._run_cache.clear()

        resp = test_client.get(f"/api/v2/proof/runs/{run_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["vacuous_pass"] is True
        assert body["passed"] is True

    def test_run_list_carries_the_flag(self, test_client, test_workspace):
        _seed(test_workspace, disable_all_gates=True)
        run_id = _run(test_client)["run_id"]

        resp = test_client.get("/api/v2/proof/runs")

        assert resp.status_code == 200
        runs = {r["run_id"]: r for r in resp.json()}
        assert runs[run_id]["overall_passed"] is True
        assert runs[run_id]["vacuous_pass"] is True
