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


@pytest.fixture
def temp_credentials_dir(tmp_path, monkeypatch):
    """Provide an isolated CredentialManager backed by a temp dir.

    Patches the settings_v2 dependency so endpoints use a clean store
    that does not touch the developer's real keyring or ~/.codeframe.
    Also clears the three target env vars so source detection is deterministic.
    """
    from codeframe.core.credentials import CredentialManager, CredentialStore

    # Force file-backed store so tests are independent of any system keyring.
    store = CredentialStore(storage_dir=tmp_path)
    store._keyring_available = False
    manager = CredentialManager.__new__(CredentialManager)
    manager._store = store

    # Clear env vars so stored/none sources are detected reliably.
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    yield manager


@pytest.fixture
def keys_client(temp_credentials_dir):
    """TestClient where the credential manager dependency is overridden."""
    from codeframe.ui.routers import settings_v2

    app = FastAPI()
    app.include_router(settings_v2.router)

    app.dependency_overrides[settings_v2.get_credential_manager] = (
        lambda: temp_credentials_dir
    )
    yield TestClient(app)


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


# ============================================================================
# API Key Management (issue #555)
# ============================================================================


VALID_ANTHROPIC = "sk-ant-api03-" + "x" * 32
VALID_OPENAI = "sk-proj-" + "x" * 32
VALID_GITHUB = "ghp_" + "x" * 36


class TestSettingsV2KeysStatus:
    """Tests for GET /api/v2/settings/keys."""

    def test_returns_three_providers_when_empty(self, keys_client):
        response = keys_client.get("/api/v2/settings/keys")
        assert response.status_code == 200
        data = response.json()
        providers = {entry["provider"] for entry in data}
        assert providers == {"LLM_ANTHROPIC", "LLM_OPENAI", "GIT_GITHUB"}
        for entry in data:
            assert entry["stored"] is False
            assert entry["source"] == "none"
            assert entry["last_four"] is None

    def test_status_reports_stored_source(self, keys_client):
        keys_client.put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC}
        )
        response = keys_client.get("/api/v2/settings/keys")
        anth = next(e for e in response.json() if e["provider"] == "LLM_ANTHROPIC")
        assert anth["stored"] is True
        assert anth["source"] == "stored"
        assert anth["last_four"] == VALID_ANTHROPIC[-4:]

    def test_status_reports_environment_source(self, keys_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env-12345678")
        response = keys_client.get("/api/v2/settings/keys")
        anth = next(e for e in response.json() if e["provider"] == "LLM_ANTHROPIC")
        assert anth["stored"] is True
        assert anth["source"] == "environment"
        assert anth["last_four"] == "5678"

    def test_status_never_returns_plaintext(self, keys_client):
        keys_client.put(
            "/api/v2/settings/keys/LLM_OPENAI", json={"value": VALID_OPENAI}
        )
        response = keys_client.get("/api/v2/settings/keys")
        body_text = response.text
        assert VALID_OPENAI not in body_text
        assert VALID_OPENAI[5:] not in body_text


class TestSettingsV2KeysStore:
    """Tests for PUT /api/v2/settings/keys/{provider}."""

    def test_store_persists_credential(self, keys_client, temp_credentials_dir):
        response = keys_client.put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stored"] is True
        assert data["source"] == "stored"
        assert data["last_four"] == VALID_ANTHROPIC[-4:]

        from codeframe.core.credentials import CredentialProvider

        assert (
            temp_credentials_dir.get_credential(CredentialProvider.LLM_ANTHROPIC)
            == VALID_ANTHROPIC
        )

    def test_store_rejects_invalid_format(self, keys_client):
        response = keys_client.put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": "not-a-real-key"}
        )
        assert response.status_code == 400

    def test_store_rejects_unknown_provider(self, keys_client):
        response = keys_client.put(
            "/api/v2/settings/keys/EVIL_PROVIDER", json={"value": "x" * 30}
        )
        assert response.status_code in (400, 422)

    def test_store_rejects_empty_value(self, keys_client):
        response = keys_client.put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": ""}
        )
        assert response.status_code == 422

    def test_store_response_excludes_plaintext(self, keys_client):
        response = keys_client.put(
            "/api/v2/settings/keys/GIT_GITHUB", json={"value": VALID_GITHUB}
        )
        assert VALID_GITHUB not in response.text


class TestSettingsV2KeysDelete:
    """Tests for DELETE /api/v2/settings/keys/{provider}."""

    def test_delete_removes_credential(self, keys_client, temp_credentials_dir):
        keys_client.put(
            "/api/v2/settings/keys/LLM_OPENAI", json={"value": VALID_OPENAI}
        )
        response = keys_client.delete("/api/v2/settings/keys/LLM_OPENAI")
        assert response.status_code == 204

        from codeframe.core.credentials import CredentialProvider

        assert (
            temp_credentials_dir.get_credential(CredentialProvider.LLM_OPENAI) is None
        )

    def test_delete_is_idempotent(self, keys_client):
        # Deleting a non-existent credential should not raise.
        response = keys_client.delete("/api/v2/settings/keys/LLM_ANTHROPIC")
        assert response.status_code == 204

    def test_delete_rejects_unknown_provider(self, keys_client):
        response = keys_client.delete("/api/v2/settings/keys/EVIL_PROVIDER")
        assert response.status_code in (400, 422)


class TestSettingsV2VerifyKey:
    """Tests for POST /api/v2/settings/verify-key.

    Verification calls patch the underlying SDK / HTTP client so tests
    don't make real network requests.
    """

    def test_verify_returns_invalid_for_missing_key(self, keys_client):
        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "LLM_ANTHROPIC", "value": None},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "no" in data["message"].lower() or "missing" in data["message"].lower()

    def test_verify_anthropic_calls_messages_create(self, keys_client, monkeypatch):
        from codeframe.ui.routers import settings_v2

        called_with = {}

        class FakeMessages:
            def create(self_, **kwargs):
                called_with["kwargs"] = kwargs
                return {"id": "msg_test"}

        class FakeAnthropicClient:
            def __init__(self, api_key):
                called_with["key"] = api_key
                self.messages = FakeMessages()

        monkeypatch.setattr(settings_v2, "_AnthropicClient", FakeAnthropicClient)

        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "LLM_ANTHROPIC", "value": VALID_ANTHROPIC},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert called_with["key"] == VALID_ANTHROPIC
        assert called_with["kwargs"]["max_tokens"] == 1

    def test_verify_anthropic_handles_auth_error(self, keys_client, monkeypatch):
        from anthropic import AuthenticationError

        from codeframe.ui.routers import settings_v2

        class FakeMessages:
            def create(self_, **kwargs):
                # Construct the AuthenticationError without going through the
                # SDK's response machinery; only the message is asserted on.
                err = AuthenticationError.__new__(AuthenticationError)
                Exception.__init__(err, "401 unauthorized")
                raise err

        class FakeAnthropicClient:
            def __init__(self, api_key):
                self.messages = FakeMessages()

        monkeypatch.setattr(settings_v2, "_AnthropicClient", FakeAnthropicClient)

        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "LLM_ANTHROPIC", "value": "sk-ant-bad-key-1234567890"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "rejected" in data["message"].lower() or "401" in data["message"]

    def test_verify_uses_stored_when_value_omitted(self, keys_client, monkeypatch):
        from codeframe.ui.routers import settings_v2

        captured = {}

        class FakeMessages:
            def create(self_, **kwargs):
                return {"id": "msg_ok"}

        class FakeAnthropicClient:
            def __init__(self, api_key):
                captured["key"] = api_key
                self.messages = FakeMessages()

        monkeypatch.setattr(settings_v2, "_AnthropicClient", FakeAnthropicClient)

        keys_client.put(
            "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": VALID_ANTHROPIC}
        )
        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "LLM_ANTHROPIC", "value": None},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True
        assert captured["key"] == VALID_ANTHROPIC

    def test_verify_openai_calls_models_list(self, keys_client, monkeypatch):
        from codeframe.ui.routers import settings_v2

        class FakeOpenAIClient:
            def __init__(self, api_key):
                self.models = type("M", (), {"list": lambda self_: ["gpt-4"]})()

        monkeypatch.setattr(settings_v2, "_OpenAIClient", FakeOpenAIClient)

        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "LLM_OPENAI", "value": VALID_OPENAI},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_verify_github_uses_http(self, keys_client, monkeypatch):
        from codeframe.ui.routers import settings_v2

        async def fake_check_github(token: str) -> tuple[bool, str]:
            assert token == VALID_GITHUB
            return True, "ok"

        monkeypatch.setattr(settings_v2, "_check_github_token", fake_check_github)

        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "GIT_GITHUB", "value": VALID_GITHUB},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True

    def test_verify_github_handles_failure(self, keys_client, monkeypatch):
        from codeframe.ui.routers import settings_v2

        async def fake_check_github(token: str) -> tuple[bool, str]:
            return False, "401 Unauthorized"

        monkeypatch.setattr(settings_v2, "_check_github_token", fake_check_github)

        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "GIT_GITHUB", "value": VALID_GITHUB},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "401" in data["message"]

    def test_verify_rejects_unknown_provider(self, keys_client):
        response = keys_client.post(
            "/api/v2/settings/verify-key",
            json={"provider": "EVIL", "value": "x"},
        )
        assert response.status_code == 422
