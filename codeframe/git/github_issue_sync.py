"""GitHub issue state synchronization for reconciliation.

Provides synchronous GitHub API calls (not async) for use in the
reconciliation background thread. Separate from github_integration.py
which is async and PR-focused.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def get_issue_state(token: str, repo: str, issue_number: int) -> str:
    """Fetch a GitHub issue's state (synchronous).

    Args:
        token: GitHub API token
        repo: Repository in "owner/repo" format
        issue_number: Issue number

    Returns:
        Issue state string ("open" or "closed")

    Raises:
        httpx.RequestError: On network failure
        httpx.HTTPStatusError: On non-2xx response
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{issue_number}"
    response = httpx.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["state"]


def build_github_task_checker(token: str, repo: str):
    """Build a callable for injecting into ReconciliationEngine.

    Returns a function(task_id, task) -> list[ExternalStateChange] that
    checks if the task's linked GitHub issue has been closed.
    """
    def checker(task_id: str, task) -> list:
        from codeframe.core.reconciliation import ExternalStateChange

        issue_number = getattr(task, "github_issue_number", None)
        if issue_number is None:
            return []

        try:
            state = get_issue_state(token, repo, issue_number)
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            logger.warning(
                "GitHub API error for issue #%d: %s", issue_number, exc,
            )
            return []

        if state == "closed":
            return [ExternalStateChange(
                task_id=task_id,
                change_type="closed",
                source="github",
                details={"issue_number": issue_number},
            )]

        return []

    return checker
