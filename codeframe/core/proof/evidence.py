"""PROOF9 evidence attachment and verification.

Attaches evidence artifacts (test results, screenshots, reports)
to requirements with SHA-256 checksums for integrity.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from codeframe.core.proof import ledger
from codeframe.core.proof.models import Evidence, Gate, Requirement
from codeframe.core.workspace import Workspace


def _sha256(file_path: str) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    path = Path(file_path)
    if path.exists():
        h.update(path.read_bytes())
    else:
        h.update(file_path.encode())
    return h.hexdigest()


def attach_evidence(
    workspace: Workspace,
    req_id: str,
    gate: Gate,
    artifact_path: str,
    satisfied: bool,
    run_id: str,
) -> Evidence:
    """Create and persist an evidence record with artifact checksum."""
    evidence = Evidence(
        req_id=req_id,
        gate=gate,
        satisfied=satisfied,
        artifact_path=artifact_path,
        artifact_checksum=_sha256(artifact_path),
        timestamp=datetime.now(timezone.utc),
        run_id=run_id,
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
