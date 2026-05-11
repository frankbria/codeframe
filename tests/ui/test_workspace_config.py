"""Tests for workspace config endpoints (issue #556).

Covers:
- GET /api/v2/workspaces/config returns sensible defaults when no file exists
- PUT /api/v2/workspaces/config persists to .codeframe/workspace_config.json
- Round-trip
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2


@pytest.fixture
def test_workspace():
    """Create a temporary workspace for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    workspace_path = temp_dir / "test_workspace"
    workspace_path.mkdir(parents=True, exist_ok=True)

    from codeframe.core.workspace import create_or_load_workspace

    workspace = create_or_load_workspace(workspace_path)

    yield workspace

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_client(test_workspace):
    """FastAPI TestClient with workspace_v2 router and workspace override."""
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import workspace_v2

    app = FastAPI()
    app.include_router(workspace_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    client = TestClient(app)
    client.workspace = test_workspace
    return client


class TestGetWorkspaceConfig:
    """Tests for GET /api/v2/workspaces/config."""

    def test_returns_defaults_when_no_config(self, test_client, test_workspace):
        response = test_client.get("/api/v2/workspaces/config")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_root"] == str(test_workspace.repo_path)
        assert data["default_branch"] == "main"
        assert data["auto_detect_tech_stack"] is True
        assert data["tech_stack_override"] is None

    def test_corrupted_json_falls_back_to_defaults(self, test_client, test_workspace):
        """Truncated/invalid JSON should not 500 — falls back to defaults."""
        config_path = test_workspace.state_dir / "workspace_config.json"
        config_path.write_text("{ not valid json")
        response = test_client.get("/api/v2/workspaces/config")
        assert response.status_code == 200
        data = response.json()
        assert data["default_branch"] == "main"
        assert data["auto_detect_tech_stack"] is True

    def test_returns_persisted_config(self, test_client, test_workspace):
        config_path = test_workspace.state_dir / "workspace_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "workspace_root": "/tmp/elsewhere",
                    "default_branch": "develop",
                    "auto_detect_tech_stack": False,
                    "tech_stack_override": "Python with uv, FastAPI",
                }
            )
        )
        response = test_client.get("/api/v2/workspaces/config")
        assert response.status_code == 200
        data = response.json()
        # workspace_root is display-only — server overrides any stored value
        # with the live workspace path so it can never drift.
        assert data["workspace_root"] == str(test_workspace.repo_path)
        assert data["default_branch"] == "develop"
        assert data["auto_detect_tech_stack"] is False
        assert data["tech_stack_override"] == "Python with uv, FastAPI"

    def test_workspace_root_always_reflects_live_path(self, test_client, test_workspace):
        """Regression: stored workspace_root must never be returned to the
        client — the live workspace.repo_path always wins."""
        config_path = test_workspace.state_dir / "workspace_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "workspace_root": "/stale/path/that/does/not/exist",
                    "default_branch": "main",
                    "auto_detect_tech_stack": True,
                    "tech_stack_override": None,
                }
            )
        )
        data = test_client.get("/api/v2/workspaces/config").json()
        assert data["workspace_root"] == str(test_workspace.repo_path)


class TestPutWorkspaceConfig:
    """Tests for PUT /api/v2/workspaces/config."""

    def test_put_persists_config(self, test_client, test_workspace):
        body = {
            "workspace_root": "/tmp/new",
            "default_branch": "release",
            "auto_detect_tech_stack": False,
            "tech_stack_override": "Rust",
        }
        response = test_client.put("/api/v2/workspaces/config", json=body)
        assert response.status_code == 200

        config_path = test_workspace.state_dir / "workspace_config.json"
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        # workspace_root in the request is dropped; the live path is stored
        assert saved["workspace_root"] == str(test_workspace.repo_path)
        assert saved["default_branch"] == body["default_branch"]
        assert saved["auto_detect_tech_stack"] == body["auto_detect_tech_stack"]
        assert saved["tech_stack_override"] == body["tech_stack_override"]

    def test_put_round_trip(self, test_client, test_workspace):
        body = {
            "workspace_root": "/tmp/proj",
            "default_branch": "main",
            "auto_detect_tech_stack": True,
            "tech_stack_override": None,
        }
        put_resp = test_client.put("/api/v2/workspaces/config", json=body)
        assert put_resp.status_code == 200

        get_resp = test_client.get("/api/v2/workspaces/config")
        assert get_resp.status_code == 200
        data = get_resp.json()
        # workspace_root is display-only: any stored value is overridden by
        # the live workspace path on GET.
        assert data["workspace_root"] == str(test_workspace.repo_path)
        assert data["default_branch"] == body["default_branch"]
        assert data["auto_detect_tech_stack"] == body["auto_detect_tech_stack"]
        assert data["tech_stack_override"] == body["tech_stack_override"]

    def test_put_ignores_client_workspace_root(self, test_client, test_workspace):
        """A client cannot relocate the workspace via PUT: workspace_root in
        the request is dropped, and the stored value is always the live
        workspace.repo_path. PUT and GET stay consistent."""
        body = {
            "workspace_root": "/attacker-controlled/path",
            "default_branch": "main",
            "auto_detect_tech_stack": True,
            "tech_stack_override": None,
        }
        put_resp = test_client.put("/api/v2/workspaces/config", json=body)
        assert put_resp.status_code == 200
        assert put_resp.json()["workspace_root"] == str(test_workspace.repo_path)

        # Persisted file reflects the live path, not the client-sent one
        saved = json.loads((test_workspace.state_dir / "workspace_config.json").read_text())
        assert saved["workspace_root"] == str(test_workspace.repo_path)

    def test_put_empty_default_branch_rejected(self, test_client):
        body = {
            "workspace_root": "/tmp/proj",
            "default_branch": "",
            "auto_detect_tech_stack": True,
            "tech_stack_override": None,
        }
        response = test_client.put("/api/v2/workspaces/config", json=body)
        assert response.status_code == 422
