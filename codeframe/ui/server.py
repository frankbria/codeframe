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

# Local imports
from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager
from codeframe.ui.routers import (
    agents,
    blockers,
    chat,
    checkpoints,
    context,
    discovery,
    lint,
    metrics,
    projects,
    quality_gates,
    review,
    session,
    tasks,
    websocket,
)
from codeframe.auth import router as auth_router

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


async def _cleanup_expired_sessions_task(db: Database):
    """Background task to periodically clean up expired sessions and old audit logs.

    Runs periodically to:
    - Delete expired sessions (every hour by default)
    - Delete audit logs older than retention period (every 24 hours by default)

    Args:
        db: Database instance
    """
    logger = logging.getLogger(__name__)
    session_cleanup_interval = int(os.getenv("SESSION_CLEANUP_INTERVAL", "3600"))  # Default: 1 hour
    audit_cleanup_interval = int(os.getenv("AUDIT_CLEANUP_INTERVAL", "86400"))  # Default: 24 hours
    audit_retention_days = int(os.getenv("AUDIT_RETENTION_DAYS", "90"))  # Default: 90 days

    # Track last audit cleanup time
    last_audit_cleanup = 0

    while True:
        try:
            await asyncio.sleep(session_cleanup_interval)

            # Always clean up expired sessions
            deleted_sessions = await db.cleanup_expired_sessions()
            if deleted_sessions > 0:
                logger.info(f"🧹 Cleaned up {deleted_sessions} expired session(s)")

            # Clean up old audit logs periodically (less frequently)
            import time

            current_time = time.time()
            if current_time - last_audit_cleanup >= audit_cleanup_interval:
                deleted_logs = await db.cleanup_old_audit_logs(retention_days=audit_retention_days)
                if deleted_logs > 0:
                    logger.info(
                        f"🗑️  Cleaned up {deleted_logs} audit log(s) older than {audit_retention_days} days"
                    )
                last_audit_cleanup = current_time

        except Exception as e:
            logger.error(f"Error during cleanup task: {e}", exc_info=True)


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

    # Log that authentication is now always required
    logger.info("🔒 Authentication: ENABLED (always required)")

    # Start background session cleanup task
    cleanup_task = asyncio.create_task(_cleanup_expired_sessions_task(app.state.db))

    yield

    # Shutdown: Cancel cleanup task and close database connection
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    if hasattr(app.state, "db") and app.state.db:
        app.state.db.close()


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="CodeFRAME Status Server",
    description="Real-time monitoring and control for CodeFRAME projects",
    version="0.1.0",
    lifespan=lifespan,
)


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
# Router Mounting
# ============================================================================

# Mount all API routers
app.include_router(agents.router)
app.include_router(blockers.router)
app.include_router(blockers.blocker_router)
app.include_router(chat.router)
app.include_router(checkpoints.router)
app.include_router(context.router)
app.include_router(discovery.router)
app.include_router(lint.router)
app.include_router(metrics.router)
app.include_router(projects.router)
app.include_router(quality_gates.router)
app.include_router(review.router)
app.include_router(session.router)
app.include_router(tasks.router)
app.include_router(tasks.project_router)
app.include_router(websocket.router)
app.include_router(auth_router.router)


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
