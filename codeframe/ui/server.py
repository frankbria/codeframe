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

from codeframe.core.models import (
    ProjectStatus,
    TaskStatus,
    BlockerResolve,
    ContextItemCreateModel,
    ContextItemResponse,
    DiscoveryAnswer,
    DiscoveryAnswerResponse,
)
from codeframe.persistence.database import Database
from codeframe.ui.models import (
    ProjectCreateRequest,
    ProjectResponse,
    SourceType,
    ReviewRequest,
    QualityGatesRequest,
    CheckpointCreateRequest,
    CheckpointResponse,
    RestoreCheckpointRequest,
    AgentAssignmentRequest,
    AgentRoleUpdateRequest,
    AgentAssignmentResponse,
    ProjectAssignmentResponse,
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

        # Fetch and return the updated assignment details
        assignment = app.state.db.get_agent_assignment(project_id, agent_id)
        if not assignment:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to retrieve updated assignment for agent {agent_id}"
            )

        return assignment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent role: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating agent role: {str(e)}")


@app.get("/api/agents/{agent_id}/projects", response_model=List[ProjectAssignmentResponse])
async def get_agent_projects(
    agent_id: str,
    active_only: bool = Query(True, alias="is_active"),
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
async def submit_discovery_answer(project_id: int, answer_data: DiscoveryAnswer):
    """Submit answer to current discovery question (Feature: 012-discovery-answer-ui, US5).

    Implementation following TDD approach (T041-T044):
    - Validates project exists and is in discovery phase
    - Processes answer through Lead Agent
    - Broadcasts WebSocket events for real-time UI updates
    - Returns updated discovery status

    Args:
        project_id: Project ID
        answer_data: Answer submission data (Pydantic model with validation)

    Returns:
        DiscoveryAnswerResponse with next question and progress

    Raises:
        HTTPException:
            - 400: Validation error or wrong phase
            - 404: Project not found
            - 500: Missing API key or processing error
    """
    from codeframe.ui.websocket_broadcasts import (
        broadcast_discovery_answer_submitted,
        broadcast_discovery_question_presented,
        broadcast_discovery_completed,
    )

    # T041: Validate project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # T041: Validate project is in discovery phase
    if project.get("phase") != "discovery":
        raise HTTPException(
            status_code=400,
            detail=f"Project is not in discovery phase. Current phase: {project.get('phase')}",
        )

    # T042: Validate ANTHROPIC_API_KEY is available
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable is not set. Cannot process discovery answers.",
        )

    # T042: Get Lead Agent and process answer
    try:
        agent = LeadAgent(project_id=project_id, db=app.state.db, api_key=api_key)

        # CRITICAL: Validate discovery is active before processing answer
        status = agent.get_discovery_status()
        if status.get("state") != "discovering":
            raise HTTPException(
                status_code=400,
                detail=f"Discovery is not active. Current state: {status.get('state')}. "
                f"Please start discovery first by calling POST /api/projects/{project_id}/discovery/start",
            )

        # Process the answer (trimmed by Pydantic validator)
        agent.process_discovery_answer(answer_data.answer)

        # Get updated discovery status after processing
        status = agent.get_discovery_status()

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Failed to process discovery answer for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process answer: {str(e)}")

    # T043: Compute derived values from status to match LeadAgent.get_discovery_status() format
    is_complete = status.get("state") == "completed"
    total_questions = status.get("total_required", 0)
    answered_count = status.get("answered_count", 0)
    current_question_index = answered_count  # Index is based on how many answered
    current_question_id = status.get("current_question", {}).get("id", "")
    current_question_text = status.get("current_question", {}).get("text", "")
    progress_percentage = status.get("progress_percentage", 0.0)

    # T043: Broadcast WebSocket events
    try:
        # Broadcast answer submitted event
        await broadcast_discovery_answer_submitted(
            manager=manager,
            project_id=project_id,
            question_id=current_question_id,
            answer_preview=answer_data.answer[:100],  # First 100 chars
            current_index=current_question_index,
            total_questions=total_questions,
        )

        # Broadcast appropriate follow-up event
        if is_complete:
            await broadcast_discovery_completed(
                manager=manager,
                project_id=project_id,
                total_answers=answered_count,
                next_phase="prd_generation",
            )
        else:
            await broadcast_discovery_question_presented(
                manager=manager,
                project_id=project_id,
                question_id=current_question_id,
                question_text=current_question_text,
                current_index=current_question_index,
                total_questions=total_questions,
            )

    except Exception as e:
        logger.warning(f"Failed to broadcast WebSocket events for project {project_id}: {e}")
        # Non-fatal - continue with response

    # T044: Generate and return response
    return DiscoveryAnswerResponse(
        success=True,
        next_question=current_question_text if not is_complete else None,
        is_complete=is_complete,
        current_index=current_question_index,
        total_questions=total_questions,
        progress_percentage=progress_percentage,
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


# Sprint 10 Phase 2: Review Agent API endpoints (T034, T035)


@app.post("/api/agents/review/analyze", status_code=202, tags=["review"])
async def analyze_code_review(request: Request, background_tasks: BackgroundTasks):
    """Trigger code review analysis for a task (T034).

    Sprint 10 - Phase 2: Review Agent API

    Accepts a task_id and optional project_id, creates a ReviewAgent instance,
    and executes the review in a background task. Returns immediately with job status.

    Args:
        request: FastAPI request containing:
            - task_id: int (required) - Task ID to review
            - project_id: int (optional) - Project ID for scoping

    Returns:
        202 Accepted: Review job started
        {
            "job_id": str,
            "status": "started",
            "message": "Code review analysis started for task {task_id}"
        }

        400 Bad Request: Invalid request (missing task_id)
        404 Not Found: Task not found

    Example:
        POST /api/agents/review/analyze
        Body: {
            "task_id": 42,
            "project_id": 123
        }
    """
    from codeframe.agents.review_agent import ReviewAgent
    from codeframe.core.models import Task
    import uuid

    try:
        # Parse request body
        data = await request.json()
        task_id = data.get("task_id")
        project_id = data.get("project_id")

        # Validate task_id
        if not task_id:
            raise HTTPException(status_code=400, detail="task_id is required")

        # Check if task exists
        task_data = app.state.db.get_task(task_id)
        if not task_data:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Use project_id from request or task data
        if not project_id:
            project_id = task_data.get("project_id")

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Create background task to run review
        async def run_review():
            """Background task to execute code review."""
            try:
                # Create ReviewAgent instance
                review_agent = ReviewAgent(
                    agent_id=f"review-{job_id[:8]}",
                    db=app.state.db,
                    project_id=project_id,
                    ws_manager=manager
                )

                # Build Task object from task_data
                task = Task(
                    id=task_id,
                    title=task_data.get("title", ""),
                    description=task_data.get("description", ""),
                    project_id=project_id,
                    status=TaskStatus(task_data.get("status", "pending")),
                    priority=task_data.get("priority", 0)
                )

                # Execute review (this saves findings to database)
                result = await review_agent.execute_task(task)

                logger.info(
                    f"Review job {job_id} completed: {result.status}, "
                    f"{len(result.findings)} findings"
                )

            except Exception as e:
                logger.error(f"Review job {job_id} failed: {e}", exc_info=True)

        # Add background task
        background_tasks.add_task(run_review)

        # Return 202 Accepted immediately
        return {
            "job_id": job_id,
            "status": "started",
            "message": f"Code review analysis started for task {task_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start code review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start review: {str(e)}")


@app.get("/api/tasks/{task_id}/reviews", tags=["review"])
async def get_task_reviews(task_id: int, severity: Optional[str] = None):
    """Get code review findings for a task (T035).

    Sprint 10 - Phase 2: Review Agent API

    Returns all code review findings for a specific task, optionally filtered by severity.
    Includes summary statistics (total findings, counts by severity, blocking status).

    Args:
        task_id: Task ID to get reviews for
        severity: Optional severity filter (critical, high, medium, low, info)

    Returns:
        200 OK: Review findings with summary statistics
        {
            "task_id": int,
            "findings": [
                {
                    "id": int,
                    "task_id": int,
                    "agent_id": str,
                    "project_id": int,
                    "file_path": str,
                    "line_number": int | null,
                    "severity": str,
                    "category": str,
                    "message": str,
                    "recommendation": str | null,
                    "code_snippet": str | null,
                    "created_at": str
                },
                ...
            ],
            "summary": {
                "total_findings": int,
                "by_severity": {
                    "critical": int,
                    "high": int,
                    "medium": int,
                    "low": int,
                    "info": int
                },
                "has_blocking_issues": bool,
                "blocking_count": int
            }
        }

        400 Bad Request: Invalid severity value
        404 Not Found: Task not found

    Example:
        GET /api/tasks/42/reviews
        GET /api/tasks/42/reviews?severity=critical
    """
    # Validate severity if provided
    valid_severities = ['critical', 'high', 'medium', 'low', 'info']
    if severity and severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid severity. Must be one of: {', '.join(valid_severities)}"
        )

    # Check if task exists
    task = app.state.db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get code reviews from database
    reviews = app.state.db.get_code_reviews(task_id=task_id, severity=severity)

    # Build summary statistics
    by_severity = {
        'critical': 0,
        'high': 0,
        'medium': 0,
        'low': 0,
        'info': 0
    }

    for review in reviews:
        severity_val = review.severity.value
        if severity_val in by_severity:
            by_severity[severity_val] += 1

    # Blocking issues are critical or high severity
    blocking_count = by_severity['critical'] + by_severity['high']
    has_blocking_issues = blocking_count > 0

    # Convert CodeReview objects to dictionaries
    findings_data = []
    for review in reviews:
        findings_data.append({
            "id": review.id,
            "task_id": review.task_id,
            "agent_id": review.agent_id,
            "project_id": review.project_id,
            "file_path": review.file_path,
            "line_number": review.line_number,
            "severity": review.severity.value,
            "category": review.category.value,
            "message": review.message,
            "recommendation": review.recommendation,
            "code_snippet": review.code_snippet,
            "created_at": review.created_at
        })

    # Build response
    return {
        "task_id": task_id,
        "findings": findings_data,
        "summary": {
            "total_findings": len(reviews),
            "by_severity": by_severity,
            "has_blocking_issues": has_blocking_issues,
            "blocking_count": blocking_count
        }
    }


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


# Sprint 10 Phase 3: Quality Gates API endpoints (T064, T065)


@app.get("/api/tasks/{task_id}/quality-gates", tags=["quality-gates"])
async def get_quality_gate_status(task_id: int):
    """Get quality gate status for a task (T064).

    Sprint 10 - Phase 3: Quality Gates API

    Returns the quality gate status for a specific task, including which gates
    passed/failed and detailed failure information.

    Args:
        task_id: Task ID to get quality gate status for

    Returns:
        200 OK: Quality gate status
        {
            "task_id": int,
            "status": str,  # 'pending', 'running', 'passed', 'failed', or None
            "failures": [
                {
                    "gate": str,  # 'tests', 'type_check', 'coverage', 'code_review', 'linting'
                    "reason": str,  # Short failure reason
                    "details": str | null,  # Detailed output
                    "severity": str  # 'critical', 'high', 'medium', 'low'
                },
                ...
            ],
            "requires_human_approval": bool,
            "timestamp": str  # ISO timestamp
        }

        404 Not Found: Task not found

    Example:
        GET /api/tasks/42/quality-gates
    """
    # Check if task exists
    task = app.state.db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get quality gate status from database
    status_data = app.state.db.get_quality_gate_status(task_id)

    # Add task_id and timestamp to response
    return {
        "task_id": task_id,
        "status": status_data.get("status"),
        "failures": status_data.get("failures", []),
        "requires_human_approval": status_data.get("requires_human_approval", False),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.post("/api/tasks/{task_id}/quality-gates", status_code=202, tags=["quality-gates"])
async def trigger_quality_gates(
    task_id: int, background_tasks: BackgroundTasks, request: QualityGatesRequest = QualityGatesRequest()
):
    """Manually trigger quality gates for a task (T065).

    Sprint 10 - Phase 3: Quality Gates API

    Triggers quality gate execution for a specific task. Runs in background and
    returns immediately with job status. Optionally accepts gate_types to run
    specific gates only.

    Args:
        task_id: Task ID to run quality gates for
        background_tasks: FastAPI background tasks
        request: QualityGatesRequest with optional gate_types list
                Valid gate types: 'tests', 'type_check', 'coverage', 'code_review', 'linting'

    Returns:
        202 Accepted: Quality gates job started
        {
            "job_id": str,
            "task_id": int,
            "status": "running",
            "gate_types": list[str],  # Gates being executed
            "message": str
        }

        400 Bad Request: Invalid gate_types
        404 Not Found: Task not found
        500 Internal Server Error: Missing project workspace or API configuration

    Example:
        POST /api/tasks/42/quality-gates
        Body: {
            "gate_types": ["tests", "coverage"]  # Optional
        }
    """
    from codeframe.lib.quality_gates import QualityGates
    from codeframe.core.models import Task
    from pathlib import Path
    import uuid

    # Extract gate_types from request
    gate_types = request.gate_types

    # Validate gate_types if provided
    valid_gate_types = [
        "tests",
        "type_check",
        "coverage",
        "code_review",
        "linting",
    ]
    if gate_types:
        invalid_gates = [g for g in gate_types if g not in valid_gate_types]
        if invalid_gates:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gate types: {invalid_gates}. Valid types: {valid_gate_types}",
            )

    # Check if task exists
    task_data = app.state.db.get_task(task_id)
    if not task_data:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get project_id from task
    project_id = task_data.get("project_id")
    if not project_id:
        raise HTTPException(
            status_code=500, detail=f"Task {task_id} has no project_id"
        )

    # Get project workspace path
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(
            status_code=500, detail=f"Project {project_id} not found"
        )

    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Build Task object for quality gates
    task = Task(
        id=task_id,
        project_id=project_id,
        task_number=task_data.get("task_number", "unknown"),
        title=task_data.get("title", ""),
        description=task_data.get("description", ""),
        status=TaskStatus(task_data.get("status", "pending")),
    )

    # Determine which gates to run
    gates_to_run = gate_types if gate_types else ["all"]

    # Background task to run quality gates
    async def run_quality_gates():
        """Background task to execute quality gates."""
        try:
            logger.info(
                f"Quality gates job {job_id} started for task {task_id}, "
                f"gates={gates_to_run}"
            )

            # Update task status to 'running'
            app.state.db.update_quality_gate_status(
                task_id=task_id, status="running", failures=[]
            )

            # Broadcast quality_gates_started event
            try:
                await manager.broadcast(
                    {
                        "type": "quality_gates_started",
                        "task_id": task_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "gate_types": gates_to_run,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast quality_gates_started: {e}")

            # Create QualityGates instance
            quality_gates = QualityGates(
                db=app.state.db,
                project_id=project_id,
                project_root=Path(workspace_path),
            )

            # Run gates based on gate_types
            if not gate_types or "all" in gates_to_run:
                # Run all gates
                result = await quality_gates.run_all_gates(task)
            else:
                # Run specific gates
                from codeframe.core.models import QualityGateResult

                all_failures = []
                execution_start = datetime.now(timezone.utc)

                gate_method_map = {
                    "tests": quality_gates.run_tests_gate,
                    "type_check": quality_gates.run_type_check_gate,
                    "coverage": quality_gates.run_coverage_gate,
                    "code_review": quality_gates.run_review_gate,
                    "linting": quality_gates.run_linting_gate,
                }

                for gate_type in gate_types:
                    gate_method = gate_method_map.get(gate_type)
                    if gate_method:
                        gate_result = await gate_method(task)
                        all_failures.extend(gate_result.failures)

                execution_time = (
                    datetime.now(timezone.utc) - execution_start
                ).total_seconds()
                status = "passed" if len(all_failures) == 0 else "failed"

                result = QualityGateResult(
                    task_id=task_id,
                    status=status,
                    failures=all_failures,
                    execution_time_seconds=execution_time,
                )

                # Update database with final result
                app.state.db.update_quality_gate_status(
                    task_id=task_id, status=status, failures=all_failures
                )

            # Broadcast completion event
            try:
                event_type = (
                    "quality_gates_passed"
                    if result.passed
                    else "quality_gates_failed"
                )
                await manager.broadcast(
                    {
                        "type": event_type,
                        "task_id": task_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "status": result.status,
                        "failures_count": len(result.failures),
                        "execution_time_seconds": result.execution_time_seconds,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast quality_gates_completed: {e}")

            logger.info(
                f"Quality gates job {job_id} completed: "
                f"status={result.status}, failures={len(result.failures)}"
            )

        except Exception as e:
            logger.error(
                f"Quality gates job {job_id} failed: {e}", exc_info=True
            )

            # Update status to 'failed' with error
            from codeframe.core.models import QualityGateFailure, QualityGateType, Severity

            error_failure = QualityGateFailure(
                gate=QualityGateType.TESTS,  # Generic gate type for errors
                reason=f"Quality gates execution failed: {str(e)}",
                details=str(e),
                severity=Severity.CRITICAL,
            )

            app.state.db.update_quality_gate_status(
                task_id=task_id, status="failed", failures=[error_failure]
            )

            # Broadcast failure event
            try:
                await manager.broadcast(
                    {
                        "type": "quality_gates_error",
                        "task_id": task_id,
                        "project_id": project_id,
                        "job_id": job_id,
                        "error": str(e),
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                )
            except Exception as broadcast_error:
                logger.warning(
                    f"Failed to broadcast quality_gates_error: {broadcast_error}"
                )

    # Add background task
    background_tasks.add_task(run_quality_gates)

    # Return 202 Accepted immediately
    return {
        "job_id": job_id,
        "task_id": task_id,
        "status": "running",
        "gate_types": gates_to_run,
        "message": f"Quality gates execution started for task {task_id}",
    }


# Sprint 10 Phase 4: Checkpoint API endpoints (T092-T097)


@app.get("/api/projects/{project_id}/checkpoints", tags=["checkpoints"])
async def list_checkpoints(project_id: int):
    """List all checkpoints for a project (T092).

    Sprint 10 - Phase 4: Checkpoint API

    Returns all checkpoints for the specified project, sorted by creation time
    (most recent first). Includes checkpoint metadata for quick inspection.

    Args:
        project_id: Project ID to list checkpoints for

    Returns:
        200 OK: List of checkpoints
        {
            "checkpoints": [
                {
                    "id": int,
                    "project_id": int,
                    "name": str,
                    "description": str | null,
                    "trigger": str,
                    "git_commit": str,
                    "database_backup_path": str,
                    "context_snapshot_path": str,
                    "metadata": {
                        "project_id": int,
                        "phase": str,
                        "tasks_completed": int,
                        "tasks_total": int,
                        "agents_active": list[str],
                        "last_task_completed": str | null,
                        "context_items_count": int,
                        "total_cost_usd": float
                    },
                    "created_at": str  # ISO 8601
                },
                ...
            ]
        }

        404 Not Found: Project not found

    Example:
        GET /api/projects/123/checkpoints
    """

    # Verify project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get checkpoints from database
    checkpoints = app.state.db.get_checkpoints(project_id)

    # Convert to response models
    checkpoint_responses = []
    for checkpoint in checkpoints:
        checkpoint_responses.append(
            CheckpointResponse(
                id=checkpoint.id,
                project_id=checkpoint.project_id,
                name=checkpoint.name,
                description=checkpoint.description,
                trigger=checkpoint.trigger,
                git_commit=checkpoint.git_commit,
                database_backup_path=checkpoint.database_backup_path,
                context_snapshot_path=checkpoint.context_snapshot_path,
                metadata=checkpoint.metadata.model_dump(),
                created_at=checkpoint.created_at.isoformat(),
            )
        )

    return {"checkpoints": checkpoint_responses}


@app.post("/api/projects/{project_id}/checkpoints", status_code=201, tags=["checkpoints"])
async def create_checkpoint(project_id: int, request: CheckpointCreateRequest):
    """Create a new checkpoint for a project (T093).

    Sprint 10 - Phase 4: Checkpoint API

    Creates a complete project checkpoint including:
    - Git commit (code state)
    - Database backup (tasks, context, metrics)
    - Context snapshot (agent context items as JSON)
    - Metadata (progress, costs, active agents)

    Args:
        project_id: Project ID to create checkpoint for
        request: CheckpointCreateRequest with name, description, trigger

    Returns:
        201 Created: Checkpoint created successfully
        {
            "id": int,
            "project_id": int,
            "name": str,
            "description": str | null,
            "trigger": str,
            "git_commit": str,
            "database_backup_path": str,
            "context_snapshot_path": str,
            "metadata": {
                "project_id": int,
                "phase": str,
                "tasks_completed": int,
                "tasks_total": int,
                "agents_active": list[str],
                "last_task_completed": str | null,
                "context_items_count": int,
                "total_cost_usd": float
            },
            "created_at": str  # ISO 8601
        }

        404 Not Found: Project not found
        500 Internal Server Error: Checkpoint creation failed

    Example:
        POST /api/projects/123/checkpoints
        Body: {
            "name": "Before refactor",
            "description": "Safety checkpoint before major refactoring",
            "trigger": "manual"
        }
    """
    from codeframe.lib.checkpoint_manager import CheckpointManager
    from pathlib import Path

    # Verify project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get project workspace path
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    try:
        # Create checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=app.state.db,
            project_root=Path(workspace_path),
            project_id=project_id,
        )

        # Create checkpoint
        checkpoint = checkpoint_mgr.create_checkpoint(
            name=request.name,
            description=request.description,
            trigger=request.trigger,
        )

        logger.info(f"Created checkpoint {checkpoint.id} for project {project_id}: {checkpoint.name}")

        # Return checkpoint response
        return CheckpointResponse(
            id=checkpoint.id,
            project_id=checkpoint.project_id,
            name=checkpoint.name,
            description=checkpoint.description,
            trigger=checkpoint.trigger,
            git_commit=checkpoint.git_commit,
            database_backup_path=checkpoint.database_backup_path,
            context_snapshot_path=checkpoint.context_snapshot_path,
            metadata=checkpoint.metadata.model_dump(),
            created_at=checkpoint.created_at.isoformat(),
        )

    except Exception as e:
        logger.error(f"Failed to create checkpoint for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Checkpoint creation failed: {str(e)}")


@app.get("/api/projects/{project_id}/checkpoints/{checkpoint_id}", tags=["checkpoints"])
async def get_checkpoint(project_id: int, checkpoint_id: int):
    """Get details of a specific checkpoint (T094).

    Sprint 10 - Phase 4: Checkpoint API

    Returns full details of a checkpoint including all metadata.

    Args:
        project_id: Project ID (for path consistency)
        checkpoint_id: Checkpoint ID to retrieve

    Returns:
        200 OK: Checkpoint details
        {
            "id": int,
            "project_id": int,
            "name": str,
            "description": str | null,
            "trigger": str,
            "git_commit": str,
            "database_backup_path": str,
            "context_snapshot_path": str,
            "metadata": {
                "project_id": int,
                "phase": str,
                "tasks_completed": int,
                "tasks_total": int,
                "agents_active": list[str],
                "last_task_completed": str | null,
                "context_items_count": int,
                "total_cost_usd": float
            },
            "created_at": str  # ISO 8601
        }

        404 Not Found: Project or checkpoint not found

    Example:
        GET /api/projects/123/checkpoints/42
    """

    # Verify project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get checkpoint from database
    checkpoint = app.state.db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    # Return checkpoint response
    return CheckpointResponse(
        id=checkpoint.id,
        project_id=checkpoint.project_id,
        name=checkpoint.name,
        description=checkpoint.description,
        trigger=checkpoint.trigger,
        git_commit=checkpoint.git_commit,
        database_backup_path=checkpoint.database_backup_path,
        context_snapshot_path=checkpoint.context_snapshot_path,
        metadata=checkpoint.metadata.model_dump(),
        created_at=checkpoint.created_at.isoformat(),
    )


@app.delete("/api/projects/{project_id}/checkpoints/{checkpoint_id}", status_code=204, tags=["checkpoints"])
async def delete_checkpoint(project_id: int, checkpoint_id: int):
    """Delete a checkpoint and its files (T095).

    Sprint 10 - Phase 4: Checkpoint API

    Deletes a checkpoint from the database and removes its backup files
    (database backup and context snapshot).

    Args:
        project_id: Project ID (for path consistency)
        checkpoint_id: Checkpoint ID to delete

    Returns:
        204 No Content: Checkpoint deleted successfully

        404 Not Found: Project or checkpoint not found
        500 Internal Server Error: File deletion failed

    Example:
        DELETE /api/projects/123/checkpoints/42
    """
    from pathlib import Path

    # Verify project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get checkpoint from database
    checkpoint = app.state.db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    try:
        # Delete backup files
        db_backup_path = Path(checkpoint.database_backup_path)
        context_snapshot_path = Path(checkpoint.context_snapshot_path)

        if db_backup_path.exists():
            db_backup_path.unlink()
            logger.debug(f"Deleted database backup: {db_backup_path}")

        if context_snapshot_path.exists():
            context_snapshot_path.unlink()
            logger.debug(f"Deleted context snapshot: {context_snapshot_path}")

        # Delete checkpoint from database
        cursor = app.state.db.conn.cursor()
        cursor.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
        app.state.db.conn.commit()

        logger.info(f"Deleted checkpoint {checkpoint_id} for project {project_id}")

        # Return 204 No Content
        return None

    except Exception as e:
        logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Checkpoint deletion failed: {str(e)}")


@app.post("/api/projects/{project_id}/checkpoints/{checkpoint_id}/restore", status_code=202, tags=["checkpoints"])
async def restore_checkpoint(
    project_id: int,
    checkpoint_id: int,
    request: RestoreCheckpointRequest = RestoreCheckpointRequest()
):
    """Restore project to checkpoint state (T096, T097).

    Sprint 10 - Phase 4: Checkpoint API

    Restores project to a previous checkpoint state. If confirm_restore=False,
    shows git diff without making changes. If confirm_restore=True, performs
    the restoration including:
    - Checking out git commit
    - Restoring database from backup
    - Restoring context items

    Args:
        project_id: Project ID
        checkpoint_id: Checkpoint ID to restore
        request: RestoreCheckpointRequest with confirm_restore flag

    Returns:
        200 OK (if confirm_restore=False): Diff preview
        {
            "checkpoint_name": str,
            "diff": str  # Git diff output
        }

        202 Accepted (if confirm_restore=True): Restore started
        {
            "success": bool,
            "checkpoint_name": str,
            "git_commit": str,
            "items_restored": int
        }

        404 Not Found: Project or checkpoint not found
        500 Internal Server Error: Restore failed

    Example:
        POST /api/projects/123/checkpoints/42/restore
        Body: {
            "confirm_restore": false  # Show diff first
        }

        POST /api/projects/123/checkpoints/42/restore
        Body: {
            "confirm_restore": true  # Actually restore
        }
    """
    from codeframe.lib.checkpoint_manager import CheckpointManager
    from pathlib import Path

    # Verify project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Get project workspace path
    workspace_path = project.get("workspace_path")
    if not workspace_path:
        raise HTTPException(
            status_code=500,
            detail=f"Project {project_id} has no workspace path configured",
        )

    # Verify checkpoint exists
    checkpoint = app.state.db.get_checkpoint_by_id(checkpoint_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

    # Verify checkpoint belongs to this project
    if checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} does not belong to project {project_id}",
        )

    try:
        # Create checkpoint manager
        checkpoint_mgr = CheckpointManager(
            db=app.state.db,
            project_root=Path(workspace_path),
            project_id=project_id,
        )

        # Restore checkpoint (or show diff if not confirmed)
        result = checkpoint_mgr.restore_checkpoint(
            checkpoint_id=checkpoint_id,
            confirm=request.confirm_restore,
        )

        if request.confirm_restore:
            logger.info(f"Restored checkpoint {checkpoint_id} for project {project_id}")
            # Return 202 Accepted for successful restore
            return result
        else:
            # Return 200 OK for diff preview
            return result

    except ValueError as e:
        # Checkpoint not found or validation error
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        # Backup files missing
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restore checkpoint {checkpoint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Checkpoint restore failed: {str(e)}")


# Sprint 10 Phase 5: Metrics API endpoints (T127-T129)


@app.get("/api/projects/{project_id}/metrics/tokens", tags=["metrics"])
async def get_project_token_metrics(
    project_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get token usage metrics for a project (T127).

    Sprint 10 - Phase 5: Metrics & Cost Tracking

    Returns token usage records for a project, optionally filtered by date range.
    Includes timeline statistics and aggregated token counts.

    Args:
        project_id: Project ID to get token metrics for
        start_date: Optional start date (ISO 8601 format, e.g., '2025-11-01T00:00:00Z')
        end_date: Optional end date (ISO 8601 format, e.g., '2025-11-30T23:59:59Z')

    Returns:
        200 OK: Token usage records with timeline stats
        {
            "project_id": int,
            "total_tokens": int,
            "total_calls": int,
            "total_cost_usd": float,
            "date_range": {
                "start": str | null,
                "end": str | null
            },
            "usage_records": [
                {
                    "id": int,
                    "task_id": int | null,
                    "agent_id": str,
                    "model_name": str,
                    "input_tokens": int,
                    "output_tokens": int,
                    "estimated_cost_usd": float,
                    "call_type": str,
                    "timestamp": str
                },
                ...
            ]
        }
        400 Bad Request: Invalid date format
        404 Not Found: Project not found
        500 Internal Server Error: Database or processing error

    Example:
        GET /api/projects/1/metrics/tokens
        GET /api/projects/1/metrics/tokens?start_date=2025-11-01T00:00:00Z&end_date=2025-11-30T23:59:59Z
    """
    from codeframe.lib.metrics_tracker import MetricsTracker

    # Validate project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    # Parse and validate date parameters
    start_dt = None
    end_dt = None

    try:
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format. Use ISO 8601 format (e.g., '2025-11-01T00:00:00Z'): {str(e)}"
        )

    try:
        # Get token usage stats using MetricsTracker
        tracker = MetricsTracker(db=app.state.db)
        stats = await tracker.get_token_usage_stats(
            project_id=project_id,
            start_date=start_dt,
            end_date=end_dt
        )

        # Get detailed usage records
        usage_records = app.state.db.get_token_usage(
            project_id=project_id,
            start_date=start_dt,
            end_date=end_dt
        )

        # Build response
        return {
            "project_id": project_id,
            "total_tokens": stats["total_tokens"],
            "total_calls": stats["total_calls"],
            "total_cost_usd": stats["total_cost_usd"],
            "date_range": stats["date_range"],
            "usage_records": usage_records
        }

    except Exception as e:
        logger.error(f"Failed to get token metrics for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve token metrics: {str(e)}"
        )


@app.get("/api/projects/{project_id}/metrics/costs", tags=["metrics"])
async def get_project_cost_metrics(project_id: int):
    """Get cost breakdown for a project (T128).

    Sprint 10 - Phase 5: Metrics & Cost Tracking

    Returns total costs and breakdowns by agent and model for a project.
    Useful for understanding cost allocation and identifying high-cost operations.

    Args:
        project_id: Project ID to get cost breakdown for

    Returns:
        200 OK: Cost breakdown
        {
            "project_id": int,
            "total_cost_usd": float,
            "total_tokens": int,
            "total_calls": int,
            "by_agent": [
                {
                    "agent_id": str,
                    "cost_usd": float,
                    "tokens": int,
                    "calls": int
                },
                ...
            ],
            "by_model": [
                {
                    "model_name": str,
                    "cost_usd": float,
                    "total_tokens": int,
                    "total_calls": int
                },
                ...
            ]
        }
        404 Not Found: Project not found
        500 Internal Server Error: Database or processing error

    Example:
        GET /api/projects/1/metrics/costs
        Response: {
            "project_id": 1,
            "total_cost_usd": 0.125,
            "total_tokens": 15000,
            "total_calls": 10,
            "by_agent": [
                {"agent_id": "backend-001", "cost_usd": 0.075, "tokens": 9000, "calls": 6},
                {"agent_id": "review-001", "cost_usd": 0.05, "tokens": 6000, "calls": 4}
            ],
            "by_model": [
                {"model_name": "claude-sonnet-4-5", "cost_usd": 0.125, "total_tokens": 15000, "total_calls": 10}
            ]
        }
    """
    from codeframe.lib.metrics_tracker import MetricsTracker

    # Validate project exists
    project = app.state.db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

    try:
        # Get project costs using MetricsTracker
        tracker = MetricsTracker(db=app.state.db)
        costs = await tracker.get_project_costs(project_id=project_id)

        logger.info(f"Retrieved cost metrics for project {project_id}: ${costs['total_cost_usd']:.6f}")

        return costs

    except Exception as e:
        logger.error(f"Failed to get cost metrics for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve cost metrics: {str(e)}"
        )


@app.get("/api/agents/{agent_id}/metrics", tags=["metrics"])
async def get_agent_metrics(agent_id: str, project_id: Optional[int] = None):
    """Get metrics for a specific agent (T129).

    Sprint 10 - Phase 5: Metrics & Cost Tracking

    Returns cost and usage statistics for a specific agent, optionally filtered
    by project. Includes breakdowns by call type and project.

    Args:
        agent_id: Agent ID to get metrics for
        project_id: Optional project ID to filter metrics (query parameter)

    Returns:
        200 OK: Agent metrics
        {
            "agent_id": str,
            "total_cost_usd": float,
            "total_tokens": int,
            "total_calls": int,
            "by_call_type": [
                {
                    "call_type": str,
                    "cost_usd": float,
                    "calls": int
                },
                ...
            ],
            "by_project": [
                {
                    "project_id": int,
                    "cost_usd": float
                },
                ...
            ]
        }
        500 Internal Server Error: Database or processing error

    Example:
        GET /api/agents/backend-001/metrics
        GET /api/agents/backend-001/metrics?project_id=1
        Response: {
            "agent_id": "backend-001",
            "total_cost_usd": 0.085,
            "total_tokens": 12000,
            "total_calls": 8,
            "by_call_type": [
                {"call_type": "task_execution", "cost_usd": 0.06, "calls": 5},
                {"call_type": "code_review", "cost_usd": 0.025, "calls": 3}
            ],
            "by_project": [
                {"project_id": 1, "cost_usd": 0.085}
            ]
        }
    """
    from codeframe.lib.metrics_tracker import MetricsTracker

    try:
        # Get agent costs using MetricsTracker
        tracker = MetricsTracker(db=app.state.db)
        costs = await tracker.get_agent_costs(agent_id=agent_id)

        # If project_id is specified, filter the results
        if project_id is not None:
            # Filter by_project to only include the specified project
            filtered_projects = [
                p for p in costs["by_project"]
                if p["project_id"] == project_id
            ]

            if not filtered_projects:
                # No data for this agent in this project
                return {
                    "agent_id": agent_id,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "total_calls": 0,
                    "by_call_type": [],
                    "by_project": []
                }

            # Recalculate totals based on filtered project
            # We need to get usage records for this specific project
            usage_records = app.state.db.get_token_usage(
                agent_id=agent_id,
                project_id=project_id
            )

            # Recalculate aggregates
            total_cost = sum(r["estimated_cost_usd"] for r in usage_records)
            total_tokens = sum(r["input_tokens"] + r["output_tokens"] for r in usage_records)
            total_calls = len(usage_records)

            # Aggregate by call type
            call_type_stats = {}
            for record in usage_records:
                call_type = record["call_type"]
                if call_type not in call_type_stats:
                    call_type_stats[call_type] = {"call_type": call_type, "cost_usd": 0.0, "calls": 0}
                call_type_stats[call_type]["cost_usd"] += record["estimated_cost_usd"]
                call_type_stats[call_type]["calls"] += 1

            # Round costs
            for stats in call_type_stats.values():
                stats["cost_usd"] = round(stats["cost_usd"], 6)

            return {
                "agent_id": agent_id,
                "total_cost_usd": round(total_cost, 6),
                "total_tokens": total_tokens,
                "total_calls": total_calls,
                "by_call_type": list(call_type_stats.values()),
                "by_project": [{"project_id": project_id, "cost_usd": round(total_cost, 6)}]
            }

        logger.info(f"Retrieved metrics for agent {agent_id}: ${costs['total_cost_usd']:.6f}")

        return costs

    except Exception as e:
        logger.error(f"Failed to get metrics for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve agent metrics: {str(e)}"
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
