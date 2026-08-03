"""GitHubIntegration's transport layer was never executed (#949).

Every existing test patches ``_make_request``, so the method that does the
actual work — building the URL, sending the auth headers, mapping error
bodies, returning ``None`` on 204, translating timeouts to 408 and connection
errors to 500 — has no coverage at all. A change to any of it passes CI.

These drive the real ``_make_request`` through ``httpx.MockTransport``, which
substitutes only the socket. The client, its headers and its timeout are the
ones ``__init__`` built.
"""

import httpx
import pytest

from codeframe.git.github_integration import GitHubAPIError, GitHubIntegration

pytestmark = pytest.mark.v2

TOKEN = "ghp_not-a-real-token"
REPO = "owner/repo"


def _integration(handler) -> GitHubIntegration:
    """A real GitHubIntegration whose socket is a MockTransport.

    Only ``_client._transport`` is replaced, so the Authorization / Accept /
    API-version headers and the 30s timeout under test are the ones the real
    constructor set.
    """
    gh = GitHubIntegration(token=TOKEN, repo=REPO)
    gh._client._transport = httpx.MockTransport(handler)
    return gh


class TestTheRequestItSends:
    @pytest.mark.asyncio
    async def test_the_url_is_built_from_the_base_and_endpoint(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={})

        await _integration(handler)._make_request("GET", "/repos/owner/repo/pulls")

        assert seen["url"] == "https://api.github.com/repos/owner/repo/pulls"

    @pytest.mark.asyncio
    async def test_the_auth_and_api_version_headers_go_out(self):
        """Never asserted before, because no test reached the wire."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, json={})

        await _integration(handler)._make_request("GET", "/x")

        assert seen["authorization"] == f"Bearer {TOKEN}"
        assert seen["accept"] == "application/vnd.github.v3+json"
        assert seen["x-github-api-version"] == "2022-11-28"

    @pytest.mark.asyncio
    async def test_the_body_is_sent_as_json(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["content"] = request.content
            seen["method"] = request.method
            return httpx.Response(201, json={"number": 1})

        await _integration(handler)._make_request(
            "POST", "/repos/owner/repo/pulls", json_data={"title": "hi"}
        )

        assert seen["method"] == "POST"
        assert b'"title"' in seen["content"]

    @pytest.mark.asyncio
    async def test_a_json_body_is_returned_parsed(self):
        gh = _integration(lambda r: httpx.Response(200, json={"number": 7}))

        assert await gh._make_request("GET", "/x") == {"number": 7}


class TestEmptyResponses:
    """AC3's named case."""

    @pytest.mark.asyncio
    async def test_204_returns_none_rather_than_raising(self):
        """A 204 body is empty, so `response.json()` would raise. Used by every
        DELETE-shaped call."""
        gh = _integration(lambda r: httpx.Response(204))

        assert await gh._make_request("DELETE", "/x") is None

    @pytest.mark.asyncio
    async def test_the_204_branch_is_reached_before_json_parsing(self):
        """Same thing from the other side: a 204 carrying a genuinely
        unparseable body must still succeed."""
        gh = _integration(lambda r: httpx.Response(204, content=b"not json"))

        assert await gh._make_request("DELETE", "/x") is None


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_the_github_message_is_lifted_out_of_the_body(self):
        gh = _integration(
            lambda r: httpx.Response(422, json={"message": "Validation Failed"})
        )

        with pytest.raises(GitHubAPIError) as exc:
            await gh._make_request("POST", "/x")

        assert exc.value.status_code == 422
        assert "Validation Failed" in str(exc.value)

    @pytest.mark.asyncio
    async def test_the_errors_array_is_carried_into_details(self):
        errors = [{"resource": "PullRequest", "code": "custom"}]
        gh = _integration(
            lambda r: httpx.Response(422, json={"message": "bad", "errors": errors})
        )

        with pytest.raises(GitHubAPIError) as exc:
            await gh._make_request("POST", "/x")

        assert exc.value.details == {"errors": errors}

    @pytest.mark.asyncio
    async def test_a_non_json_error_body_falls_back_to_the_text(self):
        """GitHub's edge proxy returns HTML for some 5xx. `response.json()`
        raises there, and the bare `except Exception` around it is the only
        thing keeping that from becoming an unrelated crash."""
        gh = _integration(
            lambda r: httpx.Response(502, content=b"<html>bad gateway</html>")
        )

        with pytest.raises(GitHubAPIError) as exc:
            await gh._make_request("GET", "/x")

        assert exc.value.status_code == 502
        assert "bad gateway" in str(exc.value)

    @pytest.mark.asyncio
    async def test_an_error_body_with_no_message_key_still_reports_something(self):
        gh = _integration(lambda r: httpx.Response(403, json={"unexpected": "shape"}))

        with pytest.raises(GitHubAPIError) as exc:
            await gh._make_request("GET", "/x")

        assert exc.value.status_code == 403
        assert str(exc.value)

    @pytest.mark.asyncio
    async def test_a_404_has_no_details_when_github_sent_no_errors_array(self):
        """`{"errors": None}` would be wrong — callers check `if details`."""
        gh = _integration(lambda r: httpx.Response(404, json={"message": "Not Found"}))

        with pytest.raises(GitHubAPIError) as exc:
            await gh._make_request("GET", "/x")

        assert exc.value.details is None

    @pytest.mark.asyncio
    async def test_the_boundary_is_400_not_401(self):
        """`>= 400` — a 399 would be treated as success. Pinning both sides."""
        ok = _integration(lambda r: httpx.Response(399, json={"ok": True}))
        assert await ok._make_request("GET", "/x") == {"ok": True}

        bad = _integration(lambda r: httpx.Response(400, json={"message": "nope"}))
        with pytest.raises(GitHubAPIError):
            await bad._make_request("GET", "/x")


class TestTransportFailures:
    @pytest.mark.asyncio
    async def test_a_timeout_becomes_408(self):
        def handler(request):
            raise httpx.TimeoutException("timed out", request=request)

        with pytest.raises(GitHubAPIError) as exc:
            await _integration(handler)._make_request("GET", "/x")

        assert exc.value.status_code == 408
        assert "timed out" in str(exc.value).lower()

    @pytest.mark.asyncio
    async def test_a_connection_error_becomes_500(self):
        def handler(request):
            raise httpx.ConnectError("name resolution failed", request=request)

        with pytest.raises(GitHubAPIError) as exc:
            await _integration(handler)._make_request("GET", "/x")

        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_the_timeout_branch_wins_over_the_generic_request_error(self):
        """TimeoutException subclasses TransportError, which subclasses
        RequestError — so ordering the handlers wrong silently turns every
        408 into a 500."""
        def handler(request):
            raise httpx.ReadTimeout("read timed out", request=request)

        with pytest.raises(GitHubAPIError) as exc:
            await _integration(handler)._make_request("GET", "/x")

        assert exc.value.status_code == 408, "a read timeout was mapped to 500"


class TestARealCallerGoesThroughIt:
    """The mapping matters because public methods propagate it unchanged."""

    @pytest.mark.asyncio
    async def test_get_pr_surfaces_the_404_from_the_wire(self):
        gh = _integration(lambda r: httpx.Response(404, json={"message": "Not Found"}))

        with pytest.raises(GitHubAPIError) as exc:
            await gh.get_pull_request(999)

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_list_pull_requests_parses_a_real_shaped_page(self):
        page = [
            {
                "number": 12,
                "html_url": "https://github.com/owner/repo/pull/12",
                "state": "open",
                "title": "Add thing",
                "body": "does things",
                "created_at": "2026-01-01T00:00:00Z",
                "merged_at": None,
                "head": {"ref": "feature/thing"},
                "base": {"ref": "main"},
            }
        ]
        gh = _integration(lambda r: httpx.Response(200, json=page))

        prs = await gh.list_pull_requests(state="open")

        assert [p.number for p in prs] == [12]
        assert prs[0].head_branch == "feature/thing"
