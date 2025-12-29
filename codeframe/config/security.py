"""
Security configuration for CodeFRAME deployments.

Defines deployment modes and security policies.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Set
import os
import logging

logger = logging.getLogger(__name__)


class DeploymentMode(Enum):
    """
    Deployment modes with different security postures.

    - SAAS_SANDBOXED: Multi-tenant SaaS with container isolation (PRIMARY: sandbox, SECONDARY: app controls)
    - SAAS_UNSANDBOXED: Multi-tenant SaaS without isolation (PRIMARY: app controls - not recommended)
    - SELFHOSTED: Single-tenant self-hosted (user responsibility)
    - DEVELOPMENT: Local development (minimal controls)
    """

    SAAS_SANDBOXED = "saas_sandboxed"
    SAAS_UNSANDBOXED = "saas_unsandboxed"
    SELFHOSTED = "selfhosted"
    DEVELOPMENT = "development"


class SecurityEnforcement(Enum):
    """
    Security enforcement levels for command execution.

    - STRICT: Block commands that fail security checks
    - WARN: Allow but log warnings for security issues
    - DISABLED: No security checks (not recommended for production)
    """

    STRICT = "strict"
    WARN = "warn"
    DISABLED = "disabled"


@dataclass
class SecurityPolicy:
    """
    Security policy configuration for a deployment.

    Attributes:
        enforcement_level: How strictly to enforce security policies
        allow_shell_operators: Whether to allow shell operators (&&, ||, etc.)
        safe_commands_only: Whether to restrict to SAFE_COMMANDS allowlist
        custom_safe_commands: Additional commands to consider safe
        blocked_commands: Commands to explicitly block
        max_command_length: Maximum allowed command length
        enable_skip_detection: Whether to enable skip pattern detection in quality gates
    """

    enforcement_level: SecurityEnforcement = SecurityEnforcement.WARN
    allow_shell_operators: bool = True
    safe_commands_only: bool = False
    custom_safe_commands: Set[str] = None
    blocked_commands: Set[str] = None
    max_command_length: int = 1000
    enable_skip_detection: bool = True

    def __post_init__(self):
        if self.custom_safe_commands is None:
            self.custom_safe_commands = set()
        if self.blocked_commands is None:
            self.blocked_commands = set()


@dataclass
class SecurityConfig:
    """
    Complete security configuration for CodeFRAME.

    Attributes:
        deployment_mode: The deployment environment type
        policy: Security policy settings
    """

    deployment_mode: DeploymentMode
    policy: SecurityPolicy

    @classmethod
    def from_environment(cls) -> "SecurityConfig":
        """
        Create SecurityConfig from environment variables.

        Environment Variables:
            CODEFRAME_DEPLOYMENT_MODE: Deployment mode (saas_sandboxed, selfhosted, development)
            CODEFRAME_SECURITY_ENFORCEMENT: Enforcement level (strict, warn, disabled)
            CODEFRAME_ALLOW_SHELL_OPERATORS: Whether to allow shell operators (true/false)
            CODEFRAME_SAFE_COMMANDS_ONLY: Restrict to safe commands only (true/false)

        Returns:
            SecurityConfig instance
        """
        # Get deployment mode
        mode_str = os.getenv("CODEFRAME_DEPLOYMENT_MODE", "development")
        try:
            deployment_mode = DeploymentMode(mode_str)
        except ValueError:
            logger.warning(
                f"Invalid CODEFRAME_DEPLOYMENT_MODE: {mode_str}. "
                f"Defaulting to DEVELOPMENT. "
                f"Valid values: {[m.value for m in DeploymentMode]}"
            )
            deployment_mode = DeploymentMode.DEVELOPMENT

        # Get enforcement level
        enforcement_str = os.getenv("CODEFRAME_SECURITY_ENFORCEMENT", "warn")
        try:
            enforcement = SecurityEnforcement(enforcement_str)
        except ValueError:
            logger.warning(
                f"Invalid CODEFRAME_SECURITY_ENFORCEMENT: {enforcement_str}. "
                f"Defaulting to WARN. "
                f"Valid values: {[e.value for e in SecurityEnforcement]}"
            )
            enforcement = SecurityEnforcement.WARN

        # Get boolean settings
        allow_shell_operators = (
            os.getenv("CODEFRAME_ALLOW_SHELL_OPERATORS", "true").lower() == "true"
        )
        safe_commands_only = os.getenv("CODEFRAME_SAFE_COMMANDS_ONLY", "false").lower() == "true"
        enable_skip_detection = (
            os.getenv("CODEFRAME_ENABLE_SKIP_DETECTION", "true").lower() == "true"
        )

        # Create policy
        policy = SecurityPolicy(
            enforcement_level=enforcement,
            allow_shell_operators=allow_shell_operators,
            safe_commands_only=safe_commands_only,
            enable_skip_detection=enable_skip_detection,
        )

        return cls(deployment_mode=deployment_mode, policy=policy)

    @classmethod
    def default_for_mode(cls, mode: DeploymentMode) -> "SecurityConfig":
        """
        Create default SecurityConfig for a deployment mode.

        Args:
            mode: Deployment mode

        Returns:
            SecurityConfig with recommended defaults for the mode
        """
        if mode == DeploymentMode.SAAS_SANDBOXED:
            # Sandbox provides primary security, app controls are defense in depth
            policy = SecurityPolicy(
                enforcement_level=SecurityEnforcement.WARN,
                allow_shell_operators=True,
                safe_commands_only=False,
            )
        elif mode == DeploymentMode.SAAS_UNSANDBOXED:
            # App controls are primary security - be strict
            logger.warning(
                "SAAS_UNSANDBOXED mode detected. "
                "This is NOT RECOMMENDED for production. "
                "Use container isolation (SAAS_SANDBOXED) instead."
            )
            policy = SecurityPolicy(
                enforcement_level=SecurityEnforcement.STRICT,
                allow_shell_operators=False,
                safe_commands_only=True,
            )
        elif mode == DeploymentMode.SELFHOSTED:
            # User responsibility - warnings only
            policy = SecurityPolicy(
                enforcement_level=SecurityEnforcement.WARN,
                allow_shell_operators=True,
                safe_commands_only=False,
            )
        else:  # DEVELOPMENT
            # Minimal controls for development
            policy = SecurityPolicy(
                enforcement_level=SecurityEnforcement.DISABLED,
                allow_shell_operators=True,
                safe_commands_only=False,
            )

        return cls(deployment_mode=mode, policy=policy)

    def should_enforce_command_security(self) -> bool:
        """
        Determine if command security should be enforced.

        Returns:
            True if security checks should block commands, False if warnings only
        """
        return self.policy.enforcement_level == SecurityEnforcement.STRICT

    def should_log_security_warnings(self) -> bool:
        """
        Determine if security warnings should be logged.

        Returns:
            True if warnings should be logged
        """
        return self.policy.enforcement_level != SecurityEnforcement.DISABLED

    def should_enable_skip_detection(self) -> bool:
        """
        Determine if skip pattern detection should be enabled.

        Returns:
            True if skip detection should run in quality gates
        """
        return self.policy.enable_skip_detection


# Global security config instance
_security_config: Optional[SecurityConfig] = None


def get_security_config() -> SecurityConfig:
    """
    Get the global security configuration.

    Loads from environment on first call, cached thereafter.

    Returns:
        SecurityConfig instance
    """
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig.from_environment()
        logger.info(
            f"Security config initialized: "
            f"mode={_security_config.deployment_mode.value}, "
            f"enforcement={_security_config.policy.enforcement_level.value}"
        )
    return _security_config


def set_security_config(config: SecurityConfig) -> None:
    """
    Override the global security configuration.

    Useful for testing or programmatic configuration.

    Args:
        config: SecurityConfig instance to use
    """
    global _security_config
    _security_config = config
    logger.info(
        f"Security config set: "
        f"mode={config.deployment_mode.value}, "
        f"enforcement={config.policy.enforcement_level.value}"
    )


def get_evidence_config() -> dict:
    """Get evidence verification configuration from environment.

    Environment Variables:
        CODEFRAME_REQUIRE_COVERAGE: Whether coverage is required (default: true)
        CODEFRAME_MIN_COVERAGE: Minimum coverage percentage (default: 85.0)
        CODEFRAME_ALLOW_SKIPPED_TESTS: Whether skipped tests are allowed (default: false)
        CODEFRAME_MIN_PASS_RATE: Minimum test pass rate percentage (default: 100.0)

    Returns:
        dict with evidence configuration parameters
    """
    return {
        "require_coverage": os.getenv("CODEFRAME_REQUIRE_COVERAGE", "true").lower() == "true",
        "min_coverage": float(os.getenv("CODEFRAME_MIN_COVERAGE", "85.0")),
        "allow_skipped_tests": os.getenv("CODEFRAME_ALLOW_SKIPPED_TESTS", "false").lower() == "true",
        "min_pass_rate": float(os.getenv("CODEFRAME_MIN_PASS_RATE", "100.0")),
    }
