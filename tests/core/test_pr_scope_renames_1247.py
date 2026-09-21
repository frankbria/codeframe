"""A rename must not let a file escape its own requirement (#1247).

GitHub reports a renamed file under its **new** path, carrying the old one in a
separate ``previous_filename`` field. ``get_pr_files`` returned only
``filename``, so once the merge gate started scoping to the PR's changed files,
renaming ``src/auth/login.py`` stopped intersecting a requirement scoped to
``src/auth/login.py`` — and the gate dropped it and merged with no override.

This is the one gate-weakening path the fail-closed defaults do not catch,
because nothing fails: the file list is simply incomplete, and an incomplete
list looks exactly like a small PR.

The old path is opt-in because the two callers want different things. The
``/pr/{n}/files`` endpoint lists what the PR *now* contains and must not show
paths that no longer exist; the gate asks what the PR *touched*.
"""

import pytest

pytestmark = pytest.mark.v2


def _client():
    from codeframe.git.github_integration import GitHubIntegration

    integration = GitHubIntegration.__new__(GitHubIntegration)
    integration.owner = "acme"
    integration.repo_name = "app"
    return integration


def _one_page(entries):
    async def _request(*_args, **kwargs):
        endpoint = kwargs.get("endpoint") or (_args[1] if len(_args) > 1 else "")
        page = 1
        if "&page=" in endpoint:
            page = int(endpoint.split("&page=")[1].split("&")[0])
        return entries if page == 1 else []

    return _request


RENAME_PAGE = [
    {"filename": "src/auth/session.py", "previous_filename": "src/auth/login.py"},
    {"filename": "README.md"},
]


class TestPreviousFilenames:
    @pytest.mark.asyncio
    async def test_default_returns_current_paths_only(self):
        """The /files endpoint must not list paths the PR no longer has."""
        from unittest.mock import patch

        integration = _client()
        with patch.object(integration, "_make_request", new=_one_page(RENAME_PAGE)):
            files = await integration.get_pr_files(42)

        assert files == ["src/auth/session.py", "README.md"]

    @pytest.mark.asyncio
    async def test_include_previous_adds_the_pre_rename_path(self):
        from unittest.mock import patch

        integration = _client()
        with patch.object(integration, "_make_request", new=_one_page(RENAME_PAGE)):
            files = await integration.get_pr_files(42, include_previous=True)

        assert set(files) == {
            "src/auth/session.py",
            "src/auth/login.py",
            "README.md",
        }

    @pytest.mark.asyncio
    async def test_include_previous_is_harmless_without_renames(self):
        from unittest.mock import patch

        integration = _client()
        page = [{"filename": "a.py"}, {"filename": "b.py"}]
        with patch.object(integration, "_make_request", new=_one_page(page)):
            files = await integration.get_pr_files(42, include_previous=True)

        assert files == ["a.py", "b.py"]

    @pytest.mark.asyncio
    async def test_pagination_still_terminates_with_previous_names(self):
        """A short page ends the loop on entry count, not on names emitted.

        Appending previous_filename makes len(files) exceed len(data); if the
        loop ever keys off the output length it would spin.
        """
        from unittest.mock import patch

        integration = _client()
        with patch.object(integration, "_make_request", new=_one_page(RENAME_PAGE)):
            files = await integration.get_pr_files(42, include_previous=True)

        assert len(files) == 3
