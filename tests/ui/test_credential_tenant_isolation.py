"""Cross-tenant isolation for per-user credentials (issue #790).

With per-user credential scoping, each authenticated principal operates on its
own credential store. These tests wire the routers exactly as production does —
``get_credential_manager(auth)`` builds ``CredentialManager(user_id=...)`` —
and assert that tenant A's keys/PAT are invisible to tenant B across every
credential surface: key status, store/delete, verify-key fallback, GitHub
connect/status/disconnect, and the issue-list cache.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from codeframe.auth.dependencies import require_auth

pytestmark = pytest.mark.v2

VALID_ANTHROPIC_A = "sk-ant-test-" + "a" * 20
VALID_ANTHROPIC_B = "sk-ant-test-" + "b" * 20
VALID_GITHUB_A = "ghp_test" + "a" * 20
VALID_GITHUB_B = "ghp_test" + "b" * 20


def _make_file_backed_manager(storage_dir, user_id: Optional[int]):
    """CredentialManager over an isolated per-user file store (no keyring)."""
    from codeframe.core.credentials import CredentialManager, CredentialStore

    store = CredentialStore(storage_dir=storage_dir, user_id=user_id)
    store._keyring_available = False
    mgr = CredentialManager.__new__(CredentialManager)
    mgr._store = store
    return mgr


@pytest.fixture
def tenants(tmp_path, monkeypatch):
    """Two-tenant app: per-user managers + per-user workspaces.

    ``as_user(uid)`` points the auth override at that principal; the manager
    and workspace overrides derive from the same auth dict, mirroring the
    production dependency wiring.
    """
    from codeframe.core.credentials import CredentialProvider

    for provider in CredentialProvider:
        monkeypatch.delenv(provider.env_var, raising=False)

    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import github_integrations_v2, settings_v2

    github_integrations_v2._ISSUE_CACHE.clear()

    app = FastAPI()
    app.include_router(settings_v2.router)
    app.include_router(github_integrations_v2.router)

    managers: dict = {}
    workspaces: dict = {}

    def _manager_dep(auth: dict = Depends(require_auth)):
        uid = auth.get("user_id")
        if uid not in managers:
            managers[uid] = _make_file_backed_manager(tmp_path / "creds", uid)
        return managers[uid]

    def _workspace_dep(auth: dict = Depends(require_auth)):
        from codeframe.core.workspace import Workspace

        uid = auth.get("user_id")
        if uid not in workspaces:
            ws_path = tmp_path / "ws" / str(uid)
            state_dir = ws_path / ".codeframe"
            state_dir.mkdir(parents=True, exist_ok=True)
            # Lightweight Workspace: the integration config is a JSON file
            # under state_dir; full workspace init is unneeded here.
            workspaces[uid] = Workspace(
                id=f"test-ws-{uid}",
                repo_path=ws_path,
                state_dir=state_dir,
                created_at=datetime.now(timezone.utc),
            )
        return workspaces[uid]

    app.dependency_overrides[settings_v2.get_credential_manager] = _manager_dep
    app.dependency_overrides[settings_v2.get_credential_manager_readonly] = _manager_dep
    app.dependency_overrides[github_integrations_v2.get_credential_manager] = _manager_dep
    app.dependency_overrides[github_integrations_v2.get_credential_manager_readonly] = _manager_dep
    app.dependency_overrides[get_v2_workspace] = _workspace_dep

    client = TestClient(app)

    def as_user(user_id: Optional[int]) -> TestClient:
        app.dependency_overrides[require_auth] = lambda: {
            "type": "jwt",
            "user_id": user_id,
            "scopes": ["read", "write", "admin"],
        }
        return client

    yield SimpleNamespace(
        client=client, as_user=as_user, managers=managers, workspaces=workspaces
    )

    github_integrations_v2._ISSUE_CACHE.clear()


def _mock_validate_connection(monkeypatch):
    from codeframe.ui.routers import github_integrations_v2

    async def fake(pat, repo, **kwargs):
        return {
            "repo_full_name": repo,
            "owner_login": repo.split("/")[0],
            "owner_avatar_url": "https://avatars/1",
        }

    monkeypatch.setattr(github_integrations_v2, "validate_connection", fake)


class TestManagerDependencyScoping:
    """The production dependency builds the manager from auth["user_id"]."""

    class _FakeCM:
        def __init__(self, storage_dir=None, user_id=None, migrate=True):
            self.user_id = user_id

    def test_settings_manager_dep_scopes_to_auth_user(self, monkeypatch):
        from codeframe.ui.routers import settings_v2

        monkeypatch.setattr(settings_v2, "CredentialManager", self._FakeCM)
        manager = settings_v2.get_credential_manager(auth={"user_id": 7})
        assert manager.user_id == 7

    def test_settings_manager_dep_machine_wide_when_no_user(self, monkeypatch):
        from codeframe.ui.routers import settings_v2

        monkeypatch.setattr(settings_v2, "CredentialManager", self._FakeCM)
        manager = settings_v2.get_credential_manager(auth={"user_id": None})
        assert manager.user_id is None

    def test_github_manager_dep_scopes_to_auth_user(self, monkeypatch):
        from codeframe.ui.routers import github_integrations_v2

        monkeypatch.setattr(github_integrations_v2, "CredentialManager", self._FakeCM)
        manager = github_integrations_v2.get_credential_manager(auth={"user_id": 7})
        assert manager.user_id == 7


class TestKeyStatusIsolation:
    def test_tenant_b_sees_no_stored_keys_after_a_stores(self, tenants):
        r = tenants.as_user(1).put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC_A}
        )
        assert r.status_code == 200
        assert r.json()["stored"] is True

        for entry in tenants.as_user(2).get("/api/v2/settings/keys").json():
            assert entry["stored"] is False
            assert entry["source"] == "none"
            assert entry["last_four"] is None

        # Tenant A still sees its own key.
        a_keys = tenants.as_user(1).get("/api/v2/settings/keys").json()
        anth = next(e for e in a_keys if e["provider"] == "LLM_ANTHROPIC")
        assert anth["stored"] is True
        assert anth["source"] == "stored"
        assert anth["last_four"] == VALID_ANTHROPIC_A[-4:]

    def test_tenant_b_put_does_not_overwrite_a(self, tenants):
        tenants.as_user(1).put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC_A}
        )
        r = tenants.as_user(2).put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC_B}
        )
        assert r.status_code == 200

        a_keys = tenants.as_user(1).get("/api/v2/settings/keys").json()
        b_keys = tenants.as_user(2).get("/api/v2/settings/keys").json()
        a_anth = next(e for e in a_keys if e["provider"] == "LLM_ANTHROPIC")
        b_anth = next(e for e in b_keys if e["provider"] == "LLM_ANTHROPIC")
        assert a_anth["last_four"] == VALID_ANTHROPIC_A[-4:]
        assert b_anth["last_four"] == VALID_ANTHROPIC_B[-4:]

    def test_tenant_b_delete_does_not_touch_a(self, tenants):
        tenants.as_user(1).put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC_A}
        )

        # Idempotent 204 against B's own (empty) store.
        r = tenants.as_user(2).delete("/api/v2/settings/keys/LLM_ANTHROPIC")
        assert r.status_code == 204

        a_keys = tenants.as_user(1).get("/api/v2/settings/keys").json()
        anth = next(e for e in a_keys if e["provider"] == "LLM_ANTHROPIC")
        assert anth["stored"] is True

    def test_verify_key_fallback_does_not_read_other_tenant(
        self, tenants, monkeypatch
    ):
        from codeframe.ui.routers import settings_v2

        calls: list[str] = []

        async def fake_check(token: str):
            calls.append(token)
            return True, "ok"

        monkeypatch.setattr(settings_v2, "_check_github_token", fake_check)

        tenants.as_user(1).put(
            "/api/v2/settings/keys/GIT_GITHUB", json={"value": VALID_GITHUB_A}
        )

        # B has no stored key and no env var — the fallback must NOT find A's.
        r = tenants.as_user(2).post(
            "/api/v2/settings/verify-key",
            json={"provider": "GIT_GITHUB", "value": None},
        )
        assert r.status_code == 200
        assert r.json()["valid"] is False
        assert "no key" in r.json()["message"].lower()
        assert calls == []

        # A's fallback resolves A's own stored key.
        r = tenants.as_user(1).post(
            "/api/v2/settings/verify-key",
            json={"provider": "GIT_GITHUB", "value": None},
        )
        assert r.status_code == 200
        assert r.json()["valid"] is True
        assert calls == [VALID_GITHUB_A]


class TestGitHubIntegrationIsolation:
    def test_connect_status_disconnect_are_per_user(self, tenants, monkeypatch):
        _mock_validate_connection(monkeypatch)

        r = tenants.as_user(1).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_A, "repo": "acme/app"},
        )
        assert r.status_code == 200

        a_status = tenants.as_user(1).get("/api/v2/integrations/github/status").json()
        assert a_status["connected"] is True
        # B's own workspace + own (empty) credential store → not connected.
        b_status = tenants.as_user(2).get("/api/v2/integrations/github/status").json()
        assert b_status["connected"] is False

        # B disconnects (idempotent on B's side); A's connection is untouched.
        r = tenants.as_user(2).delete("/api/v2/integrations/github/disconnect")
        assert r.status_code == 204
        a_status = tenants.as_user(1).get("/api/v2/integrations/github/status").json()
        assert a_status["connected"] is True

    def test_b_connect_does_not_clobber_a_pat(self, tenants, monkeypatch):
        _mock_validate_connection(monkeypatch)

        tenants.as_user(1).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_A, "repo": "acme/app"},
        )
        tenants.as_user(2).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_B, "repo": "acme/app"},
        )

        from codeframe.core.credentials import CredentialProvider

        assert (
            tenants.managers[1].get_credential(CredentialProvider.GIT_GITHUB)
            == VALID_GITHUB_A
        )
        assert (
            tenants.managers[2].get_credential(CredentialProvider.GIT_GITHUB)
            == VALID_GITHUB_B
        )

    def test_b_disconnect_leaves_a_pat(self, tenants, monkeypatch):
        _mock_validate_connection(monkeypatch)

        tenants.as_user(1).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_A, "repo": "acme/app"},
        )
        tenants.as_user(2).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_B, "repo": "acme/app"},
        )

        r = tenants.as_user(2).delete("/api/v2/integrations/github/disconnect")
        assert r.status_code == 204

        from codeframe.core.credentials import CredentialProvider

        assert (
            tenants.managers[1].get_credential(CredentialProvider.GIT_GITHUB)
            == VALID_GITHUB_A
        )
        assert tenants.managers[2].get_credential(CredentialProvider.GIT_GITHUB) is None


class TestIssueCacheTenantSeparation:
    def test_issues_cache_is_separated_by_user(self, tenants, monkeypatch):
        """Two tenants browsing the same repo slug with different PATs must not
        share cached issue listings — the cache key carries the user."""
        from codeframe.ui.routers import github_integrations_v2

        _mock_validate_connection(monkeypatch)
        tenants.as_user(1).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_A, "repo": "acme/app"},
        )
        tenants.as_user(2).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_B, "repo": "acme/app"},
        )

        calls: list[str] = []

        async def fake_list_issues(pat, repo, **kwargs):
            calls.append(pat)
            number = 1 if pat == VALID_GITHUB_A else 2
            return (
                [
                    {
                        "number": number,
                        "title": f"issue seen by {pat[-4:]}",
                        "labels": [],
                        "assignee": None,
                        "created_at": "2026-01-01T00:00:00Z",
                        "html_url": f"https://github.com/{repo}/issues/{number}",
                    }
                ],
                1,
            )

        monkeypatch.setattr(github_integrations_v2, "list_issues", fake_list_issues)

        a_resp = tenants.as_user(1).get("/api/v2/integrations/github/issues")
        assert a_resp.status_code == 200
        assert a_resp.json()["issues"][0]["number"] == 1

        # Same query as B: must hit the service with B's PAT, not A's cache.
        b_resp = tenants.as_user(2).get("/api/v2/integrations/github/issues")
        assert b_resp.status_code == 200
        assert b_resp.json()["issues"][0]["number"] == 2

        assert calls == [VALID_GITHUB_A, VALID_GITHUB_B]


class TestIssueCacheInvalidationScoping:
    """Import-time cache invalidation is scoped to the calling user (#790).

    Cache keys end with ``|{user_id}``; A's import must not wipe B's cached
    listings for the same repo.
    """

    def test_invalidate_drops_only_calling_users_entries(self, tenants):
        from codeframe.ui.routers import github_integrations_v2 as gi

        gi._ISSUE_CACHE.clear()
        gi._issue_cache_set("acme/app|1|25|||1", "A-payload")
        gi._issue_cache_set("acme/app|1|25|||2", "B-payload")

        gi._issue_cache_invalidate("acme/app", 1)

        assert gi._issue_cache_get("acme/app|1|25|||1") is None
        assert gi._issue_cache_get("acme/app|1|25|||2") == "B-payload"

    def test_import_invalidates_own_cache_not_other_tenants(
        self, tenants, monkeypatch, tmp_path
    ):
        from codeframe.core.workspace import create_or_load_workspace
        from codeframe.ui.routers import github_integrations_v2 as gi

        # A's workspace needs a real task DB: import creates tasks in it.
        ws_path = tmp_path / "ws-a-real"
        ws_path.mkdir()
        tenants.workspaces[1] = create_or_load_workspace(ws_path)

        _mock_validate_connection(monkeypatch)
        tenants.as_user(1).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_A, "repo": "acme/app"},
        )
        tenants.as_user(2).post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB_B, "repo": "acme/app"},
        )

        async def fake_list_issues(pat, repo, **kwargs):
            return ([], 0)

        monkeypatch.setattr(gi, "list_issues", fake_list_issues)
        gi._ISSUE_CACHE.clear()
        tenants.as_user(1).get("/api/v2/integrations/github/issues")
        tenants.as_user(2).get("/api/v2/integrations/github/issues")
        assert any(k.endswith("|1") for k in gi._ISSUE_CACHE)
        assert any(k.endswith("|2") for k in gi._ISSUE_CACHE)

        async def fake_get_issue(pat, repo, number, **kwargs):
            return {
                "number": number,
                "title": "One",
                "body": "x",
                "labels": [],
                "html_url": f"https://github.com/{repo}/issues/{number}",
            }

        monkeypatch.setattr(gi, "get_issue", fake_get_issue)
        r = tenants.as_user(1).post(
            "/api/v2/integrations/github/import", json={"issue_numbers": [1]}
        )
        assert r.json()["total_created"] == 1

        assert not any(k.endswith("|1") for k in gi._ISSUE_CACHE)
        assert any(k.endswith("|2") for k in gi._ISSUE_CACHE)
