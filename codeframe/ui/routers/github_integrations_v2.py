"""V2 GitHub integrations router — repository connection via PAT (issue #563).

Routes (prefix ``/api/v2/integrations/github``):
    POST   /connect      - Validate PAT against repo, store PAT, save repo metadata
    DELETE /disconnect   - Clear stored PAT + repo metadata
    GET    /status       - Report connection status (never exposes the PAT)
    GET    /issues       - List the connected repo's open issues (#564)

The PAT is stored machine-wide via ``CredentialManager`` under
``CredentialProvider.GIT_GITHUB`` — the same slot the API Keys settings tab
(#555) uses. Repo metadata (non-secret) is persisted per-workspace under
``.codeframe/github_integration.json``. The PAT is never returned in any
response.
"""

import logging
import sqlite3
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from codeframe.core.credentials import CredentialManager, CredentialProvider
from codeframe.core.github_connect_service import (
    GitHubConnectError,
    InsufficientScopeError,
    InvalidTokenError,
    RepoNotFoundError,
    parse_repo,
    validate_connection,
)
from codeframe.core.github_issues_service import (
    IssueNotFoundError,
    NotAnIssueError,
    get_issue,
    list_issues,
)
from codeframe.core.github_integration_config import (
    clear_github_integration_config,
    load_github_integration_config,
    save_github_integration_config,
)
from codeframe.core import tasks
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_ai, rate_limit_standard
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import ErrorCodes, api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/integrations/github", tags=["integrations"])


def get_credential_manager() -> CredentialManager:
    """Dependency: machine-wide CredentialManager.

    Overridden in tests to point at an isolated temp directory.
    """
    return CredentialManager()


class ConnectRequest(BaseModel):
    pat: str = Field(..., min_length=1, description="GitHub Personal Access Token")
    repo: str = Field(..., description="Repository in 'owner/repo' format")


class ConnectResponse(BaseModel):
    connected: bool
    repo: str
    owner_login: str
    owner_avatar_url: str


class StatusResponse(BaseModel):
    connected: bool
    repo: Optional[str] = None
    owner_login: Optional[str] = None
    owner_avatar_url: Optional[str] = None


class GitHubIssueItem(BaseModel):
    number: int
    title: str
    labels: list[str]
    assignee: Optional[str] = None
    created_at: str
    html_url: str


class GitHubIssuesResponse(BaseModel):
    issues: list[GitHubIssueItem]
    total: int
    page: int
    per_page: int


class ImportRequest(BaseModel):
    issue_numbers: list[int] = Field(
        ..., min_length=1, description="GitHub issue numbers to import as tasks"
    )


class ImportedTaskSummary(BaseModel):
    task_id: str
    issue_number: int
    title: str


class ImportResponse(BaseModel):
    created: list[ImportedTaskSummary]
    skipped: list[int]
    total_created: int


# In-process TTL cache for issue listings (#564). Keyed by the full query
# (repo + page + per_page + search + label); entries expire after 60s to avoid
# hammering GitHub's rate limit on repeated browses. Module-level so it is
# shared across requests within the same server process.
_ISSUE_CACHE_TTL_SECONDS = 60.0
_ISSUE_CACHE: dict[str, tuple[float, Any]] = {}


def _issue_cache_get(key: str) -> Optional[Any]:
    entry = _ISSUE_CACHE.get(key)
    if entry is None:
        return None
    expires_at, payload = entry
    if time.monotonic() >= expires_at:
        _ISSUE_CACHE.pop(key, None)
        return None
    return payload


def _issue_cache_set(key: str, payload: Any) -> None:
    _ISSUE_CACHE[key] = (time.monotonic() + _ISSUE_CACHE_TTL_SECONDS, payload)


def _issue_cache_invalidate(repo: str) -> None:
    """Drop all cached issue listings for ``repo``.

    Called after an import so reopening the browse modal doesn't keep offering
    just-imported issues as selectable (they would now be skipped as dupes).
    """
    prefix = f"{repo}|"
    for key in [k for k in _ISSUE_CACHE if k.startswith(prefix)]:
        _ISSUE_CACHE.pop(key, None)


@router.get("/status", response_model=StatusResponse)
@rate_limit_standard()
async def get_status(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> StatusResponse:
    """Report whether a GitHub repo is connected for this workspace.

    Connected means BOTH the per-workspace repo metadata exists AND the
    machine-wide GitHub PAT is present (env var or stored).
    """
    cfg = load_github_integration_config(workspace)
    has_pat = manager.get_credential(CredentialProvider.GIT_GITHUB) is not None
    if cfg is None or not has_pat:
        return StatusResponse(connected=False)
    return StatusResponse(
        connected=True,
        repo=cfg["repo"],
        owner_login=cfg["owner_login"] or None,
        owner_avatar_url=cfg["owner_avatar_url"] or None,
    )


@router.post("/connect", response_model=ConnectResponse)
@rate_limit_ai()
async def connect(
    request: Request,
    body: ConnectRequest,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> ConnectResponse:
    """Validate a PAT against the target repo, then store the PAT + repo metadata.

    The PAT is validated against the GitHub API (token validity, repo
    visibility, issues-read access) BEFORE anything is persisted. On any
    validation failure nothing is stored.
    """
    # Validate 'owner/repo' format at the boundary before any network call.
    try:
        parse_repo(body.repo)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )

    try:
        result = await validate_connection(body.pat, body.repo)
    except ValueError as e:
        # Defensive: service re-validates format too.
        raise HTTPException(
            status_code=400,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except RepoNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=api_error(str(e), ErrorCodes.NOT_FOUND),
        )
    except InsufficientScopeError as e:
        raise HTTPException(
            status_code=403,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except GitHubConnectError as e:
        raise HTTPException(
            status_code=502,
            detail=api_error(str(e), ErrorCodes.EXECUTION_FAILED),
        )

    # Validation passed — store the PAT (machine-wide) and repo metadata.
    # The GIT_GITHUB slot is shared machine-wide with the API Keys tab, so
    # capture any prior token first to restore it if the config write fails —
    # never blindly delete an unrelated, previously working credential.
    prior_pat = manager.get_credential(CredentialProvider.GIT_GITHUB)
    try:
        manager.set_credential(CredentialProvider.GIT_GITHUB, body.pat)
    except Exception as e:
        logger.error("Failed to store GitHub PAT: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to store GitHub token", ErrorCodes.EXECUTION_FAILED, str(e)
            ),
        )

    try:
        saved = save_github_integration_config(
            workspace,
            {
                "repo": result["repo_full_name"],
                "owner_login": result["owner_login"],
                "owner_avatar_url": result["owner_avatar_url"],
            },
        )
    except OSError as e:
        # Roll back the credential so we don't leave a half-connected state.
        # Restore the prior token if there was one; only delete when the slot
        # was empty before this request.
        logger.error("Failed to save integration config: %s", e, exc_info=True)
        try:
            if prior_pat is not None:
                manager.set_credential(CredentialProvider.GIT_GITHUB, prior_pat)
            else:
                manager.delete_credential(CredentialProvider.GIT_GITHUB)
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "Failed to save integration config",
                ErrorCodes.EXECUTION_FAILED,
                str(e),
            ),
        )

    return ConnectResponse(
        connected=True,
        repo=saved["repo"],
        owner_login=saved["owner_login"],
        owner_avatar_url=saved["owner_avatar_url"],
    )


@router.delete("/disconnect", status_code=204)
@rate_limit_standard()
async def disconnect(
    request: Request,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> Response:
    """Clear stored repo metadata and delete the GitHub PAT. Idempotent."""
    clear_github_integration_config(workspace)
    try:
        manager.delete_credential(CredentialProvider.GIT_GITHUB)
    except Exception as e:
        # Treat absence as success; only surface hard failures.
        msg = str(e).lower()
        if "no such" not in msg and "not found" not in msg:
            logger.warning("Failed to delete GitHub PAT on disconnect: %s", e)
    return Response(status_code=204)


@router.get("/issues", response_model=GitHubIssuesResponse)
@rate_limit_standard()
async def get_issues(
    request: Request,
    page: int = Query(1, ge=1, description="1-indexed page number"),
    per_page: int = Query(25, description="Page size (clamped to 1..100)"),
    search: str = Query("", description="Free-text title/body search"),
    label: str = Query("", description="Filter by a single label name"),
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> GitHubIssuesResponse:
    """List the connected repository's **open** issues for the import browser.

    Requires an established connection (#563): repo metadata in
    ``.codeframe/github_integration.json`` AND a stored GitHub PAT. Responses
    are cached in-process for 60s keyed by the full query to avoid GitHub
    rate-limit pressure during paging/searching. The PAT is never returned.
    """
    cfg = load_github_integration_config(workspace)
    pat = manager.get_credential(CredentialProvider.GIT_GITHUB)
    if cfg is None or not pat:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                "No GitHub repository is connected. Connect one in Settings → "
                "Integrations first.",
                ErrorCodes.CONFLICT,
            ),
        )

    # GitHub caps per_page at 100; clamp to a sane 1..100 window.
    per_page = max(1, min(per_page, 100))
    repo = cfg["repo"]

    cache_key = f"{repo}|{page}|{per_page}|{search}|{label}"
    cached = _issue_cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        issues, total = await list_issues(
            pat,
            repo,
            page=page,
            per_page=per_page,
            search=search,
            label=label,
        )
    except ValueError as e:
        # Stored repo metadata is malformed — surface as a conflict, not a 500.
        raise HTTPException(
            status_code=409,
            detail=api_error(str(e), ErrorCodes.CONFLICT),
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=401,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except InsufficientScopeError as e:
        raise HTTPException(
            status_code=403,
            detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
        )
    except GitHubConnectError as e:
        raise HTTPException(
            status_code=502,
            detail=api_error(str(e), ErrorCodes.EXECUTION_FAILED),
        )

    response = GitHubIssuesResponse(
        issues=[GitHubIssueItem(**issue) for issue in issues],
        total=total,
        page=page,
        per_page=per_page,
    )
    _issue_cache_set(cache_key, response)
    return response


def _require_connection(
    workspace: Workspace, manager: CredentialManager
) -> tuple[str, str]:
    """Return ``(repo, pat)`` for a connected workspace, or raise 409.

    Mirrors the not-connected guard used by ``get_issues``: both per-workspace
    repo metadata AND a stored PAT must be present.
    """
    cfg = load_github_integration_config(workspace)
    pat = manager.get_credential(CredentialProvider.GIT_GITHUB)
    if cfg is None or not pat:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                "No GitHub repository is connected. Connect one in Settings → "
                "Integrations first.",
                ErrorCodes.CONFLICT,
            ),
        )
    return cfg["repo"], pat


def _map_github_error(e: Exception) -> HTTPException:
    """Map a typed GitHub service error to an HTTPException (shared mapping)."""
    if isinstance(e, InvalidTokenError):
        return HTTPException(
            status_code=401, detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR)
        )
    if isinstance(e, InsufficientScopeError):
        return HTTPException(
            status_code=403, detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR)
        )
    return HTTPException(
        status_code=502, detail=api_error(str(e), ErrorCodes.EXECUTION_FAILED)
    )


@router.post("/import", response_model=ImportResponse)
@rate_limit_ai()
async def import_issues(
    request: Request,
    body: ImportRequest,
    workspace: Workspace = Depends(get_v2_workspace),
    manager: CredentialManager = Depends(get_credential_manager),
) -> ImportResponse:
    """Import selected GitHub issues as CodeFRAME tasks (issue #565).

    Each issue becomes a task (title + body, with a best-effort ``Labels:``
    footer) linked back to the issue via ``github_issue_number`` + ``external_url``.
    Issues already imported into this workspace are skipped (duplicate-import
    protection), keyed on the full issue URL so the same number in a different
    repo is still importable.

    The import is all-or-nothing on fetch: every selected issue is fetched and
    de-duplicated *before* any task is created, so a single stale/inaccessible
    issue fails the request cleanly without leaving a partial set of tasks
    behind (which would confuse a retry with phantom duplicates).
    """
    repo, pat = _require_connection(workspace, manager)

    skipped: list[int] = []
    to_create: list[tuple[int, dict]] = []
    seen_urls: set[str] = set()

    # Phase 1 — fetch + de-dupe everything first. Any fetch error aborts here,
    # before a single task has been created.
    for number in body.issue_numbers:
        try:
            issue = await get_issue(pat, repo, number)
        except ValueError as e:
            # Malformed saved repo slug (parse_repo) — surface as a recoverable
            # conflict like the browse endpoint, not a 500.
            raise HTTPException(
                status_code=409,
                detail=api_error(str(e), ErrorCodes.CONFLICT),
            )
        except NotAnIssueError as e:
            # A PR number slipped in (the browse UI filters PRs, so this only
            # happens with a malformed/manual payload). Reject the request.
            raise HTTPException(
                status_code=422,
                detail=api_error(str(e), ErrorCodes.VALIDATION_ERROR),
            )
        except IssueNotFoundError as e:
            # A stale/typo'd issue number — a client error, not a 502.
            raise HTTPException(
                status_code=404,
                detail=api_error(str(e), ErrorCodes.NOT_FOUND),
            )
        except GitHubConnectError as e:
            raise _map_github_error(e)

        url = issue["html_url"]
        # Skip both already-imported issues and in-payload duplicates (the same
        # number repeated in one request must not create two tasks).
        if url in seen_urls or tasks.get_by_external_url(workspace, url) is not None:
            skipped.append(number)
            continue
        seen_urls.add(url)
        to_create.append((number, issue))

    # Phase 2 — create the tasks. Each create commits independently, so an
    # unexpected mid-loop DB error (e.g. OperationalError on a locked DB) is
    # rolled back below to preserve the all-or-nothing contract. (The
    # URL-unique index additionally makes a retry idempotent.)
    created: list[ImportedTaskSummary] = []
    created_ids: list[str] = []
    try:
        for number, issue in to_create:
            description = issue["body"] or ""
            if issue["labels"]:
                footer = "**Labels:** " + ", ".join(issue["labels"])
                description = f"{description}\n\n{footer}" if description else footer

            try:
                task = tasks.create(
                    workspace,
                    title=issue["title"],
                    description=description,
                    github_issue_number=number,
                    external_url=issue["html_url"],
                )
            except sqlite3.IntegrityError:
                # A concurrent import (double-submit / second tab) created this
                # task between our de-dupe read and now. The unique index on
                # (workspace_id, external_url) makes that race a no-op: treat it
                # as an already-imported skip rather than a duplicate task.
                skipped.append(number)
                continue

            created_ids.append(task.id)
            created.append(
                ImportedTaskSummary(
                    task_id=task.id, issue_number=number, title=task.title
                )
            )
    except Exception:
        # Roll back the tasks created so far so a mid-create failure never leaves
        # a partial import behind.
        for task_id in created_ids:
            try:
                tasks.delete(workspace, task_id)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                logger.warning("Failed to roll back imported task %s", task_id)
        raise

    # Invalidate the browse cache so a re-open reflects current duplicate state.
    # Always — even a skipped-only import (issues created by another tab/process)
    # must drop the stale listing that still offers them as selectable.
    _issue_cache_invalidate(repo)

    return ImportResponse(
        created=created, skipped=skipped, total_created=len(created)
    )
