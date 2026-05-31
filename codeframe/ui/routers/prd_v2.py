"""V2 PRD router - delegates to core/prd module.

This module provides v2-style API endpoints for PRD (Product Requirements Document)
CRUD operations. Discovery/generation is handled by discovery_v2.py - this router
handles storage, retrieval, and management of PRD documents.

Routes:
    GET  /api/v2/prd                      - List PRDs or get latest
    GET  /api/v2/prd/{id}                 - Get a specific PRD
    POST /api/v2/prd                      - Store a new PRD
    DELETE /api/v2/prd/{id}               - Delete a PRD
    GET  /api/v2/prd/{id}/versions        - Get all versions of a PRD
    POST /api/v2/prd/{id}/versions        - Create new version
    GET  /api/v2/prd/{id}/diff            - Diff two versions
"""

import json
import logging
import os
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import prd
from codeframe.core.prd import PrdHasDependentTasksError
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/prd", tags=["prd-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class PrdResponse(BaseModel):
    """Response for a single PRD."""

    id: str
    workspace_id: str
    title: str
    content: str
    metadata: dict
    created_at: str
    version: int
    parent_id: Optional[str]
    change_summary: Optional[str]
    chain_id: Optional[str]


class PrdSummaryResponse(BaseModel):
    """Summary response for PRD list (without full content)."""

    id: str
    workspace_id: str
    title: str
    created_at: str
    version: int
    chain_id: Optional[str]


class PrdListResponse(BaseModel):
    """Response for PRD list."""

    prds: list[PrdSummaryResponse]
    total: int


class CreatePrdRequest(BaseModel):
    """Request for creating a PRD."""

    content: str = Field(..., min_length=1, description="PRD content (markdown)")
    title: Optional[str] = Field(None, description="Optional title (extracted from content if not provided)")
    metadata: Optional[dict] = Field(None, description="Optional metadata")


class CreateVersionRequest(BaseModel):
    """Request for creating a new PRD version."""

    content: str = Field(..., min_length=1, description="New PRD content")
    change_summary: str = Field(..., min_length=1, description="Description of changes")


class PrdDiffResponse(BaseModel):
    """Response for PRD version diff."""

    version1: int
    version2: int
    diff: str


class AmbiguityAnswer(BaseModel):
    """A single answered ambiguity from the stress-test results view (#562)."""

    label: str = Field(..., description="Short ambiguity label")
    questions: list[str] = Field(
        default_factory=list, description="The unanswered questions"
    )
    answer: str = Field(..., min_length=1, description="The user's answer")

    @field_validator("answer")
    @classmethod
    def _answer_not_blank(cls, v: str) -> str:
        # min_length alone admits whitespace-only answers from API callers;
        # reject them so a blank string is never treated as resolved input.
        if not v.strip():
            raise ValueError("answer must not be blank")
        return v


class StressTestRefineRequest(BaseModel):
    """Request to refine a PRD from resolved stress-test ambiguities (#562).

    Stateless: the client sends back the answered ambiguities' content (the
    server does not persist stress-test runs), which are folded into the PRD
    and saved as a new version.
    """

    prd_id: str = Field(..., description="ID of the PRD to refine")
    answers: list[AmbiguityAnswer] = Field(
        ..., min_length=1, description="Resolved ambiguities to fold into the PRD"
    )


# ============================================================================
# Helper Functions
# ============================================================================


def _prd_to_response(record: prd.PrdRecord) -> PrdResponse:
    """Convert a PrdRecord to a PrdResponse."""
    return PrdResponse(
        id=record.id,
        workspace_id=record.workspace_id,
        title=record.title,
        content=record.content,
        metadata=record.metadata,
        created_at=record.created_at.isoformat(),
        version=record.version,
        parent_id=record.parent_id,
        change_summary=record.change_summary,
        chain_id=record.chain_id,
    )


def _prd_to_summary(record: prd.PrdRecord) -> PrdSummaryResponse:
    """Convert a PrdRecord to a PrdSummaryResponse (without content)."""
    return PrdSummaryResponse(
        id=record.id,
        workspace_id=record.workspace_id,
        title=record.title,
        created_at=record.created_at.isoformat(),
        version=record.version,
        chain_id=record.chain_id,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=PrdListResponse)
@rate_limit_standard()
async def list_prds(
    request: Request,
    latest_only: bool = Query(False, description="If true, return only latest version per chain"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdListResponse:
    """List PRDs in the workspace.

    Args:
        latest_only: If true, return only the latest version of each PRD chain
        workspace: v2 Workspace

    Returns:
        List of PRD summaries (without full content)
    """
    if latest_only:
        prd_list = prd.list_chains(workspace)
    else:
        prd_list = prd.list_all(workspace)

    return PrdListResponse(
        prds=[_prd_to_summary(p) for p in prd_list],
        total=len(prd_list),
    )


@router.get("/latest", response_model=PrdResponse)
@rate_limit_standard()
async def get_latest_prd(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdResponse:
    """Get the most recently added PRD.

    Args:
        workspace: v2 Workspace

    Returns:
        The latest PRD

    Raises:
        HTTPException: 404 if no PRD exists
    """
    record = prd.get_latest(workspace)

    if not record:
        raise HTTPException(
            status_code=404,
            detail=api_error("No PRD found", ErrorCodes.NOT_FOUND, "No PRD exists in this workspace"),
        )

    return _prd_to_response(record)


def _sse(event: dict) -> str:
    """Format a stress-test event dict as an SSE ``data:`` frame."""
    return f"data: {json.dumps(event)}\n\n"


def _resolve_llm_provider(workspace: Workspace):
    """Resolve the LLM provider for PRD stress-test web operations.

    Follows the documented chain: env var → workspace config
    (``.codeframe/config.yaml``) → default ``anthropic``. (No CLI flag here —
    this is the web surface.) Mirrors ``runtime.py`` and the stress-test stream.

    Raises:
        ValueError: with a user-facing message when the Anthropic API key is
            missing or the provider cannot be constructed.
    """
    from codeframe.adapters.llm import get_provider
    from codeframe.core.config import load_environment_config

    env_cfg = load_environment_config(workspace.repo_path)
    llm_cfg = env_cfg.llm if (env_cfg and env_cfg.llm) else None
    provider_type = (
        os.getenv("CODEFRAME_LLM_PROVIDER")
        or (llm_cfg.provider if llm_cfg else None)
        or "anthropic"
    )

    # Only the Anthropic provider needs an API key up front; local providers
    # (ollama/vllm/compatible) do not.
    if provider_type == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY environment variable required.")

    provider_kwargs: dict = {}
    model_override = os.getenv("CODEFRAME_LLM_MODEL") or (
        llm_cfg.model if llm_cfg else None
    )
    base_url_override = (llm_cfg.base_url if llm_cfg else None) or os.getenv(
        "OPENAI_BASE_URL"
    )
    if model_override:
        provider_kwargs["model"] = model_override
    if base_url_override:
        provider_kwargs["base_url"] = base_url_override

    return get_provider(provider_type, **provider_kwargs)


async def _stress_test_event_stream(
    workspace: Workspace,
    max_depth: int,
    request: Optional[Request] = None,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames for a PRD stress-test.

    Recoverable problems (missing PRD, missing ``ANTHROPIC_API_KEY``) are
    surfaced as in-stream ``error`` events rather than HTTP errors, so a
    browser ``EventSource`` can display them via its message handler.

    Stops early if the client disconnects, so an abandoned stream does not keep
    issuing LLM calls — mirroring ``event_stream_generator`` in streaming_v2.
    """
    from codeframe.core.prd_stress_test import stress_test_prd_stream

    record = prd.get_latest(workspace)
    if not record:
        yield _sse({
            "type": "error",
            "message": "No PRD found. Add or generate a PRD first.",
        })
        return

    # Resolve the LLM provider following the documented chain (shared with the
    # refine endpoint). Recoverable problems become in-stream error events so a
    # browser EventSource can display them.
    try:
        provider = _resolve_llm_provider(workspace)
    except ValueError as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return

    async for event in stress_test_prd_stream(
        record.content, provider, max_depth=max_depth,
    ):
        # If the browser has gone away, stop iterating the core generator so its
        # next (blocking, billable) LLM call is never made.
        if request is not None and await request.is_disconnected():
            logger.info("Client disconnected from stress-test stream; aborting")
            break
        yield _sse(event)


@router.get("/stress-test")
@rate_limit_standard()
async def stress_test_prd_stream_endpoint(
    request: Request,
    max_depth: int = Query(3, ge=1, le=10, description="Maximum recursion depth"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> StreamingResponse:
    """Stream a PRD stress-test (recursive decomposition) via SSE.

    Runs the headless ``stress_test_prd_stream`` core generator over the
    latest PRD and emits its progress events as Server-Sent Events. This is
    the web equivalent of ``cf prd stress-test``.

    Declared as GET (not POST) so it is reachable from a browser
    ``EventSource``, matching ``GET /api/v2/tasks/{task_id}/stream``. No custom
    auth headers are required (cookie-based auth via ``withCredentials``).

    Event payloads (JSON in the SSE ``data:`` field, ``type`` field):
        - ``goals_extracted``: high-level goals parsed from the PRD
        - ``goal_analyzed``: one per top-level goal (classification + running
          ambiguity count)
        - ``complete``: ambiguity count + rendered tech spec / ambiguity report
        - ``error``: no PRD, missing API key, or decomposition failure
    """
    return StreamingResponse(
        _stress_test_event_stream(workspace, max_depth, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# NOTE: registered before the "/{prd_id}" catch-all so FastAPI does not match
# "stress-test/refine" as a PRD id.
@router.post("/stress-test/refine", response_model=PrdResponse)
@rate_limit_standard()
async def refine_prd_from_stress_test(
    request: Request,
    body: StressTestRefineRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdResponse:
    """Refine a PRD by folding in answered stress-test ambiguities (#562).

    Reconstructs :class:`Ambiguity` objects from the submitted answers, calls
    the headless ``resolve_ambiguities_into_prd`` to rewrite the PRD via the
    LLM, then persists the result as a new PRD version. Returns the new version.
    """
    from codeframe.core.prd_stress_test import (
        Ambiguity,
        resolve_ambiguities_into_prd,
    )

    record = prd.get_by_id(workspace, body.prd_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "PRD not found", ErrorCodes.NOT_FOUND, f"No PRD with id {body.prd_id}"
            ),
        )

    try:
        provider = _resolve_llm_provider(workspace)
    except ValueError as exc:
        # The request is well-formed; the server lacks LLM configuration
        # (missing API key or unknown provider) → 503, not 400.
        raise HTTPException(
            status_code=503,
            detail=api_error(
                "LLM provider unavailable", ErrorCodes.EXECUTION_FAILED, str(exc)
            ),
        )

    # resolve_ambiguities_into_prd only reads label, questions, and
    # resolved_answer, so source_node_title/recommendation are intentionally
    # left empty here (the client does not need to round-trip them).
    ambiguities = [
        Ambiguity(
            id=str(i),
            label=ans.label,
            source_node_title="",
            questions=list(ans.questions),
            recommendation="",
            resolved_answer=ans.answer,
        )
        for i, ans in enumerate(body.answers)
    ]

    try:
        refined_content = resolve_ambiguities_into_prd(
            record.content, ambiguities, provider
        )
        # resolve_ambiguities_into_prd returns the original content unchanged
        # when the LLM rewrite looks truncated. Surface that as an error rather
        # than recording a no-op duplicate version under a "success" toast.
        if refined_content == record.content:
            raise HTTPException(
                status_code=502,
                detail=api_error(
                    "PRD refinement produced no changes",
                    ErrorCodes.EXECUTION_FAILED,
                    "The model returned no usable changes (its output may have "
                    "been truncated). Please try again.",
                ),
            )
        new_record = prd.create_new_version(
            workspace,
            parent_prd_id=body.prd_id,
            new_content=refined_content,
            change_summary="Refined via stress-test ambiguity resolution",
        )
        if not new_record:
            raise HTTPException(
                status_code=404,
                detail=api_error(
                    "PRD not found",
                    ErrorCodes.NOT_FOUND,
                    f"No PRD with id {body.prd_id}",
                ),
            )
        return _prd_to_response(new_record)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refine PRD: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to refine PRD", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )


@router.get("/{prd_id}", response_model=PrdResponse)
@rate_limit_standard()
async def get_prd(
    request: Request,
    prd_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdResponse:
    """Get a specific PRD by ID.

    Args:
        prd_id: PRD identifier
        workspace: v2 Workspace

    Returns:
        PRD details

    Raises:
        HTTPException: 404 if PRD not found
    """
    record = prd.get_by_id(workspace, prd_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail=api_error("PRD not found", ErrorCodes.NOT_FOUND, f"No PRD with id {prd_id}"),
        )

    return _prd_to_response(record)


@router.post("", response_model=PrdResponse, status_code=201)
@rate_limit_standard()
async def create_prd(
    request: Request,
    body: CreatePrdRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdResponse:
    """Store a new PRD.

    Args:
        request: HTTP request for rate limiting
        body: PRD creation request
        workspace: v2 Workspace

    Returns:
        Created PRD
    """
    try:
        record = prd.store(
            workspace,
            content=body.content,
            title=body.title,
            metadata=body.metadata,
        )
        return _prd_to_response(record)

    except Exception as e:
        logger.error(f"Failed to create PRD: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to create PRD", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.delete("/{prd_id}")
@rate_limit_standard()
async def delete_prd(
    request: Request,
    prd_id: str,
    force: bool = Query(False, description="Force delete even if tasks depend on this PRD"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Delete a PRD.

    Args:
        prd_id: PRD identifier to delete
        force: If true, delete even if tasks depend on this PRD
        workspace: v2 Workspace

    Returns:
        Deletion confirmation

    Raises:
        HTTPException:
            - 404: PRD not found
            - 409: PRD has dependent tasks and force=false
    """
    try:
        # Check dependencies unless force=True
        check_deps = not force
        deleted = prd.delete(workspace, prd_id, check_dependencies=check_deps)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=api_error("PRD not found", ErrorCodes.NOT_FOUND, f"No PRD with id {prd_id}"),
            )

        return {
            "success": True,
            "message": f"PRD {prd_id[:8]} deleted successfully",
        }

    except PrdHasDependentTasksError as e:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                "Cannot delete PRD with dependent tasks",
                ErrorCodes.CONFLICT,
                f"{e.task_count} task(s) depend on this PRD. Use force=true to delete anyway.",
            ),
        )


# ============================================================================
# Version Endpoints
# ============================================================================


@router.get("/{prd_id}/versions", response_model=list[PrdResponse])
@rate_limit_standard()
async def get_prd_versions(
    request: Request,
    prd_id: str,
    workspace: Workspace = Depends(get_v2_workspace),
) -> list[PrdResponse]:
    """Get all versions of a PRD.

    Args:
        prd_id: ID of any PRD in the version chain
        workspace: v2 Workspace

    Returns:
        List of all versions, newest first

    Raises:
        HTTPException: 404 if PRD not found
    """
    versions = prd.get_versions(workspace, prd_id)

    if not versions:
        raise HTTPException(
            status_code=404,
            detail=api_error("PRD not found", ErrorCodes.NOT_FOUND, f"No PRD with id {prd_id}"),
        )

    return [_prd_to_response(v) for v in versions]


@router.post("/{prd_id}/versions", response_model=PrdResponse, status_code=201)
@rate_limit_standard()
async def create_prd_version(
    request: Request,
    prd_id: str,
    body: CreateVersionRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdResponse:
    """Create a new version of a PRD.

    Args:
        prd_id: ID of the parent PRD
        request: Version creation request
        workspace: v2 Workspace

    Returns:
        Created PRD version

    Raises:
        HTTPException: 404 if parent PRD not found
    """
    try:
        record = prd.create_new_version(
            workspace,
            parent_prd_id=prd_id,
            new_content=body.content,
            change_summary=body.change_summary,
        )

        if not record:
            raise HTTPException(
                status_code=404,
                detail=api_error("PRD not found", ErrorCodes.NOT_FOUND, f"No PRD with id {prd_id}"),
            )

        return _prd_to_response(record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create PRD version: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to create version", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/{prd_id}/diff", response_model=PrdDiffResponse)
@rate_limit_standard()
async def diff_prd_versions(
    request: Request,
    prd_id: str,
    v1: int = Query(..., ge=1, description="First version number"),
    v2: int = Query(..., ge=1, description="Second version number"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdDiffResponse:
    """Generate a diff between two versions of a PRD.

    Args:
        prd_id: ID of any PRD in the version chain
        v1: First version number
        v2: Second version number
        workspace: v2 Workspace

    Returns:
        Unified diff string

    Raises:
        HTTPException: 404 if PRD or version not found
    """
    diff_result = prd.diff_versions(workspace, prd_id, v1, v2)

    if diff_result is None:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "Version not found",
                ErrorCodes.NOT_FOUND,
                f"Could not find version {v1} or {v2} for PRD {prd_id}",
            ),
        )

    return PrdDiffResponse(
        version1=v1,
        version2=v2,
        diff=diff_result,
    )
