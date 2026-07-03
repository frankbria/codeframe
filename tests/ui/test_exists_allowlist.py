"""GET /api/v2/workspaces/exists must honor the workspace allowlist (#719 / P0.8).

Previously it resolved a raw client path and returned existence + the resolved
absolute path with no allowlist check — a filesystem-existence oracle and path
leak for any authenticated user. With WORKSPACE_ROOT set, out-of-root probes
must 403 and never echo the resolved path.
"""

import pytest
from fastapi.testclient import TestClient

from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


def _client():
    from codeframe.ui import server
    return TestClient(server.app)


class TestExistsAllowlist:
    def test_out_of_root_probe_rejected(self, tmp_path, monkeypatch):
        base = tmp_path / "roots"
        base.mkdir()
        monkeypatch.setenv("WORKSPACE_ROOT", str(base))
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        r = _client().get("/api/v2/workspaces/exists", params={"repo_path": "/etc"})
        assert r.status_code == 403
        # The resolved absolute path must not be leaked.
        assert "/etc" not in str(r.json())

    def test_in_root_path_allowed(self, tmp_path, monkeypatch):
        base = tmp_path / "roots"
        proj = base / "proj"
        proj.mkdir(parents=True)
        create_or_load_workspace(proj)
        monkeypatch.setenv("WORKSPACE_ROOT", str(base))
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        r = _client().get("/api/v2/workspaces/exists", params={"repo_path": str(proj)})
        assert r.status_code == 200
        assert r.json()["exists"] is True

    def test_traversal_escape_rejected(self, tmp_path, monkeypatch):
        base = tmp_path / "roots"
        base.mkdir()
        monkeypatch.setenv("WORKSPACE_ROOT", str(base))
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        r = _client().get(
            "/api/v2/workspaces/exists", params={"repo_path": str(base / ".." / "escape")}
        )
        assert r.status_code == 403

    def test_hosted_mode_rejects_probe(self, tmp_path, monkeypatch):
        """Hosted mode confines each user to <root>/<user_id>; with auth off in
        the test suite (user_id=None) any probe fails closed with 403."""
        base = tmp_path / "roots"
        (base / "proj").mkdir(parents=True)
        create_or_load_workspace(base / "proj")
        monkeypatch.setenv("WORKSPACE_ROOT", str(base))
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
        r = _client().get("/api/v2/workspaces/exists", params={"repo_path": str(base / "proj")})
        assert r.status_code == 403

    def test_no_root_self_hosted_unchanged(self, tmp_path, monkeypatch):
        """Self-hosted default (no WORKSPACE_ROOT): still works (single trust domain)."""
        proj = tmp_path / "proj"
        proj.mkdir()
        create_or_load_workspace(proj)
        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
        r = _client().get("/api/v2/workspaces/exists", params={"repo_path": str(proj)})
        assert r.status_code == 200
        assert r.json()["exists"] is True
