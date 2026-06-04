"""Tests for the GitHub integrations router (issue #563).

Covers connect/disconnect/status against a real (temp-dir-backed) credential
store and a real per-workspace config, with the network validation mocked.

Acceptance criteria coverage:
- connect with valid PAT + repo  -> 200, connected
- invalid PAT / missing scope     -> clear error status codes
- disconnect clears the credential
- PAT never returned in plaintext
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2

VALID_PAT = "ghp_validtoken1234567890"


@pytest.fixture
def workspace():
    temp_dir = Path(tempfile.mkdtemp())
    ws_path = temp_dir / "ws"
    ws_path.mkdir(parents=True, exist_ok=True)
    from codeframe.core.workspace import create_or_load_workspace

    ws = create_or_load_workspace(ws_path)
    try:
        yield ws
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """Isolated file-backed CredentialManager (no keyring, no ~/.codeframe)."""
    from codeframe.core.credentials import CredentialManager, CredentialStore

    store = CredentialStore(storage_dir=tmp_path)
    store._keyring_available = False
    mgr = CredentialManager.__new__(CredentialManager)
    mgr._store = store
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return mgr


@pytest.fixture
def client(workspace, manager):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import github_integrations_v2

    app = FastAPI()
    app.include_router(github_integrations_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: workspace
    app.dependency_overrides[github_integrations_v2.get_credential_manager] = (
        lambda: manager
    )
    return TestClient(app)


def _mock_validate(monkeypatch, *, result=None, exc=None):
    from codeframe.ui.routers import github_integrations_v2

    async def fake(pat, repo, **kwargs):
        if exc is not None:
            raise exc
        return result or {
            "repo_full_name": repo,
            "owner_login": repo.split("/")[0],
            "owner_avatar_url": "https://avatars/1",
        }

    monkeypatch.setattr(github_integrations_v2, "validate_connection", fake)


class TestStatus:
    def test_disconnected_by_default(self, client):
        r = client.get("/api/v2/integrations/github/status")
        assert r.status_code == 200
        assert r.json() == {
            "connected": False,
            "repo": None,
            "owner_login": None,
            "owner_avatar_url": None,
        }


class TestConnect:
    def test_connect_success(self, client, monkeypatch):
        _mock_validate(monkeypatch)
        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True
        assert data["repo"] == "acme/app"
        assert data["owner_login"] == "acme"
        assert data["owner_avatar_url"] == "https://avatars/1"

    def test_connect_persists_and_status_reflects(self, client, monkeypatch):
        _mock_validate(monkeypatch)
        client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        r = client.get("/api/v2/integrations/github/status")
        data = r.json()
        assert data["connected"] is True
        assert data["repo"] == "acme/app"

    def test_connect_stores_credential(self, client, manager, monkeypatch):
        from codeframe.core.credentials import CredentialProvider

        _mock_validate(monkeypatch)
        client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        assert manager.get_credential(CredentialProvider.GIT_GITHUB) == VALID_PAT

    def test_pat_never_in_response(self, client, monkeypatch):
        _mock_validate(monkeypatch)
        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        assert VALID_PAT not in r.text
        s = client.get("/api/v2/integrations/github/status")
        assert VALID_PAT not in s.text

    def test_invalid_repo_format_returns_400(self, client, monkeypatch):
        _mock_validate(monkeypatch)
        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "noslash"},
        )
        assert r.status_code == 400

    def test_invalid_token_returns_401(self, client, monkeypatch):
        from codeframe.core.github_connect_service import InvalidTokenError

        _mock_validate(monkeypatch, exc=InvalidTokenError("Invalid GitHub token."))
        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": "ghp_bad1234567890", "repo": "acme/app"},
        )
        assert r.status_code == 401

    def test_repo_not_found_returns_404(self, client, monkeypatch):
        from codeframe.core.github_connect_service import RepoNotFoundError

        _mock_validate(monkeypatch, exc=RepoNotFoundError("not found"))
        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/missing"},
        )
        assert r.status_code == 404

    def test_insufficient_scope_returns_403(self, client, monkeypatch):
        from codeframe.core.github_connect_service import InsufficientScopeError

        _mock_validate(monkeypatch, exc=InsufficientScopeError("no issues scope"))
        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        assert r.status_code == 403

    def test_failed_connect_does_not_store_credential(
        self, client, manager, monkeypatch
    ):
        from codeframe.core.credentials import CredentialProvider
        from codeframe.core.github_connect_service import InvalidTokenError

        _mock_validate(monkeypatch, exc=InvalidTokenError("bad"))
        client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": "ghp_bad1234567890", "repo": "acme/app"},
        )
        assert manager.get_credential(CredentialProvider.GIT_GITHUB) is None

    def test_config_save_failure_restores_prior_pat(
        self, client, manager, monkeypatch
    ):
        """A config-write failure must not clobber a pre-existing GitHub PAT.

        The PAT slot is machine-wide (shared with the API Keys tab); rollback
        must restore the prior token rather than blindly deleting it.
        """
        from codeframe.core.credentials import CredentialProvider
        from codeframe.ui.routers import github_integrations_v2

        prior = "ghp_preexisting9876543210"
        manager.set_credential(CredentialProvider.GIT_GITHUB, prior)

        _mock_validate(monkeypatch)

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(
            github_integrations_v2, "save_github_integration_config", boom
        )

        r = client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        assert r.status_code == 500
        # Prior credential preserved, not wiped.
        assert manager.get_credential(CredentialProvider.GIT_GITHUB) == prior


class TestDisconnect:
    def test_disconnect_clears_credential_and_config(
        self, client, manager, monkeypatch
    ):
        from codeframe.core.credentials import CredentialProvider

        _mock_validate(monkeypatch)
        client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_PAT, "repo": "acme/app"},
        )
        r = client.delete("/api/v2/integrations/github/disconnect")
        assert r.status_code == 204
        assert manager.get_credential(CredentialProvider.GIT_GITHUB) is None
        status = client.get("/api/v2/integrations/github/status").json()
        assert status["connected"] is False

    def test_disconnect_when_not_connected_is_ok(self, client):
        r = client.delete("/api/v2/integrations/github/disconnect")
        assert r.status_code == 204


def _connect(client, monkeypatch, repo="acme/app"):
    """Helper: establish a connected workspace (PAT + repo metadata stored)."""
    _mock_validate(monkeypatch)
    client.post(
        "/api/v2/integrations/github/connect",
        json={"pat": VALID_PAT, "repo": repo},
    )


def _mock_list_issues(monkeypatch, *, calls=None, result=None, exc=None):
    """Patch the issues service used by the router. Records call kwargs."""
    from codeframe.ui.routers import github_integrations_v2

    async def fake(pat, repo, **kwargs):
        if calls is not None:
            calls.append({"pat": pat, "repo": repo, **kwargs})
        if exc is not None:
            raise exc
        return result if result is not None else ([], 0)

    monkeypatch.setattr(github_integrations_v2, "list_issues", fake)


def _clear_issue_cache():
    from codeframe.ui.routers import github_integrations_v2

    github_integrations_v2._ISSUE_CACHE.clear()


class TestListIssues:
    def test_requires_connection(self, client, monkeypatch):
        _clear_issue_cache()
        # Not connected: no PAT, no repo metadata.
        r = client.get("/api/v2/integrations/github/issues")
        assert r.status_code == 409

    def test_returns_issues_when_connected(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        sample = (
            [
                {
                    "number": 42,
                    "title": "Fix login bug",
                    "labels": ["bug"],
                    "assignee": "alice",
                    "created_at": "2026-05-01T12:00:00Z",
                    "html_url": "https://github.com/acme/app/issues/42",
                }
            ],
            1,
        )
        _mock_list_issues(monkeypatch, result=sample)
        r = client.get("/api/v2/integrations/github/issues")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["per_page"] == 25
        assert data["issues"][0]["number"] == 42
        assert data["issues"][0]["assignee"] == "alice"

    def test_forwards_pagination_and_filters(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        calls: list = []
        _mock_list_issues(monkeypatch, calls=calls, result=([], 0))
        client.get(
            "/api/v2/integrations/github/issues"
            "?page=3&per_page=10&search=login&label=bug"
        )
        assert calls[0]["repo"] == "acme/app"
        assert calls[0]["page"] == 3
        assert calls[0]["per_page"] == 10
        assert calls[0]["search"] == "login"
        assert calls[0]["label"] == "bug"

    def test_per_page_is_clamped(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        calls: list = []
        _mock_list_issues(monkeypatch, calls=calls, result=([], 0))
        client.get("/api/v2/integrations/github/issues?per_page=500")
        assert calls[0]["per_page"] == 100

    def test_response_caches_within_ttl(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        calls: list = []
        _mock_list_issues(monkeypatch, calls=calls, result=([], 0))
        client.get("/api/v2/integrations/github/issues?page=1")
        client.get("/api/v2/integrations/github/issues?page=1")
        # Second identical request served from the 60s cache → no 2nd call.
        assert len(calls) == 1

    def test_invalid_token_maps_to_401(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        from codeframe.core.github_connect_service import InvalidTokenError

        _mock_list_issues(monkeypatch, exc=InvalidTokenError("bad"))
        r = client.get("/api/v2/integrations/github/issues")
        assert r.status_code == 401

    def test_insufficient_scope_maps_to_403(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        from codeframe.core.github_connect_service import InsufficientScopeError

        _mock_list_issues(monkeypatch, exc=InsufficientScopeError("nope"))
        r = client.get("/api/v2/integrations/github/issues")
        assert r.status_code == 403

    def test_pat_never_echoed(self, client, monkeypatch):
        _clear_issue_cache()
        _connect(client, monkeypatch)
        _mock_list_issues(monkeypatch, result=([], 0))
        r = client.get("/api/v2/integrations/github/issues")
        assert VALID_PAT not in r.text


# ─────────────────────────────────────────────────────────────────────────────
# Import execution + issue close (issue #565)
# ─────────────────────────────────────────────────────────────────────────────


def _mock_get_issue(monkeypatch, issues_by_number, *, exc=None):
    """Patch get_issue on the router. ``issues_by_number`` maps number -> dict."""
    from codeframe.ui.routers import github_integrations_v2

    async def fake(pat, repo, number, **kwargs):
        if exc is not None:
            raise exc
        data = issues_by_number[number]
        return {
            "number": number,
            "title": data["title"],
            "body": data.get("body", ""),
            "labels": data.get("labels", []),
            "html_url": data.get(
                "html_url", f"https://github.com/{repo}/issues/{number}"
            ),
        }

    monkeypatch.setattr(github_integrations_v2, "get_issue", fake)


class TestImport:
    def test_requires_connection(self, client):
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [1]}
        )
        assert r.status_code == 409

    def test_imports_create_tasks(self, client, monkeypatch, workspace):
        _connect(client, monkeypatch)
        _mock_get_issue(
            monkeypatch,
            {
                12: {"title": "Fix login", "body": "Repro steps", "labels": ["bug"]},
                34: {"title": "Dark mode", "body": "", "labels": []},
            },
        )
        r = client.post(
            "/api/v2/integrations/github/import",
            json={"issue_numbers": [12, 34]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_created"] == 2
        assert data["skipped"] == []
        titles = {c["title"] for c in data["created"]}
        assert titles == {"Fix login", "Dark mode"}

        # Tasks really exist in the workspace with the right linkage.
        from codeframe.core import tasks

        t12 = tasks.get_by_external_url(
            workspace, "https://github.com/acme/app/issues/12"
        )
        assert t12 is not None
        assert t12.title == "Fix login"
        assert "Repro steps" in t12.description
        assert t12.external_url == "https://github.com/acme/app/issues/12"
        assert t12.github_issue_number == 12

    def test_labels_appended_to_description(self, client, monkeypatch, workspace):
        _connect(client, monkeypatch)
        _mock_get_issue(
            monkeypatch,
            {5: {"title": "Tagged", "body": "Body text", "labels": ["bug", "ui"]}},
        )
        client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [5]}
        )
        from codeframe.core import tasks

        t = tasks.get_by_external_url(
            workspace, "https://github.com/acme/app/issues/5"
        )
        assert "bug" in t.description and "ui" in t.description

    def test_duplicate_import_is_skipped(self, client, monkeypatch, workspace):
        _connect(client, monkeypatch)
        _mock_get_issue(monkeypatch, {7: {"title": "Once", "body": "x"}})
        first = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [7]}
        )
        assert first.json()["total_created"] == 1

        second = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [7]}
        )
        body = second.json()
        assert body["total_created"] == 0
        assert body["skipped"] == [7]

        # Only one task exists for issue 7.
        from codeframe.core import tasks

        matching = [
            t for t in tasks.list_tasks(workspace) if t.github_issue_number == 7
        ]
        assert len(matching) == 1

    def test_repeated_number_in_payload_creates_one_task(
        self, client, monkeypatch, workspace
    ):
        """The same issue number twice in one request must create one task."""
        _connect(client, monkeypatch)
        _mock_get_issue(monkeypatch, {3: {"title": "Once", "body": "x"}})
        r = client.post(
            "/api/v2/integrations/github/import",
            json={"issue_numbers": [3, 3]},
        )
        body = r.json()
        assert body["total_created"] == 1
        assert body["skipped"] == [3]

        from codeframe.core import tasks

        matching = [
            t for t in tasks.list_tasks(workspace) if t.github_issue_number == 3
        ]
        assert len(matching) == 1

    def test_pull_request_number_is_rejected(self, client, monkeypatch, workspace):
        """A PR number is rejected (422) and creates no task."""
        _connect(client, monkeypatch)
        from codeframe.core.github_issues_service import NotAnIssueError
        from codeframe.ui.routers import github_integrations_v2

        async def pr_get_issue(pat, repo, number, **kwargs):
            raise NotAnIssueError(f"#{number} is a pull request, not an issue.")

        monkeypatch.setattr(github_integrations_v2, "get_issue", pr_get_issue)
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [50]}
        )
        assert r.status_code == 422

        from codeframe.core import tasks

        assert tasks.list_tasks(workspace) == []

    def test_import_invalidates_issue_cache(self, client, monkeypatch, workspace):
        """After import, the browse cache for the repo is cleared (#565)."""
        _clear_issue_cache()
        _connect(client, monkeypatch)
        # Prime the issue-list cache via the browse endpoint.
        _mock_list_issues(monkeypatch, result=([], 0))
        client.get("/api/v2/integrations/github/issues")
        from codeframe.ui.routers import github_integrations_v2

        assert len(github_integrations_v2._ISSUE_CACHE) > 0

        _mock_get_issue(monkeypatch, {1: {"title": "One", "body": "x"}})
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [1]}
        )
        assert r.json()["total_created"] == 1
        # The repo's cached listings were dropped.
        assert all(
            not k.startswith("acme/app|")
            for k in github_integrations_v2._ISSUE_CACHE
        )

    def test_skipped_only_import_also_invalidates_cache(
        self, client, monkeypatch, workspace
    ):
        """Even an all-skipped import drops the stale browse cache (#565)."""
        _clear_issue_cache()
        _connect(client, monkeypatch)
        # Pre-create the task so the import will skip it.
        from codeframe.core import tasks

        tasks.create(
            workspace,
            title="Already here",
            github_issue_number=1,
            external_url="https://github.com/acme/app/issues/1",
        )
        # Prime the browse cache.
        _mock_list_issues(monkeypatch, result=([], 0))
        client.get("/api/v2/integrations/github/issues")
        from codeframe.ui.routers import github_integrations_v2

        assert len(github_integrations_v2._ISSUE_CACHE) > 0

        _mock_get_issue(monkeypatch, {1: {"title": "Already here", "body": "x"}})
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [1]}
        )
        assert r.json()["total_created"] == 0
        assert r.json()["skipped"] == [1]
        assert all(
            not k.startswith("acme/app|")
            for k in github_integrations_v2._ISSUE_CACHE
        )

    def test_malformed_saved_repo_maps_to_409(self, client, monkeypatch, workspace):
        """A malformed stored repo slug surfaces as a 409, not a 500."""
        _connect(client, monkeypatch)
        from codeframe.ui.routers import github_integrations_v2

        async def bad_repo(pat, repo, number, **kwargs):
            raise ValueError("Invalid repository format: 'acme'. Expected 'owner/repo'.")

        monkeypatch.setattr(github_integrations_v2, "get_issue", bad_repo)
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [1]}
        )
        assert r.status_code == 409

    def test_create_failure_rolls_back_partial_import(
        self, client, monkeypatch, workspace
    ):
        """A mid-create DB error rolls back already-created tasks (all-or-nothing)."""
        _connect(client, monkeypatch)
        _mock_get_issue(
            monkeypatch,
            {
                1: {"title": "One", "body": "a"},
                2: {"title": "Two", "body": "b"},
                3: {"title": "Three", "body": "c"},
            },
        )

        import sqlite3 as _sqlite3

        from codeframe.core import tasks as tasks_mod

        real_create = tasks_mod.create
        calls = {"n": 0}

        def flaky_create(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 3:  # fail on the third create
                raise _sqlite3.OperationalError("database is locked")
            return real_create(*args, **kwargs)

        monkeypatch.setattr(
            "codeframe.ui.routers.github_integrations_v2.tasks.create", flaky_create
        )
        # The server raises a 500; TestClient re-raises it. The endpoint rolls
        # back the already-created tasks before the error propagates.
        with pytest.raises(_sqlite3.OperationalError):
            client.post(
                "/api/v2/integrations/github/import",
                json={"issue_numbers": [1, 2, 3]},
            )
        # The two tasks created before the failure must have been rolled back.
        assert tasks_mod.list_tasks(workspace) == []

    def test_missing_issue_number_maps_to_404(self, client, monkeypatch, workspace):
        """A stale/typo'd issue number is a client error (404), not a 502."""
        _connect(client, monkeypatch)
        from codeframe.core.github_issues_service import IssueNotFoundError
        from codeframe.ui.routers import github_integrations_v2

        async def missing(pat, repo, number, **kwargs):
            raise IssueNotFoundError(f"Issue #{number} was not found in '{repo}'.")

        monkeypatch.setattr(github_integrations_v2, "get_issue", missing)
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [9999]}
        )
        assert r.status_code == 404
        from codeframe.core import tasks

        assert tasks.list_tasks(workspace) == []

    def test_fetch_failure_creates_no_tasks(self, client, monkeypatch, workspace):
        """A mid-batch fetch error aborts cleanly — no partial tasks created."""
        _connect(client, monkeypatch)

        from codeframe.core.github_connect_service import GitHubConnectError
        from codeframe.ui.routers import github_integrations_v2

        async def flaky_get_issue(pat, repo, number, **kwargs):
            if number == 2:
                raise GitHubConnectError("issue 2 is inaccessible")
            return {
                "number": number,
                "title": f"Issue {number}",
                "body": "x",
                "labels": [],
                "html_url": f"https://github.com/acme/app/issues/{number}",
            }

        monkeypatch.setattr(
            github_integrations_v2, "get_issue", flaky_get_issue
        )
        r = client.post(
            "/api/v2/integrations/github/import",
            json={"issue_numbers": [1, 2, 3]},
        )
        assert r.status_code == 502
        # The earlier valid issue (#1) must NOT have been created.
        from codeframe.core import tasks

        assert tasks.list_tasks(workspace) == []

    def test_same_issue_number_different_repo_is_not_skipped(
        self, client, monkeypatch, workspace
    ):
        """After reconnecting to another repo, the same issue number imports."""
        _connect(client, monkeypatch, repo="acme/app")
        _mock_get_issue(monkeypatch, {12: {"title": "acme 12", "body": "x"}})
        client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [12]}
        )

        # Reconnect the same workspace to a different repo and import its #12.
        _connect(client, monkeypatch, repo="other/app")
        _mock_get_issue(monkeypatch, {12: {"title": "other 12", "body": "y"}})
        r = client.post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [12]}
        )
        assert r.json()["total_created"] == 1
        assert r.json()["skipped"] == []

        from codeframe.core import tasks

        titles = {t.title for t in tasks.list_tasks(workspace)}
        assert {"acme 12", "other 12"} <= titles


