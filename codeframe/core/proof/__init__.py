"""PROOF9: Quality memory system with evidence-based verification.

Turns every failure into a permanent proof obligation. Requirements are
tracked in a ledger, obligations are enforced on every run, and evidence
artifacts prove compliance.

This package is headless — no FastAPI or HTTP dependencies.
"""

from codeframe.core.proof.models import (
    Evidence,
    EvidenceRule,
    Gate,
    GlitchType,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Source,
    Waiver,
)

__all__ = [
    "Evidence",
    "EvidenceRule",
    "Gate",
    "GlitchType",
    "Obligation",
    "ReqStatus",
    "Requirement",
    "RequirementScope",
    "Source",
    "Waiver",
]
