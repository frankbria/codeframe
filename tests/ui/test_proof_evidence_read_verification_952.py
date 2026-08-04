"""Evidence read endpoints must not present tampered artifacts as proof (#952).

AC3 is about *reads*. Verification reached the merge gate, but the two public
evidence endpoints still serialized `satisfied` straight from the ledger and
served the artifact's current bytes alongside it — so after editing a file, the
UI showed a pass next to forged text (codex review on #1080).
"""


import pytest
from fastapi.testclient import TestClient

from codeframe.core.proof.evidence import attach_evidence
from codeframe.core.proof.ledger import save_requirement, save_run
from codeframe.core.proof.models import (
    Gate,
    GateOutcome,
    Obligation,
    ProofRun,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


@pytest.fixture
def client():
    from codeframe.ui.server import app

    return TestClient(app)


@pytest.fixture
def seeded(workspace, tmp_path):
    from datetime import datetime, timezone

    req = Requirement(
        id="REQ-READ-01",
        title="proven",
        description="d",
        severity=Severity.MEDIUM,
        source=Source.QA,
        scope=RequirementScope(),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[],
    )
    save_requirement(workspace, req)

    artifact = tmp_path / "artifact.txt"
    artifact.write_text("gate output the run actually saw")
    run_id = "11111111-2222-3333-4444-555555555555"
    save_run(
        workspace,
        ProofRun(
            run_id=run_id,
            workspace_id=workspace.id,
            duration_ms=1,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            triggered_by="test",
            overall_passed=True,
        ),
    )
    attach_evidence(
        workspace, req.id, Gate.UNIT, str(artifact), GateOutcome.PASSED, run_id
    )
    return req, artifact, run_id


def _params(workspace):
    return {"workspace_path": str(workspace.repo_path)}


class TestRequirementEvidenceRead:
    def test_intact_evidence_reports_verified(self, client, workspace, seeded):
        req, _, _ = seeded
        r = client.get(f"/api/v2/proof/requirements/{req.id}/evidence", params=_params(workspace))
        assert r.status_code == 200
        assert [e["verified"] for e in r.json()] == [True]

    def test_a_tampered_artifact_reports_unverified(self, client, workspace, seeded):
        req, artifact, _ = seeded
        artifact.write_text("forged: everything passed")

        r = client.get(f"/api/v2/proof/requirements/{req.id}/evidence", params=_params(workspace))

        assert r.status_code == 200
        item = r.json()[0]
        assert item["verified"] is False, (
            "the API presented a tampered artifact as verified evidence"
        )
        assert item["tamper_detail"]


class TestRunEvidenceRead:
    def test_intact_run_evidence_serves_its_text(self, client, workspace, seeded):
        _, _, run_id = seeded
        r = client.get(f"/api/v2/proof/runs/{run_id}/evidence", params=_params(workspace))
        assert r.status_code == 200
        ev = r.json()["evidence"][0]
        assert ev["verified"] is True
        assert "gate output the run actually saw" in ev["artifact_text"]

    def test_a_tampered_artifacts_text_is_withheld(self, client, workspace, seeded):
        _, artifact, run_id = seeded
        artifact.write_text("forged: everything passed")

        r = client.get(f"/api/v2/proof/runs/{run_id}/evidence", params=_params(workspace))

        ev = r.json()["evidence"][0]
        assert ev["verified"] is False
        assert ev["artifact_text"] is None, (
            "forged artifact contents were served as evidence text"
        )

    def test_a_deleted_artifact_reports_unverified(self, client, workspace, seeded):
        _, artifact, run_id = seeded
        artifact.unlink()

        ev = client.get(f"/api/v2/proof/runs/{run_id}/evidence", params=_params(workspace)).json()["evidence"][0]

        assert ev["verified"] is False
        assert ev["artifact_text"] is None

    def test_one_bad_artifact_does_not_break_the_whole_listing(
        self, client, workspace, seeded, tmp_path
    ):
        """Reported per record, not raised — the caller needs to see which."""
        req, artifact, run_id = seeded
        good = tmp_path / "good.txt"
        good.write_text("second gate output")
        attach_evidence(workspace, req.id, Gate.SEC, str(good), GateOutcome.PASSED, run_id)
        artifact.write_text("forged")

        r = client.get(f"/api/v2/proof/runs/{run_id}/evidence", params=_params(workspace))

        assert r.status_code == 200
        by_gate = {e["gate"]: e["verified"] for e in r.json()["evidence"]}
        assert by_gate == {"unit": False, "sec": True}


class TestUnverifiedEvidenceIsNotServedAsAPass:
    """`verified: false` beside an unchanged `satisfied: true` is not enough.

    Every existing client renders green from `satisfied`/`status` and knows
    nothing about the new fields, so a tampered artifact still showed as
    passing proof — just without its text (codex review on #1080).
    """

    def test_a_tampered_record_is_not_satisfied(self, client, workspace, seeded):
        req, artifact, _ = seeded
        artifact.write_text("forged: everything passed")

        item = client.get(
            f"/api/v2/proof/requirements/{req.id}/evidence", params=_params(workspace)
        ).json()[0]

        assert item["satisfied"] is False, (
            "a client rendering green from `satisfied` still shows tampered "
            "evidence as proof"
        )
        assert item["status"] == "unverifiable"
        assert item["verified"] is False

    def test_a_tampered_run_record_is_not_satisfied(self, client, workspace, seeded):
        _, artifact, run_id = seeded
        artifact.write_text("forged")

        ev = client.get(
            f"/api/v2/proof/runs/{run_id}/evidence", params=_params(workspace)
        ).json()["evidence"][0]

        assert ev["satisfied"] is False
        assert ev["status"] == "unverifiable"

    def test_an_intact_record_keeps_its_real_outcome(self, client, workspace, seeded):
        """The downgrade must apply only to records that fail verification."""
        req, _, _ = seeded

        item = client.get(
            f"/api/v2/proof/requirements/{req.id}/evidence", params=_params(workspace)
        ).json()[0]

        assert item["satisfied"] is True
        assert item["status"] == "passed"
        assert item["verified"] is True
