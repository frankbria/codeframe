"""GitHub API Integration for CodeFRAME.

Handles GitHub API operations for Pull Request management.
Part of Sprint 11 - GitHub PR Integration.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import logging

import httpx

if TYPE_CHECKING:
    from codeframe.core.credentials import CredentialManager

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Exception raised when GitHub API returns an error."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"GitHub API Error ({status_code}): {message}")


@dataclass
class CICheck:
    """A single CI check run result."""

    name: str
    status: str  # "queued" | "in_progress" | "completed"
    conclusion: Optional[str]  # "success" | "failure" | "neutral" | "cancelled" | etc.


@dataclass
class PRDetails:
    """Pull Request details from GitHub API."""

    number: int
    url: str
    state: str
    title: str
    body: Optional[str]
    created_at: datetime
    merged_at: Optional[datetime]
    head_branch: str
    base_branch: str
    author: Optional[str] = None


@dataclass
class MergeResult:
    """Result of a PR merge operation."""

    sha: Optional[str]
    merged: bool
    message: str


class GitHubIntegration:
    """GitHub API client for PR operations.

    Provides methods for creating, listing, merging, and closing
    pull requests via the GitHub REST API.
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: Optional[str] = None,
        repo: Optional[str] = None,
        credential_manager: Optional["CredentialManager"] = None,
    ):
        """Initialize GitHub integration.

        Args:
            token: GitHub Personal Access Token with repo scope
            repo: Repository in format "owner/repo"
            credential_manager: Optional credential manager for secure token retrieval

        Raises:
            ValueError: If repo format is invalid or no token available
        """
        # Try to get token from multiple sources in order:
        # 1. Direct token parameter
        # 2. CredentialManager (if provided)
        # 3. Environment variable (handled by CredentialManager)
        resolved_token = token

        if not resolved_token and credential_manager:
            from codeframe.core.credentials import CredentialProvider
            resolved_token = credential_manager.get_credential(CredentialProvider.GIT_GITHUB)

        if not resolved_token:
            import os
            resolved_token = os.getenv("GITHUB_TOKEN")

        if not resolved_token:
            raise ValueError(
                "GITHUB_TOKEN not set. "
                "Set the environment variable, pass token parameter, "
                "or configure via 'codeframe auth setup --provider github'."
            )

        if not repo:
            import os
            repo = os.getenv("GITHUB_REPO")

        if not repo:
            raise ValueError(
                "Repository not specified. "
                "Pass repo parameter or set GITHUB_REPO environment variable."
            )

        parts = repo.split("/", 1)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(
                f"Invalid repo format: '{repo}'. Expected 'owner/repo'"
            )

        self.token = resolved_token
        self.repo = repo
        self.owner, self.repo_name = parts[0].strip(), parts[1].strip()

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {resolved_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Make an authenticated request to GitHub API.

        Args:
            method: HTTP method (GET, POST, PATCH, PUT, DELETE)
            endpoint: API endpoint path
            json_data: Optional JSON body data

        Returns:
            Parsed JSON response

        Raises:
            GitHubAPIError: If API returns an error status
        """
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json_data,
            )

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    message = error_data.get("message", response.text)
                    details = error_data.get("errors")
                except Exception:
                    message = response.text
                    details = None

                raise GitHubAPIError(
                    status_code=response.status_code,
                    message=message,
                    details={"errors": details} if details else None,
                )

            # Handle empty responses (204 No Content)
            if response.status_code == 204:
                return None

            return response.json()

        except httpx.TimeoutException as e:
            logger.error(f"GitHub API timeout: {e}")
            raise GitHubAPIError(
                status_code=408,
                message="Request timed out",
            )
        except httpx.RequestError as e:
            logger.error(f"GitHub API request error: {e}")
            raise GitHubAPIError(
                status_code=500,
                message=f"Request failed: {str(e)}",
            )

    def _parse_pr_response(self, data: Dict[str, Any]) -> PRDetails:
        """Parse GitHub PR response into PRDetails object.

        Args:
            data: Raw GitHub API response

        Returns:
            Parsed PRDetails object
        """
        created_at = datetime.fromisoformat(
            data["created_at"].replace("Z", "+00:00")
        )
        merged_at = None
        if data.get("merged_at"):
            merged_at = datetime.fromisoformat(
                data["merged_at"].replace("Z", "+00:00")
            )

        user = data.get("user")
        author = user.get("login") if isinstance(user, dict) else None

        return PRDetails(
            number=data["number"],
            url=data["html_url"],
            state=data["state"],
            title=data["title"],
            body=data.get("body"),
            created_at=created_at,
            merged_at=merged_at,
            head_branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            author=author,
        )

    async def create_pull_request(
        self,
        branch: str,
        title: str,
        body: str,
        base: str = "main",
    ) -> PRDetails:
        """Create a new pull request.

        Args:
            branch: Head branch with changes
            title: PR title
            body: PR description
            base: Base branch to merge into (default: main)

        Returns:
            PRDetails with the created PR info

        Raises:
            GitHubAPIError: If PR creation fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls"

        data = await self._make_request(
            method="POST",
            endpoint=endpoint,
            json_data={
                "title": title,
                "body": body,
                "head": branch,
                "base": base,
            },
        )

        logger.info(f"Created PR #{data['number']}: {title}")
        return self._parse_pr_response(data)

    async def get_pull_request(self, pr_number: int) -> PRDetails:
        """Get pull request details.

        Args:
            pr_number: PR number

        Returns:
            PRDetails with the PR info

        Raises:
            GitHubAPIError: If PR not found or API error
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"

        data = await self._make_request(
            method="GET",
            endpoint=endpoint,
        )

        return self._parse_pr_response(data)

    async def list_pull_requests(
        self,
        state: str = "open",
    ) -> List[PRDetails]:
        """List pull requests for the repository.

        Args:
            state: Filter by state (open, closed, all)

        Returns:
            List of PRDetails

        Raises:
            GitHubAPIError: If API error occurs
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls"

        data = await self._make_request(
            method="GET",
            endpoint=f"{endpoint}?state={state}",
        )

        return [self._parse_pr_response(pr) for pr in data]

    async def merge_pull_request(
        self,
        pr_number: int,
        method: str = "squash",
    ) -> MergeResult:
        """Merge a pull request.

        Args:
            pr_number: PR number to merge
            method: Merge method (merge, squash, rebase)

        Returns:
            MergeResult with merge outcome

        Raises:
            GitHubAPIError: If merge fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/merge"

        data = await self._make_request(
            method="PUT",
            endpoint=endpoint,
            json_data={
                "merge_method": method,
            },
        )

        logger.info(f"Merged PR #{pr_number} with method '{method}'")
        return MergeResult(
            sha=data.get("sha"),
            merged=data.get("merged", False),
            message=data.get("message", ""),
        )

    async def close_pull_request(self, pr_number: int) -> bool:
        """Close a pull request without merging.

        Args:
            pr_number: PR number to close

        Returns:
            True if successfully closed

        Raises:
            GitHubAPIError: If close fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"

        data = await self._make_request(
            method="PATCH",
            endpoint=endpoint,
            json_data={
                "state": "closed",
            },
        )

        logger.info(f"Closed PR #{pr_number}")
        return data.get("state") == "closed"

    async def get_pr_ci_checks(
        self,
        pr_number: int,
        head_sha: Optional[str] = None,
    ) -> List[CICheck]:
        """Get CI check runs for a pull request.

        Args:
            pr_number: PR number
            head_sha: Head commit SHA (fetched from the PR if not provided)

        Returns:
            List of CICheck results
        """
        if head_sha is None:
            pr_data = await self._make_request(
                "GET",
                f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}",
            )
            head_sha = pr_data["head"]["sha"]

        data = await self._make_request(
            "GET",
            f"/repos/{self.owner}/{self.repo_name}/commits/{head_sha}/check-runs",
        )
        check_runs = data.get("check_runs", []) if isinstance(data, dict) else []
        normalized: list[CICheck] = []
        for run in check_runs:
            if not isinstance(run, dict):
                continue
            name = run.get("name")
            status = run.get("status")
            if not name or not status:
                logger.warning("Skipping malformed check-run entry: %s", run)
                continue
            normalized.append(
                CICheck(name=name, status=status, conclusion=run.get("conclusion"))
            )
        return normalized

    async def get_pr_review_status(self, pr_number: int) -> str:
        """Get the aggregate review status for a pull request.

        Returns "changes_requested" if any reviewer requested changes,
        "approved" if any reviewer approved (and none requested changes),
        or "pending" if there are no actionable reviews.

        Args:
            pr_number: PR number

        Returns:
            "approved" | "changes_requested" | "pending"
        """
        reviews = await self._make_request(
            "GET",
            f"/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}/reviews",
        )

        # Guard against unexpected response shapes.
        if not isinstance(reviews, list):
            reviews = []

        # Only count actionable states — exclude DISMISSED, COMMENTED, and non-dicts.
        ACTIONABLE = {"APPROVED", "CHANGES_REQUESTED"}

        # Collapse per-reviewer: keep only each reviewer's latest actionable review.
        # A reviewer who requested changes and later approved should be counted as
        # approved, not as both.
        latest_per_reviewer: dict[str, dict] = {}
        for r in reviews:
            if not isinstance(r, dict):
                continue
            if r.get("state") not in ACTIONABLE:
                continue
            reviewer = r.get("user", {}).get("login") if isinstance(r.get("user"), dict) else None
            if reviewer is None:
                reviewer = str(r.get("id", id(r)))
            existing = latest_per_reviewer.get(reviewer)
            if existing is None or (r.get("submitted_at") or "") >= (existing.get("submitted_at") or ""):
                latest_per_reviewer[reviewer] = r

        active = list(latest_per_reviewer.values())

        has_changes_requested = any(r.get("state") == "CHANGES_REQUESTED" for r in active)
        has_approved = any(r.get("state") == "APPROVED" for r in active)

        if has_changes_requested:
            return "changes_requested"
        if has_approved:
            return "approved"
        return "pending"

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
