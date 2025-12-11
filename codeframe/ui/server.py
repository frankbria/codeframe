"""FastAPI Status Server for CodeFRAME."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime, UTC, timezone
import asyncio
import json
import logging
import os
import shutil
import sqlite3

from codeframe.core.models import (
    ProjectStatus,
    TaskStatus,
    ContextItemCreateModel,
    ContextItemResponse,
)
from codeframe.persistence.database import Database
from codeframe.ui.models import (
    ProjectCreateRequest,
    ProjectResponse,
    SourceType,
    QualityGatesRequest,
    CheckpointCreateRequest,
    CheckpointResponse,
    CheckpointDiffResponse,
    RestoreCheckpointRequest,
    AgentAssignmentRequest,
    AgentRoleUpdateRequest,
    AgentAssignmentResponse,
    ProjectAssignmentResponse,
)
from codeframe.agents.lead_agent import LeadAgent
from codeframe.workspace import WorkspaceManager
from codeframe.ui.routers import lint
from codeframe.ui.shared import (
    manager,
    running_agents,
    review_cache,
    start_agent,
)
from codeframe.ui.routers import metrics
from codeframe.ui.routers import chat
from codeframe.ui.routers import blockers
from codeframe.ui.routers import discovery
from codeframe.ui.routers import context
from codeframe.ui.routers import review
from codeframe.ui.routers import quality_gates
from codeframe.ui.routers import checkpoints


class DeploymentMode(str, Enum):
    """Deployment mode for CodeFRAME."""

    SELF_HOSTED = "self_hosted"
    HOSTED = "hosted"


def get_deployment_mode() -> DeploymentMode:
    """Get current deployment mode from environment.

    Returns:
        DeploymentMode.SELF_HOSTED or DeploymentMode.HOSTED
    """
    mode = os.getenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted").lower()

    if mode == "hosted":
        return DeploymentMode.HOSTED
    return DeploymentMode.SELF_HOSTED


def is_hosted_mode() -> bool:
    """Check if running in hosted SaaS mode.

    Returns:
        True if hosted mode, False if self-hosted
    """
    return get_deployment_mode() == DeploymentMode.HOSTED


# Module logger
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup: Initialize database
    # If DATABASE_PATH is not set, use default relative to WORKSPACE_ROOT
    db_path_str = os.environ.get("DATABASE_PATH")
    if db_path_str:
        db_path = Path(db_path_str)
    else:
        # Use WORKSPACE_ROOT if set, otherwise use current directory
        workspace_root = Path(os.environ.get("WORKSPACE_ROOT", "."))
        db_path = workspace_root / ".codeframe" / "state.db"

    app.state.db = Database(db_path)
    app.state.db.initialize()

    # Initialize workspace manager
    # Allow WORKSPACE_ROOT override for testing
    workspace_root_str = os.environ.get(
        "WORKSPACE_ROOT", str(Path.cwd() / ".codeframe" / "workspaces")
    )
    workspace_root = Path(workspace_root_str)
    app.state.workspace_manager = WorkspaceManager(workspace_root)

    yield

    # Shutdown: Close database connection
    if hasattr(app.state, "db") and app.state.db:
        app.state.db.close()


app = FastAPI(
    title="CodeFRAME Status Server",
    description="Real-time monitoring and control for CodeFRAME projects",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration from environment variables
# Get CORS_ALLOWED_ORIGINS from env (comma-separated list)
cors_origins_env = os.environ.get("CORS_ALLOWED_ORIGINS", "")

# Parse comma-separated origins
if cors_origins_env:
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
else:
    # Fallback to development defaults if not configured
    allowed_origins = [
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:5173",  # Vite dev server
    ]

# Log CORS configuration for debugging
print("🔒 CORS Configuration:")
print(f"   CORS_ALLOWED_ORIGINS env: {cors_origins_env!r}")
print(f"   Parsed allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(lint.router)
app.include_router(metrics.router)
app.include_router(chat.router)
app.include_router(blockers.router)
app.include_router(blockers.blocker_router)
app.include_router(discovery.router)
app.include_router(context.router)
app.include_router(review.router)
app.include_router(quality_gates.router)
app.include_router(checkpoints.router)


# Shared state imported from codeframe.ui.shared:
# - ConnectionManager class
# - manager (ConnectionManager instance)
# - running_agents (Dict[int, LeadAgent])
# - review_cache (Dict[int, dict])
# - start_agent() function

# API Routes


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "online", "service": "CodeFRAME Status Server"}


@app.get("/health")
async def health_check():
    """Detailed health check with deployment info.

    Returns:
        - status: Service health status
        - version: API version from FastAPI app
        - commit: Git commit hash (short)
        - deployed_at: Server startup timestamp
        - database: Database connection status
    """
    import subprocess
    from datetime import datetime, UTC

    # Get git commit hash
    try:
        git_commit = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent.parent.parent,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except Exception:
        git_commit = "unknown"

    # Check database connection
    db_status = "connected" if hasattr(app.state, "db") and app.state.db else "disconnected"

    return {
        "status": "healthy",
        "service": "CodeFRAME Status Server",
        "version": app.version,
        "commit": git_commit,
        "deployed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database": db_status,
    }


@app.get("/api/projects")
async def list_projects():
    """List all CodeFRAME projects."""

    # Get projects from database
    projects = app.state.db.list_projects()

    return {"projects": projects}


@app.post("/api/projects", status_code=201, response_model=ProjectResponse)
async def create_project(request: ProjectCreateRequest):
    """Create a new project.

    Args:
        request: Project creation request with name, description, source config

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
        existing_projects = app.state.db.list_projects()
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
        project_id = app.state.db.create_project(
            name=request.name,
            description=request.description,
            source_type=request.source_type.value,
            source_location=request.source_location,
            source_branch=request.source_branch,
            workspace_path="",  # Will be updated after workspace creation
        )
    except sqlite3.Error as e:
        logger.error(f"Database error creating project: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Database error occurred. Please try again later."
        )

    # Create workspace
    try:
        workspace_path = app.state.workspace_manager.create_workspace(
            project_id=project_id,
            source_type=request.source_type,
            source_location=request.source_location,
            source_branch=request.source_branch,
        )

        # Update project with workspace path and git status
        try:
            app.state.db.update_project(
                project_id, {"workspace_path": str(workspace_path), "git_initialized": True}
            )
        except sqlite3.Error as db_error:
            # Database error during update - cleanup and fail
            logger.error(f"Database error updating project {project_id}: {db_error}")

            # Best-effort cleanup: delete project record
            try:
                app.state.db.delete_project(project_id)
            except sqlite3.Error as cleanup_db_error:
                logger.error(f"Failed to delete project {project_id} during cleanup: {cleanup_db_error}")

            # Best-effort cleanup: remove workspace directory (use actual workspace_path)
            if workspace_path.exists():
                try:
                    shutil.rmtree(workspace_path)
                    logger.info(f"Cleaned up workspace directory: {workspace_path}")
                except (OSError, PermissionError) as cleanup_fs_error:
                    logger.error(f"Failed to clean up workspace {workspace_path}: {cleanup_fs_error}")

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
            app.state.db.delete_project(project_id)
        except sqlite3.Error as cleanup_db_error:
            logger.error(f"Failed to delete project {project_id} during cleanup: {cleanup_db_error}")

        # Explicitly clean up workspace directory if it exists
        # (Defense in depth: WorkspaceManager has cleanup, but this ensures
        # orphaned directories are removed even if that cleanup fails)
        workspace_path = app.state.workspace_manager.workspace_root / str(project_id)
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
        project = app.state.db.get_project(project_id)
    except sqlite3.Error as e:
        logger.error(f"Database error retrieving project {project_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Database error occurred. Please try again later."
        )

    return ProjectResponse(
        id=project["id"],
        name=project["name"],
        status=project.get("status", "init"),
        phase=project.get("phase", "discovery"),
        created_at=project["created_at"],
        config=project.get("config"),
    )


@app.post("/api/projects/{project_id}/start", status_code=202)
async def start_project_agent(project_id: int, background_tasks: BackgroundTasks):
    """Start Lead Agent for a project (cf-10.2).

    Returns 202 Accepted immediately and starts agent in background.

    Args:
        project_id: Project ID to start agent for
        background_tasks: FastAPI background tasks

    Returns:
        202 Accepted with message
        200 OK if already running
        404 Not Found if project doesn't exist

    Raises:
        HTTPException: 404 if project not found
    """
    # cf-10.2: Check if project exists
    project = app.state.db.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # cf-10.2: Handle idempotent behavior - already running
    if project["status"] == ProjectStatus.RUNNING.value:
        return JSONResponse(
            status_code=200,
            content={"message": f"Project {project_id} is already running", "status": "running"},
        )

    # cf-10.2: Get API key from environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # cf-10.2: Start agent in background task (non-blocking)
    background_tasks.add_task(start_agent, project_id, app.state.db, running_agents, api_key)

    # cf-10.2: Return 202 Accepted immediately
    return {"message": f"Starting Lead Agent for project {project_id}", "status": "starting"}


@app.get("/api/projects/{project_id}/status")
async def get_project_status(project_id: int):
    """Get comprehensive project status."""
    # Get project from database
    project = app.state.db.get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Calculate progress metrics (cf-46)
    progress = app.state.db._calculate_project_progress(project_id)

    return {
        "project_id": project["id"],
        "name": project["name"],
        "status": project["status"],
        "phase": project.get("phase", "discovery"),
        "workflow_step": project.get("workflow_step", 1),
        "progress": progress,
    }


@app.get("/api/projects/{project_id}/agents", response_model=List[AgentAssignmentResponse])
async def get_project_agents(
    project_id: int,
    active_only: bool = Query(True, alias="is_active"),
):
    """Get all agents assigned to a project.

    Multi-Agent Per Project API (Phase 3) - Updated endpoint.

    Args:
        project_id: Project ID
        active_only: If True, only return currently assigned agents (default: True)

    Returns:
        List of agents with assignment metadata

    Raises:
        HTTPException: 404 if project not found, 500 on database error
    """
    try:
        # Verify project exists
        project = app.state.db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Get agents for project using new database method
        agents = app.state.db.get_agents_for_project(project_id, active_only=active_only)

        return agents
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agents for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching agents: {str(e)}")


@app.post("/api/projects/{project_id}/agents", status_code=201, response_model=dict)
async def assign_agent_to_project(project_id: int, request: AgentAssignmentRequest):
    """Assign an agent to a project.

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        project_id: Project ID
        request: Agent assignment request with agent_id and role

    Returns:
        dict with assignment_id and success message

    Raises:
        HTTPException: 400 if agent already assigned, 404 if project/agent not found, 500 on error
    """
    try:
        # Verify project exists
        project = app.state.db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Verify agent exists
        agent = app.state.db.get_agent(request.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {request.agent_id} not found")

        # Check if agent is already assigned (active)
        existing = app.state.db.get_agent_assignment(project_id, request.agent_id)
        if existing and existing.get('is_active'):
            raise HTTPException(
                status_code=400,
                detail=f"Agent {request.agent_id} is already assigned to project {project_id}"
            )

        # Assign agent to project
        assignment_id = app.state.db.assign_agent_to_project(
            project_id=project_id,
            agent_id=request.agent_id,
            role=request.role
        )

        logger.info(f"Assigned agent {request.agent_id} to project {project_id} with role {request.role}")

        return {
            "assignment_id": assignment_id,
            "message": f"Agent {request.agent_id} assigned to project {project_id} with role {request.role}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning agent to project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error assigning agent: {str(e)}")


@app.delete("/api/projects/{project_id}/agents/{agent_id}", status_code=204)
async def remove_agent_from_project(project_id: int, agent_id: str):
    """Remove an agent from a project (soft delete).

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        project_id: Project ID
        agent_id: Agent ID to remove

    Returns:
        No content (204) on success

    Raises:
        HTTPException: 404 if assignment not found, 500 on error
    """
    try:
        # Remove agent from project
        rows_affected = app.state.db.remove_agent_from_project(project_id, agent_id)

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}"
            )

        logger.info(f"Removed agent {agent_id} from project {project_id}")

        return None  # 204 No Content
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing agent from project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error removing agent: {str(e)}")


@app.put("/api/projects/{project_id}/agents/{agent_id}/role", response_model=AgentAssignmentResponse)
async def update_agent_role(project_id: int, agent_id: str, request: AgentRoleUpdateRequest):
    """Update an agent's role on a project.

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        request: New role for the agent

    Returns:
        AgentAssignmentResponse with updated assignment details

    Raises:
        HTTPException: 404 if assignment not found, 500 on error
    """
    try:
        # Update agent role
        rows_affected = app.state.db.reassign_agent_role(
            project_id=project_id,
            agent_id=agent_id,
            new_role=request.role
        )

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}"
            )

        logger.info(f"Updated agent {agent_id} role to {request.role} on project {project_id}")

        # Fetch assignment details (junction table fields only)
        assignment = app.state.db.get_agent_assignment(project_id, agent_id)
        if not assignment:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to retrieve updated assignment for agent {agent_id}"
            )

        # Fetch full agent details (type, provider, status, etc.)
        agent = app.state.db.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent {agent_id} not found"
            )

        # Merge assignment and agent data to create full AgentAssignmentResponse
        full_assignment = {
            # From agents table
            "agent_id": agent["id"],
            "type": agent["type"],
            "provider": agent.get("provider"),
            "maturity_level": agent.get("maturity_level"),
            "status": agent.get("status"),
            "current_task_id": agent.get("current_task_id"),
            "last_heartbeat": agent.get("last_heartbeat"),
            # From project_agents table
            "assignment_id": assignment["id"],
            "role": assignment["role"],
            "assigned_at": assignment["assigned_at"],
            "unassigned_at": assignment.get("unassigned_at"),
            "is_active": assignment["is_active"],
        }

        return full_assignment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent role: {str(e)}")


@app.patch("/api/projects/{project_id}/agents/{agent_id}")
async def patch_agent_role(project_id: int, agent_id: str, request: AgentRoleUpdateRequest):
    """Update an agent's role on a project (PATCH variant).

    Multi-Agent Per Project API (Phase 3) - PATCH endpoint for consistency with tests.

    Args:
        project_id: Project ID
        agent_id: Agent ID
        request: New role for the agent

    Returns:
        dict with success message

    Raises:
        HTTPException: 404 if assignment not found, 422 for validation errors, 500 on error
    """
    try:
        # Update agent role
        rows_affected = app.state.db.reassign_agent_role(
            project_id=project_id,
            agent_id=agent_id,
            new_role=request.role
        )

        if rows_affected == 0:
            raise HTTPException(
                status_code=404,
                detail=f"No active assignment found for agent {agent_id} on project {project_id}"
            )

        logger.info(f"Updated agent {agent_id} role to {request.role} on project {project_id}")

        return {
            "message": f"Agent {agent_id} role updated to {request.role} on project {project_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent role: {str(e)}")


@app.get("/api/agents/{agent_id}/projects", response_model=List[ProjectAssignmentResponse])
async def get_agent_projects(
    agent_id: str,
    active_only: bool = Query(True),
):
    """Get all projects an agent is assigned to.

    Multi-Agent Per Project API (Phase 3) - New endpoint.

    Args:
        agent_id: Agent ID
        active_only: If True, only return active assignments (default: True)

    Returns:
        List of projects with assignment metadata

    Raises:
        HTTPException: 404 if agent not found, 500 on database error
    """
    try:
        # Verify agent exists
        agent = app.state.db.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Get projects for agent using new database method
        projects = app.state.db.get_projects_for_agent(agent_id, active_only=active_only)

        return projects
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching projects for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching projects: {str(e)}")


@app.get("/api/projects/{project_id}/tasks")
async def get_tasks(project_id: int, status: str | None = None, limit: int = 50):
    """Get project tasks."""
    # TODO: Query database with filters
    return {
        "tasks": [
            {
                "id": 27,
                "title": "JWT refresh token flow",
                "description": "Implement token refresh endpoint",
                "status": "in_progress",
                "assigned_to": "backend-1",
                "priority": 0,
                "workflow_step": 7,
                "progress": 45,
            }
        ],
        "total": 40,
    }


@app.get("/api/projects/{project_id}/activity")
async def get_activity(project_id: int, limit: int = 50):
    """Get recent activity log."""
    try:
        # Query changelog table for activity
        activity_items = app.state.db.get_recent_activity(project_id, limit=limit)

        return {"activity": activity_items}
    except Exception as e:
        logger.error(f"Error fetching activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching activity: {str(e)}")


@app.get("/api/projects/{project_id}/prd")
async def get_project_prd(project_id: int):
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
    from datetime import datetime, UTC

    # Check if project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get PRD from database
    prd_data = app.state.db.get_prd(project_id)

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

@app.get("/api/projects/{project_id}/issues")
async def get_project_issues(project_id: int, include: str = None):
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
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Determine if tasks should be included
    include_tasks = include == "tasks"

    # Get issues from database
    issues_data = app.state.db.get_issues_with_tasks(project_id, include_tasks)

    # Return according to API contract
    return issues_data


# Session Lifecycle endpoints (014-session-lifecycle)


@app.get("/api/projects/{project_id}/session", tags=["session"])
async def get_session_state(project_id: int):
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
    from codeframe.core.session_manager import SessionManager

    # Get project
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

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


# Context Management endpoints (007-context-management)


@app.post(
    "/api/agents/{agent_id}/context",
    status_code=201,
    response_model=ContextItemResponse,
    tags=["context"],
)
async def create_context_item(agent_id: str, project_id: int, request: ContextItemCreateModel):
    """Create a new context item for an agent (T019).

    Args:
        agent_id: Agent ID to create context item for
        project_id: Project ID for the context item
        request: ContextItemCreateModel with item_type and content

    Returns:
        201 Created: ContextItemResponse with created context item

    Raises:
        HTTPException:
            - 422: Invalid request (validation error)
    """
    # Create context item - score auto-calculated by database layer (Phase 4)
    item_id = app.state.db.create_context_item(
        project_id=project_id,
        agent_id=agent_id,
        item_type=request.item_type.value,
        content=request.content,
    )

    # Get created item for response
    item = app.state.db.get_context_item(item_id)

    return ContextItemResponse(
        id=item["id"],
        agent_id=item["agent_id"],
        item_type=item["item_type"],
        content=item["content"],
        importance_score=item["importance_score"],
        tier=item["current_tier"],
        access_count=item["access_count"],
        created_at=item["created_at"],
        last_accessed=item["last_accessed"],
    )


@app.get(
    "/api/agents/{agent_id}/context/{item_id}", response_model=ContextItemResponse, tags=["context"]
)
async def get_context_item(agent_id: str, item_id: str):
    """Get a single context item and update access tracking (T020).

    Args:
        agent_id: Agent ID (used for path consistency)
        item_id: Context item ID to retrieve (UUID string)

    Returns:
        200 OK: ContextItemResponse with context item details

    Raises:
        HTTPException:
            - 404: Context item not found
    """
    # Get context item
    item = app.state.db.get_context_item(item_id)

    if not item:
        raise HTTPException(status_code=404, detail=f"Context item {item_id} not found")

    # Update access tracking
    app.state.db.update_context_item_access(item_id)

    # Get updated item for response
    item = app.state.db.get_context_item(item_id)

    return ContextItemResponse(
        id=item["id"],
        agent_id=item["agent_id"],
        item_type=item["item_type"],
        content=item["content"],
        importance_score=item["importance_score"],
        tier=item["current_tier"],
        access_count=item["access_count"],
        created_at=item["created_at"],
        last_accessed=item["last_accessed"],
    )



@app.post("/api/projects/{project_id}/pause")
async def pause_project(project_id: int):
    """Pause project execution."""
    # TODO: Trigger flash save and pause agents
    return {"success": True, "message": "Project paused"}


@app.post("/api/projects/{project_id}/resume")
async def resume_project(project_id: int):
    """Resume project execution."""
    # TODO: Restore from checkpoint and resume agents
    return {"success": True, "message": "Project resuming"}


# WebSocket for real-time updates


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "subscribe":
                # Subscribe to specific project updates
                project_id = message.get("project_id")
                # TODO: Track subscriptions
                await websocket.send_json({"type": "subscribed", "project_id": project_id})

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Background task to broadcast updates
async def broadcast_updates():
    """Periodically broadcast project updates to connected clients."""
    while True:
        await asyncio.sleep(5)  # Update every 5 seconds

        # TODO: Gather latest project state
        update = {
            "type": "status_update",
            "timestamp": "2025-01-15T14:35:00Z",
            "data": {"progress": 65, "active_agents": 3, "completed_tasks": 26},
        }

        await manager.broadcast(update)


def run_server(host: str = "0.0.0.0", port: int = 8080):
    """Run the Status Server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="CodeFRAME Status Server")
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0 or HOST env var)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8080"))),
        help="Port to bind to (default: 8080 or BACKEND_PORT/PORT env var)",
    )

    args = parser.parse_args()

    run_server(host=args.host, port=args.port)
