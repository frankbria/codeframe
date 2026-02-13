"""Configuration management for CodeFRAME.

This module provides two configuration systems:
1. Legacy v1 config (JSON-based): ProjectConfig, GlobalConfig
2. v2 environment config (YAML-based): EnvironmentConfig

v2 environment config is stored in .codeframe/config.yaml and controls:
- Package manager (uv, pip, poetry, npm, etc.)
- Language versions (Python, Node)
- Test framework (pytest, jest, vitest)
- Lint tools (ruff, eslint, prettier)
"""

import json
from dataclasses import dataclass, field as dataclass_field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


# =============================================================================
# v2 Environment Configuration (YAML-based)
# =============================================================================


class PackageManager(str, Enum):
    """Supported package managers."""

    UV = "uv"
    PIP = "pip"
    POETRY = "poetry"
    NPM = "npm"
    PNPM = "pnpm"
    YARN = "yarn"


class TestFramework(str, Enum):
    """Supported test frameworks."""

    PYTEST = "pytest"
    JEST = "jest"
    VITEST = "vitest"
    UNITTEST = "unittest"
    MOCHA = "mocha"


class LintTool(str, Enum):
    """Supported lint tools."""

    RUFF = "ruff"
    PYLINT = "pylint"
    FLAKE8 = "flake8"
    MYPY = "mypy"
    ESLINT = "eslint"
    PRETTIER = "prettier"
    BIOME = "biome"


@dataclass
class ContextConfig:
    """Context loading configuration."""

    max_files: int = 20
    max_file_size: int = 5000  # lines
    max_total_tokens: int = 50000


@dataclass
class AgentBudgetConfig:
    """Agent iteration budget configuration."""
    base_iterations: int = 30
    min_iterations: int = 15
    max_iterations: int = 100
    auto_fix_enabled: bool = True
    early_termination_enabled: bool = True


@dataclass
class EnvironmentConfig:
    """v2 project environment configuration.

    Stored in .codeframe/config.yaml. Controls how the agent
    interacts with the project's development environment.
    """

    # Package management
    package_manager: str = "uv"
    python_version: Optional[str] = None  # e.g., "3.11"
    node_version: Optional[str] = None  # e.g., "18"

    # Testing
    test_framework: str = "pytest"
    test_command: Optional[str] = None  # Override, e.g., "pytest -v tests/"

    # Linting
    lint_tools: list[str] = dataclass_field(default_factory=lambda: ["ruff"])
    lint_command: Optional[str] = None  # Override, e.g., "ruff check ."

    # Context loading
    context: ContextConfig = dataclass_field(default_factory=ContextConfig)

    # Agent budget
    agent_budget: AgentBudgetConfig = dataclass_field(default_factory=AgentBudgetConfig)

    # Custom command overrides
    custom_commands: dict[str, str] = dataclass_field(default_factory=dict)

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate package manager
        valid_pkg_managers = [pm.value for pm in PackageManager]
        if self.package_manager not in valid_pkg_managers:
            errors.append(
                f"Invalid package_manager '{self.package_manager}'. "
                f"Must be one of: {', '.join(valid_pkg_managers)}"
            )

        # Validate test framework
        valid_test_frameworks = [tf.value for tf in TestFramework]
        if self.test_framework not in valid_test_frameworks:
            errors.append(
                f"Invalid test_framework '{self.test_framework}'. "
                f"Must be one of: {', '.join(valid_test_frameworks)}"
            )

        # Validate lint tools
        valid_lint_tools = [lt.value for lt in LintTool]
        for tool in self.lint_tools:
            if tool not in valid_lint_tools:
                errors.append(
                    f"Invalid lint tool '{tool}'. "
                    f"Must be one of: {', '.join(valid_lint_tools)}"
                )

        # Validate agent budget
        budget = self.agent_budget
        if any(v <= 0 for v in (budget.base_iterations, budget.min_iterations, budget.max_iterations)):
            errors.append("agent_budget iterations must be positive integers")
        if budget.min_iterations > budget.max_iterations:
            errors.append("agent_budget.min_iterations cannot exceed max_iterations")
        if not (budget.min_iterations <= budget.base_iterations <= budget.max_iterations):
            errors.append(
                "agent_budget.base_iterations must be between min_iterations and max_iterations"
            )

        return errors

    def get_install_command(self, package: str) -> str:
        """Get the install command for a package.

        Args:
            package: Package name to install

        Returns:
            Full install command string
        """
        if self.package_manager == "uv":
            return f"uv pip install {package}"
        elif self.package_manager == "pip":
            return f"pip install {package}"
        elif self.package_manager == "poetry":
            return f"poetry add {package}"
        elif self.package_manager in ("npm", "pnpm", "yarn"):
            return f"{self.package_manager} install {package}"
        else:
            return f"pip install {package}"  # fallback

    def get_test_command(self) -> str:
        """Get the test command for this project.

        Returns:
            Test command string
        """
        if self.test_command:
            return self.test_command

        if self.test_framework == "pytest":
            return "pytest"
        elif self.test_framework == "jest":
            return "npm test" if self.package_manager == "npm" else "jest"
        elif self.test_framework == "vitest":
            return "npm test" if self.package_manager == "npm" else "vitest"
        elif self.test_framework == "unittest":
            return "python -m unittest discover"
        elif self.test_framework == "mocha":
            return "npm test" if self.package_manager == "npm" else "mocha"
        else:
            return "pytest"  # fallback

    def get_lint_command(self) -> str:
        """Get the lint command for this project.

        Returns:
            Lint command string
        """
        if self.lint_command:
            return self.lint_command

        if not self.lint_tools:
            return "ruff check ."  # default

        # Use the first lint tool
        tool = self.lint_tools[0]
        if tool == "ruff":
            return "ruff check ."
        elif tool == "pylint":
            return "pylint ."
        elif tool == "flake8":
            return "flake8 ."
        elif tool == "mypy":
            return "mypy ."
        elif tool == "eslint":
            return "eslint ."
        elif tool == "prettier":
            return "prettier --check ."
        elif tool == "biome":
            return "biome check ."
        else:
            return "ruff check ."  # fallback

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        data = asdict(self)
        # Convert ContextConfig to dict
        if isinstance(data.get("context"), dict):
            pass  # already a dict from asdict
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnvironmentConfig":
        """Create from dictionary (YAML deserialization)."""
        # Handle nested ContextConfig
        if "context" in data and isinstance(data["context"], dict):
            data["context"] = ContextConfig(**data["context"])
        if "agent_budget" in data and isinstance(data["agent_budget"], dict):
            data["agent_budget"] = AgentBudgetConfig(**data["agent_budget"])
        return cls(**data)


# Environment config file name
ENV_CONFIG_FILE = "config.yaml"


def load_environment_config(workspace_path: Path) -> Optional[EnvironmentConfig]:
    """Load environment configuration from workspace.

    Args:
        workspace_path: Path to the workspace root

    Returns:
        EnvironmentConfig if file exists, None otherwise
    """
    config_file = workspace_path / ".codeframe" / ENV_CONFIG_FILE
    if not config_file.exists():
        return None

    with open(config_file) as f:
        data = yaml.safe_load(f)

    if data is None:
        return EnvironmentConfig()  # empty file = defaults

    return EnvironmentConfig.from_dict(data)


def save_environment_config(workspace_path: Path, config: EnvironmentConfig) -> None:
    """Save environment configuration to workspace.

    Args:
        workspace_path: Path to the workspace root
        config: Configuration to save
    """
    config_dir = workspace_path / ".codeframe"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / ENV_CONFIG_FILE

    with open(config_file, "w") as f:
        yaml.dump(
            config.to_dict(),
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def get_default_environment_config() -> EnvironmentConfig:
    """Get default environment configuration.

    Returns:
        EnvironmentConfig with sensible defaults
    """
    return EnvironmentConfig()


# =============================================================================
# v1 Legacy Configuration (JSON-based)
# =============================================================================


class ProviderConfig(BaseModel):
    """LLM provider configuration."""

    lead_agent: str = "claude"
    backend_agent: str = "claude"
    frontend_agent: str = "gpt4"
    test_agent: str = "claude"
    review_agent: str = "gpt4"


class AgentPolicyConfig(BaseModel):
    """Global agent management policies."""

    require_review_below_maturity: str = "supporting"
    allow_full_autonomy: bool = False


class InterruptionConfig(BaseModel):
    """Interruption mode configuration."""

    enabled: bool = True
    sync_blockers: list[str] = Field(default_factory=lambda: ["requirement", "security"])
    async_blockers: list[str] = Field(default_factory=lambda: ["technical", "external"])
    auto_continue: bool = True


class NotificationChannelConfig(BaseModel):
    """Notification channel configuration."""

    enabled: bool = True
    channels: list[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    batch_interval: Optional[int] = None


class NotificationsConfig(BaseModel):
    """Multi-channel notification configuration."""

    sync_blockers: NotificationChannelConfig = Field(default_factory=NotificationChannelConfig)
    async_blockers: NotificationChannelConfig = Field(default_factory=NotificationChannelConfig)


class ContextManagementConfig(BaseModel):
    """Virtual Project context configuration."""

    enabled: bool = True  # Feature flag for context management
    hot_tier_max_tokens: int = 20000
    warm_tier_max_tokens: int = 40000
    importance_threshold_hot: float = 0.8
    importance_threshold_warm: float = 0.4


class CheckpointConfig(BaseModel):
    """Checkpoint configuration."""

    auto_save_interval: int = 1800  # seconds
    pre_compactification: bool = True
    per_task_completion: bool = True


class ProjectConfig(BaseModel):
    """Project-specific configuration."""

    project_name: str
    project_type: str = "python"
    providers: ProviderConfig = Field(default_factory=ProviderConfig)
    agent_policy: AgentPolicyConfig = Field(default_factory=AgentPolicyConfig)
    interruption_mode: InterruptionConfig = Field(default_factory=InterruptionConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    context_management: ContextManagementConfig = Field(default_factory=ContextManagementConfig)
    checkpoints: CheckpointConfig = Field(default_factory=CheckpointConfig)


class GlobalConfig(BaseSettings):
    """Global CodeFRAME configuration loaded from environment variables."""

    # API Keys (REQUIRED for Sprint 1)
    anthropic_api_key: Optional[str] = Field(None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(None, alias="OPENAI_API_KEY")

    # Notification services (optional, for future sprints)
    twilio_account_sid: Optional[str] = Field(None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(None, alias="TWILIO_AUTH_TOKEN")

    # Blocker webhook notifications (Sprint 6 - Human in the Loop)
    blocker_webhook_url: Optional[str] = Field(None, alias="BLOCKER_WEBHOOK_URL")

    # Database configuration
    database_path: str = Field(".codeframe/state.db", alias="DATABASE_PATH")

    # Status Server configuration
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8080, alias="API_PORT")
    cors_origins: str = Field("http://localhost:3000,http://localhost:5173", alias="CORS_ORIGINS")

    # Logging configuration
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_file: Optional[str] = Field(".codeframe/logs/codeframe.log", alias="LOG_FILE")

    # Development flags
    debug: bool = Field(False, alias="DEBUG")
    hot_reload: bool = Field(False, alias="HOT_RELOAD")

    # Provider defaults
    default_provider: str = "claude"
    default_model: str = "claude-sonnet-4"

    # GitHub Integration (Sprint 11 - PR Management)
    github_token: Optional[str] = Field(None, alias="GITHUB_TOKEN")
    github_repo: Optional[str] = Field(None, alias="GITHUB_REPO")  # Format: "owner/repo"

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(True, alias="RATE_LIMIT_ENABLED")
    rate_limit_storage: str = Field("memory", alias="RATE_LIMIT_STORAGE")
    redis_url: Optional[str] = Field(None, alias="REDIS_URL")
    rate_limit_auth: str = Field("10/minute", alias="RATE_LIMIT_AUTH")
    rate_limit_standard: str = Field("100/minute", alias="RATE_LIMIT_STANDARD")
    rate_limit_ai: str = Field("20/minute", alias="RATE_LIMIT_AI")
    rate_limit_websocket: str = Field("30/minute", alias="RATE_LIMIT_WEBSOCKET")
    # Comma-separated list of trusted proxy IPs/CIDRs (e.g., "10.0.0.0/8,172.16.0.0/12")
    rate_limit_trusted_proxies: str = Field("", alias="RATE_LIMIT_TRUSTED_PROXIES")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}, got: {v}")
        return v_upper

    @field_validator("api_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"API_PORT must be between 1 and 65535, got: {v}")
        return v

    @field_validator("rate_limit_storage")
    @classmethod
    def validate_rate_limit_storage(cls, v: str) -> str:
        """Validate rate limit storage is valid."""
        allowed = ["memory", "redis"]
        if v not in allowed:
            raise ValueError(f"RATE_LIMIT_STORAGE must be one of {allowed}, got: {v}")
        return v

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_required_for_sprint(self, sprint: int = 1) -> None:
        """Validate that required configuration is present for a given sprint.

        Args:
            sprint: Sprint number (1-8)

        Raises:
            ValueError: If required configuration is missing
        """
        errors = []

        if sprint >= 1:
            # Sprint 1 requires Anthropic API key for Lead Agent
            if not self.anthropic_api_key:
                errors.append(
                    "ANTHROPIC_API_KEY is required for Sprint 1 (Lead Agent with Claude).\n"
                    "  Get your API key at: https://console.anthropic.com/\n"
                    "  Then add it to your .env file (see .env.example)"
                )

        if sprint >= 4:
            # Sprint 4+ may require OpenAI for multi-agent
            if not self.openai_api_key and not self.anthropic_api_key:
                errors.append(
                    "At least one AI provider API key is required.\n"
                    "  ANTHROPIC_API_KEY or OPENAI_API_KEY must be set."
                )

        if sprint >= 5:
            # Sprint 5+ may require notification services
            pass  # Notifications are optional, will use webhook fallback

        if errors:
            error_msg = "\n\n".join(errors)
            raise ValueError(
                f"\n{'='*70}\nCONFIGURATION ERROR\n{'='*70}\n\n{error_msg}\n\n{'='*70}\n"
            )

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        # Create database directory
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create log directory if log file is specified
        if self.log_file:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)


def load_environment(env_file: str = ".env") -> None:
    """Load environment variables from .env file.

    Args:
        env_file: Path to .env file (default: .env in current directory)
    """
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
        # Also try project root .env if we're in a subdirectory
        if not env_path.is_absolute():
            root_env = Path.cwd() / ".env"
            if root_env.exists() and root_env != env_path.absolute():
                load_dotenv(root_env)


class Config:
    """Configuration manager for CodeFRAME."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config_dir = project_dir / ".codeframe"
        self.config_file = self.config_dir / "config.json"
        self._project_config: Optional[ProjectConfig] = None
        self._global_config: Optional[GlobalConfig] = None

        # Load environment variables
        load_environment()

    def load(self) -> ProjectConfig:
        """Load project configuration."""
        if self._project_config:
            return self._project_config

        if not self.config_file.exists():
            raise FileNotFoundError(f"Config not found: {self.config_file}")

        with open(self.config_file) as f:
            data = json.load(f)
            self._project_config = ProjectConfig(**data)

        return self._project_config

    def save(self, config: ProjectConfig) -> None:
        """Save project configuration."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            json.dump(config.model_dump(), f, indent=2)
        self._project_config = config

    def get_global(self) -> GlobalConfig:
        """Load global configuration from environment variables.

        Returns:
            GlobalConfig instance with values from environment

        Raises:
            ValueError: If required configuration is missing
        """
        if not self._global_config:
            self._global_config = GlobalConfig()
        return self._global_config

    def validate_for_sprint(self, sprint: int = 1) -> None:
        """Validate configuration for a specific sprint.

        Args:
            sprint: Sprint number to validate for

        Raises:
            ValueError: If required configuration is missing
        """
        global_config = self.get_global()
        global_config.validate_required_for_sprint(sprint)
        global_config.ensure_directories()

    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation."""
        config = self.load()
        keys = key.split(".")
        obj = config.model_dump()

        # Navigate to the correct nested dict
        current = obj
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        # Set the value
        current[keys[-1]] = value

        # Reload and save
        self._project_config = ProjectConfig(**obj)
        self.save(self._project_config)

    def get(self, key: str) -> Any:
        """Get configuration value using dot notation."""
        config = self.load()
        keys = key.split(".")
        obj = config.model_dump()

        current = obj
        for k in keys:
            if k not in current:
                return None
            current = current[k]

        return current


# Module-level singleton for GlobalConfig
_global_config: Optional[GlobalConfig] = None


def get_global_config() -> GlobalConfig:
    """Get the global configuration singleton.

    Loads from environment variables on first call, cached thereafter.
    This is the recommended way to access GlobalConfig for most use cases.

    Returns:
        GlobalConfig instance with values from environment
    """
    global _global_config
    if _global_config is None:
        _global_config = GlobalConfig()
    return _global_config


def reset_global_config() -> None:
    """Reset the global configuration singleton.

    Useful for testing to ensure clean state between tests.
    """
    global _global_config
    _global_config = None
