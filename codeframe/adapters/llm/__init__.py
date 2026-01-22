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
    "get_provider",
]


def get_provider(provider_type: str = "anthropic") -> LLMProvider:
    """Get a configured LLM provider.

    Args:
        provider_type: Provider type ("anthropic" or "mock")

    Returns:
        Configured LLMProvider instance

    Raises:
        ValueError: If provider type is unknown
    """
    if provider_type == "anthropic":
        return AnthropicProvider()
    elif provider_type == "mock":
        return MockProvider()
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
