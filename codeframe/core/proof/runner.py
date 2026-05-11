"""PROOF9 runner — executes obligations and collects evidence.

Determines which requirements apply to the current changes,
runs their obligations via the existing gates infrastructure,
and attaches evidence artifacts.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import attach_evidence
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    Gate,
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


def _run_gate(workspace: Workspace, gate: Gate) -> tuple[bool, str]:
    """Execute a single gate and return (passed, output).

    Uses core/gates.py for gates that have direct tool support.
    Returns (True, "") for gates without automated tooling yet.
    """
    core_gate_name = _GATE_TO_CORE.get(gate)
    if not core_gate_name:
        return False, f"Gate {gate.value} has no automated runner — cannot verify"

    try:
        from codeframe.core.gates import run as run_gates
        result = run_gates(workspace, gates=[core_gate_name], verbose=False)
        output_parts = [
            f"{check.name}: {check.status.value}" for check in result.checks
        ]
        return result.passed, "\n".join(output_parts)
    except Exception as exc:
        logger.warning("Gate %s failed to run: %s", gate.value, exc)
        return False, str(exc)


def run_proof(
    workspace: Workspace,
    *,
    full: bool = False,
    gate_filter: Optional[Gate] = None,
    run_id: Optional[str] = None,
) -> dict[str, list[tuple[Gate, bool]]]:
    """Execute proof obligations and collect evidence.

    Args:
        workspace: Target workspace
        full: If True, run ALL obligations regardless of scope
        gate_filter: If set, only run this specific gate
        run_id: Unique run identifier (auto-generated if not provided)

    Returns:
        Dict mapping req_id → list of (Gate, satisfied) tuples
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

    # Get changed scope (skip if running full)
    changed_scope = None
    if not full:
        changed_scope = get_changed_scope(workspace)

    results: dict[str, list[tuple[Gate, bool]]] = {}
    artifact_dir = workspace.state_dir / "proof_artifacts"
    artifact_dir.mkdir(exist_ok=True)

    for req in reqs:
        # Check scope intersection (unless full mode or scope detection failed)
        # None changed_scope means "failed to detect" → run everything (fail closed)
        if not full and changed_scope is not None:
            if not intersects(req.scope, changed_scope):
                continue

        req_results: list[tuple[Gate, bool]] = []

        for obl in req.obligations:
            # Apply gate filter
            if gate_filter and obl.gate != gate_filter:
                continue

            # Apply config-driven gate filter (None means "all allowed")
            if enabled_gates is not None and obl.gate not in enabled_gates:
                continue

            # Run the gate
            passed, output = _run_gate(workspace, obl.gate)

            # Write artifact
            artifact_path = artifact_dir / f"{req.id}_{obl.gate.value}_{run_id}.txt"
            artifact_path.write_text(output)

            # Attach evidence
            attach_evidence(
                workspace, req.id, obl.gate,
                str(artifact_path), passed, run_id,
            )

            # Update obligation status
            obl.status = "satisfied" if passed else "failed"
            req_results.append((obl.gate, passed))

        if req_results:
            results[req.id] = req_results

            # Always persist obligation status updates
            all_satisfied = all(passed for _, passed in req_results)
            if all_satisfied and len(req_results) == len(req.obligations):
                req.status = ReqStatus.SATISFIED
            ledger.save_requirement(workspace, req)

    completed_at = datetime.now(timezone.utc)
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    executed = [passed for gate_results in results.values() for _, passed in gate_results]
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
