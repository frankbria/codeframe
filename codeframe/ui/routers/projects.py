"""Project lifecycle and management router.

This module provides API endpoints for:
- Project CRUD (create, get, update, delete, list)
- Project status and progress
- Project tasks and activity
- Project PRD and issues
- Session lifecycle management
"""

import logging
import shutil
import sqlite3
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, HTTPException, Query

from codeframe.core.models import TaskStatus
from codeframe.core.session_manager import SessionManager
from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager
from codeframe.ui.dependencies import get_db, get_workspace_manager
from codeframe.auth import get_current_user, User
from codeframe.ui.models import (
    ProjectCreateRequest,
    ProjectResponse,
    SourceType,
)

# Valid task status values for API validation
VALID_TASK_STATUSES = {s.value for s in TaskStatus}


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/projects", tags=["projects"])


def is_hosted_mode() -> bool:
    """Check if running in hosted SaaS mode.

    Returns:
        True if hosted mode, False if self-hosted
    """
    from codeframe.ui.server import get_deployment_mode, DeploymentMode

    return get_deployment_mode() == DeploymentMode.HOSTED


@router.get("")
async def list_projects(
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all CodeFRAME projects accessible to the authenticated user."""

    # Get projects accessible to the current user
    projects = db.get_user_projects(current_user.id)

    return {"projects": projects}


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    request: ProjectCreateRequest,
    db: Database = Depends(get_db),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    current_user: User = Depends(get_current_user),
):
    """Create a new project.

    Args:
        request: Project creation request with name, description, source config
        db: Database connection
        workspace_manager: Workspace manager
        current_user: Authenticated user creating the project

    Returns:
        Created project details
    """
    # Security: Hosted mode cannot access user's local filesystem
    if is_hosted_mode() and request.source_type == SourceType.LOCAL_PATH:
        raise HTTPException(
            status_code=403, detail="source_type='local_path' not available in hosted mode"
        )

    # Check for duplicate project name
    try:
        existing_projects = db.list_projects()
    except sqlite3.Error as e:
        logger.error(f"Database error listing projects: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Database error occurred. Please try again later."
        )

    if any(p["name"] == request.name for p in existing_projects):
        raise HTTPException(
            status_code=409, detail=f"Project with name '{request.name}' already exists"
        )

    # Create project record first (to get ID)
    try:
        project_id = db.create_project(
            name=request.name,
            description=request.description,
            source_type=request.source_type.value,
            source_location=request.source_location,
            source_branch=request.source_branch,
            workspace_path="",  # Will be updated after workspace creation
            user_id=current_user.id,  # Assign project to current user
        )
    except sqlite3.Error as e:
        logger.error(f"Database error creating project: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Database error occurred. Please try again later."
        )

    # Create workspace
    try:
        workspace_path = workspace_manager.create_workspace(
            project_id=project_id,
            source_type=request.source_type,
            source_location=request.source_location,
            source_branch=request.source_branch,
        )

        # Update project with workspace path and git status
        try:
            db.update_project(
                project_id, {"workspace_path": str(workspace_path), "git_initialized": True}
            )
        except sqlite3.Error as db_error:
            # Database error during update - cleanup and fail
            logger.error(f"Database error updating project {project_id}: {db_error}")

            # Best-effort cleanup: delete project record
            try:
                db.delete_project(project_id)
            except sqlite3.Error as cleanup_db_error:
                logger.error(
                    f"Failed to delete project {project_id} during cleanup: {cleanup_db_error}"
                )

            # Best-effort cleanup: remove workspace directory (use actual workspace_path)
            if workspace_path.exists():
                try:
                    shutil.rmtree(workspace_path)
                    logger.info(f"Cleaned up workspace directory: {workspace_path}")
                except (OSError, PermissionError) as cleanup_fs_error:
                    logger.error(
                        f"Failed to clean up workspace {workspace_path}: {cleanup_fs_error}"
                    )

            raise HTTPException(
                status_code=500, detail="Database error occurred. Please try again later."
            )

    except HTTPException:
        # Re-raise HTTPException from database error handling above
        raise

    except Exception as e:
        # Cleanup: delete project and workspace if creation fails
        logger.error(f"Workspace creation failed for project {project_id}: {e}")

        # Best-effort cleanup: delete project record
        try:
            db.delete_project(project_id)
        except sqlite3.Error as cleanup_db_error:
            logger.error(
                f"Failed to delete project {project_id} during cleanup: {cleanup_db_error}"
            )

        # Explicitly clean up workspace directory if it exists
        # (Defense in depth: WorkspaceManager has cleanup, but this ensures
        # orphaned directories are removed even if that cleanup fails)
        workspace_path = workspace_manager.workspace_root / str(project_id)
        if workspace_path.exists():
            try:
                shutil.rmtree(workspace_path)
                logger.info(f"Cleaned up orphaned workspace: {workspace_path}")
            except (OSError, PermissionError) as cleanup_error:
                logger.error(f"Failed to clean up workspace {workspace_path}: {cleanup_error}")

        raise HTTPException(
            status_code=500, detail="Workspace creation failed. Please try again later."
        )

    # Return project details
    try:
        project = db.get_project(project_id)
    except sqlite3.Error as e:
        logger.error(f"Database error retrieving project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Database error occurred. Please try again later."
        )

    return ProjectResponse(
            id=project["id"],
            name=project["name"],
            status=project["status"],
            phase=project["phase"],
            created_at=project["created_at"],
            config=project["config"],
    )


@router.get("/{project_id}")
async def get_project(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get project by ID.

    Args:
        project_id: Project ID to retrieve

    Returns:
        Project details

    Raises:
        HTTPException:
            - 403: Access denied (user doesn't have access to this project)
            - 404: Project not found
    """
    # Get project from database
    project = db.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check - return 403 if user lacks access to existing project
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": project["id"],
        "name": project["name"],
        "description": project.get("description", ""),
        "status": project["status"],
        "phase": project["phase"],
        "created_at": project.get("created_at"),
        "workspace_path": project.get("workspace_path"),
        "config": project.get("config"),
    }


@router.get("/{project_id}/status")
async def get_project_status(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive project status."""
    # Get project from database
    project = db.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Calculate progress metrics (cf-46)
    progress = db._calculate_project_progress(project_id)

    return {
        "project_id": project["id"],
        "name": project["name"],
        "status": project["status"],
        "phase": project["phase"],
        "workflow_step": 1,  # Project doesn't have workflow_step, default to 1
        "progress": progress,
    }


@router.get("/{project_id}/tasks")
async def get_tasks(
    project_id: int,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000, description="Max tasks to return (1-1000)"),
    offset: int = Query(default=0, ge=0, description="Tasks to skip for pagination"),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get project tasks with filtering and pagination.

    Authorization: Requires project access.

    Args:
        project_id: Project ID to get tasks for
        status: Optional filter by task status. Valid values:
            'pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed'
        limit: Maximum number of tasks to return (1-1000, default: 50)
        offset: Number of tasks to skip for pagination (>=0, default: 0)
        db: Database instance (injected)

    Returns:
        Dictionary with:
        - tasks: List[Dict] - Paginated list of task dictionaries
        - total: int - Total number of tasks matching the filter (before pagination)

    Raises:
        HTTPException:
            - 400: Invalid status value
            - 404: Project not found
            - 422: Invalid parameters (negative offset, limit out of range)
            - 500: Database error

    Security Notes:
        - Input validation: limit constrained to 1-1000, offset must be >=0
        - Status parameter validated against TaskStatus enum values
        - Authorization: User must have project access (owner/collaborator/viewer)
    """
    try:
        # Validate status parameter against TaskStatus enum values
        if status is not None and status not in VALID_TASK_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid values: {', '.join(sorted(VALID_TASK_STATUSES))}"
            )

        # Validate project exists
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Authorization check
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")
        # if not db.user_has_project_access(current_user.id, project_id):
        #     raise HTTPException(status_code=403, detail="Access denied")

        # Query all tasks for the project
        tasks = db.get_project_tasks(project_id)

        # Apply status filtering if provided
        # NOTE: Client-side filtering used here. For large datasets (1000+ tasks),
        # consider adding database-level filtering in future optimization.
        if status is not None:
            tasks = [t for t in tasks if t.status.value == status]

        # Calculate total count before pagination
        total = len(tasks)

        # Apply pagination
        tasks = tasks[offset : offset + limit]

        # Convert Task objects to dictionaries for JSON serialization
        tasks_dicts = [t.to_dict() for t in tasks]

        return {"tasks": tasks_dicts, "total": total}

    except sqlite3.Error as e:
        logger.error(f"Database error fetching tasks for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching tasks")


@router.get("/{project_id}/activity")
async def get_activity(project_id: int, limit: int = 50, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get recent activity log."""
    try:
        # Authorization check
        project = db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        if not db.user_has_project_access(current_user.id, project_id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Query changelog table for activity
        activity_items = db.get_recent_activity(project_id, limit=limit)

        return {"activity": activity_items}
    except Exception as e:
        logger.error(f"Error fetching activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching activity: {str(e)}")


@router.get("/{project_id}/prd")
async def get_project_prd(project_id: int, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get PRD for a project (cf-26).

    Sprint 2 Foundation Contract:
    Returns PRDResponse with:
    - project_id: string (not int)
    - prd_content: string
    - generated_at: ISODate (RFC 3339 with timezone)
    - updated_at: ISODate (RFC 3339 with timezone)
    - status: 'available' | 'generating' | 'not_found'

    Args:
        project_id: Project ID

    Returns:
        PRDResponse dictionary

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get PRD from database
    prd_data = db.get_prd(project_id)

    if not prd_data:
        # PRD not found - return empty response
        return {
            "project_id": str(project_id),
            "prd_content": "",
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "not_found",
        }

    # PRD exists - return it
    return {
        "project_id": str(project_id),
        "prd_content": prd_data["prd_content"],
        "generated_at": prd_data["generated_at"],
        "updated_at": prd_data["updated_at"],
        "status": "available",
    }


@router.get("/{project_id}/issues")
async def get_project_issues(project_id: int, include: str = None, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get issues for a project (cf-26).

    Sprint 2 Foundation Contract:
    Returns IssuesResponse with:
    - issues: Issue[]
    - total_issues: number
    - total_tasks: number
    - next_cursor?: string (optional)
    - prev_cursor?: string (optional)

    Each Issue contains:
    - id: string (not int)
    - issue_number: string
    - title: string
    - description: string
    - status: WorkStatus
    - priority: number
    - depends_on: string[]
    - proposed_by: 'agent' | 'human'
    - created_at: ISODate (RFC 3339)
    - updated_at: ISODate (RFC 3339)
    - completed_at: ISODate | null
    - tasks?: Task[] (if include=tasks)

    Args:
        project_id: Project ID
        include: Optional query param, 'tasks' to include tasks

    Returns:
        IssuesResponse dictionary

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Determine if tasks should be included
    include_tasks = include == "tasks"

    # Get issues from database
    issues_data = db.get_issues_with_tasks(project_id, include_tasks)

    # Return according to API contract
    return issues_data


@router.get("/{project_id}/session", tags=["session"])
async def get_session_state(project_id: int, db: Database = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get current session state for project (T028).

    Args:
        project_id: Project ID

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
