"""V2 Interactive Sessions router.

Provides CRUD endpoints for persistent interactive agent sessions.

Routes:
    POST   /api/v2/sessions                    - Create session
    GET    /api/v2/sessions                    - List sessions (?workspace_path=&state=)
    GET    /api/v2/sessions/{id}               - Get session
    DELETE /api/v2/sessions/{id}               - End/close session
    GET    /api/v2/sessions/{id}/messages      - Get message history (?limit=&offset=)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/sessions", tags=["sessions-v2"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class SessionCreate(BaseModel):
    workspace_path: str
    task_id: Optional[str] = None
    agent_type: str = "claude"
    model: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    workspace_path: str
    state: str
    agent_type: str
    model: Optional[str]
    cost_usd: float
    input_tokens: int
    output_tokens: int
    created_at: str
    ended_at: Optional[str]


class MessageResponse(BaseModel):
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
    """Get the InteractiveSessionRepository from app state."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return db.interactive_sessions


def _session_to_response(row: dict) -> SessionResponse:
    return SessionResponse(
        id=row["id"],
        workspace_path=row["workspace_path"],
        state=row["state"],
        agent_type=row["agent_type"],
        model=row.get("model"),
        cost_usd=row.get("cost_usd", 0.0),
        input_tokens=row.get("input_tokens", 0),
        output_tokens=row.get("output_tokens", 0),
        created_at=row["created_at"],
        ended_at=row.get("ended_at"),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", status_code=201, response_model=SessionResponse)
def create_session(body: SessionCreate, request: Request):
    """Create a new interactive agent session."""
    repo = _get_repo(request)
    session = repo.create(
        workspace_path=body.workspace_path,
        task_id=body.task_id,
        agent_type=body.agent_type,
        model=body.model,
    )
    return _session_to_response(session)


@router.get("", response_model=list[SessionResponse])
def list_sessions(
    request: Request,
    workspace_path: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List sessions with optional filters."""
    repo = _get_repo(request)
    sessions = repo.list(workspace_path=workspace_path, state=state, limit=limit)
    return [_session_to_response(s) for s in sessions]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, request: Request):
    """Get a session by ID."""
    repo = _get_repo(request)
    session = repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_response(session)


@router.delete("/{session_id}", response_model=SessionResponse)
def end_session(session_id: str, request: Request):
    """End a session (sets state to 'ended')."""
    repo = _get_repo(request)
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    repo.end(session_id)
    return _session_to_response(repo.get(session_id))


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(
    session_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get message history for a session."""
    repo = _get_repo(request)
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
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
