"""Single-trust-domain enforcement (issue #718 / P0.7).

CodeFRAME's credential store is machine-wide (one LLM key set + one GitHub PAT
per host). That's fine for self-hosted (a single trust domain), but in hosted
multi-tenant mode it would let any tenant view/overwrite/delete another's
secrets. So credential + GitHub-PAT *mutation* endpoints fail closed in hosted
mode; tenants supply credentials via per-instance env vars instead.

Also verifies workspaces persist owner_user_id from the authenticated principal.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2


class TestForbidGuard:
    def test_raises_in_hosted_mode(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        from codeframe.ui.dependencies import forbid_shared_credentials_in_hosted_mode

        with pytest.raises(HTTPException) as exc:
            forbid_shared_credentials_in_hosted_mode()
        assert exc.value.status_code == 403

    def test_noop_in_self_hosted(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        from codeframe.ui.dependencies import forbid_shared_credentials_in_hosted_mode

        assert forbid_shared_credentials_in_hosted_mode() is None  # no raise


class TestCredentialEndpointHostedBlock:
    """conftest defaults auth OFF → synthetic admin principal, so these isolate
    the hosted-mode credential guard (not the scope/auth layer)."""

    def _client(self):
        from codeframe.ui import server

        return TestClient(server.app)

    def test_store_key_blocked_in_hosted_mode(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        r = self._client().put("/api/v2/settings/keys/openai", json={"value": "sk-x"})
        assert r.status_code == 403
        assert "hosted mode" in r.json().get("detail", "").lower()

    def test_delete_key_blocked_in_hosted_mode(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        r = self._client().delete("/api/v2/settings/keys/openai")
        assert r.status_code == 403

    def test_github_connect_blocked_in_hosted_mode(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        # The guard fires before workspace-allowlist resolution, so no
        # WORKSPACE_ROOT setup is needed.
        r = self._client().post(
            "/api/v2/integrations/github/connect", json={"repo": "o/r", "pat": "ghp_x"}
        )
        assert r.status_code == 403

    def test_github_disconnect_blocked_in_hosted_mode(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        r = self._client().delete("/api/v2/integrations/github/disconnect")
        assert r.status_code == 403

    def test_store_key_not_hosted_blocked_in_self_hosted(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        r = self._client().put("/api/v2/settings/keys/openai", json={"value": "sk-x"})
        # self-hosted: the hosted guard is a no-op; the request passes it and hits
        # value-format validation (400). It must never be the hosted-mode 403.
        assert r.status_code != 403, f"unexpected hosted-mode 403 in self-hosted: {r.json()}"


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
