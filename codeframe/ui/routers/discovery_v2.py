"""V2 Discovery workflow router - delegates to core modules.

This module provides v2-style API endpoints for PRD discovery that delegate
to core/prd_discovery.py. It uses the v2 Workspace model and is designed
to work alongside the v1 discovery router during migration.

Key differences from v1:
- Uses Workspace (path-based) instead of project_id
- Delegates to core/prd_discovery functions
- Stateless session management via session_id
- No LeadAgent dependency

The v1 router (discovery.py) remains for backwards compatibility with
existing web UI until Phase 3 (Web UI Rebuild).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_ai, rate_limit_standard
from codeframe.core import prd_discovery, prd, tasks
from codeframe.core.prd_discovery import (
    NoApiKeyError,
    ValidationError,
    IncompleteSessionError,
)
from codeframe.ui.dependencies import get_v2_workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/discovery", tags=["discovery-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class StartDiscoveryResponse(BaseModel):
    """Response for starting a discovery session."""

    session_id: str
    state: str
    question: dict[str, Any]


class AnswerRequest(BaseModel):
    """Request for submitting an answer."""

    answer: str = Field(..., min_length=1, max_length=10000)


class AnswerResponse(BaseModel):
    """Response for submitting an answer."""

    accepted: bool
    feedback: str
    follow_up: Optional[str] = None
    is_complete: bool
    next_question: Optional[dict[str, Any]] = None
    coverage: Optional[dict[str, Any]] = None


class StatusResponse(BaseModel):
    """Response for discovery status."""

    state: str
    session_id: Optional[str] = None
    progress: dict[str, Any] = {}
    current_question: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class GeneratePrdRequest(BaseModel):
    """Request for PRD generation."""

    template_id: Optional[str] = Field(
        None,
        description="PRD template to use (standard, lean, enterprise, etc.)",
    )


class GeneratePrdResponse(BaseModel):
    """Response for PRD generation."""

    prd_id: str
    title: str
    preview: str


class GenerateTasksResponse(BaseModel):
    """Response for task generation."""

    task_count: int
    tasks: list[dict[str, Any]]


# ============================================================================
# Discovery Endpoints
# ============================================================================


@router.post("/start", response_model=StartDiscoveryResponse)
@rate_limit_ai()
async def start_discovery(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> StartDiscoveryResponse:
    """Start a new PRD discovery session.

    Creates a new AI-driven discovery session that will ask context-sensitive
    questions to gather project requirements.

    Args:
        workspace: v2 Workspace (from workspace_path query param or default)

    Returns:
        Session ID, state, and first question

    Raises:
        HTTPException:
            - 400: Discovery session already active
            - 500: API key not configured or processing error
    """
    try:
        # Check for existing active session
        existing = prd_discovery.get_active_session(workspace)
        if existing and not existing.is_complete():
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Discovery session already active",
                    "session_id": existing.session_id,
                    "answered_count": existing.answered_count,
                    "hint": "Use POST /api/v2/discovery/{session_id}/answer to continue",
                },
            )

        # Start new session
        session = prd_discovery.start_discovery_session(workspace)
        question = session.get_current_question()

        return StartDiscoveryResponse(
            session_id=session.session_id,
            state=session.state.value,
            question=question or {},
        )

    except NoApiKeyError as e:
        raise HTTPException(
            status_code=500,
            detail=f"ANTHROPIC_API_KEY not configured: {e}",
        )
    except Exception as e:
        logger.error(f"Failed to start discovery: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start discovery: {e}",
        )


@router.get("/status", response_model=StatusResponse)
@rate_limit_standard()
async def get_status(
    request: Request,
    session_id: Optional[str] = Query(None, description="Specific session ID"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> StatusResponse:
    """Get discovery status for the workspace.

    Returns status for a specific session (if provided) or the most recent
    active session. If no active session exists, returns idle state.

    Args:
        session_id: Optional specific session ID to query
        workspace: v2 Workspace

    Returns:
        Discovery status including state, progress, and current question
    """
    status = prd_discovery.get_discovery_status(
        workspace,
        session_id=session_id,
    )
    return StatusResponse(**status)


@router.post("/{session_id}/answer", response_model=AnswerResponse)
@rate_limit_ai()
async def submit_answer(
    request: Request,
    session_id: str,
    body: AnswerRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> AnswerResponse:
    """Submit an answer to the current discovery question.

    The AI validates the answer for adequacy. If adequate, the answer is
    recorded and the next question (or completion) is returned. If not
    adequate, feedback is provided with optional follow-up question.

    Args:
        request: HTTP request for rate limiting
        session_id: Discovery session ID
        body: Answer request with answer text
        workspace: v2 Workspace

    Returns:
        Answer response with acceptance status and next steps

    Raises:
        HTTPException:
            - 400: Validation error or session not active
            - 404: Session not found
            - 500: Processing error
    """
    try:
        result = prd_discovery.process_discovery_answer(
            workspace,
            session_id,
            body.answer,
        )
        return AnswerResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NoApiKeyError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to process answer: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/generate-prd", response_model=GeneratePrdResponse)
@rate_limit_ai()
async def generate_prd(
    request: Request,
    session_id: str,
    body: GeneratePrdRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
) -> GeneratePrdResponse:
    """Generate a PRD from a completed discovery session.

    Synthesizes the discovery conversation into a structured PRD document
    using the specified template (or default).

    Args:
        request: HTTP request for rate limiting
        session_id: Discovery session ID (must be complete)
        body: Optional template selection
        workspace: v2 Workspace

    Returns:
        Generated PRD with ID, title, and preview

    Raises:
        HTTPException:
            - 400: Discovery not complete
            - 404: Session not found
            - 500: Generation error
    """
    try:
        template_id = body.template_id if body else None
        prd_record = prd_discovery.generate_prd_from_discovery(
            workspace,
            session_id,
            template_id=template_id,
        )

        preview = prd_record.content[:500]
        if len(prd_record.content) > 500:
            preview += "..."

        return GeneratePrdResponse(
            prd_id=prd_record.id,
            title=prd_record.title,
            preview=preview,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IncompleteSessionError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Discovery not complete: {e}",
        )
    except NoApiKeyError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate PRD: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
@rate_limit_standard()
async def reset_discovery(
    request: Request,
    session_id: Optional[str] = Query(None, description="Specific session to reset"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict[str, Any]:
    """Reset discovery for the workspace.

    Marks the specified session (or most recent active session) as complete/abandoned.
    Does NOT delete PRDs or tasks.

    Args:
        session_id: Optional specific session to reset
        workspace: v2 Workspace

    Returns:
        Success status and message
    """
    reset = prd_discovery.reset_discovery(workspace, session_id=session_id)

    if reset:
        return {
            "success": True,
            "message": "Discovery session reset. Start a new session with POST /api/v2/discovery/start",
        }
    else:
        return {
            "success": True,
            "message": "No active discovery session to reset.",
        }


# ============================================================================
# Task Generation Endpoints (from PRD)
# ============================================================================


@router.post("/generate-tasks", response_model=GenerateTasksResponse)
@rate_limit_ai()
async def generate_tasks_from_prd(
    request: Request,
    prd_id: Optional[str] = Query(
        None,
        description="PRD ID to generate tasks from (defaults to latest)",
    ),
    use_llm: bool = Query(
        True,
        description="Use LLM for intelligent task generation (vs simple extraction)",
    ),
    workspace: Workspace = Depends(get_v2_workspace),
) -> GenerateTasksResponse:
    """Generate tasks from a PRD.

    Uses LLM to decompose the PRD into actionable development tasks.
    Falls back to simple extraction if LLM is unavailable.

    This is the v2 equivalent of `cf tasks generate`.

    Args:
        prd_id: Optional PRD ID (defaults to latest PRD)
        use_llm: Whether to use LLM (default True)
        workspace: v2 Workspace

    Returns:
        List of generated tasks

    Raises:
        HTTPException:
            - 404: PRD not found
            - 500: Generation error
    """
    try:
        # Get PRD
        if prd_id:
            prd_record = prd.get_by_id(workspace, prd_id)
            if not prd_record:
                raise HTTPException(
                    status_code=404,
                    detail=f"PRD not found: {prd_id}",
                )
        else:
            prd_record = prd.get_latest(workspace)
            if not prd_record:
                raise HTTPException(
                    status_code=404,
                    detail="No PRD found. Generate a PRD first with POST /api/v2/discovery/start",
                )

        # Generate tasks
        generated_tasks = tasks.generate_from_prd(
            workspace,
            prd_record,
            use_llm=use_llm,
        )

        return GenerateTasksResponse(
            task_count=len(generated_tasks),
            tasks=[
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status.value,
                    "priority": t.priority,
                }
                for t in generated_tasks
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate tasks: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate tasks: {e}",
        )
