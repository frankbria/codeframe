"""GitHub repository connection validation (issue #563).

Headless service used by the Integrations settings endpoints to validate a
Personal Access Token (PAT) against a target ``owner/repo`` before storing the
credential. Verifies that:

1. The token authenticates (not 401).
2. The repository exists and is visible to the token (not 404).
3. The token can read the repository's issues (not 403) — issues read is the
   prerequisite for the later import feature.

No FastAPI / HTTP-framework imports (architecture rule #1 — core is headless).
Uses ``httpx.AsyncClient`` consistent with ``codeframe/git/github_integration.py``.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
_TIMEOUT = 15.0


class GitHubConnectError(Exception):
    """Base class for GitHub connection validation failures."""


class InvalidTokenError(GitHubConnectError):
    """The PAT was rejected by GitHub (401)."""


class RepoNotFoundError(GitHubConnectError):
    """The repository does not exist or is not visible to the token (404)."""


class InsufficientScopeError(GitHubConnectError):
    """The token cannot read the repository's issues (403)."""


def parse_repo(repo: str) -> tuple[str, str]:
    """Parse and validate an ``owner/repo`` string.

    Tolerates surrounding/inner whitespace (``" acme / app "`` -> ``("acme",
    "app")``) but requires exactly one slash with non-empty owner and name.

    Raises:
        ValueError: if the format is not a valid ``owner/repo``.
    """
    if not repo or "/" not in repo:
        raise ValueError(f"Invalid repository format: {repo!r}. Expected 'owner/repo'.")
    # Reject pasted URLs (e.g. "https://github.com/acme/app" or "github.com/acme")
    # which would otherwise parse to a bogus owner.
    if "://" in repo or repo.strip().lower().startswith("http"):
        raise ValueError(
            f"Invalid repository format: {repo!r}. Expected 'owner/repo', not a URL."
        )
    parts = repo.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repository format: {repo!r}. Expected 'owner/repo'.")
    owner, name = parts[0].strip(), parts[1].strip()
    if not owner or not name:
        raise ValueError(f"Invalid repository format: {repo!r}. Expected 'owner/repo'.")
    # GitHub owners (users/orgs) cannot contain dots — a dotted owner means the
    # user pasted a host like "github.com/acme". Repo names MAY contain dots.
    if "." in owner:
        raise ValueError(
            f"Invalid repository format: {repo!r}. "
            "Expected 'owner/repo' (did you paste a URL?)."
        )
    return owner, name


def _headers(pat: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "codeframe-integration-connect",
    }


async def validate_connection(
    pat: str,
    repo: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, str]:
    """Validate a PAT against a target repository and verify issues-read access.

    Args:
        pat: GitHub Personal Access Token.
        repo: Repository in ``owner/repo`` format.
        client: Optional httpx client (injected by tests). When ``None`` a
            short-lived client is created and closed internally.

    Returns:
        ``{"repo_full_name", "owner_login", "owner_avatar_url"}`` on success.

    Raises:
        ValueError: if ``repo`` is not a valid ``owner/repo`` string.
        InvalidTokenError: GitHub returned 401.
        RepoNotFoundError: GitHub returned 404 for the repo.
        InsufficientScopeError: the token cannot read issues (403).
        GitHubConnectError: any other non-success response or network error.
    """
    owner, name = parse_repo(repo)

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        headers = _headers(pat)
        try:
            repo_resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{name}", headers=headers
            )
        except httpx.HTTPError as exc:
            # Log only the exception class — an httpx error's str() can embed the
            # request (URL/headers, hence the PAT) depending on version/config.
            logger.warning("GitHub repo lookup failed: %s", type(exc).__name__)
            raise GitHubConnectError("Could not reach GitHub. Try again later.")

        if repo_resp.status_code == 401:
            raise InvalidTokenError("Invalid GitHub token.")
        if repo_resp.status_code == 404:
            raise RepoNotFoundError(f"Repository '{owner}/{name}' not found.")
        if repo_resp.status_code == 403:
            # Repo-level 403 means the token can't even see the repo metadata.
            raise InsufficientScopeError(
                "Token lacks access to this repository."
            )
        if repo_resp.status_code >= 400:
            raise GitHubConnectError(
                f"GitHub returned status {repo_resp.status_code}."
            )

        repo_data = repo_resp.json()
        owner_data = repo_data.get("owner") or {}
        owner_login = owner_data.get("login") or owner
        owner_avatar_url = owner_data.get("avatar_url") or ""
        repo_full_name = repo_data.get("full_name") or f"{owner}/{name}"

        # Verify issues-read access — the prerequisite for import.
        try:
            issues_resp = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{name}/issues",
                params={"per_page": 1},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            logger.warning("GitHub issues check failed: %s", type(exc).__name__)
            raise GitHubConnectError("Could not reach GitHub. Try again later.")

        # 410 Gone == issues are disabled on the repo. The connection is still
        # valid; there is simply nothing to import. Anything else 4xx (notably
        # 403) means the token cannot read issues.
        if issues_resp.status_code == 403:
            raise InsufficientScopeError(
                "Token cannot read issues for this repository "
                "(missing issues:read scope)."
            )
        if issues_resp.status_code >= 400 and issues_resp.status_code != 410:
            raise GitHubConnectError(
                f"GitHub issues check returned status {issues_resp.status_code}."
            )

        return {
            "repo_full_name": repo_full_name,
            "owner_login": owner_login,
            "owner_avatar_url": owner_avatar_url,
        }
    finally:
        if own_client:
            await client.aclose()
