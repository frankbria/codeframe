"""V2 Workspace router - delegates to core/workspace module.

This module provides v2-style API endpoints for workspace initialization
and management. Workspaces are the root container for all CodeFRAME state.

Routes:
    POST /api/v2/workspaces          - Initialize a new workspace
    GET  /api/v2/workspaces/current  - Get current workspace info
    PATCH /api/v2/workspaces/current - Update workspace (e.g., tech stack)
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError

from codeframe.core import workspace as ws
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.core.workspace import WORKSPACE_CONFIG_FILENAME, Workspace
from codeframe.ui.response_models import api_error, ErrorCodes
from codeframe.ui.routers._helpers import atomic_write_json

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


class WorkspaceRegistryResponse(BaseModel):
    """A single registered workspace from the server-side registry (issue #601)."""

    id: str
    repo_path: str
    name: Optional[str] = None
    tech_stack: Optional[str] = None
    created_at: Optional[str] = None
    last_opened_at: Optional[str] = None
    path_exists: bool = Field(
        ..., description="Whether repo_path still exists on disk (computed at list time)."
    )


class WorkspaceListResponse(BaseModel):
    """Response for listing registered workspaces."""

    workspaces: List[WorkspaceRegistryResponse]


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


def _get_registry(request: Request):
    """Return the WorkspaceRegistryRepository, or None if unavailable.

    Registry writes are best-effort: when the control-plane DB isn't attached
    (e.g. lightweight tests that mount only this router), registry tracking is
    silently skipped so core workspace operations never break.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        return None
    return getattr(db, "workspace_registry", None)


def _register_workspace(request: Request, workspace: Workspace) -> None:
    """Best-effort upsert of a workspace into the server-side registry."""
    registry = _get_registry(request)
    if registry is None:
        return
    try:
        registry.upsert(
            repo_path=str(workspace.repo_path),
            name=workspace.repo_path.name,
            tech_stack=workspace.tech_stack,
            owner_user_id=None,  # Until auth is enforced on v2 routers.
        )
    except Exception as e:  # noqa: BLE001 - tracking must never break the request
        logger.warning("Failed to register workspace in registry: %s", e)


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=WorkspaceListResponse)
@rate_limit_standard()
async def list_workspaces(request: Request) -> WorkspaceListResponse:
    """List all registered workspaces (issue #601).

    Returns server-side registry entries ordered by recency, each annotated with
    a computed ``path_exists`` so clients can flag stale projects. Returns an
    empty list when the registry is unavailable.
    """
    registry = _get_registry(request)
    if registry is None:
        return WorkspaceListResponse(workspaces=[])

    entries = registry.list_all()
    workspaces = [
        WorkspaceRegistryResponse(
            id=entry["id"],
            repo_path=entry["repo_path"],
            name=entry.get("name"),
            tech_stack=entry.get("tech_stack"),
            created_at=entry.get("created_at"),
            last_opened_at=entry.get("last_opened_at"),
            path_exists=Path(entry["repo_path"]).exists(),
        )
        for entry in entries
    ]
    return WorkspaceListResponse(workspaces=workspaces)


@router.post("", response_model=WorkspaceResponse, status_code=201)
@rate_limit_standard()
async def init_workspace(
    request: Request,
    body: InitWorkspaceRequest,
) -> WorkspaceResponse:
    """Initialize a new workspace for a repository.

    Creates a .codeframe/ directory with state storage and configuration.
    This is idempotent - safe to call multiple times on the same repo.

    Args:
        request: HTTP request for rate limiting
        body: Workspace initialization request

    Returns:
        Created or existing workspace

    Raises:
        HTTPException:
            - 400: Invalid path or conflicting options
            - 404: Repository path not found
    """
    try:
        repo_path = Path(body.repo_path).resolve()

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
        tech_stack = body.tech_stack
        if body.detect and not tech_stack:
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

        # Register (or refresh) the workspace in the server-side registry (#601).
        _register_workspace(request, workspace)

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
@rate_limit_standard()
async def get_current_workspace(
    request: Request,
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
    # Track access recency in the registry (#601). Auto-register workspaces that
    # were opened directly by path so they become server-tracked. Best-effort.
    registry = _get_registry(request)
    if registry is not None:
        try:
            entry = registry.get_by_path(str(workspace.repo_path))
            if entry is not None:
                registry.update_last_opened(entry["id"])
            else:
                _register_workspace(request, workspace)
        except Exception as e:  # noqa: BLE001 - tracking must never break the request
            logger.warning("Failed to track workspace access: %s", e)

    return _workspace_to_response(workspace)


@router.patch("/current", response_model=WorkspaceResponse)
@rate_limit_standard()
async def update_current_workspace(
    request: Request,
    body: UpdateWorkspaceRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> WorkspaceResponse:
    """Update the current workspace.

    Currently supports updating:
    - tech_stack: Natural language description of the project's technology

    Args:
        request: HTTP request for rate limiting
        body: Update request
        workspace: v2 Workspace (resolved by dependency)

    Returns:
        Updated workspace

    Raises:
        HTTPException: 500 if update fails
    """
    try:
        updated = workspace

        if body.tech_stack is not None:
            updated = ws.update_workspace_tech_stack(workspace.repo_path, body.tech_stack)

        return _workspace_to_response(updated)

    except Exception as e:
        logger.error(f"Failed to update workspace: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Update failed", ErrorCodes.EXECUTION_FAILED, str(e)),
        )


# ============================================================================
# Workspace Config (issue #556)
#
# Persists per-workspace UI-configurable settings (root path display, default
# branch, tech-stack auto-detect toggle + manual override) to
# .codeframe/workspace_config.json.
# ============================================================================


class WorkspaceConfigResponse(BaseModel):
    workspace_root: str = Field(
        ..., description="Display-only. The server resolves the active workspace from the workspace_path query parameter."
    )
    default_branch: str
    auto_detect_tech_stack: bool
    tech_stack_override: Optional[str] = None


class UpdateWorkspaceConfigRequest(BaseModel):
    workspace_root: str = Field(
        ...,
        min_length=1,
        description="Display-only — editing does not relocate the workspace.",
    )
    default_branch: str = Field(..., min_length=1)
    auto_detect_tech_stack: bool
    tech_stack_override: Optional[str] = None


def _workspace_config_path(workspace: Workspace) -> Path:
    return workspace.state_dir / WORKSPACE_CONFIG_FILENAME


def _default_workspace_config(workspace: Workspace) -> dict:
    return {
        "workspace_root": str(workspace.repo_path),
        "default_branch": "main",
        "auto_detect_tech_stack": True,
        "tech_stack_override": None,
    }


@router.get("/config", response_model=WorkspaceConfigResponse)
@rate_limit_standard()
async def get_workspace_config(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
) -> WorkspaceConfigResponse:
    """Load workspace configuration for this workspace.

    Returns defaults sourced from the Workspace itself if no config file exists.
    """
    path = _workspace_config_path(workspace)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            # workspace_root is display-only — always source it from the live
            # workspace so a stored value can't drift from reality.
            data["workspace_root"] = str(workspace.repo_path)
            return WorkspaceConfigResponse(**data)
        except (OSError, json.JSONDecodeError, ValueError, ValidationError) as e:
            logger.warning(
                "Invalid workspace_config.json — falling back to defaults: %s", e
            )
    return WorkspaceConfigResponse(**_default_workspace_config(workspace))


@router.put("/config", response_model=WorkspaceConfigResponse)
@rate_limit_standard()
async def update_workspace_config(
    request: Request,
    body: UpdateWorkspaceConfigRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> WorkspaceConfigResponse:
    """Persist workspace configuration to .codeframe/workspace_config.json.

    Note: `workspace_root` is informational/display-only. The server resolves
    the active workspace path from the `workspace_path` query parameter or
    its default — editing this field does not relocate the workspace. The
    value is replaced on write so PUT/GET stay consistent.
    """
    payload = body.model_dump(exclude={"workspace_root"})
    payload["workspace_root"] = str(workspace.repo_path)
    atomic_write_json(_workspace_config_path(workspace), payload)
    return WorkspaceConfigResponse(**payload)


@router.get("/exists")
@rate_limit_standard()
async def check_workspace_exists(
    request: Request,
    repo_path: str = Query(..., description="Path to check for workspace"),
) -> dict:
    """Check if a workspace exists at a given path.

    Args:
        request: HTTP request for rate limiting
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


@router.delete("/{workspace_id}", status_code=204)
@rate_limit_standard()
async def deregister_workspace(
    request: Request,
    workspace_id: str,
) -> Response:
    """Deregister a workspace from the server-side registry (issue #601).

    Removes only the registry entry — it never deletes the ``.codeframe/``
    directory or any on-disk state.

    Returns:
        204 No Content on success.

    Raises:
        HTTPException:
            - 404: workspace_id not found in the registry
            - 503: registry/control-plane DB unavailable
    """
    registry = _get_registry(request)
    if registry is None:
        raise HTTPException(
            status_code=503,
            detail=api_error(
                "Registry unavailable",
                ErrorCodes.EXECUTION_FAILED,
                "Workspace registry is not available on this server.",
            ),
        )

    deleted = registry.delete(workspace_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "Workspace not found",
                ErrorCodes.NOT_FOUND,
                f"No registered workspace with id: {workspace_id}",
            ),
        )

    return Response(status_code=204)
