"""FastAPI dependency injection providers.

This module provides dependency injection functions for accessing
shared application state across all API endpoints.

v2-only: All dependencies use codeframe.core modules.
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request

from codeframe.auth.dependencies import require_auth

# v2 imports
from codeframe.core.workspace import Workspace, get_workspace, workspace_exists

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from codeframe.core.credentials import CredentialManager


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
    """Get v2 Workspace from path or the server's working directory.

    This dependency resolves a Workspace from either:
    1. An explicit workspace_path query parameter
    2. The server's current working directory

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
    # Resolve workspace path. (#968 removed a middle branch that read a
    # server-configured default off app.state; nothing ever assigned that
    # attribute, so the branch was unreachable and the default was always cwd.)
    if workspace_path:
        path = Path(workspace_path).resolve()
    else:
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


def refuse_execution_in_hosted_mode() -> None:
    """403 for anything that runs tenant-controlled code, in hosted mode (#1266).

    Every process a route starts runs as the server's uid with the server's
    filesystem view, so a tenant could read ``../<other_user>/`` or the parent's
    ``/proc/$PPID/environ``. The ``<WORKSPACE_ROOT>/<user_id>`` check only
    confines the *starting path*, which is not a boundary. Until per-tenant OS
    isolation (a container or a uid per tenant) exists, hosted mode refuses.
    """
    from codeframe.ui.server import is_hosted_mode

    if is_hosted_mode():
        raise HTTPException(
            status_code=403,
            detail=(
                "Execution is disabled in hosted mode until per-tenant OS "
                "isolation exists: processes would run as the server user."
            ),
        )


def _build_credential_manager(auth: Dict[str, Any], *, migrate: bool) -> "CredentialManager":
    """Build the caller's CredentialManager, mapping an unreadable store to 500.

    Shared by every router that builds one from a request (#1303): the copy in
    the GitHub router kept migrating for non-admins after Settings stopped.
    """
    from codeframe.core.credentials import (
        CredentialManager,
        CredentialStoreUnreadableError,
    )
    from codeframe.ui.response_models import internal_error

    # CredentialManager's constructor runs the machine-wide migration, which
    # can raise CredentialStoreUnreadableError since #954. Raised from a
    # DEPENDENCY it bypasses each route's own try/except, so the client got a
    # bare 500 instead of the formatted error every other path produces (#1085).
    # The exception's message carries the recovery text the CLI already prints.
    try:
        return CredentialManager(user_id=auth.get("user_id"), migrate=migrate)
    except CredentialStoreUnreadableError as e:
        # internal_error, NOT str(e) (#934): the exception message embeds the
        # absolute store path — /home/<operator>/.codeframe/users/<id>/... —
        # so rendering it would hand an authenticated tenant the operator's
        # home directory and the per-tenant storage layout. The full message
        # goes to the operator's log under the correlation id; the client gets
        # the recovery step, which is the part that is actually actionable and
        # contains no path.
        body = internal_error(e, operation="read the credential store", logger=logger)
        body["detail"] += (
            " The credential store could not be read; re-enter your keys with "
            "`cf auth setup`."
        )
        raise HTTPException(status_code=500, detail=body)


def get_credential_manager(auth: Dict[str, Any] = Depends(require_auth)) -> "CredentialManager":
    """Dependency: CredentialManager scoped to the authenticated user (#790).

    ``user_id=None`` (auth disabled / self-hosted) yields the machine-wide
    store. Overridden in tests to point at an isolated temp directory.
    Use only on write paths.

    The machine-wide migration runs for admins only (#1303). It copies the
    operator's machine-wide credentials into the caller's per-user store, so a
    non-admin tenant storing their own LLM key would otherwise inherit the
    operator's keys (and in hosted mode that store is all they read).
    """
    from codeframe.auth.api_keys import SCOPE_ADMIN
    from codeframe.auth.scopes import has_scope

    return _build_credential_manager(auth, migrate=has_scope(auth, SCOPE_ADMIN))


def get_credential_manager_readonly(
    auth: Dict[str, Any] = Depends(require_auth),
) -> "CredentialManager":
    """Read-only variant: scoped to the authenticated user but skips migration.

    Used on GET endpoints so that a plain status check cannot trigger a
    credential write into a new tenant's store (#790).
    """
    return _build_credential_manager(auth, migrate=False)


def check_spend_limit(
    request: Request,
    workspace: Workspace,
    auth: Dict[str, Any],
    *,
    reserve: bool = False,
) -> tuple[Optional[Callable[[], list[Path]]], Optional[float]]:
    """429 when the principal has used up today's spend limit (#1303).

    Returns ``(spend_scope, budget_usd)`` for the work being started, or
    ``(None, None)`` when no limit applies: none is configured, or the principal
    is the auth-off operator. ``spend_scope()`` lists the workspaces whose spend
    counts, read fresh on each call so a batch rechecks workspaces the principal
    starts using later. ``reserve=True`` holds ``budget_usd`` for one run; the
    caller must ``spend_limit.release`` it when that run ends. Blocking I/O —
    call via ``run_in_threadpool``, and before any state is written, so a
    refusal leaves nothing behind.
    """
    from codeframe.core.spend_limit import (
        SpendLimitExceeded,
        daily_limit_usd,
        remaining_today_usd,
        reserve_today_usd,
    )
    from codeframe.ui.response_models import ErrorCodes, api_error

    user_id = auth.get("user_id")
    if user_id is None:
        return None, None
    current = str(Path(workspace.repo_path))
    registry = getattr(getattr(request.app.state, "db", None), "workspace_registry", None)
    if registry is not None:
        # Recorded even with no limit set, so turning one on mid-day still
        # counts the workspaces used earlier that day.
        registry.record_spend_use(user_id, current)
    if daily_limit_usd() is None:
        return None, None
    # The REST routes only accept react/plan; a delegated engine can still
    # arrive via batch resume, which the conductor refuses per task.
    def spend_scope() -> list[Path]:
        # ponytail: attribution is by workspace, not by who made the call, so
        # a workspace shared between users counts in full for each of them
        # (fails closed). A user_id column on token_usage would make it exact.
        paths = [Path(current)]
        if registry is not None:
            paths += [Path(p) for p in registry.spend_paths(user_id)]
        return paths

    try:
        budget = (
            reserve_today_usd(user_id, spend_scope())
            if reserve
            else remaining_today_usd(spend_scope(), user_id)
        )
    except SpendLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=api_error(str(exc), ErrorCodes.SPEND_LIMIT_EXCEEDED),
        )
    return spend_scope, budget


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
    "refuse_execution_in_hosted_mode",
    "resolve_github_pat",
]
