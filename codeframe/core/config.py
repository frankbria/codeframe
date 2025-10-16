"""Configuration management for CodeFRAME."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


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
    """Global CodeFRAME configuration."""
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None

    default_provider: str = "claude"
    default_model: str = "claude-sonnet-4"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class Config:
    """Configuration manager for CodeFRAME."""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config_dir = project_dir / ".codeframe"
        self.config_file = self.config_dir / "config.json"
        self._project_config: Optional[ProjectConfig] = None
        self._global_config: Optional[GlobalConfig] = None

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
        """Load global configuration."""
        if not self._global_config:
            self._global_config = GlobalConfig()
        return self._global_config

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
