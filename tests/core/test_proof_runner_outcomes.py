"""Tests for the tri-state gate outcome model (issue #728).

The 6 PROOF9 gates without an automated runner (e2e, visual, a11y, perf,
demo, manual) must return an explicit UNVERIFIABLE outcome instead of a
perpetual FAIL. UNVERIFIABLE:
- never satisfies a requirement (it stays OPEN and waivable)
- never fails a run (overall_passed excludes it)
- is distinct from a gate that ran and failed
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.proof.ledger import (
    get_run,
    init_proof_tables,
    list_evidence,
    save_requirement,
)
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    Gate,
    GateOutcome,
    Obligation,
    Requirement,
    RequirementScope,
    ReqStatus,
    Severity,
    Source,
)
from codeframe.core.proof.runner import _run_gate, run_proof
from codeframe.core.workspace import Workspace, create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    ws = create_or_load_workspace(tmp_path)
    init_proof_tables(ws)
    return ws


def _make_req(req_id: str, gates: list[Gate]) -> Requirement:
    return Requirement(
        id=req_id,
        title=f"Test {req_id}",
        description="test",
        severity=Severity.MEDIUM,
        source=Source.QA,
        scope=RequirementScope(files=["x.py"]),
        obligations=[Obligation(gate=g) for g in gates],
        evidence_rules=[],
        status=ReqStatus.OPEN,
        created_at=datetime.now(timezone.utc),
    )


class TestGateOutcomeEnum:
    def test_values(self):
        assert GateOutcome.PASSED == "passed"
        assert GateOutcome.FAILED == "failed"
        assert GateOutcome.UNVERIFIABLE == "unverifiable"

    def test_str_enum(self):
        assert GateOutcome.UNVERIFIABLE.value == "unverifiable"
        assert isinstance(GateOutcome.PASSED, str)


class TestRunGateOutcome:
    """_run_gate returns (GateOutcome, str)."""

    def test_unmapped_gate_is_unverifiable(self, workspace):
        outcome, output = _run_gate(workspace, Gate.E2E)
        assert outcome == GateOutcome.UNVERIFIABLE
        assert "cannot verify" in output

    def test_mapped_gate_passed(self, workspace):
        from codeframe.core.gates import GateResult

        fake = GateResult(passed=True, checks=[])
        with patch("codeframe.core.gates.run", return_value=fake):
            outcome, _ = _run_gate(workspace, Gate.UNIT)
        assert outcome == GateOutcome.PASSED

    def test_mapped_gate_failed(self, workspace):
        from codeframe.core.gates import GateResult

        fake = GateResult(passed=False, checks=[])
        with patch("codeframe.core.gates.run", return_value=fake):
            outcome, _ = _run_gate(workspace, Gate.UNIT)
        assert outcome == GateOutcome.FAILED

    def test_exception_path_is_failed(self, workspace):
        with patch("codeframe.core.gates.run", side_effect=RuntimeError("boom")):
            outcome, output = _run_gate(workspace, Gate.UNIT)
        assert outcome == GateOutcome.FAILED
        assert "boom" in output


class TestUnverifiableRollup:
    """Unverifiable obligations keep the requirement OPEN and do not fail runs."""

    def test_unverifiable_keeps_req_open(self, workspace):
        # UI_WIRING_BUG maps to [E2E, DEMO], both unmapped → unverifiable.
        save_requirement(workspace, _make_req("REQ-U1", [Gate.E2E, Gate.DEMO]))

        results = run_proof(workspace, full=True, run_id="unverif-run")

        outcomes = [o for _, o in results["REQ-U1"]]
        assert all(o == GateOutcome.UNVERIFIABLE for o in outcomes)

        from codeframe.core.proof.ledger import get_requirement

        req = get_requirement(workspace, "REQ-U1")
        assert req.status == ReqStatus.OPEN

    def test_unverifiable_only_run_passes(self, workspace):
        save_requirement(workspace, _make_req("REQ-U2", [Gate.E2E]))

        run_proof(workspace, full=True, run_id="unverif-only")

        run = get_run(workspace, "unverif-only")
        assert run is not None
        assert run.overall_passed is True

    def test_unverifiable_obligation_status_persisted(self, workspace):
        save_requirement(workspace, _make_req("REQ-U3", [Gate.E2E]))
        run_proof(workspace, full=True, run_id="unverif-status")

        from codeframe.core.proof.ledger import get_requirement

        req = get_requirement(workspace, "REQ-U3")
        assert req.obligations[0].status == "unverifiable"

    def test_unverifiable_evidence_not_satisfied(self, workspace):
        save_requirement(workspace, _make_req("REQ-U4", [Gate.E2E]))
        run_proof(workspace, full=True, run_id="unverif-ev")

        evidence = list_evidence(workspace, "REQ-U4")
        assert len(evidence) == 1
        assert evidence[0].satisfied is False
        assert evidence[0].status == "unverifiable"

    def test_mixed_pass_and_unverifiable_stays_open(self, workspace):
        # UNIT (mapped, passes) + E2E (unmapped, unverifiable).
        save_requirement(workspace, _make_req("REQ-U5", [Gate.UNIT, Gate.E2E]))

        with patch(
            "codeframe.core.proof.runner._run_gate",
            side_effect=lambda ws, gate, rules=(): (
                (GateOutcome.PASSED, "ok")
                if gate == Gate.UNIT
                else (GateOutcome.UNVERIFIABLE, "cannot verify")
            ),
        ):
            run_proof(workspace, full=True, run_id="mixed-run")

        from codeframe.core.proof.ledger import get_requirement

        req = get_requirement(workspace, "REQ-U5")
        # A partially-unverifiable requirement is not satisfied.
        assert req.status == ReqStatus.OPEN
        run = get_run(workspace, "mixed-run")
        # But the run passes — nothing actually failed.
        assert run.overall_passed is True


class TestRealFailureStillFails:
    """A gate that ran and failed still fails the run (unchanged semantics)."""

    def test_real_failure_fails_strict(self, workspace):
        save_requirement(workspace, _make_req("REQ-F1", [Gate.UNIT]))
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": ["unit"], "strictness": "strict"})
        )
        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(GateOutcome.FAILED, "boom"),
        ):
            run_proof(workspace, full=True, run_id="fail-strict")
        run = get_run(workspace, "fail-strict")
        assert run.overall_passed is False

    def test_real_failure_warns(self, workspace):
        save_requirement(workspace, _make_req("REQ-F2", [Gate.UNIT]))
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            json.dumps({"enabled_gates": ["unit"], "strictness": "warn"})
        )
        with patch(
            "codeframe.core.proof.runner._run_gate",
            return_value=(GateOutcome.FAILED, "boom"),
        ):
            run_proof(workspace, full=True, run_id="fail-warn")
        run = get_run(workspace, "fail-warn")
        assert run.overall_passed is True

    def test_failure_plus_unverifiable_fails_strict(self, workspace):
        save_requirement(workspace, _make_req("REQ-F3", [Gate.UNIT, Gate.E2E]))
        with patch(
            "codeframe.core.proof.runner._run_gate",
            side_effect=lambda ws, gate, rules=(): (
                (GateOutcome.FAILED, "boom")
                if gate == Gate.UNIT
                else (GateOutcome.UNVERIFIABLE, "cannot verify")
            ),
        ):
            run_proof(workspace, full=True, run_id="fail-plus-unverif")
        run = get_run(workspace, "fail-plus-unverif")
        assert run.overall_passed is False
