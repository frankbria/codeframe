"""FastAPI Status Server for CodeFRAME."""

# Standard library imports
import asyncio
import logging
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path

# Third-party imports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Local imports - v2 only (no v1 persistence layer)
from codeframe.workspace import WorkspaceManager
from codeframe.ui.routers import (
    # v2 routers only - delegate to codeframe.core modules
    batches_v2,
    blockers_v2,
    checkpoints_v2,
    diagnose_v2,
    discovery_v2,
    environment_v2,
    gates_v2,
    git_v2,
    pr_v2,
    prd_v2,
    review_v2,
    schedule_v2,
    streaming_v2,
    tasks_v2,
    templates_v2,
    workspace_v2,
)
from codeframe.auth import router as auth_router
from codeframe.lib.rate_limiter import (
    get_rate_limiter,
    rate_limit_exceeded_handler,
)
from codeframe.config.rate_limits import get_rate_limit_config

# ============================================================================
# Configuration and Setup
# ============================================================================


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


# Logger setup
logger = logging.getLogger(__name__)


# ============================================================================
# Application Lifespan
# ============================================================================


# Note: Session cleanup removed - v1 persistence layer not used in v2
# If session management is needed, implement in v2 core modules


def _validate_security_config():
    """Validate security configuration at startup.

    Raises:
        RuntimeError: If security configuration is invalid for the deployment mode
    """
    from codeframe.auth.manager import SECRET, DEFAULT_SECRET

    deployment_mode = get_deployment_mode()

    # In hosted mode, fail fast if using default JWT secret
    if deployment_mode == DeploymentMode.HOSTED and SECRET == DEFAULT_SECRET:
        raise RuntimeError(
            "🚨 SECURITY: AUTH_SECRET must be set in hosted/production mode. "
            "Using the default secret compromises all JWT tokens. "
            "Set the AUTH_SECRET environment variable to a secure random value."
        )

    # Log security status
    if SECRET == DEFAULT_SECRET:
        logger.warning(
            "⚠️  Running with default AUTH_SECRET - acceptable for self-hosted development only"
        )
    else:
        logger.info("🔐 AUTH_SECRET configured (custom secret in use)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Load environment variables from .env file
    from codeframe.core.config import load_environment
    load_environment()

    # Validate security configuration before starting
    _validate_security_config()

    # Initialize workspace manager for v2 core
    workspace_root_str = os.environ.get(
        "WORKSPACE_ROOT", str(Path.cwd() / ".codeframe" / "workspaces")
    )
    workspace_root = Path(workspace_root_str)
    app.state.workspace_manager = WorkspaceManager(workspace_root)

    # Log that authentication is now always required
    logger.info("🔒 Authentication: ENABLED (always required)")

    # Initialize rate limiting
    rate_limit_config = get_rate_limit_config()
    if rate_limit_config.enabled:
        limiter = get_rate_limiter()
        if limiter:
            app.state.limiter = limiter
            logger.info(
                f"🚦 Rate limiting: ENABLED "
                f"(storage={rate_limit_config.storage}, "
                f"standard={rate_limit_config.standard_limit})"
            )
    else:
        logger.info("🚦 Rate limiting: DISABLED")

    yield

    # Shutdown: nothing to clean up (v2 uses per-workspace databases managed by core)


# ============================================================================
# OpenAPI Tags and Metadata
# ============================================================================

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Health check endpoints - verify API availability and get deployment information.",
    },
    {
        "name": "projects",
        "description": "Project lifecycle and management - create, read, update, delete projects and access project status, tasks, activity, PRD, and session state.",
    },
    {
        "name": "tasks",
        "description": "Task creation, management, and approval workflow - create tasks, approve generated tasks to start development, and manually trigger task assignment.",
    },
    {
        "name": "agents",
        "description": "Agent lifecycle and assignment - start/pause/resume agents, assign agents to projects with roles, and manage multi-agent workflows.",
    },
    {
        "name": "blockers",
        "description": "Human-in-the-loop blocker management - list, view, and resolve blockers that require human guidance for agents to continue.",
    },
    {
        "name": "checkpoints",
        "description": "Project checkpoint and restore functionality - create snapshots of project state and restore to previous checkpoints.",
    },
    {
        "name": "chat",
        "description": "Chat and communication endpoints for real-time interaction with agents.",
    },
    {
        "name": "context",
        "description": "Context management for agent execution - manage codebase context, file references, and relevant information.",
    },
    {
        "name": "discovery",
        "description": "Discovery phase operations - codebase analysis, structure detection, and initial project understanding.",
    },
    {
        "name": "git",
        "description": "Git operations - commit, branch, diff, and repository management.",
    },
    {
        "name": "lint",
        "description": "Code linting operations - run and manage linting checks.",
    },
    {
        "name": "metrics",
        "description": "Metrics and analytics - project progress, agent performance, and quality metrics.",
    },
    {
        "name": "quality_gates",
        "description": "Quality gates and checks - run tests, type checking, coverage, and code review gates.",
    },
    {
        "name": "review",
        "description": "Code review functionality - trigger and manage AI-powered code reviews.",
    },
    {
        "name": "schedule",
        "description": "Task scheduling - view schedule predictions, bottlenecks, and critical path analysis.",
    },
    {
        "name": "session",
        "description": "Session management - track session state, progress, and continuity across work sessions.",
    },
    {
        "name": "templates",
        "description": "Project and task templates - list, view, and apply reusable templates.",
    },
    {
        "name": "websocket",
        "description": "WebSocket connections for real-time updates and event streaming.",
    },
    {
        "name": "auth",
        "description": "Authentication and authorization - login, logout, API keys, and session management.",
    },
]

OPENAPI_DESCRIPTION = """
# CodeFRAME API

**CodeFRAME** is an AI-powered software development framework that orchestrates multiple agents
to complete programming tasks. This API provides real-time monitoring and control for CodeFRAME projects.

## Overview

The CodeFRAME API enables you to:

- **Create and manage projects** - Initialize projects from git repos, local paths, or start empty
- **Generate and approve tasks** - AI generates implementation tasks from PRDs; approve to start development
- **Monitor agent execution** - Track agents as they work through tasks with real-time WebSocket updates
- **Handle blockers** - Provide human guidance when agents encounter decisions requiring input
- **Review and ship** - Run quality gates, review code changes, and manage the deployment process

## Authentication

All endpoints require authentication. The API supports two authentication methods:

1. **API Key** - Include `X-API-Key` header with your API key
2. **Session Token** - Use JWT token from login endpoint in `Authorization: Bearer <token>` header

## Rate Limiting

The API implements rate limiting to ensure fair usage:
- **Standard endpoints**: Higher request limits for read operations
- **AI endpoints** (agent start, LLM calls): Lower limits due to computational cost

Rate limit headers are included in responses: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

## WebSocket Events

For real-time updates, connect to the WebSocket endpoint. Events include:
- `task_assigned`, `task_completed`, `task_failed`
- `agent_created`, `agent_status`
- `blocker_created`, `blocker_resolved`
- `discovery_starting`, `discovery_completed`

## Error Responses

All errors follow a consistent format:
```json
{
    "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:
- `400` - Bad Request (validation error)
- `401` - Unauthorized (authentication required)
- `403` - Forbidden (insufficient permissions)
- `404` - Not Found (resource doesn't exist)
- `409` - Conflict (duplicate resource or state conflict)
- `422` - Unprocessable Entity (Pydantic validation failure)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error
"""


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="CodeFRAME API",
    description=OPENAPI_DESCRIPTION,
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    contact={
        "name": "CodeFRAME Support",
        "url": "https://github.com/frankbria/codeframe",
    },
    license_info={
        "name": "MIT",
        "identifier": "MIT",
    },
)


# ============================================================================
# Rate Limiting Setup
# ============================================================================

# Add rate limiting exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add rate limiting middleware if enabled
# Initialize limiter immediately so it's available before lifespan runs
rate_limit_config = get_rate_limit_config()
if rate_limit_config.enabled:
    limiter = get_rate_limiter()
    if limiter:
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)


# ============================================================================
# CORS Middleware
# ============================================================================

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
        "http://localhost:3001",  # Next.js E2E test server
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


# ============================================================================
# Health Check Endpoints
# ============================================================================


@app.get(
    "/",
    summary="Basic health check",
    description="Simple health check endpoint that returns online status. Use /health for detailed information.",
    tags=["health"],
)
async def root():
    """Health check endpoint."""
    return {"status": "online", "service": "CodeFRAME API"}


@app.get(
    "/health",
    summary="Detailed health check",
    description="Returns comprehensive health information including version, git commit, deployment time, "
                "and database connection status. Useful for monitoring and debugging.",
    tags=["health"],
)
async def health_check():
    """Detailed health check with deployment info.

    Returns:
        - status: Service health status
        - version: API version from FastAPI app
        - commit: Git commit hash (short)
        - deployed_at: Server startup timestamp
        - database: Database connection status
    """
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

    return {
        "status": "healthy",
        "service": "CodeFRAME Status Server",
        "version": app.version,
        "commit": git_commit,
        "deployed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


# ============================================================================
# Test-Only Endpoints (for WebSocket integration tests)
# ============================================================================


@app.post("/test/broadcast")
async def test_broadcast(message: dict, project_id: int = None):
    """Trigger a WebSocket broadcast for testing purposes.

    This endpoint is only intended for use in integration tests to trigger
    broadcasts from the server subprocess. In production, broadcasts are
    triggered by actual server-side events.

    Args:
        message: The message dict to broadcast
        project_id: Optional project ID for filtered broadcasts

    Returns:
        Success confirmation
    """
    from codeframe.ui.shared import manager

    await manager.broadcast(message, project_id=project_id)
    return {"status": "broadcast_sent", "project_id": project_id}


# ============================================================================
# Router Mounting (v2 only)
# ============================================================================

# Authentication router
app.include_router(auth_router.router)

# v2 API routers - all delegate to codeframe.core modules
app.include_router(batches_v2.router)       # /api/v2/batches
app.include_router(blockers_v2.router)      # /api/v2/blockers
app.include_router(checkpoints_v2.router)   # /api/v2/checkpoints
app.include_router(diagnose_v2.router)      # /api/v2/tasks/{id}/diagnose
app.include_router(discovery_v2.router)     # /api/v2/discovery
app.include_router(environment_v2.router)   # /api/v2/env
app.include_router(gates_v2.router)         # /api/v2/gates
app.include_router(git_v2.router)           # /api/v2/git
app.include_router(pr_v2.router)            # /api/v2/pr
app.include_router(prd_v2.router)           # /api/v2/prd
app.include_router(review_v2.router)        # /api/v2/review
app.include_router(schedule_v2.router)      # /api/v2/schedule
app.include_router(streaming_v2.router)     # /api/v2/tasks/{id}/stream (SSE)
app.include_router(tasks_v2.router)         # /api/v2/tasks
app.include_router(templates_v2.router)     # /api/v2/templates
app.include_router(workspace_v2.router)     # /api/v2/workspaces


# ============================================================================
# Server Startup
# ============================================================================


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
