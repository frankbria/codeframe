"""PROOF9 evidence attachment and verification.

Attaches evidence artifacts (test results, screenshots, reports)
to requirements with SHA-256 checksums for integrity.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from codeframe.core.proof import ledger
from codeframe.core.proof.models import Evidence, Gate, GateOutcome, Requirement
from codeframe.core.workspace import Workspace


def _sha256(file_path: str) -> str:
    """Compute SHA-256 checksum of a file. Raises if file missing."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {file_path}")
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def attach_evidence(
    workspace: Workspace,
    req_id: str,
    gate: Gate,
    artifact_path: str,
    outcome: GateOutcome,
    run_id: str,
) -> Evidence:
    """Create and persist an evidence record with artifact checksum.

    `satisfied` is True only when the gate PASSED; UNVERIFIABLE and FAILED both
    record satisfied=False. The tri-state `outcome` is preserved in `status`.
    """
    evidence = Evidence(
        req_id=req_id,
        gate=gate,
        satisfied=(outcome == GateOutcome.PASSED),
        artifact_path=artifact_path,
        artifact_checksum=_sha256(artifact_path),
        timestamp=datetime.now(timezone.utc),
        run_id=run_id,
        status=outcome.value,
    )
    ledger.save_evidence(workspace, evidence)
    return evidence


def check_obligation_satisfied(
    workspace: Workspace, req: Requirement, gate: Gate
) -> bool:
    """Check if a gate obligation has passing evidence."""
    evidence_list = ledger.list_evidence(workspace, req.id)
    for ev in evidence_list:
        if ev.gate == gate and ev.satisfied:
            return True
    return False
