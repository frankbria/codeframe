"""Tests for the GitHub issues listing service (issue #564).

Covers:
- plain list endpoint returns simplified open issues
- pull requests are filtered out (the /issues endpoint returns PRs too)
- label filter is forwarded as the ``labels`` query param
- free-text search routes to /search/issues and parses ``total_count``
- pagination total is derived from the ``Link`` header (last page)
- 401 -> InvalidTokenError, 403 -> InsufficientScopeError
- 410 (issues disabled) -> empty list, no error

Validated against a mocked httpx transport — no real network call is made.
"""

from __future__ import annotations

import httpx
import pytest

from codeframe.core.github_connect_service import (
    InsufficientScopeError,
    InvalidTokenError,
)
from codeframe.core.github_issues_service import list_issues

pytestmark = pytest.mark.v2

VALID_PAT = "ghp_validtoken1234567890"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _issue(number, title, *, labels=None, login=None, is_pr=False):
    data = {
        "number": number,
        "title": title,
        "labels": [{"name": n} for n in (labels or [])],
        "assignee": ({"login": login} if login else None),
        "created_at": "2026-05-01T12:00:00Z",
        "html_url": f"https://github.com/acme/app/issues/{number}",
    }
    if is_pr:
        data["pull_request"] = {"url": "https://api.github.com/.../pulls/1"}
    return data


class TestListEndpoint:
    @pytest.mark.asyncio
    async def test_returns_simplified_open_issues(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/repos/acme/app/issues"
            assert request.url.params.get("state") == "open"
            assert request.url.params.get("page") == "1"
            assert request.url.params.get("per_page") == "25"
            return httpx.Response(
                200,
                json=[
                    _issue(42, "Fix login bug", labels=["bug", "auth"], login="alice"),
                    _issue(41, "Add dark mode", labels=["ui"], login=None),
                ],
            )

        async with _client(handler) as client:
            issues, total = await list_issues(
                VALID_PAT, "acme/app", page=1, per_page=25, client=client
            )
        assert total == 2
        assert issues[0] == {
            "number": 42,
            "title": "Fix login bug",
            "labels": ["bug", "auth"],
            "assignee": "alice",
            "created_at": "2026-05-01T12:00:00Z",
            "html_url": "https://github.com/acme/app/issues/42",
        }
        assert issues[1]["assignee"] is None

    @pytest.mark.asyncio
    async def test_filters_out_pull_requests(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    _issue(42, "Real issue"),
                    _issue(40, "A PR masquerading as issue", is_pr=True),
                ],
            )

        async with _client(handler) as client:
            issues, total = await list_issues(
                VALID_PAT, "acme/app", page=1, per_page=25, client=client
            )
        assert [i["number"] for i in issues] == [42]
        assert total == 1

    @pytest.mark.asyncio
    async def test_label_filter_forwarded(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["labels"] = request.url.params.get("labels")
            return httpx.Response(200, json=[_issue(1, "x", labels=["bug"])])

        async with _client(handler) as client:
            await list_issues(
                VALID_PAT, "acme/app", page=1, per_page=25, label="bug", client=client
            )
        assert seen["labels"] == "bug"

    @pytest.mark.asyncio
    async def test_total_from_link_header(self):
        def handler(request: httpx.Request) -> httpx.Response:
            link = (
                '<https://api.github.com/repos/acme/app/issues?page=2&per_page=2>; '
                'rel="next", '
                '<https://api.github.com/repos/acme/app/issues?page=5&per_page=2>; '
                'rel="last"'
            )
            return httpx.Response(
                200,
                headers={"Link": link},
                json=[_issue(1, "a"), _issue(2, "b")],
            )

        async with _client(handler) as client:
            issues, total = await list_issues(
                VALID_PAT, "acme/app", page=1, per_page=2, client=client
            )
        # last page 5 * per_page 2 == 10 (upper-bound estimate)
        assert total == 10
        assert len(issues) == 2


class TestSearchEndpoint:
    @pytest.mark.asyncio
    async def test_search_routes_to_search_api(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["q"] = request.url.params.get("q")
            return httpx.Response(
                200,
                json={
                    "total_count": 3,
                    "items": [
                        _issue(7, "login flow", login="bob"),
                    ],
                },
            )

        async with _client(handler) as client:
            issues, total = await list_issues(
                VALID_PAT,
                "acme/app",
                page=1,
                per_page=25,
                search="login",
                client=client,
            )
        assert seen["path"] == "/search/issues"
        assert "login" in seen["q"]
        assert "repo:acme/app" in seen["q"]
        assert "is:issue" in seen["q"]
        assert "is:open" in seen["q"]
        assert total == 3
        assert issues[0]["number"] == 7

    @pytest.mark.asyncio
    async def test_search_with_label_adds_qualifier(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["q"] = request.url.params.get("q")
            return httpx.Response(200, json={"total_count": 0, "items": []})

        async with _client(handler) as client:
            await list_issues(
                VALID_PAT,
                "acme/app",
                page=1,
                per_page=25,
                search="bug",
                label="ui",
                client=client,
            )
        assert 'label:"ui"' in seen["q"]


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_401_invalid_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        async with _client(handler) as client:
            with pytest.raises(InvalidTokenError):
                await list_issues(
                    VALID_PAT, "acme/app", page=1, per_page=25, client=client
                )

    @pytest.mark.asyncio
    async def test_403_insufficient_scope(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"message": "Forbidden"})

        async with _client(handler) as client:
            with pytest.raises(InsufficientScopeError):
                await list_issues(
                    VALID_PAT, "acme/app", page=1, per_page=25, client=client
                )

    @pytest.mark.asyncio
    async def test_410_issues_disabled_returns_empty(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(410, json={"message": "Issues are disabled"})

        async with _client(handler) as client:
            issues, total = await list_issues(
                VALID_PAT, "acme/app", page=1, per_page=25, client=client
            )
        assert issues == []
        assert total == 0


# ─────────────────────────────────────────────────────────────────────────────
# get_issue / close_issue (issue #565 — import execution + auto-close)
# ─────────────────────────────────────────────────────────────────────────────

from codeframe.core.github_connect_service import GitHubConnectError  # noqa: E402
from codeframe.core.github_issues_service import (  # noqa: E402
    IssueNotFoundError,
    NotAnIssueError,
    close_issue,
    get_issue,
)


class TestGetIssue:
    @pytest.mark.asyncio
    async def test_rejects_pull_requests(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "number": 50,
                    "title": "A PR",
                    "body": "diff",
                    "labels": [],
                    "html_url": "https://github.com/acme/app/pull/50",
                    "pull_request": {"url": "https://api.github.com/.../pulls/50"},
                },
            )

        async with _client(handler) as client:
            with pytest.raises(NotAnIssueError):
                await get_issue(VALID_PAT, "acme/app", 50, client=client)

    @pytest.mark.asyncio
    async def test_returns_issue_fields(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/repos/acme/app/issues/42"
            return httpx.Response(
                200,
                json={
                    "number": 42,
                    "title": "Fix login bug",
                    "body": "Steps to reproduce...",
                    "labels": [{"name": "bug"}, {"name": "auth"}],
                    "html_url": "https://github.com/acme/app/issues/42",
                },
            )

        async with _client(handler) as client:
            issue = await get_issue(VALID_PAT, "acme/app", 42, client=client)
        assert issue["number"] == 42
        assert issue["title"] == "Fix login bug"
        assert issue["body"] == "Steps to reproduce..."
        assert issue["labels"] == ["bug", "auth"]
        assert issue["html_url"] == "https://github.com/acme/app/issues/42"

    @pytest.mark.asyncio
    async def test_handles_null_body(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "number": 7,
                    "title": "No body issue",
                    "body": None,
                    "labels": [],
                    "html_url": "https://github.com/acme/app/issues/7",
                },
            )

        async with _client(handler) as client:
            issue = await get_issue(VALID_PAT, "acme/app", 7, client=client)
        assert issue["body"] == ""
        assert issue["labels"] == []

    @pytest.mark.asyncio
    async def test_401_maps_to_invalid_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        async with _client(handler) as client:
            with pytest.raises(InvalidTokenError):
                await get_issue(VALID_PAT, "acme/app", 1, client=client)

    @pytest.mark.asyncio
    async def test_404_maps_to_issue_not_found(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        async with _client(handler) as client:
            with pytest.raises(IssueNotFoundError):
                await get_issue(VALID_PAT, "acme/app", 999, client=client)


class TestCloseIssue:
    @pytest.mark.asyncio
    async def test_patches_state_closed(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            return httpx.Response(200, json={"number": 42, "state": "closed"})

        async with _client(handler) as client:
            ok = await close_issue(VALID_PAT, "acme/app", 42, client=client)
        assert ok is True
        assert ("PATCH", "/repos/acme/app/issues/42") in calls

    @pytest.mark.asyncio
    async def test_posts_comment_then_closes_when_comment_given(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path.endswith("/comments"):
                return httpx.Response(201, json={"id": 1})
            return httpx.Response(200, json={"number": 42, "state": "closed"})

        async with _client(handler) as client:
            ok = await close_issue(
                VALID_PAT, "acme/app", 42, comment="Completed via CodeFRAME", client=client
            )
        assert ok is True
        assert ("POST", "/repos/acme/app/issues/42/comments") in calls
        assert ("PATCH", "/repos/acme/app/issues/42") in calls
        # Comment must be posted before the close patch.
        assert calls.index(("POST", "/repos/acme/app/issues/42/comments")) < calls.index(
            ("PATCH", "/repos/acme/app/issues/42")
        )

    @pytest.mark.asyncio
    async def test_closes_even_when_comment_fails(self):
        """A failed completion comment must not prevent the close itself."""
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path.endswith("/comments"):
                return httpx.Response(403, json={"message": "locked"})
            return httpx.Response(200, json={"number": 42, "state": "closed"})

        async with _client(handler) as client:
            ok = await close_issue(
                VALID_PAT, "acme/app", 42, comment="hi", client=client
            )
        assert ok is True
        assert ("PATCH", "/repos/acme/app/issues/42") in calls

    @pytest.mark.asyncio
    async def test_no_comment_skips_comment_call(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            return httpx.Response(200, json={"number": 42, "state": "closed"})

        async with _client(handler) as client:
            await close_issue(VALID_PAT, "acme/app", 42, client=client)
        assert not any(p.endswith("/comments") for _, p in calls)

    @pytest.mark.asyncio
    async def test_401_maps_to_invalid_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        async with _client(handler) as client:
            with pytest.raises(InvalidTokenError):
                await close_issue(VALID_PAT, "acme/app", 1, client=client)
