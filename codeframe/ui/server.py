"""FastAPI Status Server for CodeFRAME."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum
import asyncio
import json
import logging
import os
import sqlite3

from codeframe.core.project import Project
from codeframe.core.models import (
    TaskStatus, AgentMaturity, ProjectStatus, BlockerResolve,
    ContextItemCreateModel, ContextItemResponse
)
from codeframe.persistence.database import Database
from codeframe.ui.models import ProjectCreateRequest, ProjectResponse, SourceType
from codeframe.agents.lead_agent import LeadAgent
from codeframe.workspace import WorkspaceManager


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
    db_path_str = os.environ.get("DATABASE_PATH", ".codeframe/state.db")
    db_path = Path(db_path_str)

    app.state.db = Database(db_path)
    app.state.db.initialize()

    # Initialize workspace manager
    workspace_root = Path.cwd() / ".codeframe" / "workspaces"
    app.state.workspace_manager = WorkspaceManager(workspace_root)

    yield

    # Shutdown: Close database connection
    if hasattr(app.state, "db") and app.state.db:
        app.state.db.close()


app = FastAPI(
    title="CodeFRAME Status Server",
    description="Real-time monitoring and control for CodeFRAME projects",
    version="0.1.0",
    lifespan=lifespan
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
        "http://localhost:3000",      # Next.js dev server
        "http://localhost:5173",      # Vite dev server
    ]

# Log CORS configuration for debugging
print(f"🔒 CORS Configuration:")
print(f"   CORS_ALLOWED_ORIGINS env: {cors_origins_env!r}")
print(f"   Parsed allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Client disconnected
                pass


manager = ConnectionManager()

# cf-10.1: Dictionary to track running agents by project_id
running_agents: Dict[int, LeadAgent] = {}


async def start_agent(
    project_id: int,
    db: Database,
    agents_dict: Dict[int, LeadAgent],
    api_key: str
) -> None:
    """Start Lead Agent for a project (cf-10.1).
    
    Args:
        project_id: Project ID to start agent for
        db: Database connection
        agents_dict: Dictionary to store running agents
        api_key: Anthropic API key for Lead Agent
        
    This function:
    - Creates LeadAgent instance
    - Updates project status to RUNNING
    - Saves greeting message to database
    - Broadcasts status updates via WebSocket
    """
    try:
        # cf-10.1: Create Lead Agent instance
        agent = LeadAgent(
            project_id=project_id,
            db=db,
            api_key=api_key
        )
        
        # cf-10.1: Store agent reference
        agents_dict[project_id] = agent
        
        # cf-10.1: Update project status to RUNNING
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})
        
        # cf-10.4: Broadcast agent_started message
        try:
            await manager.broadcast({
                "type": "agent_started",
                "project_id": project_id,
                "agent_type": "lead",
                "timestamp": asyncio.get_event_loop().time()
            })
        except Exception:
            # Continue even if broadcast fails
            pass
        
        # cf-10.4: Broadcast status_update message
        try:
            await manager.broadcast({
                "type": "status_update",
                "project_id": project_id,
                "status": "running"
            })
        except Exception:
            pass
        
        # cf-10.3: Send greeting message
        greeting = "Hi! I'm your Lead Agent. I'm here to help build your project. What would you like to create?"
        
        # cf-10.3: Save greeting to database
        db.create_memory(
            project_id=project_id,
            category="conversation",
            key="assistant",
            value=greeting
        )
        
        # cf-10.4: Broadcast greeting via WebSocket
        try:
            await manager.broadcast({
                "type": "chat_message",
                "project_id": project_id,
                "role": "assistant",
                "content": greeting
            })
        except Exception:
            pass
            
    except Exception as e:
        # Log error but let it propagate
        raise


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
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent.parent,
            stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        git_commit = "unknown"

    # Check database connection
    db_status = "connected" if hasattr(app.state, "db") and app.state.db else "disconnected"

    return {
        "status": "healthy",
        "service": "CodeFRAME Status Server",
        "version": app.version,
        "commit": git_commit,
        "deployed_at": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        "database": db_status
    }


@app.get("/api/projects")
async def list_projects():
    """List all CodeFRAME projects."""
    from fastapi import Request

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
            status_code=403,
            detail="source_type='local_path' not available in hosted mode"
        )

    # Create project record first (to get ID)
    project_id = app.state.db.create_project(
        name=request.name,
        description=request.description,
        source_type=request.source_type.value,
        source_location=request.source_location,
        source_branch=request.source_branch,
        workspace_path=""  # Will be updated after workspace creation
    )

    # Create workspace
    try:
        workspace_path = app.state.workspace_manager.create_workspace(
            project_id=project_id,
            source_type=request.source_type,
            source_location=request.source_location,
            source_branch=request.source_branch
        )

        # Update project with workspace path and git status
        app.state.db.update_project(
            project_id,
            {
                "workspace_path": str(workspace_path),
                "git_initialized": True
            }
        )

    except Exception as e:
        # Cleanup: delete project if workspace creation fails
        app.state.db.delete_project(project_id)
        raise HTTPException(status_code=500, detail=f"Workspace creation failed: {str(e)}")

    # Return project details
    project = app.state.db.get_project(project_id)

    return ProjectResponse(
        id=project["id"],
        name=project["name"],
        status=project.get("status", "init"),
        phase=project.get("phase", "discovery"),
        created_at=project["created_at"],
        config=project.get("config")
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
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )
    
    # cf-10.2: Handle idempotent behavior - already running
    if project["status"] == ProjectStatus.RUNNING.value:
        return JSONResponse(
            status_code=200,
            content={
                "message": f"Project {project_id} is already running",
                "status": "running"
            }
        )
    
    # cf-10.2: Get API key from environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY not configured"
        )
    
    # cf-10.2: Start agent in background task (non-blocking)
    background_tasks.add_task(
        start_agent,
        project_id,
        app.state.db,
        running_agents,
        api_key
    )
    
    # cf-10.2: Return 202 Accepted immediately
    return {
        "message": f"Starting Lead Agent for project {project_id}",
        "status": "starting"
    }


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
        "progress": progress
    }


@app.get("/api/projects/{project_id}/agents")
async def get_agent_status(project_id: int):
    """Get status of all agents."""
    # Get agents from database
    agents = app.state.db.list_agents()

    return {"agents": agents}


@app.get("/api/projects/{project_id}/tasks")
async def get_tasks(
    project_id: int,
    status: str | None = None,
    limit: int = 50
):
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
                "progress": 45
            }
        ],
        "total": 40
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


@app.post("/api/projects/{project_id}/chat")
async def chat_with_lead(project_id: int, message: Dict[str, str]):
    """Chat with Lead Agent (cf-14.1).

    Send user message to Lead Agent and get AI response.
    Broadcasts message via WebSocket for real-time updates.

    Args:
        project_id: Project ID
        message: Dict with 'message' key containing user message

    Returns:
        Dict with 'response' and 'timestamp'

    Raises:
        HTTPException:
            - 404: Project not found
            - 400: Empty message or agent not started
            - 500: Agent communication failure
    """
    from datetime import datetime, UTC

    # Validate input
    user_message = message.get("message", "").strip()
    if not user_message:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    # Check if project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Check if Lead Agent is running
    agent = running_agents.get(project_id)
    if not agent:
        raise HTTPException(
            status_code=400,
            detail="Lead Agent not started for this project. Start the agent first."
        )

    try:
        # Send message to Lead Agent
        response_text = agent.chat(user_message)

        # Get current timestamp
        timestamp = datetime.now(UTC).isoformat().replace('+00:00', 'Z')

        # Broadcast assistant response via WebSocket
        try:
            await manager.broadcast({
                "type": "chat_message",
                "project_id": project_id,
                "role": "assistant",
                "content": response_text,
                "timestamp": timestamp
            })
        except Exception:
            # Continue even if broadcast fails
            pass

        return {
            "response": response_text,
            "timestamp": timestamp
        }

    except Exception as e:
        # Log error and return 500
        raise HTTPException(
            status_code=500,
            detail=f"Error communicating with Lead Agent: {str(e)}"
        )


@app.get("/api/projects/{project_id}/chat/history")
async def get_chat_history(
    project_id: int,
    limit: int = 100,
    offset: int = 0
):
    """Get conversation history for a project (cf-14.1).

    Args:
        project_id: Project ID
        limit: Maximum messages to return (default: 100)
        offset: Number of messages to skip (default: 0)

    Returns:
        Dict with 'messages' list containing conversation history

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Get conversation history from database
    db_messages = app.state.db.get_conversation(project_id)

    # Apply pagination
    start = offset
    end = offset + limit
    paginated_messages = db_messages[start:end]

    # Format messages for API response
    messages = []
    for msg in paginated_messages:
        messages.append({
            "role": msg["key"],  # 'user' or 'assistant'
            "content": msg["value"],
            "timestamp": msg["created_at"]
        })

    return {"messages": messages}


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
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Get PRD from database
    prd_data = app.state.db.get_prd(project_id)

    if not prd_data:
        # PRD not found - return empty response
        return {
            "project_id": str(project_id),
            "prd_content": "",
            "generated_at": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            "updated_at": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
            "status": "not_found"
        }

    # PRD exists - return it
    return {
        "project_id": str(project_id),
        "prd_content": prd_data["prd_content"],
        "generated_at": prd_data["generated_at"],
        "updated_at": prd_data["updated_at"],
        "status": "available"
    }


@app.get("/api/projects/{project_id}/discovery/progress")
async def get_discovery_progress(project_id: int):
    """Get discovery progress for a project (cf-17.2).

    Returns discovery progress combined with project phase.

    Response format:
        {
            "project_id": int,
            "phase": str,  # Project phase (discovery, planning, development, etc.)
            "discovery": {  # null if discovery not started (idle state)
                "state": str,  # idle, discovering, completed
                "progress_percentage": float,  # 0-100
                "answered_count": int,
                "total_required": int,
                "remaining_count": int,  # Only in discovering state
                "current_question": dict,  # Only in discovering state
                "structured_data": dict  # Only in completed state
            }
        }

    Args:
        project_id: Project ID

    Returns:
        Discovery progress response

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Get project phase (default to "discovery" if not set)
    project_phase = project.get("phase", "discovery")

    # Initialize LeadAgent to get discovery status
    # Use dummy API key for status retrieval (no API calls made)
    try:
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(
            project_id=project_id,
            db=app.state.db,
            api_key="dummy-key-for-status"
        )

        # Get discovery status
        status = agent.get_discovery_status()

        # If discovery is in idle state, return null for discovery field
        if status["state"] == "idle":
            discovery_data = None
        else:
            # Build discovery response, excluding sensitive fields
            discovery_data = {
                "state": status["state"],
                "progress_percentage": status["progress_percentage"],
                "answered_count": status["answered_count"],
                "total_required": status["total_required"],
            }

            # Add state-specific fields
            if status["state"] == "discovering":
                discovery_data["remaining_count"] = status["remaining_count"]
                discovery_data["current_question"] = status.get("current_question")

            if status["state"] == "completed":
                discovery_data["structured_data"] = status.get("structured_data")

            # Exclude "answers" field for security (contains raw user input)

        return {
            "project_id": project_id,
            "phase": project_phase,
            "discovery": discovery_data
        }

    except Exception as e:
        # Log error but don't expose internals
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving discovery progress: {str(e)}"
        )


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
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Determine if tasks should be included
    include_tasks = include == "tasks"

    # Get issues from database
    issues_data = app.state.db.get_issues_with_tasks(project_id, include_tasks)

    # Return according to API contract
    return issues_data


# Blocker endpoints (049-human-in-loop)

@app.get("/api/projects/{project_id}/blockers")
async def get_project_blockers(
    project_id: int,
    status: str = None
):
    """Get blockers for a project (049-human-in-loop).

    Args:
        project_id: Project ID
        status: Optional filter by status ('PENDING', 'RESOLVED', 'EXPIRED')

    Returns:
        BlockerListResponse dictionary with:
        - blockers: List of blocker dictionaries
        - total: Total number of blockers
        - pending_count: Number of pending blockers
        - sync_count: Number of SYNC blockers
        - async_count: Number of ASYNC blockers

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Check if project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found"
        )

    # Get blockers from database
    blockers_data = app.state.db.list_blockers(project_id, status)

    return blockers_data


@app.get("/api/blockers/{blocker_id}")
async def get_blocker(blocker_id: int):
    """Get details of a specific blocker (049-human-in-loop).

    Args:
        blocker_id: Blocker ID

    Returns:
        Blocker dictionary

    Raises:
        HTTPException:
            - 404: Blocker not found
    """
    blocker = app.state.db.get_blocker(blocker_id)

    if not blocker:
        raise HTTPException(
            status_code=404,
            detail=f"Blocker {blocker_id} not found"
        )

    return blocker


@app.post("/api/blockers/{blocker_id}/resolve")
async def resolve_blocker_endpoint(blocker_id: int, request: BlockerResolve):
    """Resolve a blocker with user's answer (049-human-in-loop, Phase 4/US2).

    Args:
        blocker_id: Blocker ID to resolve
        request: BlockerResolve containing the answer

    Returns:
        200 OK: Blocker resolution successful
        {
            "blocker_id": int,
            "status": "RESOLVED",
            "resolved_at": ISODate (RFC 3339)
        }

        409 Conflict: Blocker already resolved
        {
            "error": "Blocker already resolved",
            "blocker_id": int,
            "resolved_at": ISODate (RFC 3339)
        }

        404 Not Found: Blocker doesn't exist
        {
            "error": "Blocker not found",
            "blocker_id": int
        }

    Raises:
        HTTPException:
            - 404: Blocker not found
            - 409: Blocker already resolved (duplicate resolution)
            - 422: Invalid request (validation error)
    """
    from datetime import datetime, UTC

    # Check if blocker exists
    blocker = app.state.db.get_blocker(blocker_id)
    if not blocker:
        raise HTTPException(
            status_code=404,
            detail={"error": "Blocker not found", "blocker_id": blocker_id}
        )

    # Attempt to resolve blocker (returns False if already resolved)
    success = app.state.db.resolve_blocker(blocker_id, request.answer)

    if not success:
        # Blocker already resolved - return 409 Conflict
        blocker = app.state.db.get_blocker(blocker_id)
        return JSONResponse(
            status_code=409,
            content={
                "error": "Blocker already resolved",
                "blocker_id": blocker_id,
                "resolved_at": blocker["resolved_at"]
            }
        )

    # Get updated blocker for response
    blocker = app.state.db.get_blocker(blocker_id)

    # Broadcast blocker_resolved event via WebSocket
    try:
        await manager.broadcast({
            "type": "blocker_resolved",
            "blocker_id": blocker_id,
            "answer": request.answer,
            "resolved_at": blocker["resolved_at"]
        })
    except Exception as e:
        # Log error but don't fail the request
        logger.error(f"Failed to broadcast blocker_resolved event: {e}")

    # Return success response
    return {
        "blocker_id": blocker_id,
        "status": "RESOLVED",
        "resolved_at": blocker["resolved_at"]
    }


@app.get("/api/projects/{project_id}/blockers/metrics")
async def get_blocker_metrics_endpoint(project_id: int):
    """Get blocker metrics for a project (049-human-in-loop, Phase 10/T062).

    Provides analytics on blocker resolution times and expiration rates.

    Args:
        project_id: Project ID to get metrics for

    Returns:
        200 OK: Blocker metrics
        {
            "avg_resolution_time_seconds": float | null,
            "expiration_rate_percent": float,
            "total_blockers": int,
            "resolved_count": int,
            "expired_count": int,
            "pending_count": int,
            "sync_count": int,
            "async_count": int
        }

        404 Not Found: Project doesn't exist
        {
            "error": "Project not found",
            "project_id": int
        }

    Raises:
        HTTPException:
            - 404: Project not found
    """
    # Verify project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404,
            detail={"error": "Project not found", "project_id": project_id}
        )

    # Get metrics
    metrics = app.state.db.get_blocker_metrics(project_id)
    return metrics


# Context Management endpoints (007-context-management)

@app.post("/api/agents/{agent_id}/context", status_code=201, response_model=ContextItemResponse, tags=["context"])
async def create_context_item(agent_id: str, request: ContextItemCreateModel):
    """Create a new context item for an agent (T019).

    Args:
        agent_id: Agent ID to create context item for
        request: ContextItemCreateModel with item_type and content

    Returns:
        201 Created: ContextItemResponse with created context item

    Raises:
        HTTPException:
            - 422: Invalid request (validation error)
    """
    # Create context item - score auto-calculated by database layer (Phase 4)
    item_id = app.state.db.create_context_item(
        agent_id=agent_id,
        item_type=request.item_type.value,
        content=request.content
    )

    # Get created item for response
    item = app.state.db.get_context_item(item_id)

    return ContextItemResponse(
        id=item["id"],
        agent_id=item["agent_id"],
        item_type=item["item_type"],
        content=item["content"],
        importance_score=item["importance_score"],
        tier=item["tier"],
        access_count=item["access_count"],
        created_at=item["created_at"],
        last_accessed=item["last_accessed"]
    )


@app.get("/api/agents/{agent_id}/context/{item_id}", response_model=ContextItemResponse, tags=["context"])
async def get_context_item(agent_id: str, item_id: int):
    """Get a single context item and update access tracking (T020).

    Args:
        agent_id: Agent ID (used for path consistency)
        item_id: Context item ID to retrieve

    Returns:
        200 OK: ContextItemResponse with context item details

    Raises:
        HTTPException:
            - 404: Context item not found
    """
    # Get context item
    item = app.state.db.get_context_item(item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Context item {item_id} not found"
        )

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
        tier=item["tier"],
        access_count=item["access_count"],
        created_at=item["created_at"],
        last_accessed=item["last_accessed"]
    )


@app.get("/api/agents/{agent_id}/context", tags=["context"])
async def list_context_items(
    agent_id: str,
    tier: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List context items for an agent with optional filters (T021).

    Args:
        agent_id: Agent ID to list context items for
        tier: Optional filter by tier (HOT, WARM, COLD)
        limit: Maximum items to return (default: 100)
        offset: Number of items to skip (default: 0)

    Returns:
        200 OK: Dictionary with:
            - items: List[ContextItemResponse]
            - total: int (total items matching filter)
            - offset: int
            - limit: int

    Raises:
        HTTPException:
            - 422: Invalid request (validation error)
    """
    # Get context items from database
    items_dict = app.state.db.list_context_items(
        agent_id=agent_id,
        tier=tier,
        limit=limit,
        offset=offset
    )

    # Convert items to ContextItemResponse models
    items = [
        ContextItemResponse(
            id=item["id"],
            agent_id=item["agent_id"],
            item_type=item["item_type"],
            content=item["content"],
            importance_score=item["importance_score"],
            tier=item["tier"],
            access_count=item["access_count"],
            created_at=item["created_at"],
            last_accessed=item["last_accessed"]
        )
        for item in items_dict["items"]
    ]

    return {
        "items": items,
        "total": items_dict["total"],
        "offset": offset,
        "limit": limit
    }


@app.delete("/api/agents/{agent_id}/context/{item_id}", status_code=204, tags=["context"])
async def delete_context_item(agent_id: str, item_id: int):
    """Delete a context item (T022).

    Args:
        agent_id: Agent ID (used for path consistency)
        item_id: Context item ID to delete

    Returns:
        204 No Content: Successful deletion

    Raises:
        HTTPException:
            - 404: Context item not found
    """
    # Check if item exists before deletion
    item = app.state.db.get_context_item(item_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"Context item {item_id} not found"
        )

    # Delete context item
    app.state.db.delete_context_item(item_id)

    # Return 204 No Content (no response body)
    return None


@app.post(
    "/api/agents/{agent_id}/context/update-scores",
    tags=["context"],
    response_model=dict
)
async def update_context_scores(agent_id: str):
    """Recalculate importance scores for all context items (T033).

    Triggers batch recalculation of importance scores for all context items
    belonging to the specified agent. Scores are recalculated based on:
    - Current age (time since creation)
    - Access patterns (access_count)
    - Item type weights

    Use cases:
    - Periodic batch updates (cron job)
    - Manual trigger after time passage
    - Debugging/testing score calculations

    Args:
        agent_id: Agent ID to recalculate scores for

    Returns:
        200 OK: {updated_count: int} - Number of items updated

    Example:
        POST /api/agents/backend-worker-001/context/update-scores
        Response: {"updated_count": 150}
    """
    from codeframe.lib.context_manager import ContextManager

    # Create context manager
    context_mgr = ContextManager(db=app.state.db)

    # Recalculate scores for all agent context items
    updated_count = context_mgr.recalculate_scores_for_agent(agent_id)

    return {"updated_count": updated_count}


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
                await websocket.send_json({
                    "type": "subscribed",
                    "project_id": project_id
                })

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
            "data": {
                "progress": 65,
                "active_agents": 3,
                "completed_tasks": 26
            }
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
        help="Host to bind to (default: 0.0.0.0 or HOST env var)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("BACKEND_PORT", os.environ.get("PORT", "8080"))),
        help="Port to bind to (default: 8080 or BACKEND_PORT/PORT env var)"
    )

    args = parser.parse_args()

    run_server(host=args.host, port=args.port)