"""Tests for the GitHub connection validation service (issue #563).

Covers:
- repo format parsing (valid + invalid)
- successful validation returns owner login + avatar
- 401 from GitHub -> InvalidTokenError
- 404 from GitHub -> RepoNotFoundError
- 403 from the issues endpoint -> InsufficientScopeError
- issues endpoint 410 (issues disabled) is treated as a valid connection

The service is validated against a mocked httpx transport so no real network
call is made.
"""

from __future__ import annotations

import httpx
import pytest

from codeframe.core.github_connect_service import (
    InsufficientScopeError,
    InvalidTokenError,
    RepoNotFoundError,
    parse_repo,
    validate_connection,
)

pytestmark = pytest.mark.v2


def _client(handler) -> httpx.AsyncClient:
    """Build an AsyncClient backed by a MockTransport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestParseRepo:
    def test_valid(self):
        assert parse_repo("acme/app") == ("acme", "app")

    def test_strips_whitespace(self):
        assert parse_repo("  acme / app  ") == ("acme", "app")

    @pytest.mark.parametrize("bad", ["", "noslash", "acme/", "/app", "a/b/c", "   "])
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            parse_repo(bad)


class TestValidateConnection:
    @pytest.mark.asyncio
    async def test_success(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/repos/acme/app":
                return httpx.Response(
                    200,
                    json={
                        "full_name": "acme/app",
                        "owner": {
                            "login": "acme",
                            "avatar_url": "https://avatars.githubusercontent.com/u/1",
                        },
                    },
                )
            if request.url.path == "/repos/acme/app/issues":
                return httpx.Response(200, json=[])
            return httpx.Response(500)

        async with _client(handler) as c:
            result = await validate_connection("ghp_token", "acme/app", client=c)

        assert result == {
            "repo_full_name": "acme/app",
            "owner_login": "acme",
            "owner_avatar_url": "https://avatars.githubusercontent.com/u/1",
        }

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "Bad credentials"})

        async with _client(handler) as c:
            with pytest.raises(InvalidTokenError):
                await validate_connection("ghp_bad", "acme/app", client=c)

    @pytest.mark.asyncio
    async def test_repo_not_found(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

        async with _client(handler) as c:
            with pytest.raises(RepoNotFoundError):
                await validate_connection("ghp_token", "acme/missing", client=c)

    @pytest.mark.asyncio
    async def test_insufficient_scope_on_issues(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/repos/acme/app":
                return httpx.Response(
                    200,
                    json={
                        "full_name": "acme/app",
                        "owner": {"login": "acme", "avatar_url": "https://x/y"},
                    },
                )
            # Issues read denied -> token lacks issues scope.
            return httpx.Response(403, json={"message": "Forbidden"})

        async with _client(handler) as c:
            with pytest.raises(InsufficientScopeError):
                await validate_connection("ghp_token", "acme/app", client=c)

    @pytest.mark.asyncio
    async def test_issues_disabled_is_ok(self):
        """A repo with issues disabled returns 410 — connection is still valid."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/repos/acme/app":
                return httpx.Response(
                    200,
                    json={
                        "full_name": "acme/app",
                        "owner": {"login": "acme", "avatar_url": "https://x/y"},
                    },
                )
            return httpx.Response(410, json={"message": "Issues are disabled"})

        async with _client(handler) as c:
            result = await validate_connection("ghp_token", "acme/app", client=c)
        assert result["repo_full_name"] == "acme/app"

    @pytest.mark.asyncio
    async def test_invalid_repo_format_raises_before_network(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("network should not be hit for bad format")

        async with _client(handler) as c:
            with pytest.raises(ValueError):
                await validate_connection("ghp_token", "noslash", client=c)
