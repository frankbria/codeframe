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

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
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
async def list_prds(
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
async def get_latest_prd(
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


@router.get("/{prd_id}", response_model=PrdResponse)
async def get_prd(
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
async def create_prd(
    request: CreatePrdRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PrdResponse:
    """Store a new PRD.

    Args:
        request: PRD creation request
        workspace: v2 Workspace

    Returns:
        Created PRD
    """
    try:
        record = prd.store(
            workspace,
            content=request.content,
            title=request.title,
            metadata=request.metadata,
        )
        return _prd_to_response(record)

    except Exception as e:
        logger.error(f"Failed to create PRD: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to create PRD", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.delete("/{prd_id}")
async def delete_prd(
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
async def get_prd_versions(
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
async def create_prd_version(
    prd_id: str,
    request: CreateVersionRequest,
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
            new_content=request.content,
            change_summary=request.change_summary,
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
async def diff_prd_versions(
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
