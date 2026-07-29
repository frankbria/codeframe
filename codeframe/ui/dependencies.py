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

# v2 imports
from codeframe.core.workspace import Workspace, get_workspace, workspace_exists


def _allowed_workspace_roots() -> list[Path]:
    """Permitted workspace roots from ``WORKSPACE_ROOT`` (os.pathsep-separated).

    This is the **only** reader of ``WORKSPACE_ROOT`` (issue #896). The server
    lifespan used to parse the same variable as a single directory and mkdir it,
    so the documented multi-root form ``/srv/a:/srv/b`` created a junk directory
    at boot. One name, one meaning: an allowlist, never a location.

    Empty when unset — meaning "no allowlist". Startup refuses to serve in that
    configuration whenever auth is enforced, so an empty list can only reach a
    request on a server that is either auth-free or has explicitly opted out via
    ``CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES`` (see
    ``server._validate_workspace_allowlist_config``).

    Each root is resolved so containment checks defeat ``..`` escapes.
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


def github_env_fallback_allowed(auth: Dict[str, Any]) -> bool:
    """Whether this caller may fall back to the process-wide GitHub env vars (#900).

    One rule, stated once: **the process environment belongs to the operator, so
    only the operator may act with it.** ``GITHUB_TOKEN``/``GITHUB_REPO`` are the
    machine's ambient configuration, not any particular user's credential, so
    serving them to an ordinary principal opens PRs — and reads private repos —
    on the operator's behalf, unattributed.

    Gating this on *deployment mode* is not enough, and was the first cut's
    mistake: the default deployment is self-hosted **with auth enabled**, so an
    ordinary authenticated user with no PAT of their own would still have been
    handed the operator's token there.

    - auth disabled (``user_id is None``) — the caller *is* the local operator.
    - authenticated operator — an ``admin``-scoped principal. Since #898 that
      means an ``is_superuser`` account, and an admin-scoped API key is clamped
      to a superuser owner on every request, so this is a real operator check
      rather than a self-asserted one.
    - anyone else — store-only. They get a clear "connect a repository" 400
      rather than someone else's credential.
    - hosted mode — never. There the environment is shared by every tenant, so
      falling back to it is precisely the cross-tenant leak.
    """
    from codeframe.auth.api_keys import SCOPE_ADMIN
    from codeframe.auth.scopes import has_scope
    from codeframe.ui.server import is_hosted_mode

    if is_hosted_mode():
        return False
    if auth.get("user_id") is None:
        return True
    return has_scope(auth, SCOPE_ADMIN)


def resolve_github_pat(credential_manager, auth: Dict[str, Any]) -> Optional[str]:
    """The GitHub PAT this caller may act with (#900).

    Shared by the PR router and the Integrations router so the two cannot drift
    on whose credential is used. ``get_credential`` is env-*first* by default,
    so a plain call would let the operator's ambient ``GITHUB_TOKEN`` displace
    the PAT a user connected in the UI.
    """
    from codeframe.core.credentials import CredentialProvider

    if github_env_fallback_allowed(auth):
        return credential_manager.get_credential(
            CredentialProvider.GIT_GITHUB,
            prefer_stored=auth.get("user_id") is not None,
        )
    return credential_manager.get_stored_credential(CredentialProvider.GIT_GITHUB)


__all__ = [
    "get_v2_workspace",
    "enforce_workspace_allowlist",
    "github_env_fallback_allowed",
    "resolve_github_pat",
]
