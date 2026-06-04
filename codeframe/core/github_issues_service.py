"""GitHub open-issues listing service (issue #564).

Headless service used by the Integrations issues endpoint to fetch a connected
repository's **open** issues for the import browser UI. Builds on the connection
established in #563: the PAT comes from the machine-wide ``CredentialManager``
and the ``owner/repo`` from per-workspace ``.codeframe/github_integration.json``
— this module only performs the GitHub API call given those values.

No FastAPI / HTTP-framework imports (architecture rule #1 — core is headless).
Reuses the shared helpers and typed errors from ``github_connect_service``.

Search note: GitHub's REST *list* endpoint (``/repos/{o}/{r}/issues``) does not
support free-text search, so when a ``search`` term is supplied this routes to
``/search/issues`` with a ``repo:`` + ``is:issue`` + ``is:open`` qualifier and
reads the authoritative ``total_count``. The plain list endpoint also returns
pull requests, which are filtered out here.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, TypedDict

import httpx

from codeframe.core.github_connect_service import (
    GITHUB_API_BASE,
    GitHubConnectError,
    InsufficientScopeError,
    InvalidTokenError,
    _headers,
    parse_repo,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0

# Parse the ``page=N`` query param out of a Link header's rel="last" URL.
_LAST_PAGE_RE = re.compile(r'[?&]page=(\d+)[^>]*>;\s*rel="last"')


class GitHubIssue(TypedDict):
    number: int
    title: str
    labels: list[str]
    assignee: Optional[str]
    created_at: str
    html_url: str


def _simplify(raw: dict) -> GitHubIssue:
    labels_raw = raw.get("labels") or []
    labels = [
        (lbl.get("name") if isinstance(lbl, dict) else str(lbl))
        for lbl in labels_raw
    ]
    labels = [n for n in labels if n]
    assignee_raw = raw.get("assignee") or None
    assignee = assignee_raw.get("login") if isinstance(assignee_raw, dict) else None
    return {
        "number": int(raw.get("number", 0)),
        "title": str(raw.get("title") or ""),
        "labels": labels,
        "assignee": assignee,
        "created_at": str(raw.get("created_at") or ""),
        "html_url": str(raw.get("html_url") or ""),
    }


def _raise_for_status(status_code: int, *, context: str) -> None:
    """Map a GitHub HTTP status to a typed error. 2xx/410 are handled by callers."""
    if status_code == 401:
        raise InvalidTokenError("Invalid GitHub token.")
    if status_code == 403:
        raise InsufficientScopeError(
            "Token cannot read issues for this repository "
            "(missing issues:read scope)."
        )
    if status_code >= 400:
        raise GitHubConnectError(
            f"GitHub {context} returned status {status_code}."
        )


def _total_from_link_header(link: Optional[str], items_len: int, per_page: int) -> int:
    """Estimate total issue count from the ``Link`` header's rel="last" page.

    GitHub does not return an exact count on the list endpoint; the last-page
    number times ``per_page`` is the standard upper-bound estimate used for
    pagination controls. Falls back to ``items_len`` when there is no next page.
    """
    if link:
        match = _LAST_PAGE_RE.search(link)
        if match:
            return int(match.group(1)) * per_page
    return items_len


async def list_issues(
    pat: str,
    repo: str,
    *,
    page: int = 1,
    per_page: int = 25,
    search: str = "",
    label: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> tuple[list[GitHubIssue], int]:
    """List **open** issues for ``repo``, optionally filtered by search/label.

    Args:
        pat: GitHub Personal Access Token.
        repo: Repository in ``owner/repo`` format.
        page: 1-indexed page number.
        per_page: Page size (caller should clamp to GitHub's 1..100 range).
        search: Free-text title/body search (routes to the search API).
        label: Single label name to filter by.
        client: Optional httpx client (injected by tests). When ``None`` a
            short-lived client is created and closed internally.

    Returns:
        ``(issues, total)`` where ``issues`` is a list of simplified open issues
        (pull requests excluded) and ``total`` is the best-available count for
        pagination.

    Raises:
        ValueError: if ``repo`` is not a valid ``owner/repo`` string.
        InvalidTokenError: GitHub returned 401.
        InsufficientScopeError: the token cannot read issues (403).
        GitHubConnectError: any other non-success response or network error.
    """
    owner, name = parse_repo(repo)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        headers = _headers(pat)
        if search.strip():
            return await _search_issues(
                client, headers, owner, name, page, per_page, search, label
            )
        return await _list_issues(
            client, headers, owner, name, page, per_page, label
        )
    finally:
        if own_client:
            await client.aclose()


async def _list_issues(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    owner: str,
    name: str,
    page: int,
    per_page: int,
    label: str,
) -> tuple[list[GitHubIssue], int]:
    params: dict[str, object] = {
        "state": "open",
        "page": page,
        "per_page": per_page,
    }
    if label.strip():
        params["labels"] = label.strip()
    try:
        resp = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{name}/issues",
            params=params,
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.warning("GitHub issues list failed: %s", type(exc).__name__)
        raise GitHubConnectError("Could not reach GitHub. Try again later.")

    # 410 Gone == issues disabled on the repo: nothing to import, not an error.
    if resp.status_code == 410:
        return [], 0
    _raise_for_status(resp.status_code, context="issues list")

    raw_items = resp.json()
    if not isinstance(raw_items, list):
        raw_items = []
    # The /issues endpoint includes pull requests — drop them.
    issues = [_simplify(it) for it in raw_items if "pull_request" not in it]
    total = _total_from_link_header(resp.headers.get("Link"), len(issues), per_page)
    return issues, total


class GitHubIssueDetail(TypedDict):
    number: int
    title: str
    body: str
    labels: list[str]
    html_url: str


async def get_issue(
    pat: str,
    repo: str,
    number: int,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> GitHubIssueDetail:
    """Fetch a single issue's details for import (issue #565).

    Unlike the list endpoint, this returns the issue ``body`` so the importer
    can populate the task description.

    Args:
        pat: GitHub Personal Access Token.
        repo: Repository in ``owner/repo`` format.
        number: Issue number to fetch.
        client: Optional httpx client (injected by tests). When ``None`` a
            short-lived client is created and closed internally.

    Returns:
        ``{number, title, body, labels, html_url}`` — ``body`` is normalized to
        ``""`` when GitHub returns null.

    Raises:
        ValueError: if ``repo`` is not a valid ``owner/repo`` string.
        InvalidTokenError: GitHub returned 401.
        InsufficientScopeError: the token cannot read issues (403).
        GitHubConnectError: any other non-success response or network error.
    """
    owner, name = parse_repo(repo)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        try:
            resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{name}/issues/{number}",
                headers=_headers(pat),
            )
        except httpx.HTTPError as exc:
            logger.warning("GitHub get issue failed: %s", type(exc).__name__)
            raise GitHubConnectError("Could not reach GitHub. Try again later.")

        _raise_for_status(resp.status_code, context="get issue")

        raw = resp.json()
        if not isinstance(raw, dict):
            raw = {}
        labels_raw = raw.get("labels") or []
        labels = [
            (lbl.get("name") if isinstance(lbl, dict) else str(lbl))
            for lbl in labels_raw
        ]
        labels = [n for n in labels if n]
        return {
            "number": int(raw.get("number", number)),
            "title": str(raw.get("title") or ""),
            "body": str(raw.get("body") or ""),
            "labels": labels,
            "html_url": str(raw.get("html_url") or ""),
        }
    finally:
        if own_client:
            await client.aclose()


async def close_issue(
    pat: str,
    repo: str,
    number: int,
    *,
    comment: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Close a GitHub issue, optionally posting a comment first (issue #565).

    Args:
        pat: GitHub Personal Access Token.
        repo: Repository in ``owner/repo`` format.
        number: Issue number to close.
        comment: Optional comment body to post before closing.
        client: Optional httpx client (injected by tests). When ``None`` a
            short-lived client is created and closed internally.

    Returns:
        ``True`` when the issue was closed.

    Raises:
        ValueError: if ``repo`` is not a valid ``owner/repo`` string.
        InvalidTokenError: GitHub returned 401.
        InsufficientScopeError: the token cannot write issues (403).
        GitHubConnectError: any other non-success response or network error.
    """
    owner, name = parse_repo(repo)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        headers = _headers(pat)
        base = f"{GITHUB_API_BASE}/repos/{owner}/{name}/issues/{number}"

        if comment:
            try:
                cresp = await client.post(
                    f"{base}/comments", json={"body": comment}, headers=headers
                )
            except httpx.HTTPError as exc:
                logger.warning("GitHub issue comment failed: %s", type(exc).__name__)
                raise GitHubConnectError("Could not reach GitHub. Try again later.")
            _raise_for_status(cresp.status_code, context="issue comment")

        try:
            resp = await client.patch(
                base, json={"state": "closed"}, headers=headers
            )
        except httpx.HTTPError as exc:
            logger.warning("GitHub close issue failed: %s", type(exc).__name__)
            raise GitHubConnectError("Could not reach GitHub. Try again later.")

        _raise_for_status(resp.status_code, context="close issue")
        return True
    finally:
        if own_client:
            await client.aclose()


async def _search_issues(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    owner: str,
    name: str,
    page: int,
    per_page: int,
    search: str,
    label: str,
) -> tuple[list[GitHubIssue], int]:
    qualifiers = [
        search.strip(),
        f"repo:{owner}/{name}",
        "is:issue",
        "is:open",
    ]
    if label.strip():
        qualifiers.append(f'label:"{label.strip()}"')
    q = " ".join(qualifiers)
    try:
        resp = await client.get(
            f"{GITHUB_API_BASE}/search/issues",
            params={"q": q, "page": page, "per_page": per_page},
            headers=headers,
        )
    except httpx.HTTPError as exc:
        logger.warning("GitHub issues search failed: %s", type(exc).__name__)
        raise GitHubConnectError("Could not reach GitHub. Try again later.")

    _raise_for_status(resp.status_code, context="issues search")

    data = resp.json()
    if not isinstance(data, dict):
        data = {}
    raw_items = data.get("items") or []
    # The search API can still surface PRs if the qualifier is loosened; guard.
    issues = [_simplify(it) for it in raw_items if "pull_request" not in it]
    total = int(data.get("total_count", len(issues)))
    return issues, total
