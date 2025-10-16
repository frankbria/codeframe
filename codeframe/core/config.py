"""Configuration management for CodeFRAME."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


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
    context_management: ContextManagementConfig = Field(
        default_factory=ContextManagementConfig
    )
    checkpoints: CheckpointConfig = Field(default_factory=CheckpointConfig)


class GlobalConfig(BaseSettings):
    """Global CodeFRAME configuration loaded from environment variables."""

    # API Keys (REQUIRED for Sprint 1)
    anthropic_api_key: Optional[str] = Field(None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(None, alias="OPENAI_API_KEY")

    # Notification services (optional, for future sprints)
    twilio_account_sid: Optional[str] = Field(None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(None, alias="TWILIO_AUTH_TOKEN")

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
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
            raise ValueError(f"\n{'='*70}\nCONFIGURATION ERROR\n{'='*70}\n\n{error_msg}\n\n{'='*70}\n")

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
