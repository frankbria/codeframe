"""Tests for PROOF9 config endpoints (issue #556).

Covers:
- GET /api/v2/proof/config returns defaults when no config file exists
- PUT /api/v2/proof/config persists settings to .codeframe/proof_config.json
- Round-trip: PUT then GET returns the saved config
- Invalid gate names are rejected with 422
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
    """Create a FastAPI TestClient with proof_v2 router and workspace override."""
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import proof_v2

    app = FastAPI()
    app.include_router(proof_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    client = TestClient(app)
    client.workspace = test_workspace
    return client


class TestGetProofConfig:
    """Tests for GET /api/v2/proof/config."""

    def test_returns_defaults_when_no_config(self, test_client):
        """All 9 gates enabled and strict by default when no file exists."""
        response = test_client.get("/api/v2/proof/config")
        assert response.status_code == 200
        data = response.json()
        assert set(data["enabled_gates"]) == {
            "unit",
            "contract",
            "e2e",
            "visual",
            "a11y",
            "perf",
            "sec",
            "demo",
            "manual",
        }
        assert data["strictness"] == "strict"

    def test_returns_existing_config(self, test_client, test_workspace):
        """GET returns the persisted config."""
        config_path = test_workspace.state_dir / "proof_config.json"
        config_path.write_text(
            json.dumps({"enabled_gates": ["unit", "sec"], "strictness": "warn"})
        )
        response = test_client.get("/api/v2/proof/config")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled_gates"] == ["unit", "sec"]
        assert data["strictness"] == "warn"


class TestPutProofConfig:
    """Tests for PUT /api/v2/proof/config."""

    def test_put_persists_config(self, test_client, test_workspace):
        body = {"enabled_gates": ["unit", "e2e", "sec"], "strictness": "warn"}
        response = test_client.put("/api/v2/proof/config", json=body)
        assert response.status_code == 200

        config_path = test_workspace.state_dir / "proof_config.json"
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["enabled_gates"] == ["unit", "e2e", "sec"]
        assert saved["strictness"] == "warn"

    def test_put_round_trip(self, test_client):
        body = {"enabled_gates": ["unit"], "strictness": "warn"}
        put_resp = test_client.put("/api/v2/proof/config", json=body)
        assert put_resp.status_code == 200

        get_resp = test_client.get("/api/v2/proof/config")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["enabled_gates"] == ["unit"]
        assert data["strictness"] == "warn"

    def test_put_rejects_unknown_gate(self, test_client):
        body = {"enabled_gates": ["unit", "bogus_gate"], "strictness": "strict"}
        response = test_client.put("/api/v2/proof/config", json=body)
        assert response.status_code == 422

    def test_put_rejects_invalid_strictness(self, test_client):
        body = {"enabled_gates": ["unit"], "strictness": "lenient"}
        response = test_client.put("/api/v2/proof/config", json=body)
        assert response.status_code == 422

    def test_put_allows_empty_gate_list(self, test_client):
        """Disabling all gates is allowed (only strictness matters then)."""
        body = {"enabled_gates": [], "strictness": "strict"}
        response = test_client.put("/api/v2/proof/config", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["enabled_gates"] == []
