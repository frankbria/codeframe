"""FastAPI dependency injection providers.

This module provides dependency injection functions for accessing
shared application state across all API endpoints.

v2-only: All dependencies use codeframe.core modules.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request

from codeframe.auth.dependencies import require_auth
from codeframe.workspace import WorkspaceManager

# v2 imports
from codeframe.core.workspace import Workspace, get_workspace, workspace_exists


def _allowed_workspace_roots() -> list[Path]:
    """Permitted workspace roots from ``WORKSPACE_ROOT`` (os.pathsep-separated).

    Empty when unset — meaning "no allowlist" (single-operator self-hosted, the
    default). Each root is resolved so containment checks defeat ``..`` escapes.
    """
    raw = os.getenv("WORKSPACE_ROOT", "").strip()
    if not raw:
        return []
    return [
        Path(p).expanduser().resolve()
        for p in raw.split(os.pathsep)
        if p.strip()
    ]


def _within_any_root(path: Path, roots: list[Path]) -> bool:
    return any(path == r or path.is_relative_to(r) for r in roots)


def enforce_workspace_allowlist(path: Path, user_id: Optional[int]) -> Path:
    """Validate a resolved workspace path against the allowlist (issue #655).

    Shared by every entry point that resolves a client-supplied workspace path:
    ``get_v2_workspace`` (REST) and interactive session creation (whose stored
    path later becomes a terminal shell's ``cwd``). Without it, an authenticated
    user can point operations at any host directory — authenticated
    cross-tenant RCE once the server serves >1 user.

    Returns the (resolved) path on success; raises ``HTTPException`` otherwise.
    """
    # Local import avoids a circular import (server -> routers -> dependencies).
    from codeframe.ui.server import is_hosted_mode

    path = path.resolve()
    roots = _allowed_workspace_roots()
    if is_hosted_mode():
        # Hosted/multi-tenant: the allowlist is mandatory (fail closed) and each
        # user is confined to <root>/<user_id> so one tenant can't reach
        # another's subtree.
        # ponytail: path-namespace binding, not a DB ownership table. Upgrade to
        # registry-backed owner_user_id checks if workspaces ever live outside a
        # per-user root.
        if not roots:
            raise HTTPException(
                status_code=500,
                detail="Server misconfigured: WORKSPACE_ROOT must be set in hosted mode.",
            )
        if user_id is None:
            raise HTTPException(status_code=403, detail="Authenticated user required.")
        roots = [r / str(user_id) for r in roots]

    if roots and not _within_any_root(path, roots):
        raise HTTPException(
            status_code=403,
            detail="Workspace path is outside the permitted workspace roots.",
        )
    return path


def revalidate_workspace_path(workspace_path: str, user_id: Optional[int]) -> Optional[Path]:
    """Re-check a stored session workspace path against the allowlist at use time (#704).

    ``create_session`` validates the path once, but the terminal/chat WebSockets
    open later — a tenant could swap a dir (or ancestor) for a symlink pointing
    outside its allowed root in between (TOCTOU). ``enforce_workspace_allowlist``
    calls ``.resolve()``, which follows symlinks, so a swapped-in escape is caught
    here. Returns the freshly resolved path, or ``None`` if it no longer passes
    (the WS caller closes the socket instead of raising HTTP).

    Note: this closes the practical window; a sub-millisecond race remains between
    this check and the shell spawn. True TOCTOU-proof isolation needs a per-tenant
    container/chroot or openat2(RESOLVE_NO_SYMLINKS) — infra-level, deferred.
    """
    try:
        return enforce_workspace_allowlist(Path(workspace_path), user_id)
    except HTTPException:
        return None


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


def get_v2_workspace(
    workspace_path: Optional[str] = Query(
        None,
        description="Path to workspace directory (defaults to server's working directory)",
    ),
    request: Request = None,
    auth: Dict[str, Any] = Depends(require_auth),
) -> Workspace:
    """Get v2 Workspace from path or server default.

    This dependency resolves a Workspace from either:
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

    # Enforce the workspace allowlist (issue #655).
    path = enforce_workspace_allowlist(path, auth.get("user_id"))

    # Validate workspace exists
    # Note: Avoid exposing full filesystem paths in error messages for hosted deployments
    if not workspace_exists(path):
        raise HTTPException(
            status_code=404,
            detail="Workspace not found at specified path. Initialize with 'cf init <path>'",
        )

    try:
        workspace = get_workspace(path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found at specified path. Initialize with 'cf init <path>'",
        )

    # Note: get_workspace() raises FileNotFoundError rather than returning None,
    # so no additional null check is needed here.
    return workspace


__all__ = [
    "get_workspace_manager",
    "get_v2_workspace",
    "enforce_workspace_allowlist",
]
