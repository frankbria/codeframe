"""Anthropic LLM provider implementation.

Provides Claude model access via the Anthropic API.
"""

import os
from typing import Iterator, Optional

from codeframe.adapters.llm.base import (
    LLMProvider,
    LLMResponse,
    ModelSelector,
    Purpose,
    Tool,
    ToolCall,
)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider.

    Uses the Anthropic Python SDK to make API calls.
    Supports tool use and streaming.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_selector: Optional[ModelSelector] = None,
    ):
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model_selector: Custom model selector

        Raises:
            ValueError: If no API key is available
        """
        super().__init__(model_selector)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Set the environment variable or pass api_key parameter."
            )
        self._client = None

    @property
    def client(self):
        """Lazy-load the Anthropic client."""
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def complete(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        tools: Optional[list[Tool]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a completion using Claude.

        Args:
            messages: Conversation messages
            purpose: Purpose of call (for model selection)
            tools: Available tools for the model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt

        Returns:
            LLMResponse with content and/or tool calls
        """
        model = self.get_model(purpose)

        # Build request kwargs
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": self._convert_messages(messages),
        }

        if temperature > 0:
            kwargs["temperature"] = temperature

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        # Make the API call
        response = self.client.messages.create(**kwargs)

        # Parse response
        return self._parse_response(response)

    def stream(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream a completion token by token.

        Args:
            messages: Conversation messages
            purpose: Purpose of call (for model selection)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt

        Yields:
            Text chunks as they are generated
        """
        model = self.get_model(purpose)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": self._convert_messages(messages),
        }

        if temperature > 0:
            kwargs["temperature"] = temperature

        if system:
            kwargs["system"] = system

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert messages to Anthropic format.

        Handles tool results by converting them to the expected format.
        """
        converted = []
        for msg in messages:
            if "tool_results" in msg and msg["tool_results"]:
                # Convert tool results to Anthropic format
                content = []
                for tr in msg["tool_results"]:
                    content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tr["tool_call_id"],
                            "content": tr["content"],
                            "is_error": tr.get("is_error", False),
                        }
                    )
                converted.append({"role": "user", "content": content})
            elif "tool_calls" in msg and msg["tool_calls"]:
                # Convert assistant message with tool calls
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        }
                    )
                converted.append({"role": "assistant", "content": content})
            else:
                # Simple text message
                converted.append({"role": msg["role"], "content": msg["content"]})
        return converted

    def _convert_tools(self, tools: list[Tool]) -> list[dict]:
        """Convert Tool objects to Anthropic format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]

    def _parse_response(self, response) -> LLMResponse:
        """Parse Anthropic response into LLMResponse."""
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
