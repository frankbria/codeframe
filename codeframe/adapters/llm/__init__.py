"""LLM adapter package.

Provides a unified interface for LLM providers with task-based model selection.

Usage:
    from codeframe.adapters.llm import AnthropicProvider, get_provider

    # Get configured provider
    provider = get_provider()

    # Or create directly
    provider = AnthropicProvider()

    # Make a completion
    response = provider.complete(
        messages=[{"role": "user", "content": "Hello"}],
        purpose="planning",  # Selects appropriate model
    )
"""

import os

from codeframe.adapters.llm.base import (
    LLMProvider,
    LLMResponse,
    Message,
    ModelSelector,
    Purpose,
    Tool,
    ToolCall,
    ToolResult,
)
from codeframe.adapters.llm.anthropic import AnthropicProvider
from codeframe.adapters.llm.mock import MockProvider
from codeframe.adapters.llm.openai import OpenAIProvider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "Message",
    "ModelSelector",
    "Purpose",
    "Tool",
    "ToolCall",
    "ToolResult",
    "AnthropicProvider",
    "MockProvider",
    "OpenAIProvider",
    "get_provider",
]

_OPENAI_COMPATIBLE = {"openai", "ollama", "vllm", "compatible"}


def get_provider(provider_type: str = "anthropic", **kwargs) -> LLMProvider:
    """Get a configured LLM provider.

    Args:
        provider_type: Provider type ("anthropic", "openai", "ollama",
            "vllm", "compatible", or "mock"). OpenAI-compatible types are
            all routed to OpenAIProvider.
        **kwargs: Optional overrides passed to the provider constructor.
            Supported keys: api_key, model, base_url.
            For local providers (ollama, vllm, compatible) that don't
            require authentication, api_key defaults to "not-required"
            if OPENAI_API_KEY is not set.

    Returns:
        Configured LLMProvider instance

    Raises:
        ValueError: If provider type is unknown
    """
    if provider_type in _OPENAI_COMPATIBLE:
        api_key = kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key and provider_type != "openai":
            # Local providers (ollama, vllm, compatible) don't need real auth;
            # the openai SDK still requires a non-empty api_key value.
            api_key = "not-required"
        return OpenAIProvider(
            api_key=api_key,
            model=kwargs.get("model", os.environ.get("CODEFRAME_LLM_MODEL", "gpt-4o")),
            base_url=kwargs.get("base_url", os.environ.get("OPENAI_BASE_URL")),
        )
    elif provider_type == "anthropic":
        return AnthropicProvider()
    elif provider_type == "mock":
        return MockProvider()
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
