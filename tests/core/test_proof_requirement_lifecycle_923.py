"""PROOF9 requirement lifecycle defects (#923 / P1.5).

Five independent problems, each verified against the code first:

1. **A satisfied requirement is never re-verified.** ``run_proof`` loads only
   ``ReqStatus.OPEN`` and, on pass, sets ``SATISFIED`` — with no path that ever
   re-opens it. A later regression never re-fails, and the #731 merge gate
   (which inspects only *open* requirements) then blocks nothing.
2. **``satisfied_at`` is never assigned**, so the ledger column and the API
   field are permanently null.
3. **REQ ids collide.** ``next_req_id`` computes ``MAX+1`` and closes its
   connection; ``save_requirement`` then does ``INSERT OR REPLACE`` on a
   separate one. Two concurrent captures silently overwrite each other.
4. **Run lookup is cache-only.** ``GET /proof/runs/{run_id}`` reads a 300s
   in-process cache and 404s for runs that are durably persisted.
5. **A waiver is unattributable.** ``approved_by`` comes from the request body,
   so a merge-gate bypass records whatever the caller typed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


def _requirement(req_id: str, title: str = "t"):
    from codeframe.core.proof.models import (
        Gate,
        Obligation,
        ReqStatus,
        Requirement,
        RequirementScope,
        Severity,
        Source,
    )

    return Requirement(
        id=req_id,
        title=title,
        description="d",
        severity=Severity.HIGH,
        source=Source.QA,
        scope=RequirementScope(),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[],
        status=ReqStatus.OPEN,
    )


# ---------------------------------------------------------------------------
# 1 + 2. satisfied_at, and re-verification
# ---------------------------------------------------------------------------


class TestSatisfiedLifecycle:
    def test_satisfied_at_is_recorded(self, workspace):
        """AC1. The column and the API field were permanently null."""
        from codeframe.core.proof import ledger
        from codeframe.core.proof.models import ReqStatus

        req = _requirement("REQ-0001")
        ledger.save_requirement(workspace, req)

        ledger.mark_satisfied(workspace, req)

        stored = ledger.get_requirement(workspace, "REQ-0001")
        assert stored.status == ReqStatus.SATISFIED
        assert stored.satisfied_at is not None, "satisfied_at never assigned"

    def test_a_satisfied_requirement_is_loaded_by_a_full_run(self, workspace):
        """AC2. Loading only OPEN meant a regression could never re-fail."""
        from codeframe.core.proof import ledger
        from codeframe.core.proof.runner import _requirements_for_run

        satisfied = _requirement("REQ-0001")
        ledger.save_requirement(workspace, satisfied)
        ledger.mark_satisfied(workspace, satisfied)
        ledger.save_requirement(workspace, _requirement("REQ-0002"))

        ids = {r.id for r in _requirements_for_run(workspace, full=True)}

        assert ids == {"REQ-0001", "REQ-0002"}, (
            "a --full run must re-verify satisfied requirements, or a "
            "regression never re-fails and the merge gate blocks nothing"
        )

    def test_a_scoped_run_still_prioritises_open_requirements(self, workspace):
        """The default run keeps its cheaper behaviour."""
        from codeframe.core.proof import ledger
        from codeframe.core.proof.runner import _requirements_for_run

        satisfied = _requirement("REQ-0001")
        ledger.save_requirement(workspace, satisfied)
        ledger.mark_satisfied(workspace, satisfied)
        ledger.save_requirement(workspace, _requirement("REQ-0002"))

        ids = {r.id for r in _requirements_for_run(workspace, full=False)}

        assert "REQ-0002" in ids

    def test_a_satisfied_requirement_can_return_to_open(self, workspace):
        """AC2, the pass → break → re-fail path."""
        from codeframe.core.proof import ledger
        from codeframe.core.proof.models import ReqStatus

        req = _requirement("REQ-0001")
        ledger.save_requirement(workspace, req)
        ledger.mark_satisfied(workspace, req)

        ledger.reopen_requirement(workspace, req.id, reason="gate LINT regressed")

        stored = ledger.get_requirement(workspace, "REQ-0001")
        assert stored.status == ReqStatus.OPEN
        assert stored.satisfied_at is None, "a re-opened requirement is not satisfied"

    def test_reopening_a_waived_requirement_is_refused(self, workspace):
        """A waiver is a human decision; a gate result must not silently undo it."""
        from codeframe.core.proof import ledger
        from codeframe.core.proof.models import ReqStatus, Waiver

        req = _requirement("REQ-0001")
        req.status = ReqStatus.WAIVED
        req.waiver = Waiver(reason="accepted", expires=None,
                            manual_checklist=[], approved_by="alice")
        ledger.save_requirement(workspace, req)

        ledger.reopen_requirement(workspace, req.id, reason="regressed")

        assert ledger.get_requirement(workspace, "REQ-0001").status == ReqStatus.WAIVED


# ---------------------------------------------------------------------------
# 3. REQ id allocation
# ---------------------------------------------------------------------------


class TestReqIdAllocation:
    def test_concurrent_captures_get_distinct_ids(self, workspace):
        """AC3. MAX+1 outside a transaction plus INSERT OR REPLACE means two
        captures silently overwrite each other and share a stub directory."""
        from codeframe.core.proof import ledger

        def _capture(n: int) -> str:
            req_id = ledger.allocate_requirement(workspace, title=f"t{n}")
            return req_id

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(_capture, range(8)))

        assert len(set(ids)) == len(ids), f"colliding REQ ids: {sorted(ids)}"

    def test_save_refuses_to_clobber_an_existing_id(self, workspace):
        """AC3. INSERT OR REPLACE let a second capture overwrite the first."""
        from codeframe.core.proof import ledger

        ledger.save_requirement(workspace, _requirement("REQ-0001", title="first"))

        with pytest.raises(ValueError):
            ledger.save_requirement(
                workspace, _requirement("REQ-0001", title="second"), create_only=True
            )

        assert ledger.get_requirement(workspace, "REQ-0001").title == "first"

    def test_an_ordinary_update_still_works(self, workspace):
        """The runner updates requirements in place on every run."""
        from codeframe.core.proof import ledger

        req = _requirement("REQ-0001", title="first")
        ledger.save_requirement(workspace, req)

        req.title = "updated"
        ledger.save_requirement(workspace, req)

        assert ledger.get_requirement(workspace, "REQ-0001").title == "updated"


# ---------------------------------------------------------------------------
# 4. Durable run lookup
# ---------------------------------------------------------------------------


class TestRunLookupFallsBackToLedger:
    def test_a_persisted_run_resolves_after_the_cache_expires(self, workspace):
        """AC4. The endpoint read only a 300s in-process cache, so a durably
        persisted run 404'd after expiry or a restart."""
        from datetime import datetime, timezone

        from codeframe.core.proof import ledger
        from codeframe.core.proof.models import ProofRun

        started = datetime.now(timezone.utc)
        ledger.save_run(
            workspace,
            ProofRun(
                run_id="run-923", workspace_id=workspace.id, started_at=started,
                completed_at=started, triggered_by="human", overall_passed=True,
                duration_ms=1,
            ),
        )

        assert ledger.get_run(workspace, "run-923") is not None


# ---------------------------------------------------------------------------
# 5. Waiver attribution
# ---------------------------------------------------------------------------


class TestWaiverAttribution:
    def test_the_request_model_no_longer_carries_approved_by(self):
        """AC5. Taken from the body, a merge-gate bypass records whatever the
        caller typed — the one field that must be the authenticated principal."""
        from codeframe.ui.routers.proof_v2 import WaiveRequirementRequest as WaiveRequest

        assert "approved_by" not in WaiveRequest.model_fields, (
            "approved_by must come from require_auth, not the request body"
        )

    def test_the_capture_model_no_longer_carries_created_by(self):
        from codeframe.ui.routers.proof_v2 import CaptureRequirementRequest as CaptureRequest

        assert "created_by" not in CaptureRequest.model_fields
