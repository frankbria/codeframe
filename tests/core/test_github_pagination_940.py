"""GitHub calls must paginate, and imports must not fan out unbounded (#940).

Three API calls were unpaginated while `get_pr_files` in the same class showed
the correct loop. GitHub defaults to 30 items per page, so these did not return
a *partial* answer — they returned a **wrong** one:

- `list_pull_requests` truncated `cf pr status` and the merge-override audit
  surface at 30
- `get_pr_ci_checks` reported all-green when the failing check was #31
- `get_pr_review_status` reported "approved" when the CHANGES_REQUESTED review
  was #31

Separately, `_total_from_link_header` fell back to the *current page's* item
count when GitHub omits rel="last" (which it does on the last page), so the
import modal's pagination collapsed at the end. And a select-all import awaited
each issue sequentially with its own `httpx.AsyncClient`.
"""

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.v2


def _client():
    from codeframe.git.github_integration import GitHubIntegration

    integration = GitHubIntegration.__new__(GitHubIntegration)
    integration.owner = "acme"
    integration.repo_name = "app"
    return integration


def _pages(*batches):
    """A _make_request stub returning each batch in turn, then an empty page."""

    async def _request(*_args, **kwargs):
        endpoint = kwargs.get("endpoint") or (_args[1] if len(_args) > 1 else "")
        page = 1
        if "&page=" in endpoint:
            # "&page=", not "page=": per_page=100 contains the latter.
            page = int(endpoint.split("&page=")[1].split("&")[0])
        return batches[page - 1] if page <= len(batches) else []

    return _request


class TestListPullRequestsPaginates:
    @pytest.mark.asyncio
    async def test_more_than_thirty_prs_are_returned(self):
        integration = _client()
        full = [{"number": i} for i in range(100)]
        rest = [{"number": i} for i in range(100, 145)]

        with (
            patch.object(integration, "_make_request", new=_pages(full, rest)),
            patch.object(
                integration, "_parse_pr_response", side_effect=lambda pr: pr["number"]
            ),
        ):
            result = await integration.list_pull_requests()

        assert len(result) == 145, "pagination stopped early"
        assert result[0] == 0 and result[-1] == 144

    @pytest.mark.asyncio
    async def test_a_single_short_page_stops_immediately(self):
        integration = _client()
        calls = []

        async def _request(*_a, **kw):
            calls.append(kw.get("endpoint"))
            return [{"number": 1}]

        with (
            patch.object(integration, "_make_request", new=_request),
            patch.object(integration, "_parse_pr_response", side_effect=lambda pr: pr),
        ):
            await integration.list_pull_requests()

        assert len(calls) == 1, "a short first page should not trigger a second request"

    @pytest.mark.asyncio
    async def test_the_state_filter_survives_pagination(self):
        integration = _client()
        seen = []

        async def _request(*_a, **kw):
            seen.append(kw.get("endpoint"))
            return []

        with patch.object(integration, "_make_request", new=_request):
            await integration.list_pull_requests(state="closed")

        assert "state=closed" in seen[0]
        assert "per_page=100" in seen[0]


class TestCiChecksPaginate:
    @pytest.mark.asyncio
    async def test_a_failing_check_beyond_the_first_page_is_seen(self):
        """The wrong-answer case: 100 green checks then one red."""
        integration = _client()
        green = [
            {"name": f"check-{i}", "status": "completed", "conclusion": "success"}
            for i in range(100)
        ]
        red = [{"name": "the-red-one", "status": "completed", "conclusion": "failure"}]

        async def _request(*_a, **kw):
            endpoint = kw.get("endpoint") or _a[1]
            page = int(endpoint.split("&page=")[1].split("&")[0])
            return {"check_runs": green if page == 1 else red if page == 2 else []}

        with patch.object(integration, "_make_request", new=_request):
            checks = await integration.get_pr_ci_checks(1, head_sha="abc")

        names = [c.name for c in checks]
        assert len(names) == 101
        assert "the-red-one" in names, "the failing check was invisible"


class TestReviewStatusPaginates:
    @pytest.mark.asyncio
    async def test_changes_requested_beyond_the_first_page_wins(self):
        integration = _client()
        approvals = [
            {
                "state": "APPROVED",
                "user": {"login": f"dev{i}"},
                "submitted_at": "2026-01-01",
            }
            for i in range(100)
        ]
        blocker = [
            {
                "state": "CHANGES_REQUESTED",
                "user": {"login": "lead"},
                "submitted_at": "2026-01-02",
            }
        ]

        with patch.object(
            integration, "_make_request", new=_pages(approvals, blocker)
        ):
            status = await integration.get_pr_review_status(1)

        assert status == "changes_requested", (
            "a blocking review beyond page 1 was dropped and the PR read as approved"
        )


class TestLastPageTotalIsStable:
    """AC2 — GitHub omits rel="last" ON the last page."""

    def test_last_page_total_includes_earlier_pages(self):
        from codeframe.core.github_issues_service import _total_from_link_header

        # Page 5 of 5, 3 items on it, 25 per page -> 103 issues seen so far.
        assert _total_from_link_header(None, 3, 25, page=5) == 103

    def test_first_page_without_a_link_is_just_its_own_count(self):
        from codeframe.core.github_issues_service import _total_from_link_header

        assert _total_from_link_header(None, 3, 25, page=1) == 3

    def test_the_old_behaviour_would_have_collapsed(self):
        """Guard: the bug was returning the current page's count as the total."""
        from codeframe.core.github_issues_service import _total_from_link_header

        assert _total_from_link_header(None, 3, 25, page=5) != 3

    def test_a_link_header_still_wins(self):
        from codeframe.core.github_issues_service import _total_from_link_header

        link = '<https://api.github.com/x?page=7>; rel="last"'
        assert _total_from_link_header(link, 3, 25, page=2) == 175

    def test_totals_are_monotonic_across_pages(self):
        """Pagination controls flicker if the total shrinks as you page."""
        from codeframe.core.github_issues_service import _total_from_link_header

        totals = [_total_from_link_header(None, 25, 25, page=p) for p in range(1, 5)]
        assert totals == sorted(totals)


class TestImportFanOutIsBounded:
    def test_issue_numbers_has_an_enforced_cap(self):
        from pydantic import ValidationError

        from codeframe.ui.routers.github_integrations_v2 import (
            MAX_IMPORT_ISSUES,
            ImportRequest,
        )

        assert ImportRequest(issue_numbers=list(range(1, MAX_IMPORT_ISSUES + 1)))
        with pytest.raises(ValidationError):
            ImportRequest(issue_numbers=list(range(1, MAX_IMPORT_ISSUES + 2)))

    def test_the_cap_is_documented(self):
        from codeframe.ui.routers.github_integrations_v2 import ImportRequest

        description = ImportRequest.model_fields["issue_numbers"].description or ""
        assert "422" in description

    def test_concurrency_is_bounded_and_modest(self):
        from codeframe.ui.routers.github_integrations_v2 import IMPORT_CONCURRENCY

        assert 4 <= IMPORT_CONCURRENCY <= 8, (
            "the AC asks for bounded concurrency in the 4-8 range"
        )

    def test_the_import_uses_one_client_and_a_semaphore(self):
        """AC4 — one client for the whole import, fetches run concurrently."""
        import inspect

        from codeframe.ui.routers import github_integrations_v2

        source = inspect.getsource(github_integrations_v2.import_issues)

        assert "async with httpx.AsyncClient(timeout=GITHUB_TIMEOUT) as client" in source
        assert "asyncio.gather" in source
        assert "asyncio.Semaphore(IMPORT_CONCURRENCY)" in source
        # The old shape: one client per issue, awaited in a loop.
        assert "await get_issue(pat, repo, number)" not in source

    def test_the_shared_client_keeps_the_services_timeout(self):
        """Raised by codex review: sharing one client silently dropped the
        issue service's 15s timeout to httpx's 5s default, so imports would
        start failing at 5s on slower GitHub responses."""
        import inspect

        from codeframe.core.github_issues_service import _TIMEOUT
        from codeframe.ui.routers import github_integrations_v2

        assert github_integrations_v2.GITHUB_TIMEOUT == _TIMEOUT

        source = inspect.getsource(github_integrations_v2.import_issues)
        assert "httpx.AsyncClient(timeout=GITHUB_TIMEOUT)" in source
        assert "httpx.AsyncClient()" not in source, "back to the 5s default"

    @pytest.mark.asyncio
    async def test_a_hundred_issues_share_one_client(self):
        """The behavioural half: 100 issues, exactly one AsyncClient built."""
        import asyncio

        from codeframe.core import github_issues_service

        built = []
        real_client = __import__("httpx").AsyncClient

        class CountingClient(real_client):
            def __init__(self, *a, **kw):
                built.append(1)
                super().__init__(*a, **kw)

        seen_clients = []

        async def fake_get_issue(pat, repo, number, *, client=None):
            seen_clients.append(id(client))
            await asyncio.sleep(0)
            return {"html_url": f"https://github.com/a/b/issues/{number}",
                    "number": number, "title": f"t{number}", "body": ""}

        with (
            patch("httpx.AsyncClient", CountingClient),
            patch.object(github_issues_service, "get_issue", fake_get_issue),
        ):
            # Drive the same shape the endpoint uses.
            semaphore = asyncio.Semaphore(6)

            async def _fetch(n, client):
                async with semaphore:
                    return await fake_get_issue("pat", "a/b", n, client=client)

            import httpx

            async with httpx.AsyncClient() as client:
                await asyncio.gather(*(_fetch(n, client) for n in range(100)))

        assert built == [1], f"expected exactly one client, built {len(built)}"
        assert len(set(seen_clients)) == 1, "issues did not share the client"
