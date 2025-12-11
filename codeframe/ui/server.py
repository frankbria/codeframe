"""FastAPI Status Server for CodeFRAME."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict, Optional
from enum import Enum
from datetime import datetime, UTC, timezone
import asyncio
import json
import logging
import os

from codeframe.core.models import (
    ProjectStatus,
    TaskStatus,
    ContextItemCreateModel,
    ContextItemResponse,
)
from codeframe.persistence.database import Database
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
from codeframe.ui.routers import agents
from codeframe.ui.routers import projects


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
app.include_router(agents.router)
app.include_router(projects.router)


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
