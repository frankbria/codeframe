"""Pre-workflow credential validation for CodeFRAME.

This module provides validation to ensure required credentials are
available before starting workflows. It fails fast with clear error
messages if credentials are missing.

Usage:
    from codeframe.core.credential_validator import (
        validate_workflow_credentials,
        WorkflowType,
    )

    # Check credentials before starting agent work
    result = validate_workflow_credentials(WorkflowType.AGENT_EXECUTION)
    if not result.is_valid:
        for error in result.errors:
            print(f"Missing: {error}")
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from codeframe.core.credentials import (
    CredentialManager,
    CredentialProvider,
    CredentialSource,
)


logger = logging.getLogger(__name__)


class WorkflowType(Enum):
    """Types of workflows that require credential validation."""

    AGENT_EXECUTION = "agent_execution"  # Running the AI agent
    TASK_GENERATION = "task_generation"  # Generating tasks from PRD
    PR_OPERATIONS = "pr_operations"  # Creating/managing pull requests
    GIT_OPERATIONS = "git_operations"  # Git push/pull operations
    CODE_REVIEW = "code_review"  # Running code reviews
    GENERIC = "generic"  # Generic validation


# Map workflows to required providers
WORKFLOW_REQUIREMENTS: dict[WorkflowType, list[CredentialProvider]] = {
    WorkflowType.AGENT_EXECUTION: [CredentialProvider.LLM_ANTHROPIC],
    WorkflowType.TASK_GENERATION: [CredentialProvider.LLM_ANTHROPIC],
    WorkflowType.PR_OPERATIONS: [CredentialProvider.GIT_GITHUB],
    WorkflowType.GIT_OPERATIONS: [CredentialProvider.GIT_GITHUB],
    WorkflowType.CODE_REVIEW: [CredentialProvider.LLM_ANTHROPIC],
    WorkflowType.GENERIC: [],
}


@dataclass
class ValidationError:
    """Details about a missing or invalid credential."""

    provider: CredentialProvider
    error_type: str  # "missing", "invalid", "expired"
    message: str
    suggestion: str


@dataclass
class ValidationResult:
    """Result of credential validation."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(
        self,
        provider: CredentialProvider,
        error_type: str,
        message: str,
        suggestion: str,
    ) -> None:
        """Add a validation error."""
        self.errors.append(
            ValidationError(
                provider=provider,
                error_type=error_type,
                message=message,
                suggestion=suggestion,
            )
        )
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Add a validation warning (non-blocking)."""
        self.warnings.append(message)


def validate_workflow_credentials(
    workflow_type: WorkflowType,
    credential_manager: Optional[CredentialManager] = None,
) -> ValidationResult:
    """Validate that required credentials are available for a workflow.

    Args:
        workflow_type: The type of workflow to validate for
        credential_manager: Optional credential manager (creates one if not provided)

    Returns:
        ValidationResult with is_valid status and any errors
    """
    if credential_manager is None:
        credential_manager = CredentialManager()

    result = ValidationResult(is_valid=True)
    required_providers = WORKFLOW_REQUIREMENTS.get(workflow_type, [])

    for provider in required_providers:
        # Check if credential is available
        value = credential_manager.get_credential(provider)

        if not value:
            result.add_error(
                provider=provider,
                error_type="missing",
                message=f"No credential configured for {provider.display_name}",
                suggestion=(
                    f"Run 'codeframe auth setup --provider {provider.name.lower()}' "
                    f"or set the {provider.env_var} environment variable"
                ),
            )
            continue

        # Check format validation
        if not credential_manager.validate_credential_format(provider, value):
            result.add_error(
                provider=provider,
                error_type="invalid",
                message=f"Credential for {provider.display_name} has invalid format",
                suggestion=(
                    f"Check the credential value and update with "
                    f"'codeframe auth rotate {provider.name.lower()}'"
                ),
            )
            continue

        # Note source for logging
        source = credential_manager.get_credential_source(provider)
        if source == CredentialSource.ENVIRONMENT:
            logger.debug(f"{provider.display_name} credential from environment variable")
        else:
            logger.debug(f"{provider.display_name} credential from secure storage")

    return result


def validate_provider_credential(
    provider: CredentialProvider,
    credential_manager: Optional[CredentialManager] = None,
) -> ValidationResult:
    """Validate a specific provider's credential.

    Args:
        provider: The provider to validate
        credential_manager: Optional credential manager

    Returns:
        ValidationResult with is_valid status and any errors
    """
    if credential_manager is None:
        credential_manager = CredentialManager()

    result = ValidationResult(is_valid=True)

    value = credential_manager.get_credential(provider)

    if not value:
        result.add_error(
            provider=provider,
            error_type="missing",
            message=f"No credential configured for {provider.display_name}",
            suggestion=(
                f"Run 'codeframe auth setup --provider {provider.name.lower()}' "
                f"or set the {provider.env_var} environment variable"
            ),
        )
        return result

    if not credential_manager.validate_credential_format(provider, value):
        result.add_error(
            provider=provider,
            error_type="invalid",
            message=f"Credential for {provider.display_name} has invalid format",
            suggestion="Check the credential value and try again",
        )

    return result


def require_credential(
    provider: CredentialProvider,
    credential_manager: Optional[CredentialManager] = None,
) -> str:
    """Get a credential, raising an error if not available.

    This is a convenience function for code that requires a credential
    and wants to fail immediately if it's not available.

    Args:
        provider: The provider to get credential for
        credential_manager: Optional credential manager

    Returns:
        The credential value

    Raises:
        ValueError: If credential is not available
    """
    if credential_manager is None:
        credential_manager = CredentialManager()

    result = validate_provider_credential(provider, credential_manager)

    if not result.is_valid:
        error = result.errors[0]
        raise ValueError(
            f"{error.message}\n\n"
            f"Suggestion: {error.suggestion}"
        )

    value = credential_manager.get_credential(provider)
    if not value:
        raise ValueError(f"Credential for {provider.display_name} not found")

    return value


def check_llm_credentials(
    credential_manager: Optional[CredentialManager] = None,
) -> ValidationResult:
    """Check if any LLM provider credential is available.

    Args:
        credential_manager: Optional credential manager

    Returns:
        ValidationResult - valid if at least one LLM provider is configured
    """
    if credential_manager is None:
        credential_manager = CredentialManager()

    result = ValidationResult(is_valid=False)

    llm_providers = [
        CredentialProvider.LLM_ANTHROPIC,
        CredentialProvider.LLM_OPENAI,
    ]

    available_providers = []
    for provider in llm_providers:
        value = credential_manager.get_credential(provider)
        if value and credential_manager.validate_credential_format(provider, value):
            available_providers.append(provider)

    if available_providers:
        result.is_valid = True
        logger.debug(f"Available LLM providers: {[p.display_name for p in available_providers]}")
    else:
        result.add_error(
            provider=CredentialProvider.LLM_ANTHROPIC,
            error_type="missing",
            message="No LLM provider credentials configured",
            suggestion=(
                "Configure at least one LLM provider:\n"
                "  - Run 'codeframe auth setup --provider anthropic' for Claude\n"
                "  - Run 'codeframe auth setup --provider openai' for GPT\n"
                "  - Or set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable"
            ),
        )

    return result
