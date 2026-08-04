"""PROOF9 evidence attachment and verification.

Attaches evidence artifacts (test results, screenshots, reports)
to requirements with SHA-256 checksums for integrity.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from codeframe.core.proof import ledger
from codeframe.core.proof.models import Evidence, Gate, GateOutcome, Requirement
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


class EvidenceTamperError(Exception):
    """A stored artifact no longer matches the checksum recorded with it.

    A hard state, never a warning: the whole point of the ledger is that a
    recorded pass is attributable. Raised on a mutated artifact, a missing one,
    and on one transplanted from a different run or gate.
    """


def _sha256(file_path: str) -> str:
    """Compute SHA-256 checksum of a file's bytes. Raises if file missing.

    The pre-#952 digest. Kept because evidence written before that change is
    stored in this form — see ``verify_evidence``.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {file_path}")
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _bound_digest(run_id: str, gate: Gate, artifact_path: str) -> str:
    """Checksum binding the artifact's bytes to *where it came from* (#952).

    Hashing bytes alone proves only that a file is unmodified — it says nothing
    about which run produced it, so a genuinely passing artifact could be
    transplanted into another run's evidence and still verify. The digest
    therefore covers a canonical header (run id, gate, resolved path) as well
    as the content.

    The header is length-prefixed so no two different tuples can produce the
    same byte stream (``run="a|b", gate="c"`` vs ``run="a", gate="b|c"``).
    """
    path = Path(artifact_path)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")
    h = hashlib.sha256()
    for part in ("codeframe-proof-evidence-v1", run_id, gate.value, str(path.resolve())):
        raw = part.encode("utf-8")
        h.update(len(raw).to_bytes(4, "big"))
        h.update(raw)
    h.update(path.read_bytes())
    return h.hexdigest()


def verify_evidence(evidence: Evidence) -> None:
    """Re-derive an artifact's checksum and raise if it does not match.

    Checksums were computed and stored but never checked on read, so the
    integrity claim was unenforced (#952). This is the check.

    Accepts the legacy bytes-only digest as well as the bound one, so evidence
    recorded before #952 does not all become 'tampered' at once. Legacy rows
    still detect modification of the artifact; they just cannot detect a
    transplant. New evidence is always written in the bound form, so the
    legacy path drains as runs happen.
    """
    try:
        if _bound_digest(evidence.run_id, evidence.gate, evidence.artifact_path) == evidence.artifact_checksum:
            return
        if _sha256(evidence.artifact_path) == evidence.artifact_checksum:
            logger.debug(
                "Evidence for %s/%s verified via the pre-#952 bytes-only digest",
                evidence.req_id, evidence.gate.value,
            )
            return
    except FileNotFoundError as exc:
        raise EvidenceTamperError(
            f"Evidence artifact for {evidence.req_id}/{evidence.gate.value} "
            f"is missing: {evidence.artifact_path}"
        ) from exc

    raise EvidenceTamperError(
        f"Evidence artifact for {evidence.req_id}/{evidence.gate.value} does not "
        f"match its recorded checksum: {evidence.artifact_path} "
        f"(run {evidence.run_id})"
    )


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
        artifact_checksum=_bound_digest(run_id, gate, artifact_path),
        timestamp=datetime.now(timezone.utc),
        run_id=run_id,
        status=outcome.value,
    )
    ledger.save_evidence(workspace, evidence)
    return evidence


def check_obligation_satisfied(
    workspace: Workspace, req: Requirement, gate: Gate
) -> bool:
    """Check if a gate obligation has passing evidence.

    Evidence whose artifact no longer matches its checksum does not count. The
    verification has to happen here, before a gate accepts the artifact, or the
    stored checksum buys nothing (#952). A tampered record is skipped and
    logged rather than raised: one corrupted artifact must not take down the
    whole proof run, and the obligation correctly reports unsatisfied.
    """
    evidence_list = ledger.list_evidence(workspace, req.id)
    for ev in evidence_list:
        if ev.gate != gate or not ev.satisfied:
            continue
        try:
            verify_evidence(ev)
        except EvidenceTamperError as exc:
            logger.warning("Rejecting evidence for %s: %s", req.id, exc)
            continue
        return True
    return False


def list_blocking_requirements(workspace: Workspace) -> list[Requirement]:
    """Requirements that must stop a merge (#731 gate, #952 verification).

    Two reasons a requirement blocks:

    * It is still OPEN — never proven.
    * It is recorded SATISFIED but its evidence no longer verifies. Checksum
      verification is worthless if the only path that runs it is a fresh proof
      run: a requirement marked satisfied yesterday keeps that status forever,
      so editing its artifact afterwards left the merge gate waving the change
      through (codex review on #952).

    Only the **latest** passing evidence per gate is checked, not every row
    ever recorded. Runs accumulate evidence, and deleting last month's
    artifacts is routine housekeeping — blocking on any historical row would
    make that cleanup wedge the gate permanently, which is a worse failure than
    the hole this closes (codex review). Each gate is judged separately, so a
    stale-but-intact UNIT artifact cannot mask a tampered SEC one.

    A SATISFIED requirement with *no* evidence rows does not block. That is a
    pre-existing state in older ledgers, not a tamper signal, and treating it
    as one would wedge every workspace that has it. Only evidence that is
    present and fails to verify counts.
    """
    from codeframe.core.proof.models import ReqStatus

    blocking = list(ledger.list_requirements(workspace, status=ReqStatus.OPEN))

    for req in ledger.list_requirements(workspace, status=ReqStatus.SATISFIED):
        # list_evidence returns newest first, so the first passing row for a
        # gate is that gate's current proof.
        latest: dict[Gate, Evidence] = {}
        for ev in ledger.list_evidence(workspace, req.id):
            if ev.satisfied:
                latest.setdefault(ev.gate, ev)

        for ev in latest.values():
            try:
                verify_evidence(ev)
            except EvidenceTamperError as exc:
                logger.warning(
                    "Requirement %s blocks the merge gate: %s", req.id, exc
                )
                blocking.append(req)
                break

    return blocking
