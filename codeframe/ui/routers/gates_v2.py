"""V2 Gates router - delegates to core/gates module.

This module provides v2-style API endpoints for verification gates.
Gates are automated checks (tests, lint) that run before code is considered complete.

Routes:
    POST /api/v2/gates/run  - Run verification gates
    GET  /api/v2/gates      - List available gates
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.core import gates
from codeframe.core.gates import GateResult, GateCheck
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/gates", tags=["gates-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class GateCheckResponse(BaseModel):
    """Response for a single gate check."""

    name: str
    status: str  # GateStatus value
    exit_code: Optional[int]
    output: str
    duration_ms: int


class GateResultResponse(BaseModel):
    """Response for gate run results."""

    passed: bool
    checks: list[GateCheckResponse]
    summary: str
    started_at: Optional[str]
    completed_at: Optional[str]


class RunGatesRequest(BaseModel):
    """Request for running gates."""

    gates: Optional[list[str]] = Field(None, description="Specific gates to run (None = all)")
    verbose: bool = Field(False, description="Include verbose output")


# ============================================================================
# Helper Functions
# ============================================================================


def _check_to_response(check: GateCheck) -> GateCheckResponse:
    """Convert a GateCheck to a GateCheckResponse."""
    return GateCheckResponse(
        name=check.name,
        status=check.status.value,
        exit_code=check.exit_code,
        output=check.output,
        duration_ms=check.duration_ms,
    )


def _result_to_response(result: GateResult) -> GateResultResponse:
    """Convert a GateResult to a GateResultResponse."""
    return GateResultResponse(
        passed=result.passed,
        checks=[_check_to_response(c) for c in result.checks],
        summary=result.summary,
        started_at=result.started_at.isoformat() if result.started_at else None,
        completed_at=result.completed_at.isoformat() if result.completed_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/run", response_model=GateResultResponse)
@rate_limit_standard()
async def run_gates(
    request: Request,
    body: RunGatesRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
) -> GateResultResponse:
    """Run verification gates.

    Runs automated checks (tests, lint) on the workspace code.

    Args:
        request: Gate run options
        workspace: v2 Workspace

    Returns:
        Gate results with pass/fail status for each check
    """
    gate_list = body.gates if body else None
    verbose = body.verbose if body else False

    try:
        result = gates.run(workspace, gates=gate_list, verbose=verbose)
        return _result_to_response(result)

    except Exception as e:
        logger.error(f"Failed to run gates: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Gate execution failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("", response_model=dict)
@rate_limit_standard()
async def list_gates(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """List available verification gates.

    Returns the gates that can be run on this workspace.

    Args:
        workspace: v2 Workspace

    Returns:
        List of available gates with descriptions
    """
    # Currently available gates
    available_gates = [
        {
            "name": "pytest",
            "description": "Run Python tests",
            "command": "pytest",
        },
        {
            "name": "ruff",
            "description": "Run ruff linter",
            "command": "ruff check",
        },
        {
            "name": "ruff-fix",
            "description": "Run ruff with auto-fix",
            "command": "ruff check --fix",
        },
    ]

    return {
        "gates": available_gates,
        "total": len(available_gates),
        "message": "Use POST /api/v2/gates/run to execute gates",
    }
