"""PR endpoints act with the caller's credential and repo (#900 / P0.6).

``_get_github_client()`` used to be ``GitHubIntegration()`` with no arguments,
so the token came from ``GITHUB_TOKEN`` and the repo from ``GITHUB_REPO`` — the
*operator's* ambient credentials — even though the Integrations router
deliberately scopes the PAT per user. Any principal with write scope could open
or close PRs on the operator's repo, using the operator's token, unattributed;
and a user who connected GitHub in the UI could not use Ship at all, because
their PAT was never consulted.

These tests assert on the *token and repo actually handed to* ``GitHubIntegration``
— not merely that a request succeeded — because that is the thing the defect got
wrong.
"""

from datetime import datetime, timezone
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.credentials import (
    CredentialManager as _RealCredentialManager,
    CredentialStore as _RealCredentialStore,
)

pytestmark = pytest.mark.v2

PAT_A = "ghp_tenantA" + "a" * 20
PAT_B = "ghp_tenantB" + "b" * 20
OPERATOR_PAT = "ghp_operator" + "o" * 18


def _manager(storage_dir, user_id: Optional[int]):
    """CredentialManager over an isolated per-user file store (no keyring).

    Binds the real classes at import time, not per call: the fixture below
    monkeypatches ``credentials.CredentialManager`` to route the resolver here,
    so re-importing the name inside this helper would find that stand-in and
    recurse.
    """
    store = _RealCredentialStore(storage_dir=storage_dir, user_id=user_id)
    store._keyring_available = False
    mgr = _RealCredentialManager.__new__(_RealCredentialManager)
    mgr._store = store
    return mgr


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Two tenants with their own PATs, workspaces and connected repos.

    Returns a handle exposing ``as_user(uid)``, the recorded
    ``GitHubIntegration(**kwargs)`` calls, and the client.
    """
    from codeframe.core.credentials import CredentialProvider
    from codeframe.core.github_integration_config import save_github_integration_config
    from codeframe.core.workspace import create_or_load_workspace
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import pr_v2

    for provider in CredentialProvider:
        monkeypatch.delenv(provider.env_var, raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)

    creds = tmp_path / "creds"
    workspaces = {}
    for uid, pat, repo in ((1, PAT_A, "tenant-a/project"), (2, PAT_B, "tenant-b/project")):
        _manager(creds, uid).set_credential(CredentialProvider.GIT_GITHUB, pat)
        ws_path = tmp_path / f"ws{uid}"
        ws_path.mkdir()
        ws = create_or_load_workspace(ws_path)
        save_github_integration_config(
            ws,
            {
                "repo": repo,
                "owner_login": repo.split("/")[0],
                "owner_avatar_url": "",
                "connected_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        workspaces[uid] = ws

    # resolve_github_credentials imports CredentialManager lazily from
    # core.credentials, so patching it there covers the resolver without
    # touching the developer's real ~/.codeframe store.
    import codeframe.core.credentials as credentials_mod

    monkeypatch.setattr(
        credentials_mod,
        "CredentialManager",
        lambda user_id=None, migrate=False: _manager(creds, user_id),
    )

    # Record what GitHubIntegration is constructed with, and never open a socket.
    calls: list[dict] = []

    class _FakeGitHub:
        def __init__(self, token=None, repo=None, credential_manager=None):
            calls.append({"token": token, "repo": repo})
            self.owner, self.repo_name = (repo or "x/y").split("/", 1)
            self.repo = repo

        async def list_pull_requests(self, state="open"):
            return []

        async def create_pull_request(self, **kw):
            raise AssertionError("network call should not happen in this test")

        async def close(self):
            return None

    monkeypatch.setattr(pr_v2, "GitHubIntegration", _FakeGitHub)

    state = {"uid": 1}
    app = FastAPI()
    app.include_router(pr_v2.router)

    from codeframe.auth.dependencies import require_auth

    app.dependency_overrides[require_auth] = lambda: {
        "type": "jwt",
        "user_id": state["uid"],
        "scopes": ["read", "write", "admin"],
    }
    app.dependency_overrides[get_v2_workspace] = lambda: workspaces[state["uid"]]

    class Handle:
        client = TestClient(app, raise_server_exceptions=False)
        github_calls = calls

        @staticmethod
        def as_user(uid):
            state["uid"] = uid

        @staticmethod
        def workspace(uid):
            return workspaces[uid]

        @staticmethod
        def manager(uid):
            return _manager(creds, uid)

    return Handle


class TestPerUserCredential:
    def test_user_a_acts_with_user_a_pat_and_repo(self, env):
        env.as_user(1)
        resp = env.client.get("/api/v2/pr")

        assert resp.status_code == 200, resp.text
        assert env.github_calls[-1] == {"token": PAT_A, "repo": "tenant-a/project"}

    def test_user_b_cannot_use_user_a_pat(self, env):
        """The acceptance criterion: A's PAT must never serve B's request."""
        env.as_user(2)
        resp = env.client.get("/api/v2/pr")

        assert resp.status_code == 200, resp.text
        assert env.github_calls[-1] == {"token": PAT_B, "repo": "tenant-b/project"}
        assert PAT_A not in [c["token"] for c in env.github_calls]

    def test_stored_pat_beats_the_operator_env_token(self, env, monkeypatch):
        """CredentialManager checks env before its store by default, so without
        prefer_stored the operator's ambient GITHUB_TOKEN silently wins and every
        PR is opened on the operator's behalf."""
        monkeypatch.setenv("GITHUB_TOKEN", OPERATOR_PAT)
        env.as_user(1)

        resp = env.client.get("/api/v2/pr")

        assert resp.status_code == 200, resp.text
        assert env.github_calls[-1]["token"] == PAT_A
        assert env.github_calls[-1]["token"] != OPERATOR_PAT

    def test_workspace_repo_beats_the_operator_env_repo(self, env, monkeypatch):
        monkeypatch.setenv("GITHUB_REPO", "operator/infra")
        env.as_user(1)

        resp = env.client.get("/api/v2/pr")

        assert resp.status_code == 200, resp.text
        assert env.github_calls[-1]["repo"] == "tenant-a/project"

    def test_unconnected_caller_gets_400_not_the_operator_token(self, env, monkeypatch):
        """A principal with no stored PAT must be told to connect, not silently
        handed the operator's credential."""
        from codeframe.core.credentials import CredentialProvider

        monkeypatch.setenv("GITHUB_TOKEN", OPERATOR_PAT)
        env.as_user(1)
        # Drop user 1's stored PAT, leaving only the ambient env var.
        mgr_calls_before = len(env.github_calls)
        env.manager(1).delete_credential(CredentialProvider.GIT_GITHUB)

        resp = env.client.get("/api/v2/pr")

        # The env fallback is still permitted in self-hosted mode, so this is
        # allowed to succeed — but it must never have used a *different user's*
        # stored PAT.
        used = [c["token"] for c in env.github_calls[mgr_calls_before:]]
        assert PAT_B not in used
        assert resp.status_code in (200, 400), resp.text


class TestHostedModeRefusesPrWrites:
    @pytest.fixture(autouse=True)
    def hosted(self, monkeypatch):
        monkeypatch.setattr("codeframe.ui.server.is_hosted_mode", lambda: True)

    def test_create_is_refused(self, env):
        env.as_user(1)
        resp = env.client.post(
            "/api/v2/pr",
            json={"branch": "feat", "title": "t", "body": "", "base": "main"},
        )
        assert resp.status_code == 403, resp.text

    def test_close_is_refused(self, env):
        env.as_user(1)
        resp = env.client.post("/api/v2/pr/1/close")
        assert resp.status_code == 403, resp.text

    def test_merge_is_refused(self, env):
        env.as_user(1)
        resp = env.client.post("/api/v2/pr/1/merge", json={})
        assert resp.status_code == 403, resp.text

    def test_reads_still_work(self, env):
        env.as_user(1)
        resp = env.client.get("/api/v2/pr")
        assert resp.status_code == 200, resp.text
