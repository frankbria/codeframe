"""V2 Interactive Sessions router.

Provides CRUD endpoints for persistent interactive agent sessions.

Routes:
    POST   /api/v2/sessions                        - Create session
    GET    /api/v2/sessions                        - List sessions (?workspace_path=&state=)
    GET    /api/v2/sessions/{id}                   - Get session
    DELETE /api/v2/sessions/{id}                   - End/close session
    POST   /api/v2/sessions/{id}/messages          - Add message to session
    GET    /api/v2/sessions/{id}/messages          - Get message history (?limit=&offset=)

Auth: enforced project-wide via router-level ``require_auth`` (#336). Session
creation additionally validates ``workspace_path`` against the workspace
allowlist (#655) since the stored path becomes a terminal shell ``cwd``.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator

from codeframe.auth.dependencies import require_auth
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.ui.dependencies import enforce_workspace_allowlist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/sessions", tags=["sessions-v2"])

VALID_STATES = frozenset({"active", "paused", "ended"})
VALID_ROLES = frozenset(
    {"user", "assistant", "tool_use", "tool_result", "thinking", "system", "error"}
)


# ============================================================================
# Pydantic Schemas
# ============================================================================


class SessionCreate(BaseModel):
    """Request body for creating a new interactive agent session."""

    workspace_path: str
    task_id: Optional[str] = None
    # agent_type is intentionally open-ended for extensibility (claude, codex, opencode, etc.)
    agent_type: str = "claude"
    model: Optional[str] = None


class SessionResponse(BaseModel):
    """Response body for a single interactive agent session."""

    id: str
    workspace_path: str
    task_id: Optional[str]
    state: str
    agent_type: str
    model: Optional[str]
    cost_usd: float
    input_tokens: int
    output_tokens: int
    created_at: str
    updated_at: str
    ended_at: Optional[str]


class MessageCreate(BaseModel):
    """Request body for adding a message to a session."""

    role: str
    content: str
    metadata: Optional[dict] = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate that role is one of the allowed values."""
        if v not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        return v


class MessageResponse(BaseModel):
    """Response body for a single session message."""

    id: str
    session_id: str
    role: str
    content: str
    metadata: Optional[dict]
    created_at: str


# ============================================================================
# Helpers
# ============================================================================


def _get_repo(request: Request):
    """Get the InteractiveSessionRepository from app state.

    Raises 503 if app.state.db is not available (server lifespan should set it).
    For backward compat with tests that set app.state.db directly.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Database not available. Ensure the server is fully initialized.",
        )
    return db.interactive_sessions


def _get_owned_session(repo, session_id: str, auth: Dict[str, Any]) -> dict:
    """Fetch a session, enforcing owner-scoping (#704).

    Returns the row, or raises 404 if it is missing OR owned by another user.
    404 (not 403) so a tenant can't probe which session IDs exist. In no-auth
    mode ``user_id`` is None → ownership is not enforced (matches REST/#655).
    """
    session = repo.get(session_id)
    user_id = auth.get("user_id")
    if session is None or (
        user_id is not None and session.get("user_id") != user_id
    ):
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _session_to_response(row: dict) -> SessionResponse:
    """Convert a DB row dict to a SessionResponse."""
    return SessionResponse(
        id=row["id"],
        workspace_path=row["workspace_path"],
        task_id=row.get("task_id"),
        state=row["state"],
        agent_type=row["agent_type"],
        model=row.get("model"),
        cost_usd=row.get("cost_usd", 0.0),
        input_tokens=row.get("input_tokens", 0),
        output_tokens=row.get("output_tokens", 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        ended_at=row.get("ended_at"),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", status_code=201, response_model=SessionResponse)
@rate_limit_standard()
def create_session(
    body: SessionCreate,
    request: Request,
    auth: Dict[str, Any] = Depends(require_auth),
):
    """Create a new interactive agent session.

    The stored ``workspace_path`` later becomes a terminal shell's ``cwd``
    (terminal_ws / session_chat_ws), so it must clear the same allowlist as
    REST workspace access (issue #655) — validated and resolved here.
    """
    repo = _get_repo(request)
    workspace_path = enforce_workspace_allowlist(
        Path(body.workspace_path), auth.get("user_id")
    )
    session = repo.create(
        workspace_path=str(workspace_path),
        task_id=body.task_id,
        agent_type=body.agent_type,
        model=body.model,
        user_id=auth.get("user_id"),
    )
    return _session_to_response(session)


@router.get("", response_model=list[SessionResponse])
@rate_limit_standard()
def list_sessions(
    request: Request,
    workspace_path: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    auth: Dict[str, Any] = Depends(require_auth),
):
    """List sessions with optional filters by workspace_path and state."""
    if state is not None and state not in VALID_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid state '{state}'. Must be one of {sorted(VALID_STATES)}",
        )
    repo = _get_repo(request)
    sessions = repo.list(
        workspace_path=workspace_path,
        state=state,
        limit=limit,
        user_id=auth.get("user_id"),
    )
    return [_session_to_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
@rate_limit_standard()
def get_session(
    session_id: str,
    request: Request,
    auth: Dict[str, Any] = Depends(require_auth),
):
    """Get a session by ID."""
    repo = _get_repo(request)
    return _session_to_response(_get_owned_session(repo, session_id, auth))


@router.delete("/{session_id}", response_model=SessionResponse)
@rate_limit_standard()
def end_session(
    session_id: str,
    request: Request,
    auth: Dict[str, Any] = Depends(require_auth),
):
    """End a session (sets state to 'ended' and records ended_at)."""
    repo = _get_repo(request)
    _get_owned_session(repo, session_id, auth)
    updated = repo.end(session_id)
    if updated is None:
        # Vanished between the ownership check and end() (concurrent delete).
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(updated)


@router.post("/{session_id}/messages", status_code=201, response_model=MessageResponse)
@rate_limit_standard()
def add_message(
    session_id: str,
    body: MessageCreate,
    request: Request,
    auth: Dict[str, Any] = Depends(require_auth),
):
    """Add a message to a session's history."""
    repo = _get_repo(request)
    _get_owned_session(repo, session_id, auth)
    message = repo.add_message(
        session_id=session_id,
        role=body.role,
        content=body.content,
        metadata=body.metadata,
    )
    return MessageResponse(
        id=message["id"],
        session_id=message["session_id"],
        role=message["role"],
        content=message["content"],
        metadata=message.get("metadata"),
        created_at=message["created_at"],
    )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
@rate_limit_standard()
def get_messages(
    session_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    auth: Dict[str, Any] = Depends(require_auth),
):
    """Get paginated message history for a session."""
    repo = _get_repo(request)
    _get_owned_session(repo, session_id, auth)
    messages = repo.get_messages(session_id, limit=limit, offset=offset)
    return [
        MessageResponse(
            id=m["id"],
            session_id=m["session_id"],
            role=m["role"],
            content=m["content"],
            metadata=m.get("metadata"),
            created_at=m["created_at"],
        )
        for m in messages
    ]
