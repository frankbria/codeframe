"""V2 Pull Request router - delegates to git/github_integration module.

This module provides v2-style API endpoints for GitHub PR management.
Requires GITHUB_TOKEN and GITHUB_REPO environment variables.

Routes:
    GET  /api/v2/pr             - List pull requests
    GET  /api/v2/pr/{number}    - Get PR details
    POST /api/v2/pr             - Create a new PR
    POST /api/v2/pr/{number}/merge - Merge a PR
    POST /api/v2/pr/{number}/close - Close a PR without merging
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from codeframe.auth.api_keys import SCOPE_ADMIN
from codeframe.auth.dependencies import require_auth, require_scope
from codeframe.core.proof.models import ReqStatus
from codeframe.core.workspace import Workspace
from codeframe.lib.rate_limiter import rate_limit_standard
from codeframe.git.github_integration import GitHubIntegration, GitHubAPIError, PRDetails
from codeframe.ui.dependencies import get_v2_workspace
from codeframe.ui.response_models import api_error, ErrorCodes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/pr", tags=["pr-v2"])


# ============================================================================
# Request/Response Models
# ============================================================================


class PRResponse(BaseModel):
    """Response for a single pull request."""

    number: int
    url: str
    state: str
    title: str
    body: Optional[str]
    created_at: str
    merged_at: Optional[str]
    head_branch: str
    base_branch: str


class PRListResponse(BaseModel):
    """Response for PR list."""

    pull_requests: list[PRResponse]
    total: int


class CreatePRRequest(BaseModel):
    """Request for creating a pull request."""

    branch: str = Field(..., min_length=1, description="Head branch with changes")
    title: str = Field(..., min_length=1, description="PR title")
    body: str = Field("", description="PR description/body")
    base: str = Field("main", description="Target branch to merge into")


class MergePRRequest(BaseModel):
    """Request for merging a pull request."""

    method: str = Field("squash", description="Merge method: merge, squash, or rebase")
    override: bool = Field(
        False, description="Explicitly bypass the PROOF9 merge gate (audited)"
    )
    override_reason: Optional[str] = Field(
        None, description="Why the gate is being bypassed (required when override=true)"
    )


class MergeResponse(BaseModel):
    """Response for merge operation."""

    sha: Optional[str]
    merged: bool
    message: str


class CICheckResponse(BaseModel):
    """A single CI check run result."""

    name: str
    status: str
    conclusion: Optional[str]


class PRStatusResponse(BaseModel):
    """Live PR status: CI checks, review status, and merge state."""

    ci_checks: list[CICheckResponse]
    review_status: str   # "approved" | "changes_requested" | "pending"
    merge_state: str     # "open" | "merged" | "closed"
    pr_url: str
    pr_number: int


class GateBreakdownItem(BaseModel):
    """A single gate pass/fail entry in a proof snapshot."""

    gate: str
    status: str


class ProofSnapshotOut(BaseModel):
    """Proof snapshot at time of PR creation."""

    gates_passed: int
    gates_total: int
    gate_breakdown: list[GateBreakdownItem]


class MergeOverrideOut(BaseModel):
    """Audited PROOF9 merge-gate override record (#731)."""

    actor: str
    reason: str
    bypassed_count: int
    overridden_at: str


class PRHistoryItem(BaseModel):
    """A single merged PR with optional proof snapshot."""

    number: int
    title: str
    merged_at: str
    author: Optional[str]
    url: str
    proof_snapshot: Optional[ProofSnapshotOut]
    merge_override: Optional[MergeOverrideOut] = None


class PRFilesResponse(BaseModel):
    """Response for PR changed files."""

    files: list[str]


class PRHistoryResponse(BaseModel):
    """Response for PR history list."""

    pull_requests: list[PRHistoryItem]
    total: int


# ============================================================================
# Helper Functions
# ============================================================================


def _pr_to_response(pr: PRDetails) -> PRResponse:
    """Convert a PRDetails to a PRResponse."""
    return PRResponse(
        number=pr.number,
        url=pr.url,
        state=pr.state,
        title=pr.title,
        body=pr.body,
        created_at=pr.created_at.isoformat(),
        merged_at=pr.merged_at.isoformat() if pr.merged_at else None,
        head_branch=pr.head_branch,
        base_branch=pr.base_branch,
    )


def _get_github_client() -> GitHubIntegration:
    """Get a GitHub integration client.

    Returns:
        GitHubIntegration instance

    Raises:
        HTTPException: If GitHub token or repo not configured
    """
    try:
        return GitHubIntegration()
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=api_error(
                "GitHub not configured",
                ErrorCodes.INVALID_REQUEST,
                str(e),
            ),
        )


def _dispatch_pr_merged_webhook(workspace: Workspace, pr_number: int) -> None:
    """Best-effort outbound webhook for ``pr.merged`` (issue #560).

    Builds the canonical ``https://github.com/{owner}/{repo}/pull/{N}`` URL
    from the GitHub integration when available; sets ``pr_url`` to ``None``
    when the integration can't be constructed (e.g., ``GITHUB_REPO`` unset).
    The always-present ``pr_number`` field lets consumers branch without
    parsing a URL.
    """
    try:
        from codeframe.core.notifications_config import is_webhook_active
        from codeframe.notifications.webhook import (
            WebhookNotificationService,
            format_pr_payload,
        )

        url = is_webhook_active(workspace)
        if url is None:
            return

        # Canonical github.com URL when GITHUB_REPO is configured, ``None``
        # otherwise. The payload always carries ``pr_number`` so consumers
        # can branch on it without parsing the URL.
        try:
            gh = GitHubIntegration()
            pr_url: Optional[str] = f"https://github.com/{gh.repo}/pull/{pr_number}"
        except Exception:
            pr_url = None

        svc = WebhookNotificationService(webhook_url=url, timeout=5)
        svc.send_event_background(format_pr_payload(pr_number, pr_url))
    except Exception:
        logger.warning(
            "Failed to dispatch pr.merged webhook for PR #%s", pr_number, exc_info=True
        )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status", response_model=PRStatusResponse)
@rate_limit_standard()
async def get_pr_status(
    request: Request,
    pr_number: int = Query(..., description="PR number to poll"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRStatusResponse:
    """Get live PR status: CI checks, review status, and merge state.

    Polls the GitHub API for the given PR number and returns a snapshot
    of all three status dimensions. The frontend polls this every 30 s
    and stops when merge_state is merged or closed.

    Args:
        pr_number: PR number to inspect
        workspace: v2 Workspace (for context)

    Returns:
        PRStatusResponse with CI checks, review status, and merge state
    """
    # _get_github_client() raises HTTPException if GitHub isn't configured —
    # no client to close in that case, so call it before the try/finally.
    client = _get_github_client()
    try:
        # Single call to get PR state, URL, and head SHA.
        pr_raw = await client._make_request(
            "GET",
            f"/repos/{client.owner}/{client.repo_name}/pulls/{pr_number}",
        )

        # Validate payload shape: non-dict responses (e.g. a list) or a dict with
        # a non-dict "head" field would blow up before reaching the field checks.
        if not isinstance(pr_raw, dict):
            raise HTTPException(
                status_code=502,
                detail=api_error(
                    "Invalid GitHub response",
                    ErrorCodes.EXECUTION_FAILED,
                    "PR payload was not an object",
                ),
            )

        # Use safe access; raise 502 if required fields are absent rather than
        # letting a KeyError bubble into an unhandled 500.
        head = pr_raw.get("head")
        head_sha: str | None = head.get("sha") if isinstance(head, dict) else None
        pr_url: str | None = pr_raw.get("html_url")
        state: str | None = pr_raw.get("state")

        if not head_sha or not pr_url or not state:
            raise HTTPException(
                status_code=502,
                detail=api_error(
                    "Invalid GitHub response",
                    ErrorCodes.EXECUTION_FAILED,
                    "Missing required fields (head.sha / html_url / state) in PR payload",
                ),
            )

        merge_state: str = "merged" if pr_raw.get("merged_at") else state

        # Fetch CI checks and reviews in parallel (2 more GitHub API calls).
        ci_checks, review_status = await asyncio.gather(
            client.get_pr_ci_checks(pr_number, head_sha=head_sha),
            client.get_pr_review_status(pr_number),
        )

        return PRStatusResponse(
            ci_checks=[
                CICheckResponse(name=c.name, status=c.status, conclusion=c.conclusion)
                for c in ci_checks
            ],
            review_status=review_status,
            merge_state=merge_state,
            pr_url=pr_url,
            pr_number=pr_number,
        )

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PR #{pr_number} status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get PR status", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.get("", response_model=PRListResponse)
@rate_limit_standard()
async def list_pull_requests(
    request: Request,
    state: str = Query("open", description="Filter by state: open, closed, all"),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRListResponse:
    """List pull requests for the repository.

    Args:
        state: Filter by PR state
        workspace: v2 Workspace (for context)

    Returns:
        List of pull requests
    """
    client = _get_github_client()
    try:
        prs = await client.list_pull_requests(state=state)

        return PRListResponse(
            pull_requests=[_pr_to_response(pr) for pr in prs],
            total=len(prs),
        )

    except GitHubAPIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list PRs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to list PRs", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.get("/history", response_model=PRHistoryResponse)
@rate_limit_standard()
async def get_pr_history(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRHistoryResponse:
    """List recently merged PRs with proof snapshots.

    Returns merged PRs sorted by merged_at descending, each with an
    optional proof snapshot showing gate pass/fail at PR creation time.

    Args:
        limit: Maximum number of PRs to return (1-50, default 10)
        workspace: v2 Workspace

    Returns:
        PRHistoryResponse with merged PRs and proof snapshots
    """
    from codeframe.core.proof.ledger import get_pr_merge_override, get_pr_proof_snapshot

    client = _get_github_client()
    try:
        prs = await client.list_pull_requests(state="closed")

        # Filter to only merged PRs and sort newest first.
        merged = [pr for pr in prs if pr.merged_at is not None]
        merged.sort(key=lambda pr: pr.merged_at, reverse=True)
        merged = merged[:limit]

        items: list[PRHistoryItem] = []
        for pr in merged:
            snapshot = get_pr_proof_snapshot(workspace, pr.number)
            proof_snapshot = None
            if snapshot:
                proof_snapshot = ProofSnapshotOut(
                    gates_passed=snapshot["gates_passed"],
                    gates_total=snapshot["gates_total"],
                    gate_breakdown=[
                        GateBreakdownItem(**g) for g in snapshot["gate_breakdown"]
                    ],
                )
            override = get_pr_merge_override(workspace, pr.number)
            items.append(
                PRHistoryItem(
                    number=pr.number,
                    title=pr.title,
                    merged_at=pr.merged_at.isoformat(),
                    author=pr.author,
                    url=pr.url,
                    proof_snapshot=proof_snapshot,
                    merge_override=MergeOverrideOut(
                        actor=override["actor"],
                        reason=override["reason"],
                        bypassed_count=len(override["bypassed"]),
                        overridden_at=override["overridden_at"],
                    ) if override else None,
                )
            )

        return PRHistoryResponse(pull_requests=items, total=len(items))

    except GitHubAPIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PR history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get PR history", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.get("/{pr_number}/files", response_model=PRFilesResponse)
@rate_limit_standard()
async def get_pr_files(
    request: Request,
    pr_number: int,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRFilesResponse:
    """Get the list of files changed in a pull request.

    Args:
        pr_number: PR number
        workspace: v2 Workspace (for context)

    Returns:
        List of changed filenames
    """
    client = _get_github_client()
    try:
        files = await client.get_pr_files(pr_number)
        return PRFilesResponse(files=files)
    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get files for PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get PR files", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.get("/{pr_number}", response_model=PRResponse)
@rate_limit_standard()
async def get_pull_request(
    request: Request,
    pr_number: int,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRResponse:
    """Get details of a specific pull request.

    Args:
        pr_number: PR number
        workspace: v2 Workspace (for context)

    Returns:
        PR details
    """
    client = _get_github_client()
    try:
        pr = await client.get_pull_request(pr_number)

        return _pr_to_response(pr)

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to get PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.post("", response_model=PRResponse, status_code=201)
@rate_limit_standard()
async def create_pull_request(
    request: Request,
    body: CreatePRRequest,
    workspace: Workspace = Depends(get_v2_workspace),
) -> PRResponse:
    """Create a new pull request.

    Args:
        request: HTTP request for rate limiting
        body: PR creation request
        workspace: v2 Workspace (for context)

    Returns:
        Created PR details
    """
    client = _get_github_client()
    try:
        pr = await client.create_pull_request(
            branch=body.branch,
            title=body.title,
            body=body.body,
            base=body.base,
        )

        # Capture proof snapshot at PR creation time.
        try:
            from codeframe.core.proof.ledger import (
                init_proof_tables,
                list_requirements,
                save_pr_proof_snapshot,
            )

            init_proof_tables(workspace)
            reqs = list_requirements(workspace)

            gates_total = 0
            gates_passed = 0
            gate_breakdown: list[dict] = []
            for req in reqs:
                for ob in req.obligations:
                    gates_total += 1
                    passed = ob.status == "satisfied"
                    if passed:
                        gates_passed += 1
                    gate_breakdown.append({
                        "gate": ob.gate.value,
                        "status": ob.status,
                    })

            save_pr_proof_snapshot(
                workspace,
                pr_number=pr.number,
                gates_passed=gates_passed,
                gates_total=gates_total,
                gate_breakdown=gate_breakdown,
            )
        except Exception as snap_err:
            logger.warning(f"Failed to save proof snapshot for PR #{pr.number}: {snap_err}")

        return _pr_to_response(pr)

    except GitHubAPIError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create PR: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to create PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.post(
    "/{pr_number}/merge",
    response_model=MergeResponse,
    dependencies=[Depends(require_scope(SCOPE_ADMIN))],  # merging to the repo is admin-only (#717)
)
@rate_limit_standard()
async def merge_pull_request(
    request: Request,
    pr_number: int,
    body: MergePRRequest = None,
    workspace: Workspace = Depends(get_v2_workspace),
    auth: dict = Depends(require_auth),
) -> MergeResponse:
    """Merge a pull request.

    The PROOF9 merge gate (#731) runs first: open (non-waived) requirements
    block the merge unless the caller sets override=true with a reason, which
    is persisted as an audit record.

    Args:
        request: HTTP request for rate limiting
        pr_number: PR number to merge
        body: Merge options
        workspace: v2 Workspace (for context)
        auth: Authenticated principal (override audit actor)

    Returns:
        Merge result
    """
    method = body.method if body else "squash"
    override = bool(body and body.override)
    override_reason = (body.override_reason or "").strip() if body else ""

    if override and not override_reason:
        raise HTTPException(
            status_code=422,
            detail=api_error(
                "override_reason is required when override=true",
                ErrorCodes.VALIDATION_ERROR,
                "Provide a reason for bypassing the PROOF9 merge gate",
            ),
        )

    # PROOF9 merge gate: a ledger failure blocks the merge (explicit 500)
    # rather than silently allowing an ungated merge.
    from codeframe.core.proof import ledger as proof_ledger

    try:
        open_reqs = proof_ledger.list_requirements(workspace, status=ReqStatus.OPEN)
    except Exception as e:
        logger.error(f"PROOF9 gate check failed for PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error(
                "PROOF9 gate check failed — merge blocked",
                ErrorCodes.EXECUTION_FAILED,
                str(e),
            ),
        )

    bypassed: list[dict] = []
    if open_reqs:
        bypassed = [{"id": r.id, "title": r.title} for r in open_reqs]
        if not override:
            summary = ", ".join(f"{b['id']}: {b['title']}" for b in bypassed[:10])
            raise HTTPException(
                status_code=409,
                detail=api_error(
                    f"PROOF9 merge gate: {len(open_reqs)} open requirement(s) block this merge",
                    ErrorCodes.INVALID_STATE,
                    f"{summary}. Satisfy or waive them, or pass override=true with a reason.",
                ),
            )

    client = _get_github_client()
    try:
        result = await client.merge_pull_request(pr_number, method=method)

        if result.merged and bypassed:
            # Persist the audited override only after the merge actually
            # happened — a failed merge must not leave a bypass record. If the
            # audit write itself fails, the merge is already done: log loudly
            # but report the merge result truthfully.
            try:
                # "local-admin" only when auth is explicitly disabled; an
                # authenticated principal without a user_id stays "unknown".
                actor = auth.get("user_id") or (
                    "local-admin" if auth.get("type") == "disabled" else "unknown"
                )
                proof_ledger.save_merge_override(
                    workspace,
                    pr_number=pr_number,
                    actor=actor,
                    reason=override_reason,
                    bypassed=bypassed,
                )
            except Exception as audit_err:
                logger.error(
                    f"Merge of PR #{pr_number} succeeded but override audit write failed: {audit_err}",
                    exc_info=True,
                )

        # Outbound webhook for pr.merged (issue #560) — only on successful
        # merge, never raises into the caller.
        if result.merged:
            _dispatch_pr_merged_webhook(workspace, pr_number)

        return MergeResponse(
            sha=result.sha,
            merged=result.merged,
            message=result.message,
        )

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        if e.status_code == 405:
            raise HTTPException(
                status_code=400,
                detail=api_error("Cannot merge", ErrorCodes.INVALID_STATE, e.message),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to merge PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to merge PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()


@router.post("/{pr_number}/close")
@rate_limit_standard()
async def close_pull_request(
    request: Request,
    pr_number: int,
    workspace: Workspace = Depends(get_v2_workspace),
) -> dict:
    """Close a pull request without merging.

    Args:
        pr_number: PR number to close
        workspace: v2 Workspace (for context)

    Returns:
        Close confirmation
    """
    client = _get_github_client()
    try:
        closed = await client.close_pull_request(pr_number)

        return {
            "success": closed,
            "message": f"PR #{pr_number} closed" if closed else f"Failed to close PR #{pr_number}",
        }

    except GitHubAPIError as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail=api_error("PR not found", ErrorCodes.NOT_FOUND, f"No PR #{pr_number}"),
            )
        raise HTTPException(
            status_code=e.status_code,
            detail=api_error("GitHub API error", ErrorCodes.EXECUTION_FAILED, e.message),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close PR #{pr_number}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=api_error("Failed to close PR", ErrorCodes.EXECUTION_FAILED, str(e)),
        )
    finally:
        await client.close()
