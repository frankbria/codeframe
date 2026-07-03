"""PROOF9 runner — executes obligations and collects evidence.

Determines which requirements apply to the current changes,
runs their obligations via the existing gates infrastructure,
and attaches evidence artifacts.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import attach_evidence
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    EvidenceRule,
    Gate,
    GateOutcome,
    ProofRun,
    ReqStatus,
)
from codeframe.core.proof.scope import get_changed_scope, intersects
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


def _load_proof_config(workspace: Workspace) -> tuple[Optional[set[Gate]], str]:
    """Load (enabled_gates, strictness) from .codeframe/proof_config.json.

    Returns:
        (enabled_gates, strictness). enabled_gates is None when no config file
        exists (meaning "all gates allowed"); a set of Gate enums otherwise.
        strictness defaults to 'strict' when missing or invalid.
    """
    path = workspace.state_dir / PROOF_CONFIG_FILENAME
    if not path.exists():
        return None, "strict"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Invalid %s — using defaults: %s", PROOF_CONFIG_FILENAME, exc)
        return None, "strict"

    enabled: Optional[set[Gate]] = None
    gates_raw = data.get("enabled_gates")
    if isinstance(gates_raw, list):
        enabled = set()
        valid_values = {g.value for g in Gate}
        for name in gates_raw:
            if name in valid_values:
                enabled.add(Gate(name))
            else:
                logger.warning(
                    "Unknown gate name '%s' in %s — skipped (valid: %s)",
                    name,
                    PROOF_CONFIG_FILENAME,
                    valid_values,
                )

    strictness = data.get("strictness", "strict")
    if strictness not in ("strict", "warn"):
        strictness = "strict"
    return enabled, strictness


# Map PROOF9 gates to existing core/gates.py gate names
_GATE_TO_CORE: dict[Gate, str] = {
    Gate.UNIT: "pytest",
    Gate.CONTRACT: "pytest",
    Gate.SEC: "ruff",
}

# Map a gate outcome to the persisted obligation status string.
_OUTCOME_TO_OBLIGATION_STATUS: dict[GateOutcome, str] = {
    GateOutcome.PASSED: "satisfied",
    GateOutcome.FAILED: "failed",
    GateOutcome.UNVERIFIABLE: "unverifiable",
}


def _run_gate(
    workspace: Workspace,
    gate: Gate,
    rules: Sequence[EvidenceRule] = (),
) -> tuple[GateOutcome, str]:
    """Execute a single gate and return (outcome, output).

    Uses core/gates.py for gates that have direct tool support. Gates without
    an automated runner return UNVERIFIABLE — the obligation could not be
    checked, which is distinct from running and failing.

    For pytest-backed gates, each ``must_pass`` evidence rule is enforced
    individually: pytest runs scoped to the rule's ``test_id`` (via ``-k``),
    and a named test that doesn't exist is a FAILED obligation — a green
    whole-suite run proves nothing about a test that was never written.
    Rules with ``must_pass=False`` are informational only.

    Each enforced rule deliberately gets its own pytest subprocess — do not
    collapse them into one ``-k "a or b"`` run; per-rule exit codes are what
    distinguish "named test missing" from "collected but failing".
    """
    core_gate_name = _GATE_TO_CORE.get(gate)
    if not core_gate_name:
        return (
            GateOutcome.UNVERIFIABLE,
            f"Gate {gate.value} has no automated runner — cannot verify",
        )

    try:
        from codeframe.core import gates as core_gates

        # Only pytest-style test_ids can be enforced by a scoped pytest run;
        # e.g. SEC's test_sec_* rules are pytest tests even though the SEC
        # gate's own runner is ruff.
        enforced = [r for r in rules if r.must_pass and r.test_id.startswith("test_")]

        lines: list[str] = []
        all_passed = True

        for rule in enforced:
            result = core_gates.run(
                workspace,
                gates=["pytest"],
                verbose=False,
                test_selector=rule.test_id,
            )
            check = result.checks[0] if result.checks else None
            if check is None:
                lines.append(f"{rule.test_id}: FAILED — no gate check returned")
                all_passed = False
            elif check.exit_code == 5:
                lines.append(f"{rule.test_id}: FAILED — named test missing (not collected)")
                all_passed = False
            elif result.passed:
                lines.append(f"{rule.test_id}: passed")
            else:
                lines.append(f"{rule.test_id}: FAILED")
                all_passed = False

        # Run the gate's own runner unless it is pytest and the enforced rules
        # already covered it (scoped runs replace the whole-suite run).
        if core_gate_name != "pytest" or not enforced:
            result = core_gates.run(workspace, gates=[core_gate_name], verbose=False)
            lines.extend(
                f"{check.name}: {check.status.value}" for check in result.checks
            )
            all_passed = all_passed and result.passed

        for rule in rules:
            if not rule.must_pass:
                lines.append(f"{rule.test_id}: informational (must_pass=False, not enforced)")

        outcome = GateOutcome.PASSED if all_passed else GateOutcome.FAILED
        return outcome, "\n".join(lines)
    except Exception as exc:
        logger.warning("Gate %s failed to run: %s", gate.value, exc)
        return GateOutcome.FAILED, str(exc)


def run_proof(
    workspace: Workspace,
    *,
    full: bool = False,
    gate_filter: Optional[Gate] = None,
    run_id: Optional[str] = None,
) -> dict[str, list[tuple[Gate, GateOutcome]]]:
    """Execute proof obligations and collect evidence.

    Args:
        workspace: Target workspace
        full: If True, run ALL obligations regardless of scope
        gate_filter: If set, only run this specific gate
        run_id: Unique run identifier (auto-generated if not provided)

    Returns:
        Dict mapping req_id → list of (Gate, GateOutcome) tuples
    """
    if not run_id:
        run_id = str(uuid.uuid4())[:8]

    started_at = datetime.now(timezone.utc)

    # Load PROOF9 config (enabled gates + strictness)
    enabled_gates, strictness = _load_proof_config(workspace)

    # Expire any stale waivers
    expired = ledger.check_expired_waivers(workspace)
    if expired:
        logger.info("Expired %d waivers", len(expired))

    # Get all open requirements
    reqs = ledger.list_requirements(workspace, status=ReqStatus.OPEN)
    if not reqs:
        completed_at = datetime.now(timezone.utc)
        ledger.save_run(
            workspace,
            ProofRun(
                run_id=run_id,
                workspace_id=workspace.id,
                started_at=started_at,
                completed_at=completed_at,
                triggered_by="human",
                overall_passed=True,
                duration_ms=int((completed_at - started_at).total_seconds() * 1000),
            ),
        )
        return {}

    # Warn loudly when config disables every gate — a "vacuous pass" is
    # easy to overlook: nothing runs, overall_passed=True, no evidence.
    if enabled_gates is not None and not enabled_gates:
        logger.warning(
            "Proof run %s: all 9 gates are disabled by proof_config.json — "
            "no obligations will run and the run will pass vacuously",
            run_id,
        )

    # Get changed scope (skip if running full)
    changed_scope = None
    if not full:
        changed_scope = get_changed_scope(workspace)

    results: dict[str, list[tuple[Gate, GateOutcome]]] = {}
    artifact_dir = workspace.state_dir / "proof_artifacts"
    artifact_dir.mkdir(exist_ok=True)

    for req in reqs:
        # Check scope intersection (unless full mode or scope detection failed)
        # None changed_scope means "failed to detect" → run everything (fail closed)
        if not full and changed_scope is not None:
            if not intersects(req.scope, changed_scope):
                continue

        req_results: list[tuple[Gate, GateOutcome]] = []

        unresolved = [r.test_id for r in req.evidence_rules if r.gate is None]
        if unresolved:
            logger.warning(
                "REQ %s: %d evidence rule(s) with no resolvable gate are not enforced: %s",
                req.id, len(unresolved), unresolved,
            )

        for obl in req.obligations:
            # Apply gate filter
            if gate_filter and obl.gate != gate_filter:
                continue

            # Apply config-driven gate filter (None means "all allowed")
            if enabled_gates is not None and obl.gate not in enabled_gates:
                continue

            # Run the gate, enforcing this requirement's evidence rules for it
            gate_rules = [r for r in req.evidence_rules if r.gate == obl.gate]
            outcome, output = _run_gate(workspace, obl.gate, gate_rules)

            # Write artifact
            artifact_path = artifact_dir / f"{req.id}_{obl.gate.value}_{run_id}.txt"
            artifact_path.write_text(output)

            # Attach evidence
            attach_evidence(
                workspace, req.id, obl.gate,
                str(artifact_path), outcome, run_id,
            )

            # Update obligation status
            obl.status = _OUTCOME_TO_OBLIGATION_STATUS[outcome]
            req_results.append((obl.gate, outcome))

        if req_results:
            results[req.id] = req_results

            # Always persist obligation status updates. A requirement is only
            # SATISFIED when every obligation PASSED and all obligations ran —
            # an unverifiable obligation leaves it OPEN (and waivable).
            all_passed = all(o == GateOutcome.PASSED for _, o in req_results)
            if all_passed and len(req_results) == len(req.obligations):
                req.status = ReqStatus.SATISFIED
            ledger.save_requirement(workspace, req)

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    # Only gates that actually ran (passed or failed) count toward the tally;
    # unverifiable gates neither pass nor fail, so a run with only unverifiable
    # outcomes passes.
    executed = [
        outcome == GateOutcome.PASSED
        for gate_results in results.values()
        for _, outcome in gate_results
        if outcome != GateOutcome.UNVERIFIABLE
    ]
    all_passed = all(executed) if executed else True
    if not all_passed and strictness == "warn":
        logger.warning(
            "Proof run %s had gate failures but strictness='warn' — overall_passed=True",
            run_id,
        )
        overall_passed = True
    else:
        overall_passed = all_passed
    ledger.save_run(
        workspace,
        ProofRun(
            run_id=run_id,
            workspace_id=workspace.id,
            started_at=started_at,
            completed_at=completed_at,
            triggered_by="human",
            overall_passed=overall_passed,
            duration_ms=duration_ms,
        ),
    )

    return results
