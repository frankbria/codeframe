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
import time
import uuid
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.ledger import (
    get_requirement,
    get_run,
    get_run_evidence,
    list_evidence,
    list_requirements,
    list_runs,
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

# Module-level cache: (workspace_path, run_id) → {results, passed, message, _ts}
# Bounded to _CACHE_MAX_SIZE entries; entries expire after _CACHE_TTL_SECONDS.
# NOTE: in-memory only — a process running multiple uvicorn workers will have
# separate caches per worker. Suitable for single-worker dev/demo deployments.
_run_cache: dict[tuple[str, str], dict] = {}
_CACHE_MAX_SIZE = 100
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _evict_run_cache() -> None:
    """Remove expired entries and trim to max size (oldest first)."""
    now = time.time()
    expired = [k for k, v in _run_cache.items() if now - v["_ts"] > _CACHE_TTL_SECONDS]
    for k in expired:
        del _run_cache[k]
    if len(_run_cache) > _CACHE_MAX_SIZE:
        oldest = sorted(_run_cache, key=lambda k: _run_cache[k]["_ts"])
        for k in oldest[: len(_run_cache) - _CACHE_MAX_SIZE]:
            del _run_cache[k]


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
    waived_at: Optional[str] = None


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


class RunStatusResponse(BaseModel):
    """Response for GET /runs/{run_id} — poll a completed run.

    status is currently always "complete" because POST /run executes
    synchronously before returning run_id. The "running" value is reserved
    for a future async execution model.
    """

    run_id: str
    status: str  # "complete" (currently); "running" reserved for future async
    results: dict[str, list[dict[str, Any]]]
    passed: bool
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


class EvidenceWithContentResponse(EvidenceResponse):
    """Evidence record including artifact file contents."""

    artifact_text: Optional[str] = None


class ProofRunSummaryResponse(BaseModel):
    """Summary of a single proof gate run."""

    run_id: str
    started_at: str
    completed_at: Optional[str]
    triggered_by: str
    overall_passed: bool
    duration_ms: Optional[int]


class ProofRunDetailResponse(ProofRunSummaryResponse):
    """Proof run detail including per-gate evidence with artifact content."""

    evidence: list[EvidenceWithContentResponse]


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
            waived_at=req.waiver.waived_at.isoformat() if req.waiver.waived_at else None,
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
        # Generate run_id before calling run_proof so the response ID matches evidence records
        run_id = str(uuid.uuid4())[:8]
        results = run_proof(
            workspace,
            full=body.full,
            gate_filter=body.gate,
            run_id=run_id,
        )
        # Serialize: dict[req_id → list[tuple[Gate, bool]]] → JSON-safe
        serialized = {
            req_id: [{"gate": gate.value, "satisfied": satisfied} for gate, satisfied in gate_results]
            for req_id, gate_results in results.items()
        }

        passed = all(
            satisfied
            for gate_results in results.values()
            for _, satisfied in gate_results
        )
        response = RunProofResponse(
            success=True,
            run_id=run_id,
            results=serialized,
            message=f"Proof run complete: {len(results)} requirement(s) evaluated.",
        )
        _evict_run_cache()
        _run_cache[(str(workspace.repo_path), run_id)] = {
            "results": serialized,
            "passed": passed,
            "message": response.message,
            "_ts": time.time(),
        }
        return response
    except Exception as e:
        logger.error("Proof run failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Proof run failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
@rate_limit_standard()
async def get_run_status_endpoint(
    request: Request,
    run_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> RunStatusResponse:
    """Get the status of a completed proof run by run_id.

    Since POST /run is synchronous, a run is always complete immediately after
    the POST returns. Returns 404 if run_id is unknown.
    """
    cached = _run_cache.get((str(workspace.repo_path), run_id))
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                f"Run not found: {run_id}",
                ErrorCodes.NOT_FOUND,
                f"No proof run with id {run_id}",
            ),
        )
    return RunStatusResponse(
        run_id=run_id,
        status="complete",
        results=cached["results"],
        passed=cached["passed"],
        message=cached["message"],
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


@router.get("/runs", response_model=list[ProofRunSummaryResponse])
@rate_limit_standard()
async def list_runs_endpoint(
    request: Request,
    limit: int = Query(default=5, ge=1, le=50, description="Maximum number of runs to return"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> list[ProofRunSummaryResponse]:
    """List the most recent proof gate runs for this workspace."""
    runs = list_runs(workspace, limit=limit)
    return [
        ProofRunSummaryResponse(
            run_id=r.run_id,
            started_at=r.started_at.isoformat(),
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            triggered_by=r.triggered_by,
            overall_passed=r.overall_passed,
            duration_ms=r.duration_ms,
        )
        for r in runs
    ]


_ARTIFACT_LINE_LIMIT = 200


def _read_artifact_text(artifact_path: str, max_lines: int = _ARTIFACT_LINE_LIMIT) -> Optional[str]:
    """Read artifact file content up to max_lines, returning None if the file is missing."""
    from pathlib import Path
    try:
        p = Path(artifact_path)
        if not p.exists():
            return None
        lines = p.read_text(errors="replace").splitlines(keepends=True)
        return "".join(lines[:max_lines])
    except Exception:
        return None


@router.get("/runs/{run_id}/evidence", response_model=ProofRunDetailResponse)
@rate_limit_standard()
async def get_run_evidence_endpoint(
    request: Request,
    run_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> ProofRunDetailResponse:
    """Get per-gate evidence with artifact content for a completed proof run."""
    # Try to get run metadata from DB first; fall back to in-memory cache
    run = get_run(workspace, run_id)

    if run is None:
        # Fall back to cache for very recent runs not yet in DB
        cached = _run_cache.get((str(workspace.repo_path), run_id))
        if cached is None:
            raise HTTPException(
                status_code=404,
                detail=api_error(
                    f"Run not found: {run_id}",
                    ErrorCodes.NOT_FOUND,
                    f"No proof run with id {run_id}",
                ),
            )
        # Build a minimal response from cache
        evidence_list: list[EvidenceWithContentResponse] = []
        for req_id, gate_results in cached["results"].items():
            for gate_result in gate_results:
                evidence_list.append(EvidenceWithContentResponse(
                    req_id=req_id,
                    gate=gate_result["gate"],
                    satisfied=gate_result["satisfied"],
                    artifact_path="",
                    artifact_checksum="",
                    timestamp="",
                    run_id=run_id,
                    artifact_text=None,
                ))
        import time as _time
        ts = cached.get("_ts", _time.time())
        from datetime import datetime as _dt, timezone as _tz
        ts_str = _dt.fromtimestamp(ts, tz=_tz.utc).isoformat()
        return ProofRunDetailResponse(
            run_id=run_id,
            started_at=ts_str,
            completed_at=ts_str,
            triggered_by="human",
            overall_passed=cached["passed"],
            duration_ms=None,
            evidence=evidence_list,
        )

    evidence_records = get_run_evidence(workspace, run_id)
    evidence_out = [
        EvidenceWithContentResponse(
            req_id=e.req_id,
            gate=e.gate.value,
            satisfied=e.satisfied,
            artifact_path=e.artifact_path,
            artifact_checksum=e.artifact_checksum,
            timestamp=e.timestamp.isoformat(),
            run_id=e.run_id,
            artifact_text=_read_artifact_text(e.artifact_path),
        )
        for e in evidence_records
    ]
    return ProofRunDetailResponse(
        run_id=run.run_id,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        triggered_by=run.triggered_by,
        overall_passed=run.overall_passed,
        duration_ms=run.duration_ms,
        evidence=evidence_out,
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
