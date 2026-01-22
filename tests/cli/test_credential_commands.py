"""Tests for CLI credential management commands.

Tests the `codeframe auth setup/list/validate/rotate/remove` commands.
"""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# Mark all tests in this file as v2
pytestmark = pytest.mark.v2


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_credential_manager():
    """Create a mock credential manager."""
    with patch("codeframe.cli.auth_commands.CredentialManager") as mock:
        manager_instance = MagicMock()
        mock.return_value = manager_instance
        yield manager_instance


class TestAuthSetup:
    """Tests for `codeframe auth setup` command."""

    def test_setup_prompts_for_provider(self, runner):
        """Setup prompts user to select provider type."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.validate_credential_format.return_value = True

            result = runner.invoke(
                app,
                ["auth", "setup"],
                input="1\nsk-ant-test-key-12345\n",  # Select Anthropic, enter key
            )

            # Should prompt for provider selection
            assert "provider" in result.output.lower() or "select" in result.output.lower()

    def test_setup_stores_valid_credential(self, runner):
        """Setup stores credential after validation."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.validate_credential_format.return_value = True

            result = runner.invoke(
                app,
                ["auth", "setup", "--provider", "anthropic", "--value", "sk-ant-test-key"],
            )

            mock_instance.set_credential.assert_called_once()

    def test_setup_rejects_invalid_format(self, runner):
        """Setup rejects credentials with invalid format."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.validate_credential_format.return_value = False

            result = runner.invoke(
                app,
                ["auth", "setup", "--provider", "anthropic", "--value", "bad"],
            )

            assert result.exit_code != 0 or "invalid" in result.output.lower()


class TestAuthList:
    """Tests for `codeframe auth list` command."""

    def test_list_shows_configured_credentials(self, runner):
        """List displays all configured credentials."""
        from codeframe.cli import app
        from codeframe.core.credentials import (
            CredentialInfo,
            CredentialProvider,
            CredentialSource,
        )

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.list_credentials.return_value = [
                CredentialInfo(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    source=CredentialSource.ENVIRONMENT,
                    masked_value="sk-a...1234",
                ),
                CredentialInfo(
                    provider=CredentialProvider.GIT_GITHUB,
                    source=CredentialSource.STORED,
                    masked_value="ghp_...abcd",
                ),
            ]

            result = runner.invoke(app, ["auth", "list"])

            assert result.exit_code == 0
            assert "anthropic" in result.output.lower() or "claude" in result.output.lower()
            assert "github" in result.output.lower()

    def test_list_shows_source_type(self, runner):
        """List indicates whether credential is from env or stored."""
        from codeframe.cli import app
        from codeframe.core.credentials import (
            CredentialInfo,
            CredentialProvider,
            CredentialSource,
        )

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.list_credentials.return_value = [
                CredentialInfo(
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    source=CredentialSource.ENVIRONMENT,
                    masked_value="sk-a...1234",
                ),
            ]

            result = runner.invoke(app, ["auth", "list"])

            assert result.exit_code == 0
            # Should indicate source is environment
            assert "env" in result.output.lower() or "environment" in result.output.lower()

    def test_list_empty_shows_message(self, runner):
        """List shows helpful message when no credentials configured."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.list_credentials.return_value = []

            result = runner.invoke(app, ["auth", "list"])

            assert result.exit_code == 0
            assert "no credentials" in result.output.lower() or "none" in result.output.lower()


class TestAuthValidate:
    """Tests for `codeframe auth validate` command."""

    def test_validate_checks_credential_health(self, runner):
        """Validate tests credential with provider API."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = "sk-ant-valid-key"

            with patch("codeframe.cli.auth_commands.validate_anthropic_credential") as mock_validate:
                mock_validate.return_value = (True, "Valid")

                result = runner.invoke(app, ["auth", "validate", "anthropic"])

                mock_validate.assert_called_once()
                assert result.exit_code == 0

    def test_validate_reports_invalid_credential(self, runner):
        """Validate reports failure for invalid credentials."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = "invalid-key"

            with patch("codeframe.cli.auth_commands.validate_anthropic_credential") as mock_validate:
                mock_validate.return_value = (False, "Authentication failed")

                result = runner.invoke(app, ["auth", "validate", "anthropic"])

                assert result.exit_code != 0

    def test_validate_missing_credential(self, runner):
        """Validate reports when credential not found."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = None

            result = runner.invoke(app, ["auth", "validate", "anthropic"])

            assert result.exit_code != 0
            # Check for "no credential configured" message
            assert "no credential" in result.output.lower() or "not configured" in result.output.lower()


class TestAuthRotate:
    """Tests for `codeframe auth rotate` command."""

    def test_rotate_replaces_credential(self, runner):
        """Rotate stores new credential value."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = "old-key"
            mock_instance.validate_credential_format.return_value = True

            # Use --force to skip API validation (which would fail without real credentials)
            result = runner.invoke(
                app,
                ["auth", "rotate", "anthropic", "--value", "sk-ant-new-key-12345", "--force"],
            )

            assert result.exit_code == 0, f"Command failed with: {result.output}"
            mock_instance.rotate_credential.assert_called_once()

    def test_rotate_validates_new_credential(self, runner):
        """Rotate validates new credential before storing."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = "old-key"
            mock_instance.validate_credential_format.return_value = False

            result = runner.invoke(
                app,
                ["auth", "rotate", "anthropic", "--value", "bad"],
            )

            # Should not rotate if validation fails
            mock_instance.rotate_credential.assert_not_called()

    def test_rotate_with_force_skips_validation(self, runner):
        """Rotate with --force skips API validation."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = "old-key"
            mock_instance.validate_credential_format.return_value = True

            result = runner.invoke(
                app,
                ["auth", "rotate", "anthropic", "--value", "sk-ant-new-key", "--force"],
            )

            mock_instance.rotate_credential.assert_called_once()


class TestAuthRemove:
    """Tests for `codeframe auth remove` command."""

    def test_remove_deletes_credential(self, runner):
        """Remove deletes stored credential."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance

            result = runner.invoke(
                app,
                ["auth", "remove", "anthropic", "--yes"],
            )

            mock_instance.delete_credential.assert_called_once()

    def test_remove_prompts_for_confirmation(self, runner):
        """Remove prompts for confirmation without --yes."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance

            # Input 'n' to decline
            result = runner.invoke(
                app,
                ["auth", "remove", "anthropic"],
                input="n\n",
            )

            mock_instance.delete_credential.assert_not_called()

    def test_remove_with_yes_skips_confirmation(self, runner):
        """Remove with --yes skips confirmation prompt."""
        from codeframe.cli import app

        with patch("codeframe.cli.auth_commands.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance

            result = runner.invoke(
                app,
                ["auth", "remove", "anthropic", "--yes"],
            )

            # Should delete without prompting
            mock_instance.delete_credential.assert_called_once()


class TestProviderNameMapping:
    """Tests for provider name resolution in CLI commands."""

    def test_anthropic_aliases(self, runner):
        """Various Anthropic aliases resolve correctly."""
        from codeframe.cli.auth_commands import resolve_provider_name
        from codeframe.core.credentials import CredentialProvider

        assert resolve_provider_name("anthropic") == CredentialProvider.LLM_ANTHROPIC
        assert resolve_provider_name("claude") == CredentialProvider.LLM_ANTHROPIC
        assert resolve_provider_name("ANTHROPIC") == CredentialProvider.LLM_ANTHROPIC

    def test_github_aliases(self, runner):
        """Various GitHub aliases resolve correctly."""
        from codeframe.cli.auth_commands import resolve_provider_name
        from codeframe.core.credentials import CredentialProvider

        assert resolve_provider_name("github") == CredentialProvider.GIT_GITHUB
        assert resolve_provider_name("gh") == CredentialProvider.GIT_GITHUB
        assert resolve_provider_name("GITHUB") == CredentialProvider.GIT_GITHUB

    def test_openai_aliases(self, runner):
        """Various OpenAI aliases resolve correctly."""
        from codeframe.cli.auth_commands import resolve_provider_name
        from codeframe.core.credentials import CredentialProvider

        assert resolve_provider_name("openai") == CredentialProvider.LLM_OPENAI
        assert resolve_provider_name("gpt") == CredentialProvider.LLM_OPENAI
        assert resolve_provider_name("gpt4") == CredentialProvider.LLM_OPENAI

    def test_invalid_provider_raises(self, runner):
        """Invalid provider name raises appropriate error."""
        from codeframe.cli.auth_commands import resolve_provider_name

        with pytest.raises(ValueError):
            resolve_provider_name("invalid-provider")
