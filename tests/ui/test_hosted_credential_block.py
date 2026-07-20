"""Per-user credentials in hosted mode (issue #790; supersedes the #718 block).

The #718 stopgap blocked credential + GitHub-PAT *mutation* endpoints in hosted
multi-tenant mode because the credential store was machine-wide. With per-user
credential scoping (#790) each tenant operates on their own store, so hosted
mode now ALLOWS these endpoints — the old 403 is gone. These tests pin that
behavior against the real server app with an isolated credential store.

Also verifies workspaces persist owner_user_id from the authenticated principal
(#718 workspace ownership — unrelated to the credential guard; kept intact).
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2

VALID_OPENAI = "sk-test-" + "x" * 20
VALID_GITHUB = "ghp_test" + "x" * 20


@pytest.fixture
def hosted_client(tmp_path, monkeypatch):
    """Real server app in hosted mode, backed by an isolated credential store.

    conftest leaves auth disabled (synthetic admin principal), so these tests
    isolate the hosted-mode credential behavior from the auth/scope layer.
    """
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")

    from codeframe.core.credentials import (
        CredentialManager,
        CredentialProvider,
        CredentialStore,
    )

    for provider in CredentialProvider:
        monkeypatch.delenv(provider.env_var, raising=False)

    from codeframe.core.workspace import Workspace
    from codeframe.ui import server
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import github_integrations_v2, settings_v2

    store = CredentialStore(storage_dir=tmp_path / "creds")
    store._keyring_available = False
    manager = CredentialManager.__new__(CredentialManager)
    manager._store = store

    # Lightweight Workspace: connect only writes the JSON config under state_dir.
    ws_path = tmp_path / "ws"
    state_dir = ws_path / ".codeframe"
    state_dir.mkdir(parents=True)
    workspace = Workspace(
        id="test-ws-hosted",
        repo_path=ws_path,
        state_dir=state_dir,
        created_at=datetime.now(timezone.utc),
    )

    app = server.app
    app.dependency_overrides[settings_v2.get_credential_manager] = lambda: manager
    app.dependency_overrides[settings_v2.get_credential_manager_readonly] = lambda: manager
    app.dependency_overrides[github_integrations_v2.get_credential_manager] = (
        lambda: manager
    )
    app.dependency_overrides[github_integrations_v2.get_credential_manager_readonly] = (
        lambda: manager
    )
    app.dependency_overrides[get_v2_workspace] = lambda: workspace

    yield TestClient(app)

    # Restore the shared app for other tests in this process.
    for dep in (
        settings_v2.get_credential_manager,
        settings_v2.get_credential_manager_readonly,
        github_integrations_v2.get_credential_manager,
        github_integrations_v2.get_credential_manager_readonly,
        get_v2_workspace,
    ):
        app.dependency_overrides.pop(dep, None)


class TestCredentialMutationAllowedInHostedMode:
    """Hosted mode no longer blocks per-user credential mutation (#790)."""

    def test_store_key_allowed_in_hosted_mode(self, hosted_client):
        r = hosted_client.put(
            "/api/v2/settings/keys/LLM_OPENAI", json={"value": VALID_OPENAI}
        )
        assert r.status_code == 200, r.text
        assert r.json()["stored"] is True
        assert r.json()["source"] == "stored"

    def test_delete_key_allowed_in_hosted_mode(self, hosted_client):
        hosted_client.put(
            "/api/v2/settings/keys/LLM_OPENAI", json={"value": VALID_OPENAI}
        )
        r = hosted_client.delete("/api/v2/settings/keys/LLM_OPENAI")
        assert r.status_code == 204, r.text

        keys = hosted_client.get("/api/v2/settings/keys").json()
        openai = next(e for e in keys if e["provider"] == "LLM_OPENAI")
        assert openai["stored"] is False

    def test_github_connect_allowed_in_hosted_mode(self, hosted_client, monkeypatch):
        from codeframe.ui.routers import github_integrations_v2

        async def fake_validate(pat, repo, **kwargs):
            return {
                "repo_full_name": repo,
                "owner_login": repo.split("/")[0],
                "owner_avatar_url": "https://avatars/1",
            }

        monkeypatch.setattr(github_integrations_v2, "validate_connection", fake_validate)

        r = hosted_client.post(
            "/api/v2/integrations/github/connect",
            json={"pat": VALID_GITHUB, "repo": "acme/app"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["connected"] is True

    def test_github_disconnect_allowed_in_hosted_mode(self, hosted_client):
        r = hosted_client.delete("/api/v2/integrations/github/disconnect")
        assert r.status_code == 204, r.text

    def test_self_hosted_mutation_still_allowed(self, hosted_client, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        r = hosted_client.put(
            "/api/v2/settings/keys/LLM_OPENAI", json={"value": VALID_OPENAI}
        )
        assert r.status_code == 200, r.text


class TestOwnerPersistence:
    def test_register_workspace_passes_owner_id(self, monkeypatch):
        """_register_workspace forwards the authenticated user_id to the registry."""
        from codeframe.ui.routers import workspace_v2

        captured = {}

        class _FakeRegistry:
            def upsert(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setattr(workspace_v2, "_get_registry", lambda request: _FakeRegistry())

        class _WS:
            from pathlib import Path as _P
            repo_path = _P("/tmp/demo-repo")
            tech_stack = "python"

        workspace_v2._register_workspace(request=None, workspace=_WS(), owner_user_id=42)
        assert captured["owner_user_id"] == 42
