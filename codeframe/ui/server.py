"""FastAPI Status Server for CodeFRAME."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime, UTC
import asyncio
import json
import logging
import os

from codeframe.core.models import (
    ProjectStatus,
    BlockerResolve,
    ContextItemCreateModel,
    ContextItemResponse,
)
from codeframe.persistence.database import Database
from codeframe.ui.models import (
    ProjectCreateRequest,
    ProjectResponse,
    SourceType,
    ReviewRequest,
)
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

# Sprint 9: Cache for review reports (task_id -> review report dict)
review_cache: Dict[int, dict] = {}


async def start_agent(
    project_id: int, db: Database, agents_dict: Dict[int, LeadAgent], api_key: str
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
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # cf-10.1: Store agent reference
        agents_dict[project_id] = agent

        # cf-10.1: Update project status to RUNNING
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # cf-10.4: Broadcast agent_started message
        try:
            await manager.broadcast(
                {
                    "type": "agent_started",
                    "project_id": project_id,
                    "agent_type": "lead",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )
        except Exception:
            # Continue even if broadcast fails
            pass

        # cf-10.4: Broadcast status_update message
        try:
            await manager.broadcast(
                {"type": "status_update", "project_id": project_id, "status": "running"}
            )
        except Exception:
            pass

        # cf-10.3: Send greeting message
        greeting = "Hi! I'm your Lead Agent. I'm here to help build your project. What would you like to create?"

        # cf-10.3: Save greeting to database
        db.create_memory(
            project_id=project_id, category="conversation", key="assistant", value=greeting
        )

        # cf-10.4: Broadcast greeting via WebSocket
        try:
            await manager.broadcast(
                {
                    "type": "chat_message",
                    "project_id": project_id,
                    "role": "assistant",
                    "content": greeting,
                }
            )
        except Exception:
            pass

    except Exception:
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
    existing_projects = app.state.db.list_projects()
    if any(p["name"] == request.name for p in existing_projects):
        raise HTTPException(
            status_code=409, detail=f"Project with name '{request.name}' already exists"
        )

    # Create project record first (to get ID)
    project_id = app.state.db.create_project(
        name=request.name,
        description=request.description,
        source_type=request.source_type.value,
        source_location=request.source_location,
        source_branch=request.source_branch,
        workspace_path="",  # Will be updated after workspace creation
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
        app.state.db.update_project(
            project_id, {"workspace_path": str(workspace_path), "git_initialized": True}
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


@app.get("/api/projects/{project_id}/agents")
async def get_agent_status(project_id: int):
    """Get status of all agents."""
    # Get agents from database
    agents = app.state.db.list_agents()

    return {"agents": agents}


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
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Check if project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Check if Lead Agent is running
    agent = running_agents.get(project_id)
    if not agent:
        raise HTTPException(
            status_code=400,
            detail="Lead Agent not started for this project. Start the agent first.",
        )

    try:
        # Send message to Lead Agent
        response_text = agent.chat(user_message)

        # Get current timestamp
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Broadcast assistant response via WebSocket
        try:
            await manager.broadcast(
                {
                    "type": "chat_message",
                    "project_id": project_id,
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": timestamp,
                }
            )
        except Exception:
            # Continue even if broadcast fails
            pass

        return {"response": response_text, "timestamp": timestamp}

    except Exception as e:
        # Log error and return 500
        raise HTTPException(
            status_code=500, detail=f"Error communicating with Lead Agent: {str(e)}"
        )


@app.get("/api/projects/{project_id}/chat/history")
async def get_chat_history(project_id: int, limit: int = 100, offset: int = 0):
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
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get conversation history from database
    db_messages = app.state.db.get_conversation(project_id)

    # Apply pagination
    start = offset
    end = offset + limit
    paginated_messages = db_messages[start:end]

    # Format messages for API response
    messages = []
    for msg in paginated_messages:
        messages.append(
            {
                "role": msg["key"],  # 'user' or 'assistant'
                "content": msg["value"],
                "timestamp": msg["created_at"],
            }
        )

    return {"messages": messages}


@app.post("/api/projects/{project_id}/discovery/answer")
async def submit_discovery_answer(project_id: int):
    """Submit answer to current discovery question (Feature: 012-discovery-answer-ui).

    This is a stub endpoint that returns 501 Not Implemented.
    Full implementation will be added in later tasks following TDD approach.

    Args:
        project_id: Project ID

    Returns:
        501 Not Implemented
    """
    raise HTTPException(
        status_code=501,
        detail="Discovery answer submission endpoint not yet implemented. Will be completed in Phase 6 (US5)."
    )


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
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get project phase (default to "discovery" if not set)
    project_phase = project.get("phase", "discovery")

    # Initialize LeadAgent to get discovery status
    # Use dummy API key for status retrieval (no API calls made)
    try:
        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=app.state.db, api_key="dummy-key-for-status")

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

        return {"project_id": project_id, "phase": project_phase, "discovery": discovery_data}

    except Exception as e:
        # Log error but don't expose internals
        raise HTTPException(
            status_code=500, detail=f"Error retrieving discovery progress: {str(e)}"
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
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Determine if tasks should be included
    include_tasks = include == "tasks"

    # Get issues from database
    issues_data = app.state.db.get_issues_with_tasks(project_id, include_tasks)

    # Return according to API contract
    return issues_data


# Blocker endpoints (049-human-in-loop)


@app.get("/api/projects/{project_id}/blockers")
async def get_project_blockers(project_id: int, status: str = None):
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
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

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
        raise HTTPException(status_code=404, detail=f"Blocker {blocker_id} not found")

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

    # Check if blocker exists
    blocker = app.state.db.get_blocker(blocker_id)
    if not blocker:
        raise HTTPException(
            status_code=404, detail={"error": "Blocker not found", "blocker_id": blocker_id}
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
                "resolved_at": blocker["resolved_at"],
            },
        )

    # Get updated blocker for response
    blocker = app.state.db.get_blocker(blocker_id)

    # Broadcast blocker_resolved event via WebSocket
    try:
        await manager.broadcast(
            {
                "type": "blocker_resolved",
                "blocker_id": blocker_id,
                "answer": request.answer,
                "resolved_at": blocker["resolved_at"],
            }
        )
    except Exception as e:
        # Log error but don't fail the request
        logger.error(f"Failed to broadcast blocker_resolved event: {e}")

    # Return success response
    return {"blocker_id": blocker_id, "status": "RESOLVED", "resolved_at": blocker["resolved_at"]}


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
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    # Get metrics
    metrics = app.state.db.get_blocker_metrics(project_id)
    return metrics


# Linting endpoints (Sprint 9 Phase 5: T115-T119)


@app.get("/api/lint/results", tags=["lint"])
async def get_lint_results(task_id: int):
    """Get lint results for a specific task (T116).

    Args:
        task_id: Task ID to get lint results for

    Returns:
        List of lint results with error/warning counts and full output

    Example:
        GET /api/lint/results?task_id=123
    """
    results = app.state.db.get_lint_results_for_task(task_id)
    return {"task_id": task_id, "results": results}


@app.get("/api/lint/trend", tags=["lint"])
async def get_lint_trend(project_id: int, days: int = 7):
    """Get lint error trend for project over time (T117).

    Args:
        project_id: Project ID
        days: Number of days to look back (default: 7)

    Returns:
        List of {date, linter, error_count, warning_count} dictionaries

    Example:
        GET /api/lint/trend?project_id=1&days=7
    """
    trend = app.state.db.get_lint_trend(project_id, days=days)
    return {"project_id": project_id, "days": days, "trend": trend}


@app.get("/api/lint/config", tags=["lint"])
async def get_lint_config(project_id: int):
    """Get current lint configuration for project (T118).

    Args:
        project_id: Project ID

    Returns:
        Lint configuration from pyproject.toml and .eslintrc.json

    Example:
        GET /api/lint/config?project_id=1
    """
    from pathlib import Path
    from codeframe.testing.lint_runner import LintRunner

    # Get project workspace path
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    workspace_path = Path(project.get("workspace_path", "."))

    # Load config using LintRunner
    lint_runner = LintRunner(workspace_path)

    return {
        "project_id": project_id,
        "config": lint_runner.config,
        "has_ruff_config": "ruff" in lint_runner.config,
        "has_eslint_config": "eslint" in lint_runner.config,
    }


@app.post("/api/lint/run", status_code=202, tags=["lint"])
async def run_lint_manual(request: Request):
    """Trigger manual lint run for specific files or task (T115).

    Args:
        request.json():
            - project_id: int
            - task_id: int (optional)
            - files: list[str] (optional, if not using task_id)

    Returns:
        202 Accepted: Lint results with error/warning counts

    Example:
        POST /api/lint/run
        {
            "project_id": 1,
            "task_id": 123
        }
    """
    from pathlib import Path
    from codeframe.testing.lint_runner import LintRunner

    data = await request.json()
    project_id = data.get("project_id")
    task_id = data.get("task_id")
    files = data.get("files", [])

    if not project_id:
        raise HTTPException(status_code=422, detail="project_id is required")

    # Get project workspace
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=404, detail={"error": "Project not found", "project_id": project_id}
        )

    workspace_path = Path(project.get("workspace_path", "."))

    # Get files to lint
    if task_id:
        # Get files from task metadata (placeholder - would need implementation)
        task = app.state.db.get_task(task_id)
        if task and "files_modified" in task:
            files = task["files_modified"]
        else:
            raise HTTPException(status_code=422, detail="Task has no files to lint")
    elif not files:
        raise HTTPException(status_code=422, detail="Either task_id or files must be provided")

    # Convert to Path objects
    file_paths = [Path(workspace_path) / f for f in files]

    # Broadcast lint started (T119)
    from codeframe.ui.websocket_broadcasts import broadcast_to_project

    await broadcast_to_project(
        project_id,
        {
            "type": "lint_started",
            "task_id": task_id,
            "file_count": len(file_paths),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # Run lint
    lint_runner = LintRunner(workspace_path)
    try:
        results = await lint_runner.run_lint(file_paths)
    except Exception as e:
        # Broadcast lint failed (T119)
        await broadcast_to_project(
            project_id,
            {
                "type": "lint_failed",
                "task_id": task_id,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        raise HTTPException(status_code=500, detail=str(e))

    # Store results if task_id provided
    if task_id:
        for result in results:
            result.task_id = task_id
            app.state.db.create_lint_result(
                task_id=result.task_id,
                linter=result.linter,
                error_count=result.error_count,
                warning_count=result.warning_count,
                files_linted=result.files_linted,
                output=result.output,
            )

    # Check quality gate
    has_errors = lint_runner.has_critical_errors(results)

    # Broadcast lint completed (T119)
    total_errors = sum(r.error_count for r in results)
    total_warnings = sum(r.warning_count for r in results)

    await broadcast_to_project(
        project_id,
        {
            "type": "lint_completed",
            "task_id": task_id,
            "has_errors": has_errors,
            "error_count": total_errors,
            "warning_count": total_warnings,
            "results": [r.to_dict() for r in results],
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    # Prepare response
    return {
        "status": "completed",
        "project_id": project_id,
        "task_id": task_id,
        "has_errors": has_errors,
        "results": [
            {
                "linter": r.linter,
                "error_count": r.error_count,
                "warning_count": r.warning_count,
                "files_linted": r.files_linted,
            }
            for r in results
        ],
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


@app.get("/api/agents/{agent_id}/context", tags=["context"])
async def list_context_items(
    agent_id: str, project_id: int, tier: Optional[str] = None, limit: int = 100, offset: int = 0
):
    """List context items for an agent with optional filters (T021).

    Args:
        agent_id: Agent ID to list context items for
        project_id: Project ID for the context items
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
    # Get context items from database (returns a list, not a dict)
    items_list = app.state.db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier=tier, limit=limit, offset=offset
    )

    # Convert items to ContextItemResponse models
    items = [
        ContextItemResponse(
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
        for item in items_list
    ]

    return {"items": items, "total": len(items), "offset": offset, "limit": limit}


@app.delete("/api/agents/{agent_id}/context/{item_id}", status_code=204, tags=["context"])
async def delete_context_item(agent_id: str, item_id: str):
    """Delete a context item (T022).

    Args:
        agent_id: Agent ID (used for path consistency)
        item_id: Context item ID to delete (UUID string)

    Returns:
        204 No Content: Successful deletion

    Raises:
        HTTPException:
            - 404: Context item not found
    """
    # Check if item exists before deletion
    item = app.state.db.get_context_item(item_id)

    if not item:
        raise HTTPException(status_code=404, detail=f"Context item {item_id} not found")

    # Delete context item
    app.state.db.delete_context_item(item_id)

    # Return 204 No Content (no response body)
    return None


@app.post("/api/agents/{agent_id}/context/update-scores", tags=["context"], response_model=dict)
async def update_context_scores(agent_id: str, project_id: int):
    """Recalculate importance scores for all context items (T033).

    Triggers batch recalculation of importance scores for all context items
    belonging to the specified agent on a project. Scores are recalculated based on:
    - Current age (time since creation)
    - Access patterns (access_count)
    - Item type weights

    Use cases:
    - Periodic batch updates (cron job)
    - Manual trigger after time passage
    - Debugging/testing score calculations

    Args:
        agent_id: Agent ID to recalculate scores for
        project_id: Project ID the agent is working on (query parameter)

    Returns:
        200 OK: {updated_count: int} - Number of items updated

    Example:
        POST /api/agents/backend-worker-001/context/update-scores?project_id=123
        Response: {"updated_count": 150}
    """
    from codeframe.lib.context_manager import ContextManager

    # Create context manager
    context_mgr = ContextManager(db=app.state.db)

    # Recalculate scores for all agent context items on this project
    updated_count = context_mgr.recalculate_scores_for_agent(project_id, agent_id)

    return {"updated_count": updated_count}


@app.post("/api/agents/{agent_id}/context/update-tiers", tags=["context"], response_model=dict)
async def update_context_tiers(agent_id: str, project_id: int):
    """Recalculate scores and reassign tiers for all context items (T042).

    Triggers batch recalculation of importance scores AND tier reassignment
    for all context items belonging to the specified agent on a project. This operation:
    1. Recalculates importance scores based on current age/access patterns
    2. Reassigns tiers (HOT >= 0.8, WARM 0.4-0.8, COLD < 0.4)

    Use cases:
    - Periodic tier maintenance (hourly cron job)
    - Manual trigger to move aged items to lower tiers
    - After major time passage (e.g., daily cleanup)

    Args:
        agent_id: Agent ID to update tiers for
        project_id: Project ID the agent is working on (query parameter)

    Returns:
        200 OK: {updated_count: int} - Number of items updated with new tiers

    Example:
        POST /api/agents/backend-worker-001/context/update-tiers?project_id=123
        Response: {"updated_count": 150}
    """
    from codeframe.lib.context_manager import ContextManager

    # Create context manager
    context_mgr = ContextManager(db=app.state.db)

    # Recalculate scores AND reassign tiers for all agent context items on this project
    updated_count = context_mgr.update_tiers_for_agent(project_id, agent_id)

    return {"updated_count": updated_count}


@app.post("/api/agents/{agent_id}/flash-save")
async def flash_save_context(agent_id: str, project_id: int, force: bool = False):
    """Trigger flash save for an agent's context (T054).

    Creates a checkpoint with full context state and archives COLD tier items
    to reduce memory footprint. Only triggers if context exceeds 80% of 180k token limit
    (144k tokens) unless force=True.

    Args:
        agent_id: Agent ID to flash save
        project_id: Project ID the agent is working on (query parameter)
        force: Force flash save even if below threshold (default: False)

    Returns:
        200 OK: FlashSaveResponse with checkpoint_id, tokens_before, tokens_after, reduction_percentage
        400 Bad Request: If below threshold and force=False

    Example:
        POST /api/agents/backend-worker-001/flash-save?project_id=123&force=false
        Response: {
            "checkpoint_id": 42,
            "tokens_before": 150000,
            "tokens_after": 50000,
            "reduction_percentage": 66.67,
            "items_archived": 20,
            "hot_items_retained": 10,
            "warm_items_retained": 15
        }
    """
    from codeframe.lib.context_manager import ContextManager

    # Create context manager
    context_mgr = ContextManager(db=app.state.db)

    # Check if flash save should be triggered
    should_save = context_mgr.should_flash_save(project_id, agent_id, force=force)

    if not should_save:
        return JSONResponse(
            status_code=400,
            content={"error": "Context below threshold. Use force=true to override."},
        )

    # Execute flash save
    result = context_mgr.flash_save(project_id, agent_id)

    # Emit WebSocket event (T059)
    await manager.broadcast_json(
        {
            "type": "flash_save_completed",
            "agent_id": agent_id,
            "project_id": project_id,
            "checkpoint_id": result["checkpoint_id"],
            "reduction_percentage": result["reduction_percentage"],
        }
    )

    return result


@app.get("/api/agents/{agent_id}/flash-save/checkpoints")
async def list_flash_save_checkpoints(agent_id: str, limit: int = 10):
    """List checkpoints for an agent (T055).

    Returns metadata about flash save checkpoints, sorted by creation time (most recent first).
    Does not include the full checkpoint_data JSON to keep response lightweight.

    Args:
        agent_id: Agent ID to list checkpoints for
        limit: Maximum number of checkpoints to return (default: 10, max: 100)

    Returns:
        200 OK: List of checkpoint metadata objects

    Example:
        GET /api/agents/backend-worker-001/flash-save/checkpoints?limit=5
        Response: [
            {
                "id": 42,
                "agent_id": "backend-worker-001",
                "items_count": 50,
                "items_archived": 20,
                "hot_items_retained": 15,
                "token_count": 150000,
                "created_at": "2025-11-14T10:30:00Z"
            },
            ...
        ]
    """
    # Clamp limit to reasonable range
    limit = min(max(limit, 1), 100)

    # Get checkpoints from database
    checkpoints = app.state.db.list_checkpoints(agent_id, limit=limit)

    # Remove checkpoint_data from response (too large)
    for checkpoint in checkpoints:
        checkpoint.pop("checkpoint_data", None)

    return checkpoints


@app.post("/api/agents/{agent_id}/review", tags=["review"])
async def trigger_review(agent_id: str, request: ReviewRequest):
    """Trigger code review for a task (T056).

    Sprint 9 - User Story 1: Review Agent API

    Executes code review using ReviewWorkerAgent and returns review report
    with findings, scores, and recommendations.

    Args:
        agent_id: Review agent ID to use
        request: ReviewRequest with task_id, project_id, files_modified

    Returns:
        200 OK: ReviewReport with status, overall_score, findings
        500 Internal Server Error: Review execution failed

    Example:
        POST /api/agents/review-001/review
        Body: {
            "task_id": 42,
            "project_id": 123,
            "files_modified": ["/path/to/file.py"]
        }

        Response: {
            "status": "approved",
            "overall_score": 85.5,
            "findings": [
                {
                    "category": "complexity",
                    "severity": "medium",
                    "message": "Function has complexity of 12",
                    "file_path": "/path/to/file.py",
                    "line_number": 42,
                    "suggestion": "Consider breaking into smaller functions"
                }
            ],
            "reviewer_agent_id": "review-001",
            "task_id": 42
        }
    """
    from codeframe.agents.review_worker_agent import ReviewWorkerAgent

    try:
        # Emit review started event (T059)
        await manager.broadcast(
            {
                "type": "review_started",
                "agent_id": agent_id,
                "project_id": request.project_id,
                "task_id": request.task_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Create review agent
        review_agent = ReviewWorkerAgent(
            agent_id=agent_id, project_id=request.project_id, db=app.state.db
        )

        # Get task data from database
        task_data = app.state.db.get_task(request.task_id)
        if not task_data:
            raise HTTPException(status_code=404, detail=f"Task {request.task_id} not found")

        # Build task dict for execute_task
        task = {
            "id": request.task_id,
            "task_number": task_data.get("task_number", "unknown"),
            "title": task_data.get("title", ""),
            "description": task_data.get("description", ""),
            "files_modified": request.files_modified,
        }

        # Execute review
        report = await review_agent.execute_task(task)

        if not report:
            raise HTTPException(status_code=500, detail="Review failed to produce report")

        # Cache the review report for later retrieval (T057, T058)
        report_dict = report.model_dump()
        report_dict["project_id"] = request.project_id  # Add project_id for filtering
        review_cache[request.task_id] = report_dict

        # Emit WebSocket event based on review status (T059)
        event_type_map = {
            "approved": "review_approved",
            "changes_requested": "review_changes_requested",
            "rejected": "review_rejected",
        }
        event_type = event_type_map.get(report.status, "review_completed")

        await manager.broadcast(
            {
                "type": event_type,
                "agent_id": agent_id,
                "project_id": request.project_id,
                "task_id": request.task_id,
                "status": report.status,
                "overall_score": report.overall_score,
                "findings_count": len(report.findings),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Return report as dict
        return report_dict

    except HTTPException:
        raise
    except Exception as e:
        # Emit failure event
        await manager.broadcast(
            {
                "type": "review_failed",
                "agent_id": agent_id,
                "project_id": request.project_id,
                "task_id": request.task_id,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        raise HTTPException(status_code=500, detail=f"Review execution failed: {str(e)}")


@app.get("/api/tasks/{task_id}/review-status", tags=["review"])
async def get_review_status(task_id: int):
    """Get review status for a task (T057).

    Returns the cached review report if available, otherwise indicates no review exists.

    Args:
        task_id: Task ID to get review status for

    Returns:
        200 OK: Review status object

    Example:
        GET /api/tasks/123/review-status
        Response: {
            "has_review": true,
            "status": "approved",
            "overall_score": 85.5,
            "findings_count": 3
        }
    """
    try:
        # Check if review exists in cache
        if task_id in review_cache:
            report = review_cache[task_id]
            return {
                "has_review": True,
                "status": report["status"],
                "overall_score": report["overall_score"],
                "findings_count": len(report.get("findings", [])),
            }
        else:
            # No review exists yet
            return {
                "has_review": False,
                "status": None,
                "overall_score": None,
                "findings_count": 0,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get review status: {str(e)}")


@app.get("/api/projects/{project_id}/review-stats", tags=["review"])
async def get_review_stats(project_id: int):
    """Get aggregated review statistics for a project (T058).

    Returns counts and averages for all reviews in the project.

    Args:
        project_id: Project ID to get review stats for

    Returns:
        200 OK: Review statistics object

    Example:
        GET /api/projects/123/review-stats
        Response: {
            "total_reviews": 5,
            "approved_count": 3,
            "changes_requested_count": 1,
            "rejected_count": 1,
            "average_score": 75.5
        }
    """
    try:
        # Filter reviews for this project
        project_reviews = [
            report for report in review_cache.values() if report.get("project_id") == project_id
        ]

        # Calculate stats
        total_reviews = len(project_reviews)

        if total_reviews == 0:
            return {
                "total_reviews": 0,
                "approved_count": 0,
                "changes_requested_count": 0,
                "rejected_count": 0,
                "average_score": 0.0,
            }

        # Count by status
        approved_count = sum(1 for r in project_reviews if r.get("status") == "approved")
        changes_requested_count = sum(
            1 for r in project_reviews if r.get("status") == "changes_requested"
        )
        rejected_count = sum(1 for r in project_reviews if r.get("status") == "rejected")

        # Calculate average score
        total_score = sum(r.get("overall_score", 0) for r in project_reviews)
        average_score = round(total_score / total_reviews, 1) if total_reviews > 0 else 0.0

        return {
            "total_reviews": total_reviews,
            "approved_count": approved_count,
            "changes_requested_count": changes_requested_count,
            "rejected_count": rejected_count,
            "average_score": average_score,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get review stats: {str(e)}")


@app.get("/api/agents/{agent_id}/context/stats")
async def get_context_stats(agent_id: str, project_id: int):
    """Get context statistics for an agent (T067).

    Returns tier counts and token usage breakdown for an agent's context.

    Args:
        agent_id: Agent ID to get stats for
        project_id: Project ID the agent is working on

    Returns:
        200 OK: ContextStats object with tier counts and token usage

    Example:
        GET /api/agents/backend-worker-001/context/stats?project_id=123
        Response: {
            "agent_id": "backend-worker-001",
            "project_id": 123,
            "hot_count": 20,
            "warm_count": 50,
            "cold_count": 30,
            "total_count": 100,
            "hot_tokens": 15000,
            "warm_tokens": 25000,
            "cold_tokens": 10000,
            "total_tokens": 50000,
            "token_usage_percentage": 27.8,
            "calculated_at": "2025-11-14T10:30:00Z"
        }
    """
    from codeframe.lib.token_counter import TokenCounter
    from datetime import datetime, UTC

    # Get all context items for this agent
    hot_items = app.state.db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier="hot", limit=10000
    )

    warm_items = app.state.db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier="warm", limit=10000
    )

    cold_items = app.state.db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier="cold", limit=10000
    )

    # Calculate token counts per tier
    token_counter = TokenCounter(cache_enabled=True)

    hot_tokens = token_counter.count_context_tokens(hot_items)
    warm_tokens = token_counter.count_context_tokens(warm_items)
    cold_tokens = token_counter.count_context_tokens(cold_items)

    total_tokens = hot_tokens + warm_tokens + cold_tokens

    # Calculate token usage percentage (out of 180k limit)
    TOKEN_LIMIT = 180000
    token_usage_percentage = (total_tokens / TOKEN_LIMIT) * 100 if TOKEN_LIMIT > 0 else 0.0

    return {
        "agent_id": agent_id,
        "project_id": project_id,
        "hot_count": len(hot_items),
        "warm_count": len(warm_items),
        "cold_count": len(cold_items),
        "total_count": len(hot_items) + len(warm_items) + len(cold_items),
        "hot_tokens": hot_tokens,
        "warm_tokens": warm_tokens,
        "cold_tokens": cold_tokens,
        "total_tokens": total_tokens,
        "token_usage_percentage": round(token_usage_percentage, 2),
        "calculated_at": datetime.now(UTC).isoformat(),
    }


@app.get("/api/agents/{agent_id}/context/items")
async def get_context_items(
    agent_id: str, project_id: int, tier: Optional[str] = None, limit: int = 100
):
    """Get context items for an agent, optionally filtered by tier.

    Returns a list of context items with their content and metadata.

    Args:
        agent_id: Agent ID to get items for
        project_id: Project ID the agent is working on
        tier: Optional tier filter ('hot', 'warm', 'cold')
        limit: Maximum number of items to return (default: 100, max: 1000)

    Returns:
        200 OK: List of ContextItem objects

    Example:
        GET /api/agents/backend-worker-001/context/items?project_id=123&tier=hot&limit=20
    """
    # Clamp limit to reasonable range
    limit = min(max(limit, 1), 1000)

    # Validate tier if provided
    if tier and tier not in ["hot", "warm", "cold"]:
        raise HTTPException(
            status_code=400, detail="Invalid tier. Must be 'hot', 'warm', or 'cold'"
        )

    # Get items from database
    items = app.state.db.list_context_items(
        project_id=project_id, agent_id=agent_id, tier=tier, limit=limit
    )

    return items


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
