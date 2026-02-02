"""FastAPI dependency injection providers.

This module provides dependency injection functions for accessing
shared application state (database, workspace manager, etc.) across
all API endpoints.

Supports both v1 (Database, WorkspaceManager) and v2 (Workspace) patterns.
"""

from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Query, Request, WebSocket

from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager

# v2 imports
from codeframe.core.workspace import Workspace, get_workspace, workspace_exists


def get_db(request: Request) -> Database:
    """Get database connection from application state.

    Args:
        request: FastAPI request object

    Returns:
        Database instance from app.state.db

    Usage:
        @router.get("/endpoint")
        async def endpoint(db: Database = Depends(get_db)):
            # Use db here
            ...
    """
    return request.app.state.db


def get_workspace_manager(request: Request) -> WorkspaceManager:
    """Get workspace manager from application state.

    Args:
        request: FastAPI request object

    Returns:
        WorkspaceManager instance from app.state.workspace_manager

    Usage:
        @router.post("/endpoint")
        async def endpoint(workspace_mgr: WorkspaceManager = Depends(get_workspace_manager)):
            # Use workspace_mgr here
            ...
    """
    return request.app.state.workspace_manager


def get_db_websocket(websocket: WebSocket) -> Database:
    """Get database connection from application state for WebSocket endpoints.

    Args:
        websocket: FastAPI WebSocket object

    Returns:
        Database instance from app.state.db

    Usage:
        @router.websocket("/ws/endpoint")
        async def websocket_endpoint(websocket: WebSocket, db: Database = Depends(get_db_websocket)):
            # Use db here
            ...
    """
    return websocket.app.state.db


def get_v2_workspace(
    workspace_path: Optional[str] = Query(
        None,
        description="Path to workspace directory (defaults to server's working directory)",
    ),
    request: Request = None,
) -> Workspace:
    """Get v2 Workspace from path or server default.

    This dependency bridges v1 routes to v2 core modules. It resolves
    a Workspace from either:
    1. An explicit workspace_path query parameter
    2. The server's default workspace (from app.state.default_workspace_path)
    3. The server's current working directory

    Args:
        workspace_path: Optional explicit path to workspace
        request: FastAPI request for accessing app state

    Returns:
        v2 Workspace instance

    Raises:
        HTTPException:
            - 400: No workspace path provided and no default configured
            - 404: Workspace not found at path

    Usage:
        @router.get("/v2/endpoint")
        async def endpoint(workspace: Workspace = Depends(get_v2_workspace)):
            # Use workspace here
            ...
    """
    # Resolve workspace path
    if workspace_path:
        path = Path(workspace_path).resolve()
    elif request and getattr(request.app.state, "default_workspace_path", None):
        path = Path(request.app.state.default_workspace_path).resolve()
    else:
        # Fall back to current working directory
        path = Path.cwd()

    # Validate workspace exists
    if not workspace_exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found at {path}. Initialize with 'cf init {path}'",
        )

    try:
        workspace = get_workspace(path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found at {path}. Initialize with 'cf init {path}'",
        )

    if not workspace:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found at {path}. Initialize with 'cf init {path}'",
        )

    return workspace


__all__ = [
    "get_db",
    "get_db_websocket",
    "get_workspace_manager",
    "get_v2_workspace",
]
