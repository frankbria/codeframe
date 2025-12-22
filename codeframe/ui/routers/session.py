"""Session lifecycle management router.

This module handles session state management endpoints for projects,
allowing retrieval of current session state including last session summary,
next actions, progress, and active blockers.
"""

from datetime import datetime, UTC
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db
from codeframe.ui.auth import get_current_user, User
from codeframe.core.session_manager import SessionManager

router = APIRouter(prefix="/api/projects", tags=["session"])


@router.get("/{project_id}/session")
async def get_session_state(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get current session state for project (T028).

    Args:
        project_id: Project ID
        db: Database instance (injected)

    Returns:
        Session state with last session summary, next actions, progress, blockers
        Returns empty state if no session file exists

    Raises:
        HTTPException:
            - 404: Project not found

    Example:
        GET /api/projects/1/session
    """
    # Get project
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get project path
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        # Return empty state if no workspace path
        return {
            "last_session": {
                "summary": "No previous session",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "next_actions": [],
            "progress_pct": 0.0,
            "active_blockers": [],
        }

    # Load session state
    session_mgr = SessionManager(workspace_path)
    session = session_mgr.load_session()

    if not session:
        # Return empty state
        return {
            "last_session": {
                "summary": "No previous session",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "next_actions": [],
            "progress_pct": 0.0,
            "active_blockers": [],
        }

    # Return session state (omit completed_tasks and current_plan for API response)
    return {
        "last_session": {
            "summary": session["last_session"]["summary"],
            "timestamp": session["last_session"]["timestamp"],
        },
        "next_actions": session.get("next_actions", []),
        "progress_pct": session.get("progress_pct", 0.0),
        "active_blockers": session.get("active_blockers", []),
    }
