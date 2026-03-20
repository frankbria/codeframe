"""PROOF9 REST API router — thin adapter over codeframe.core.proof.

Maps HTTP endpoints to core proof functions (capture, list, get, run, waive,
status, evidence). No business logic lives here.

Routes:
    POST   /api/v2/proof/requirements              capture_requirement()
    GET    /api/v2/proof/requirements              list_requirements()
    GET    /api/v2/proof/requirements/{req_id}     get_requirement()
    POST   /api/v2/proof/run                       run_proof()
    POST   /api/v2/proof/requirements/{req_id}/waive  waive_requirement()
    GET    /api/v2/proof/status                    aggregated status
    GET    /api/v2/proof/requirements/{req_id}/evidence  list_evidence()
"""

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.ledger import (
    get_requirement,
    list_evidence,
    list_requirements,
    waive_requirement,
)
from codeframe.core.proof.models import (
    Gate,
    ReqStatus,
    Severity,
    Source,
    Waiver,
)
from codeframe.core.proof.runner import run_proof
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_ai, rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import ErrorCodes, api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/proof", tags=["proof-v2"])


# ============================================================================
# Request / Response Models
# ============================================================================


class CaptureRequirementRequest(BaseModel):
    """Request body for capturing a requirement from a glitch."""

    title: str = Field(..., min_length=1, description="Short title of the glitch")
    description: str = Field(..., min_length=1, description="Detailed description for glitch classification")
    where: str = Field(..., min_length=1, description="Location (file, route, API, tag) where glitch occurred")
    severity: Severity = Field(..., description="Severity: critical, high, medium, low")
    source: Source = Field(..., description="Source: production, qa, dogfooding, monitoring, user_report")
    created_by: str = Field(default="human", description="Who captured this requirement")
    source_issue: Optional[str] = Field(default=None, description="External issue reference (e.g. GH-123)")


class WaiveRequirementRequest(BaseModel):
    """Request body for waiving a requirement."""

    reason: str = Field(..., min_length=1, description="Why this requirement is being waived")
    expires: Optional[date] = Field(default=None, description="ISO date when waiver expires (e.g. 2026-06-01)")
    manual_checklist: list[str] = Field(default_factory=list, description="Manual verification steps")
    approved_by: str = Field(default="", description="Who approved this waiver")


class RunProofRequest(BaseModel):
    """Request body for running proof obligations."""

    full: bool = Field(default=False, description="Run ALL obligations regardless of scope")
    gate: Optional[Gate] = Field(default=None, description="Run only this gate (unit, sec, contract, etc.)")


class ObligationOut(BaseModel):
    """Serialized proof obligation."""

    gate: str
    status: str


class EvidenceRuleOut(BaseModel):
    """Serialized evidence rule."""

    test_id: str
    must_pass: bool


class WaiverOut(BaseModel):
    """Serialized waiver."""

    reason: str
    expires: Optional[str]
    manual_checklist: list[str]
    approved_by: str


class RequirementResponse(BaseModel):
    """Full requirement response."""

    id: str
    title: str
    description: str
    severity: str
    source: str
    status: str
    glitch_type: Optional[str]
    obligations: list[ObligationOut]
    evidence_rules: list[EvidenceRuleOut]
    waiver: Optional[WaiverOut]
    created_at: Optional[str]
    satisfied_at: Optional[str]
    created_by: str
    source_issue: Optional[str]
    related_reqs: list[str]


class CaptureRequirementResponse(RequirementResponse):
    """Capture response adds stubs_count."""

    stubs_count: int = Field(description="Number of test stub files generated")


class RequirementListResponse(BaseModel):
    """Response for list/filter endpoints."""

    requirements: list[RequirementResponse]
    total: int
    by_status: dict[str, int]


class RunProofResponse(BaseModel):
    """Response for POST /run."""

    success: bool
    run_id: str
    results: dict[str, list[dict[str, Any]]]
    message: str


class ProofStatusResponse(BaseModel):
    """Aggregated proof status response."""

    total: int
    open: int
    satisfied: int
    waived: int
    requirements: list[RequirementResponse]


class EvidenceResponse(BaseModel):
    """Serialized evidence record."""

    req_id: str
    gate: str
    satisfied: bool
    artifact_path: str
    artifact_checksum: str
    timestamp: str
    run_id: str


# ============================================================================
# Helper
# ============================================================================


def _req_to_response(req) -> RequirementResponse:
    """Convert a core Requirement dataclass to RequirementResponse."""
    return RequirementResponse(
        id=req.id,
        title=req.title,
        description=req.description,
        severity=req.severity.value,
        source=req.source.value,
        status=req.status.value,
        glitch_type=req.glitch_type.value if req.glitch_type else None,
        obligations=[
            ObligationOut(gate=o.gate.value, status=o.status)
            for o in req.obligations
        ],
        evidence_rules=[
            EvidenceRuleOut(test_id=r.test_id, must_pass=r.must_pass)
            for r in req.evidence_rules
        ],
        waiver=WaiverOut(
            reason=req.waiver.reason,
            expires=req.waiver.expires.isoformat() if req.waiver.expires else None,
            manual_checklist=req.waiver.manual_checklist,
            approved_by=req.waiver.approved_by,
        ) if req.waiver else None,
        created_at=req.created_at.isoformat() if req.created_at else None,
        satisfied_at=req.satisfied_at.isoformat() if req.satisfied_at else None,
        created_by=req.created_by,
        source_issue=req.source_issue,
        related_reqs=req.related_reqs,
    )


def _count_by_status(reqs) -> dict[str, int]:
    """Aggregate requirement counts by status value."""
    counts: dict[str, int] = {s.value: 0 for s in ReqStatus}
    for req in reqs:
        counts[req.status.value] = counts.get(req.status.value, 0) + 1
    return counts


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/requirements", response_model=CaptureRequirementResponse, status_code=201)
@rate_limit_standard()
async def capture_requirement_endpoint(
    request: Request,
    body: CaptureRequirementRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> CaptureRequirementResponse:
    """Capture a requirement from a glitch report.

    Classifies the glitch, derives proof obligations, generates test stubs,
    and persists the requirement to the ledger.
    """
    try:
        req, stubs = capture_requirement(
            workspace,
            title=body.title,
            description=body.description,
            where=body.where,
            severity=body.severity,
            source=body.source,
            created_by=body.created_by,
            source_issue=body.source_issue,
        )
        resp = _req_to_response(req)
        return CaptureRequirementResponse(**resp.model_dump(), stubs_count=len(stubs))
    except Exception as e:
        logger.error("Failed to capture requirement: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to capture requirement", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/requirements", response_model=RequirementListResponse)
@rate_limit_standard()
async def list_requirements_endpoint(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status: open, satisfied, waived"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> RequirementListResponse:
    """List all requirements, optionally filtered by status."""
    status_filter = None
    if status:
        try:
            status_filter = ReqStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    f"Invalid status: {status}",
                    ErrorCodes.VALIDATION_ERROR,
                    f"Valid values: {[s.value for s in ReqStatus]}",
                ),
            )

    reqs = list_requirements(workspace, status=status_filter)
    all_reqs = list_requirements(workspace) if status_filter else reqs

    return RequirementListResponse(
        requirements=[_req_to_response(r) for r in reqs],
        total=len(reqs),
        by_status=_count_by_status(all_reqs),
    )


@router.get("/requirements/{req_id}", response_model=RequirementResponse)
@rate_limit_standard()
async def get_requirement_endpoint(
    request: Request,
    req_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> RequirementResponse:
    """Get a single requirement by ID."""
    req = get_requirement(workspace, req_id)
    if not req:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                f"Requirement not found: {req_id}",
                ErrorCodes.NOT_FOUND,
                f"No requirement with id {req_id}",
            ),
        )
    return _req_to_response(req)


@router.post("/run", response_model=RunProofResponse)
@rate_limit_ai()
async def run_proof_endpoint(
    request: Request,
    body: RunProofRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> RunProofResponse:
    """Execute proof obligations and collect evidence.

    Runs gate checks (pytest, ruff, etc.) for open requirements and records
    evidence artifacts. Use full=True to run all obligations regardless of
    changed scope.
    """
    try:
        results = run_proof(
            workspace,
            full=body.full,
            gate_filter=body.gate,
        )
        # Serialize: dict[req_id → list[tuple[Gate, bool]]] → JSON-safe
        serialized = {
            req_id: [{"gate": gate.value, "satisfied": satisfied} for gate, satisfied in gate_results]
            for req_id, gate_results in results.items()
        }
        # Derive a run_id from the results or generate one
        import uuid
        run_id = str(uuid.uuid4())[:8]

        return RunProofResponse(
            success=True,
            run_id=run_id,
            results=serialized,
            message=f"Proof run complete: {len(results)} requirement(s) evaluated.",
        )
    except Exception as e:
        logger.error("Proof run failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Proof run failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.post("/requirements/{req_id}/waive", response_model=RequirementResponse)
@rate_limit_standard()
async def waive_requirement_endpoint(
    request: Request,
    req_id: str,
    body: WaiveRequirementRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> RequirementResponse:
    """Waive a requirement with a reason and optional expiry date."""
    existing = get_requirement(workspace, req_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                f"Requirement not found: {req_id}",
                ErrorCodes.NOT_FOUND,
                f"No requirement with id {req_id}",
            ),
        )

    waiver = Waiver(
        reason=body.reason,
        expires=body.expires,
        manual_checklist=body.manual_checklist,
        approved_by=body.approved_by,
    )
    updated = waive_requirement(workspace, req_id, waiver)
    return _req_to_response(updated)


@router.get("/status", response_model=ProofStatusResponse)
@rate_limit_standard()
async def proof_status_endpoint(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ProofStatusResponse:
    """Get aggregated proof status: totals by status and full requirement list."""
    reqs = list_requirements(workspace)
    counts = _count_by_status(reqs)

    return ProofStatusResponse(
        total=len(reqs),
        open=counts.get("open", 0),
        satisfied=counts.get("satisfied", 0),
        waived=counts.get("waived", 0),
        requirements=[_req_to_response(r) for r in reqs],
    )


@router.get("/requirements/{req_id}/evidence", response_model=list[EvidenceResponse])
@rate_limit_standard()
async def list_evidence_endpoint(
    request: Request,
    req_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> list[EvidenceResponse]:
    """List all evidence records for a requirement."""
    req = get_requirement(workspace, req_id)
    if not req:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                f"Requirement not found: {req_id}",
                ErrorCodes.NOT_FOUND,
                f"No requirement with id {req_id}",
            ),
        )

    evidence = list_evidence(workspace, req_id)
    return [
        EvidenceResponse(
            req_id=e.req_id,
            gate=e.gate.value,
            satisfied=e.satisfied,
            artifact_path=e.artifact_path,
            artifact_checksum=e.artifact_checksum,
            timestamp=e.timestamp.isoformat(),
            run_id=e.run_id,
        )
        for e in evidence
    ]
