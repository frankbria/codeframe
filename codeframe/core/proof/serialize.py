"""JSON documents for `cf proof … --json` (#1488).

The proof9 plugin reads these instead of parsing Rich tables. Every value is
plain data (str, int, bool, None, list, dict), user text is passed through
verbatim, and nothing here reports a status the ledger does not hold.

A run's verdict is three fields, not one, because a run that verified nothing
is neither a pass nor a failure (#1118):

- ``failed``: an obligation failed (the CLI exits 1);
- ``passed``: obligations ran and none failed;
- neither: nothing ran, and ``empty_reason`` says why. The exit code then
  depends on that reason and ``--allow-empty``, exactly as without ``--json``.

``vacuous`` marks a run that passed without verifying anything (#1247).

A command that fails before it has a result (no workspace, an unknown
requirement, a suite that cannot run) writes nothing to stdout.
"""

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

from codeframe.core.proof.models import (
    Evidence,
    Gate,
    GateOutcome,
    ProofRun,
    ReqStatus,
    Requirement,
    Source,
)

if TYPE_CHECKING:
    from codeframe.core.proof.ratchet import RatchetResult, SuiteResult


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def requirement_to_dict(req: Requirement, today: Optional[date] = None) -> dict:
    from codeframe.core.proof.ledger import waiver_expired

    waiver = None
    if req.waiver:
        waiver = {
            "reason": req.waiver.reason,
            "expires": _iso(req.waiver.expires),
            "expired": waiver_expired(req, today),
            "approved_by": req.waiver.approved_by,
            "waived_at": _iso(req.waiver.waived_at),
            "manual_checklist": list(req.waiver.manual_checklist),
        }
    return {
        "id": req.id,
        "title": req.title,
        "description": req.description,
        "severity": req.severity.value,
        "source": req.source.value,
        "status": req.status.value,
        "glitch_type": req.glitch_type.value if req.glitch_type else None,
        "source_issue": req.source_issue,
        "created_at": _iso(req.created_at),
        "satisfied_at": _iso(req.satisfied_at),
        "scope": {
            "files": list(req.scope.files),
            "routes": list(req.scope.routes),
            "apis": list(req.scope.apis),
            "components": list(req.scope.components),
            "tags": list(req.scope.tags),
        },
        "obligations": [{"gate": o.gate.value, "status": o.status} for o in req.obligations],
        "evidence_rules": [
            {
                "test_id": r.test_id,
                "gate": r.gate.value if r.gate else None,
                "must_pass": r.must_pass,
            }
            for r in req.evidence_rules
        ],
        "waiver": waiver,
    }


def evidence_to_dict(ev: Evidence) -> dict:
    # Legacy rows (status=None) fall back to the satisfied bool, as `cf proof show` does.
    status = ev.status or ("passed" if ev.satisfied else "failed")
    return {
        "gate": ev.gate.value,
        "status": status,
        "artifact_path": ev.artifact_path,
        "artifact_checksum": ev.artifact_checksum,
        "run_id": ev.run_id,
        "timestamp": _iso(ev.timestamp),
    }


def is_failing(req: Requirement) -> bool:
    """Not waived, and an obligation's last recorded outcome was a failure."""
    return req.status != ReqStatus.WAIVED and any(o.status == "failed" for o in req.obligations)


def run_summary(run: ProofRun) -> dict:
    return {
        "run_id": run.run_id,
        "started_at": _iso(run.started_at),
        "passed": run.overall_passed,
        "vacuous": run.vacuous_pass,
        "duration_ms": run.duration_ms,
    }


def status_document(reqs: list[Requirement], expired: list[Requirement]) -> dict:
    counts = {"total": len(reqs), "open": 0, "satisfied": 0, "waived": 0, "failing": 0, "locked": 0}
    for req in reqs:
        counts[req.status.value] = counts.get(req.status.value, 0) + 1
        counts["failing"] += is_failing(req)
        counts["locked"] += req.source == Source.RATCHET
    return {"counts": counts, "expired_waivers": [r.id for r in expired]}


def list_document(reqs: list[Requirement], runs: Sequence[ProofRun]) -> dict:
    """``cf proof list --json``: the requirements and, newest first, recent runs
    (#1491). Read-only — unlike ``status``, which reverts expired waivers — so the
    proof9 pane can read the ledger without changing it."""
    return {
        "requirements": [requirement_to_dict(r) for r in reqs],
        "runs": [run_summary(r) for r in runs],
    }


def capture_document(
    req: Requirement,
    stubs: dict[Gate, Path],
    repo_root: Path,
    *,
    workspace_created: bool,
    warnings: list[str],
) -> dict:
    def _rel(path: Path) -> str:
        try:
            return str(path.relative_to(repo_root))
        except ValueError:
            return str(path)

    return {
        "requirement": requirement_to_dict(req),
        "stubs": {gate.value: _rel(path) for gate, path in stubs.items()},
        "workspace_created": workspace_created,
        "warnings": warnings,
    }


def ratchet_document(
    suite: "SuiteResult",
    result: Optional["RatchetResult"],
    *,
    dry_run: bool,
    workspace_created: bool,
) -> dict:
    """``result`` is None when nothing was eligible to lock in."""
    return {
        "dry_run": dry_run,
        "workspace_created": workspace_created,
        "locked": dict(result.locked) if result else {},
        "req_ids": list(result.req_ids) if result else [],
        "already_locked": list(result.already_locked) if result else [],
        "failed": list(suite.failed),
        "skipped": list(suite.skipped),
        "unenforceable": list(suite.unenforceable),
        "per_test_scope": suite.per_file_scope,
    }


def run_document(
    *,
    run_id: str,
    full: bool,
    gate_filter: Optional[Gate],
    results: dict[str, list[tuple[Gate, GateOutcome]]],
    before: dict[str, Requirement],
    after: dict[str, Requirement],
    vacuous: bool,
    empty_reason: Optional[str],
    description: Optional[str],
) -> dict:
    requirements = []
    for req_id, gate_results in results.items():
        req = after.get(req_id) or before.get(req_id)
        prior = before.get(req_id)
        requirements.append({
            "id": req_id,
            "title": req.title if req else None,
            "status_before": prior.status.value if prior else None,
            "status_after": after[req_id].status.value if req_id in after else None,
            "gates": [
                {
                    "gate": gate.value,
                    "outcome": outcome.value,
                    "tests": [
                        r.test_id for r in (req.evidence_rules if req else []) if r.gate == gate
                    ],
                }
                for gate, outcome in gate_results
            ],
        })
    failed = any(o == GateOutcome.FAILED for gr in results.values() for _, o in gr)
    return {
        "run_id": run_id,
        "mode": "full" if full else "scope",
        "gate": gate_filter.value if gate_filter else None,
        "passed": bool(results) and not failed,
        "failed": failed,
        "vacuous": vacuous,
        "empty_reason": empty_reason,
        "description": description,
        "requirements": requirements,
    }
