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
        assert data["workspace_root"] == "/tmp/elsewhere"
        assert data["default_branch"] == "develop"
        assert data["auto_detect_tech_stack"] is False
        assert data["tech_stack_override"] == "Python with uv, FastAPI"


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
        assert saved == body

    def test_put_round_trip(self, test_client):
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
        assert get_resp.json() == body

    def test_put_empty_default_branch_rejected(self, test_client):
        body = {
            "workspace_root": "/tmp/proj",
            "default_branch": "",
            "auto_detect_tech_stack": True,
            "tech_stack_override": None,
        }
        response = test_client.put("/api/v2/workspaces/config", json=body)
        assert response.status_code == 422
