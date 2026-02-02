"""V2 Workspace router - delegates to core/workspace module.

This module provides v2-style API endpoints for workspace initialization
and management. Workspaces are the root container for all CodeFRAME state.

Routes:
    POST /api/v2/workspaces          - Initialize a new workspace
    GET  /api/v2/workspaces/current  - Get current workspace info
    PATCH /api/v2/workspaces/current - Update workspace (e.g., tech stack)
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from codeframe.core import workspace as ws
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.core.workspace import Workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/workspaces", tags=["workspaces-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class WorkspaceResponse(BaseModel):
    """Response for workspace information."""

    id: str
    repo_path: str
    state_dir: str
    tech_stack: Optional[str]
    created_at: str


class InitWorkspaceRequest(BaseModel):
    """Request for initializing a workspace."""

    repo_path: str = Field(..., min_length=1, description="Path to the repository")
    tech_stack: Optional[str] = Field(None, description="Tech stack description")
    detect: bool = Field(False, description="Auto-detect tech stack from project files")


class UpdateWorkspaceRequest(BaseModel):
    """Request for updating workspace."""

    tech_stack: Optional[str] = Field(None, description="New tech stack description")


# ============================================================================
# Helper Functions
# ============================================================================


def _workspace_to_response(workspace: Workspace) -> WorkspaceResponse:
    """Convert a Workspace to a WorkspaceResponse."""
    return WorkspaceResponse(
        id=workspace.id,
        repo_path=str(workspace.repo_path),
        state_dir=str(workspace.state_dir),
        tech_stack=workspace.tech_stack,
        created_at=workspace.created_at.isoformat(),
    )


def _detect_tech_stack(repo_path: Path) -> Optional[str]:
    """Auto-detect tech stack from project files.

    Looks for common project files and infers the tech stack.
    """
    tech_parts = []

    # Python detection
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        if "uv" in content or "[tool.uv]" in content:
            tech_parts.append("Python with uv")
        elif "poetry" in content:
            tech_parts.append("Python with poetry")
        else:
            tech_parts.append("Python")

        if "pytest" in content:
            tech_parts.append("pytest")
        if "ruff" in content:
            tech_parts.append("ruff for linting")
        if "fastapi" in content.lower():
            tech_parts.append("FastAPI")

    # Node.js detection
    package_json = repo_path / "package.json"
    if package_json.exists():
        content = package_json.read_text()
        if "next" in content:
            tech_parts.append("Next.js")
        elif "react" in content:
            tech_parts.append("React")
        if "typescript" in content:
            tech_parts.append("TypeScript")

    # Rust detection
    cargo_toml = repo_path / "Cargo.toml"
    if cargo_toml.exists():
        tech_parts.append("Rust with cargo")

    # Go detection
    go_mod = repo_path / "go.mod"
    if go_mod.exists():
        tech_parts.append("Go")

    return ", ".join(tech_parts) if tech_parts else None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def init_workspace(
    request: InitWorkspaceRequest,
) -> WorkspaceResponse:
    """Initialize a new workspace for a repository.

    Creates a .codeframe/ directory with state storage and configuration.
    This is idempotent - safe to call multiple times on the same repo.

    Args:
        request: Workspace initialization request

    Returns:
        Created or existing workspace

    Raises:
        HTTPException:
            - 400: Invalid path or conflicting options
            - 404: Repository path not found
    """
    try:
        repo_path = Path(request.repo_path).resolve()

        # Validate path exists
        if not repo_path.exists():
            raise HTTPException(
                status_code=404,
                detail=api_error(
                    "Path not found",
                    ErrorCodes.NOT_FOUND,
                    f"Repository path does not exist: {repo_path}",
                ),
            )

        if not repo_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=api_error(
                    "Invalid path",
                    ErrorCodes.VALIDATION_ERROR,
                    "Path must be a directory",
                ),
            )

        # Determine tech stack
        tech_stack = request.tech_stack
        if request.detect and not tech_stack:
            tech_stack = _detect_tech_stack(repo_path)

        # Check if workspace already exists
        already_existed = ws.workspace_exists(repo_path)

        if already_existed:
            workspace = ws.get_workspace(repo_path)
            # Update tech stack if provided for existing workspace
            if tech_stack:
                workspace = ws.update_workspace_tech_stack(repo_path, tech_stack)
        else:
            workspace = ws.create_or_load_workspace(repo_path, tech_stack=tech_stack)

        return _workspace_to_response(workspace)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to initialize workspace: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Initialization failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/current", response_model=WorkspaceResponse)
async def get_current_workspace(
    workspace: Workspace = Depends(get_v2_workspace),
) -> WorkspaceResponse:
    """Get information about the current workspace.

    The workspace is resolved from the workspace_path query parameter
    or the server's default workspace.

    Args:
        workspace: v2 Workspace (resolved by dependency)

    Returns:
        Workspace information
    """
    return _workspace_to_response(workspace)


@router.patch("/current", response_model=WorkspaceResponse)
async def update_current_workspace(
    request: UpdateWorkspaceRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> WorkspaceResponse:
    """Update the current workspace.

    Currently supports updating:
    - tech_stack: Natural language description of the project's technology

    Args:
        request: Update request
        workspace: v2 Workspace (resolved by dependency)

    Returns:
        Updated workspace

    Raises:
        HTTPException: 500 if update fails
    """
    try:
        updated = workspace

        if request.tech_stack is not None:
            updated = ws.update_workspace_tech_stack(workspace.repo_path, request.tech_stack)

        return _workspace_to_response(updated)

    except Exception as e:
        logger.error(f"Failed to update workspace: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Update failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


@router.get("/exists")
async def check_workspace_exists(
    repo_path: str = Query(..., description="Path to check for workspace"),
) -> dict:
    """Check if a workspace exists at a given path.

    Args:
        repo_path: Path to check

    Returns:
        Whether workspace exists and path info
    """
    path = Path(repo_path).resolve()

    return {
        "exists": ws.workspace_exists(path),
        "path": str(path),
        "state_dir": str(path / ".codeframe") if ws.workspace_exists(path) else None,
    }
