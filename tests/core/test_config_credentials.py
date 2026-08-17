"""Tests for GlobalConfig credential integration.

Tests that GlobalConfig properly integrates with CredentialManager.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Mark all tests in this file as v2
pytestmark = pytest.mark.v2


class TestGlobalConfigCredentials:
    """Tests for credential loading in GlobalConfig."""

    def test_anthropic_key_from_env_var(self):
        """Anthropic key is loaded from environment variable."""
        from codeframe.core.config import GlobalConfig

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-env-key"}):
            config = GlobalConfig()
            assert config.anthropic_api_key == "sk-ant-env-key"

    def test_anthropic_key_from_credential_manager(self):
        """Anthropic key can be retrieved via credential manager."""
        from codeframe.core.config import GlobalConfig
        from codeframe.core.credentials import CredentialManager, CredentialProvider

        # Clear env var
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch.object(CredentialManager, "get_credential") as mock_get:
                mock_get.return_value = "sk-ant-stored-key"

                config = GlobalConfig()
                manager = CredentialManager()
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)

                assert value == "sk-ant-stored-key"

    def test_github_token_from_env_var(self):
        """GitHub token is loaded from environment variable."""
        from codeframe.core.config import GlobalConfig

        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test_token"}):
            config = GlobalConfig()
            assert config.github_token == "ghp_test_token"


class TestConfigGetCredential:
    """Tests for Config.get_credential helper method."""

    def test_get_credential_returns_value(self):
        """get_credential returns the credential value."""
        from codeframe.core.config import GlobalConfig
        from codeframe.core.credentials import CredentialProvider

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            config = GlobalConfig()
            # Use the credential manager to get the credential
            from codeframe.core.credentials import CredentialManager
            manager = CredentialManager()
            value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
            assert value == "sk-ant-test"

    def test_get_credential_returns_none_when_missing(self):
        """get_credential returns None when credential not found."""
        from codeframe.core.credentials import CredentialManager, CredentialProvider

        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with patch("codeframe.core.credentials.keyring") as mock_keyring:
                mock_keyring.get_keyring.return_value = MagicMock()
                mock_keyring.get_password.return_value = None

                manager = CredentialManager()
                value = manager.get_credential(CredentialProvider.LLM_ANTHROPIC)
                assert value is None
