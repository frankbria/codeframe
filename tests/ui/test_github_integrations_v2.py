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
