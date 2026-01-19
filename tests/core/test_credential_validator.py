"""Tests for credential validation system.

Tests the pre-workflow credential validation functionality.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Mark all tests in this file as v2
pytestmark = pytest.mark.v2


class TestWorkflowValidation:
    """Tests for validate_workflow_credentials."""

    def test_agent_execution_requires_anthropic(self):
        """Agent execution workflow requires Anthropic credential."""
        from codeframe.core.credential_validator import (
            validate_workflow_credentials,
            WorkflowType,
        )

        with patch("codeframe.core.credential_validator.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = None

            result = validate_workflow_credentials(
                WorkflowType.AGENT_EXECUTION,
                credential_manager=mock_instance,
            )

            assert not result.is_valid
            assert len(result.errors) == 1
            assert result.errors[0].error_type == "missing"
            assert "anthropic" in result.errors[0].suggestion.lower()

    def test_pr_operations_requires_github(self):
        """PR operations workflow requires GitHub credential."""
        from codeframe.core.credential_validator import (
            validate_workflow_credentials,
            WorkflowType,
        )

        with patch("codeframe.core.credential_validator.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = None

            result = validate_workflow_credentials(
                WorkflowType.PR_OPERATIONS,
                credential_manager=mock_instance,
            )

            assert not result.is_valid
            assert len(result.errors) == 1
            assert "github" in result.errors[0].message.lower()

    def test_valid_credential_passes(self):
        """Valid credential passes validation."""
        from codeframe.core.credential_validator import (
            validate_workflow_credentials,
            WorkflowType,
        )
        from codeframe.core.credentials import CredentialSource

        with patch("codeframe.core.credential_validator.CredentialManager") as mock_cm:
            mock_instance = MagicMock()
            mock_cm.return_value = mock_instance
            mock_instance.get_credential.return_value = "sk-ant-valid-key-12345"
            mock_instance.validate_credential_format.return_value = True
            mock_instance.get_credential_source.return_value = CredentialSource.ENVIRONMENT

            result = validate_workflow_credentials(
                WorkflowType.AGENT_EXECUTION,
                credential_manager=mock_instance,
            )

            assert result.is_valid
            assert len(result.errors) == 0

    def test_invalid_format_fails(self):
        """Invalid credential format fails validation."""
        from codeframe.core.credential_validator import (
            validate_workflow_credentials,
            WorkflowType,
        )

        mock_instance = MagicMock()
        mock_instance.get_credential.return_value = "bad-key"
        mock_instance.validate_credential_format.return_value = False

        result = validate_workflow_credentials(
            WorkflowType.AGENT_EXECUTION,
            credential_manager=mock_instance,
        )

        assert not result.is_valid
        assert result.errors[0].error_type == "invalid"


class TestRequireCredential:
    """Tests for require_credential helper."""

    def test_returns_value_when_valid(self):
        """Returns credential value when available."""
        from codeframe.core.credential_validator import require_credential
        from codeframe.core.credentials import CredentialProvider

        mock_instance = MagicMock()
        mock_instance.get_credential.return_value = "sk-ant-valid-key-12345"
        mock_instance.validate_credential_format.return_value = True

        value = require_credential(
            CredentialProvider.LLM_ANTHROPIC,
            credential_manager=mock_instance,
        )

        assert value == "sk-ant-valid-key-12345"

    def test_raises_when_missing(self):
        """Raises ValueError when credential missing."""
        from codeframe.core.credential_validator import require_credential
        from codeframe.core.credentials import CredentialProvider

        mock_instance = MagicMock()
        mock_instance.get_credential.return_value = None

        with pytest.raises(ValueError) as exc_info:
            require_credential(
                CredentialProvider.LLM_ANTHROPIC,
                credential_manager=mock_instance,
            )

        assert "no credential" in str(exc_info.value).lower()
        assert "suggestion" in str(exc_info.value).lower()


class TestCheckLLMCredentials:
    """Tests for check_llm_credentials."""

    def test_passes_with_anthropic(self):
        """Passes when Anthropic credential is available."""
        from codeframe.core.credential_validator import check_llm_credentials
        from codeframe.core.credentials import CredentialProvider

        mock_instance = MagicMock()

        def get_credential_side_effect(provider):
            if provider == CredentialProvider.LLM_ANTHROPIC:
                return "sk-ant-valid-key"
            return None

        mock_instance.get_credential.side_effect = get_credential_side_effect
        mock_instance.validate_credential_format.return_value = True

        result = check_llm_credentials(credential_manager=mock_instance)

        assert result.is_valid

    def test_passes_with_openai(self):
        """Passes when OpenAI credential is available."""
        from codeframe.core.credential_validator import check_llm_credentials
        from codeframe.core.credentials import CredentialProvider

        mock_instance = MagicMock()

        def get_credential_side_effect(provider):
            if provider == CredentialProvider.LLM_OPENAI:
                return "sk-openai-valid-key"
            return None

        mock_instance.get_credential.side_effect = get_credential_side_effect
        mock_instance.validate_credential_format.return_value = True

        result = check_llm_credentials(credential_manager=mock_instance)

        assert result.is_valid

    def test_fails_with_no_llm_providers(self):
        """Fails when no LLM providers configured."""
        from codeframe.core.credential_validator import check_llm_credentials

        mock_instance = MagicMock()
        mock_instance.get_credential.return_value = None

        result = check_llm_credentials(credential_manager=mock_instance)

        assert not result.is_valid
        assert len(result.errors) == 1
        assert "no llm provider" in result.errors[0].message.lower()


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_add_error_sets_invalid(self):
        """Adding an error marks result as invalid."""
        from codeframe.core.credential_validator import ValidationResult
        from codeframe.core.credentials import CredentialProvider

        result = ValidationResult(is_valid=True)
        assert result.is_valid

        result.add_error(
            provider=CredentialProvider.LLM_ANTHROPIC,
            error_type="missing",
            message="Test error",
            suggestion="Test suggestion",
        )

        assert not result.is_valid
        assert len(result.errors) == 1

    def test_add_warning_keeps_valid(self):
        """Adding a warning doesn't mark result as invalid."""
        from codeframe.core.credential_validator import ValidationResult

        result = ValidationResult(is_valid=True)
        result.add_warning("Test warning")

        assert result.is_valid
        assert len(result.warnings) == 1
