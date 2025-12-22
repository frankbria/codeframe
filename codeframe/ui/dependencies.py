"""FastAPI dependency injection providers.

This module provides dependency injection functions for accessing
shared application state (database, workspace manager, etc.) across
all API endpoints.
"""

from fastapi import Request

from codeframe.persistence.database import Database
from codeframe.workspace import WorkspaceManager


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


__all__ = [
    "get_db",
    "get_workspace_manager",
]
