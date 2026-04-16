"""Integration tests for settings_v2 router.

Tests:
- GET /api/v2/settings returns defaults for empty workspace
- PUT /api/v2/settings persists new settings
- GET after PUT returns the saved settings (round-trip)
- PUT merges into existing EnvironmentConfig without losing other fields
"""

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
    """Create a FastAPI TestClient with settings_v2 router and workspace override."""
    from codeframe.ui.routers import settings_v2
    from codeframe.ui.dependencies import get_v2_workspace

    app = FastAPI()
    app.include_router(settings_v2.router)

    def get_test_workspace():
        return test_workspace

    app.dependency_overrides[get_v2_workspace] = get_test_workspace

    client = TestClient(app)
    client.workspace = test_workspace
    yield client


class TestSettingsV2Get:
    """Tests for GET /api/v2/settings."""

    def test_returns_defaults_when_no_config(self, test_client):
        """GET returns default settings for a workspace with no config file."""
        response = test_client.get("/api/v2/settings")
        assert response.status_code == 200
        data = response.json()

        # Maps to EnvironmentConfig.agent_budget.max_iterations (default 100)
        assert data["max_turns"] == 100
        assert data["max_cost_usd"] is None

        agent_types = {entry["agent_type"] for entry in data["agent_models"]}
        assert agent_types == {"claude_code", "codex", "opencode", "react"}

        for entry in data["agent_models"]:
            assert entry["default_model"] == ""

    def test_returns_existing_config(self, test_client, test_workspace):
        """GET returns saved settings from .codeframe/config.yaml."""
        from codeframe.core.config import (
            EnvironmentConfig,
            save_environment_config,
        )

        config = EnvironmentConfig()
        config.max_cost_usd = 5.50
        config.agent_type_models = {"claude_code": "claude-opus-4"}
        config.agent_budget.max_iterations = 42
        save_environment_config(test_workspace.repo_path, config)

        response = test_client.get("/api/v2/settings")
        assert response.status_code == 200
        data = response.json()

        assert data["max_turns"] == 42
        assert data["max_cost_usd"] == 5.50
        cc_entry = next(
            e for e in data["agent_models"] if e["agent_type"] == "claude_code"
        )
        assert cc_entry["default_model"] == "claude-opus-4"


class TestSettingsV2Put:
    """Tests for PUT /api/v2/settings."""

    def test_put_persists_settings(self, test_client, test_workspace):
        """PUT saves settings to .codeframe/config.yaml."""
        body = {
            "agent_models": [
                {"agent_type": "claude_code", "default_model": "claude-sonnet-4"},
                {"agent_type": "codex", "default_model": "gpt-4o"},
                {"agent_type": "opencode", "default_model": ""},
                {"agent_type": "react", "default_model": "claude-opus-4"},
            ],
            "max_turns": 30,
            "max_cost_usd": 10.0,
        }

        response = test_client.put("/api/v2/settings", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["max_turns"] == 30
        assert data["max_cost_usd"] == 10.0

        # Verify persisted to disk
        from codeframe.core.config import load_environment_config

        loaded = load_environment_config(test_workspace.repo_path)
        assert loaded is not None
        assert loaded.agent_budget.max_iterations == 30
        assert loaded.max_cost_usd == 10.0
        assert loaded.agent_type_models["claude_code"] == "claude-sonnet-4"
        assert loaded.agent_type_models["codex"] == "gpt-4o"
        assert loaded.agent_type_models["react"] == "claude-opus-4"

    def test_put_round_trip(self, test_client):
        """GET after PUT returns the saved settings."""
        body = {
            "agent_models": [
                {"agent_type": "claude_code", "default_model": "claude-opus-4"},
                {"agent_type": "codex", "default_model": ""},
                {"agent_type": "opencode", "default_model": ""},
                {"agent_type": "react", "default_model": ""},
            ],
            "max_turns": 25,
            "max_cost_usd": 7.5,
        }
        put_resp = test_client.put("/api/v2/settings", json=body)
        assert put_resp.status_code == 200

        get_resp = test_client.get("/api/v2/settings")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["max_turns"] == 25
        assert data["max_cost_usd"] == 7.5
        cc = next(e for e in data["agent_models"] if e["agent_type"] == "claude_code")
        assert cc["default_model"] == "claude-opus-4"

    def test_put_preserves_unrelated_config(self, test_client, test_workspace):
        """PUT does not destroy other EnvironmentConfig fields like package_manager."""
        from codeframe.core.config import (
            EnvironmentConfig,
            save_environment_config,
            load_environment_config,
        )

        # Pre-existing config with non-default fields
        existing = EnvironmentConfig()
        existing.package_manager = "poetry"
        existing.test_framework = "jest"
        save_environment_config(test_workspace.repo_path, existing)

        body = {
            "agent_models": [
                {"agent_type": "claude_code", "default_model": "claude-opus-4"},
                {"agent_type": "codex", "default_model": ""},
                {"agent_type": "opencode", "default_model": ""},
                {"agent_type": "react", "default_model": ""},
            ],
            "max_turns": 50,
            "max_cost_usd": None,
        }
        response = test_client.put("/api/v2/settings", json=body)
        assert response.status_code == 200

        loaded = load_environment_config(test_workspace.repo_path)
        assert loaded.package_manager == "poetry"
        assert loaded.test_framework == "jest"
        assert loaded.agent_budget.max_iterations == 50

    def test_put_validates_max_turns_positive(self, test_client):
        """PUT rejects max_turns <= 0."""
        body = {
            "agent_models": [
                {"agent_type": "claude_code", "default_model": ""},
                {"agent_type": "codex", "default_model": ""},
                {"agent_type": "opencode", "default_model": ""},
                {"agent_type": "react", "default_model": ""},
            ],
            "max_turns": 0,
            "max_cost_usd": None,
        }
        response = test_client.put("/api/v2/settings", json=body)
        assert response.status_code == 422

    def test_put_rejects_unknown_agent_type(self, test_client):
        """Pydantic Literal rejects agent_types outside the supported set."""
        body = {
            "agent_models": [
                {"agent_type": "evil_bot", "default_model": "anything"},
            ],
            "max_turns": 20,
            "max_cost_usd": None,
        }
        response = test_client.put("/api/v2/settings", json=body)
        assert response.status_code == 422

    def test_put_skips_empty_model_strings(self, test_client, test_workspace):
        """PUT does not persist empty default_model entries to the YAML."""
        body = {
            "agent_models": [
                {"agent_type": "claude_code", "default_model": "claude-opus-4"},
                {"agent_type": "codex", "default_model": ""},
                {"agent_type": "opencode", "default_model": ""},
                {"agent_type": "react", "default_model": ""},
            ],
            "max_turns": 20,
            "max_cost_usd": None,
        }
        response = test_client.put("/api/v2/settings", json=body)
        assert response.status_code == 200

        from codeframe.core.config import load_environment_config

        loaded = load_environment_config(test_workspace.repo_path)
        # Only the non-empty entry is persisted.
        assert loaded.agent_type_models == {"claude_code": "claude-opus-4"}

    def test_get_handles_null_agent_budget(self, test_client, test_workspace):
        """GET tolerates legacy YAML that drops or nulls agent_budget."""
        from codeframe.core.config import (
            EnvironmentConfig,
            save_environment_config,
        )

        config = EnvironmentConfig()
        save_environment_config(test_workspace.repo_path, config)
        # Manually break agent_budget to simulate a hand-edited legacy file.
        import yaml

        config_path = test_workspace.repo_path / ".codeframe" / "config.yaml"
        with open(config_path) as f:
            data = yaml.safe_load(f)
        data["agent_budget"] = None
        with open(config_path, "w") as f:
            yaml.dump(data, f)

        response = test_client.get("/api/v2/settings")
        assert response.status_code == 200
        assert response.json()["max_turns"] == 100  # AgentBudgetConfig default
