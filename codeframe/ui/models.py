"""Pydantic models for the CodeFRAME v2 API.

Scope is deliberately narrow: the settings/API-key surface consumed by
``codeframe.ui.routers.settings_v2``. Every other v2 router declares its own
request/response models locally. The v1-era shapes that used to live here —
projects, checkpoints, agent assignments, activity, issues, blockers — were
deleted in #968; they described endpoints that no longer exist and were kept
alive only by a test of themselves.
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# ============================================================================
# Settings (issue #554)
# ============================================================================


AgentType = Literal["claude_code", "codex", "opencode", "react"]
AGENT_TYPES: tuple[AgentType, ...] = ("claude_code", "codex", "opencode", "react")


class AgentTypeModelConfig(BaseModel):
    """Default model for a single agent type."""

    agent_type: AgentType = Field(
        ..., description="One of: claude_code, codex, opencode, react"
    )
    default_model: str = Field(
        default="",
        description="Model identifier (e.g. 'claude-opus-4', 'gpt-4o'); empty string means unset",
    )


class AgentSettings(BaseModel):
    """Agent settings shared by GET response and PUT request.

    Defaults match `EnvironmentConfig.agent_budget.max_iterations` so that a
    fresh workspace round-trips its real defaults through GET.
    """

    agent_models: List[AgentTypeModelConfig] = Field(
        ..., description="Default model per agent type"
    )
    max_turns: int = Field(
        default=100, gt=0, description="Maximum turns per task (must be > 0)"
    )
    max_cost_usd: Optional[float] = Field(
        default=None, ge=0, description="Maximum cost per task in USD"
    )


class AgentSettingsResponse(AgentSettings):
    """Response shape for GET /api/v2/settings."""


class UpdateAgentSettingsRequest(AgentSettings):
    """Request shape for PUT /api/v2/settings."""


# ============================================================================
# API Key Management (issue #555)
# ============================================================================


KeyProvider = Literal["LLM_ANTHROPIC", "LLM_OPENAI", "GIT_GITHUB"]
KEY_PROVIDERS: tuple[KeyProvider, ...] = ("LLM_ANTHROPIC", "LLM_OPENAI", "GIT_GITHUB")

KeySource = Literal["environment", "stored", "none"]


class StoreKeyRequest(BaseModel):
    """Request shape for PUT /api/v2/settings/keys/{provider}."""

    value: str = Field(..., min_length=1, description="The credential value to store")


class KeyStatusResponse(BaseModel):
    """Status of a single API key. Never includes the plaintext value."""

    provider: KeyProvider = Field(..., description="One of: LLM_ANTHROPIC, LLM_OPENAI, GIT_GITHUB")
    stored: bool = Field(..., description="True if a key is available (env or storage)")
    source: KeySource = Field(
        ..., description="Where the key comes from: environment, stored, or none"
    )
    last_four: Optional[str] = Field(
        default=None,
        description="Last 4 characters of the key for display (None if no key available)",
    )


class VerifyKeyRequest(BaseModel):
    """Request shape for POST /api/v2/settings/verify-key."""

    provider: KeyProvider = Field(..., description="Which provider's key to verify")
    value: Optional[str] = Field(
        default=None,
        description="The key value to verify; if None, the stored/env key is used",
    )


class VerifyKeyResponse(BaseModel):
    """Result of a live verification attempt against a provider."""

    provider: KeyProvider
    valid: bool = Field(..., description="True if the provider accepted the key")
    message: str = Field(..., description="Human-readable result message")
