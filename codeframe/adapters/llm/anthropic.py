"""Anthropic LLM provider implementation.

Provides Claude model access via the Anthropic API.
"""

import asyncio
import os
from typing import TYPE_CHECKING, AsyncIterator, Iterator, Optional

from codeframe.adapters.llm.base import (
    LLMProvider,
    LLMResponse,
    ModelSelector,
    Purpose,
    StreamChunk,
    Tool,
    ToolCall,
)

if TYPE_CHECKING:
    from codeframe.core.credentials import CredentialManager


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider.

    Uses the Anthropic Python SDK to make API calls.
    Supports tool use and streaming.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_selector: Optional[ModelSelector] = None,
        credential_manager: Optional["CredentialManager"] = None,
    ):
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model_selector: Custom model selector
            credential_manager: Optional credential manager for secure key retrieval

        Raises:
            ValueError: If no API key is available
        """
        super().__init__(model_selector)

        # Try to get API key from multiple sources in order:
        # 1. Direct api_key parameter
        # 2. CredentialManager (if provided)
        # 3. Environment variable
        self.api_key = api_key

        if not self.api_key and credential_manager:
            from codeframe.core.credentials import CredentialProvider
            self.api_key = credential_manager.get_credential(CredentialProvider.LLM_ANTHROPIC)

        if not self.api_key:
            self.api_key = os.getenv("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Set the environment variable, pass api_key parameter, "
                "or configure via 'codeframe auth setup --provider anthropic'."
            )
        self._client = None
        self._async_client = None

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

    async def async_complete(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        tools: Optional[list[Tool]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """True async completion via AsyncAnthropic.

        Raises LLMAuthError / LLMRateLimitError / LLMConnectionError on failure.
        """
        from anthropic import AsyncAnthropic
        from anthropic import (
            AuthenticationError,
            RateLimitError,
            APIConnectionError,
        )
        from codeframe.adapters.llm.base import (
            LLMAuthError,
            LLMRateLimitError,
            LLMConnectionError,
        )

        if self._async_client is None:
            self._async_client = AsyncAnthropic(api_key=self.api_key)

        model = self.get_model(purpose)
        kwargs: dict = {
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

        try:
            response = await self._async_client.messages.create(**kwargs)
            return self._parse_response(response)
        except AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except APIConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc

    def supports(self, capability: str) -> bool:
        """Return True for capabilities this provider supports."""
        return capability == "extended_thinking"

    async def async_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        model: str,
        max_tokens: int,
        interrupt_event: Optional[asyncio.Event] = None,
        extended_thinking: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        """Stream using Anthropic AsyncAnthropic SDK, yielding StreamChunk objects.

        Translates Anthropic SDK events into the normalized StreamChunk format.
        Tool inputs are collected and emitted in the final message_stop chunk
        via tool_inputs_by_id, which is more reliable than streaming input deltas.

        When ``extended_thinking=True``, requests interleaved thinking via the
        Anthropic betas API.  The flag is silently ignored on SDK versions that
        do not support it.
        """
        from anthropic import AsyncAnthropic

        if self._async_client is None:
            self._async_client = AsyncAnthropic(api_key=self.api_key)

        kwargs: dict = {
            "model": model,
            "system": system,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        }

        if extended_thinking:
            # interleaved-thinking requires the beta header; degrade gracefully
            # if the running SDK version doesn't recognise the param.
            try:
                kwargs["betas"] = ["interleaved-thinking-2025-05-14"]
            except Exception:  # pragma: no cover
                pass

        active_tool_id: Optional[str] = None

        async with self._async_client.messages.stream(**kwargs) as stream:
            async for sdk_event in stream:
                if interrupt_event and interrupt_event.is_set():
                    return

                event_type = sdk_event.type

                if event_type == "content_block_start":
                    block = sdk_event.content_block
                    if block.type == "tool_use":
                        active_tool_id = block.id
                        yield StreamChunk(
                            type="tool_use_start",
                            tool_id=block.id,
                            tool_name=block.name,
                            tool_input=getattr(block, "input", {}),
                        )

                elif event_type == "content_block_delta":
                    delta = sdk_event.delta
                    if delta.type == "text_delta":
                        yield StreamChunk(type="text_delta", text=delta.text)
                    elif delta.type == "thinking_delta":
                        yield StreamChunk(type="thinking_delta", text=delta.thinking)
                    # input_json_delta: final inputs are rebuilt from message_stop

                elif event_type == "content_block_stop":
                    if active_tool_id is not None:
                        yield StreamChunk(type="tool_use_stop")
                        active_tool_id = None

                elif event_type == "message_stop":
                    # Flush any open tool block
                    if active_tool_id is not None:
                        yield StreamChunk(type="tool_use_stop")
                        active_tool_id = None

                    final_msg = stream.get_final_message()
                    stop_reason = final_msg.stop_reason or "end_turn"

                    # Build tool_inputs_by_id from final content blocks
                    tool_inputs_by_id: dict = {}
                    if hasattr(final_msg, "content"):
                        for block in final_msg.content:
                            if getattr(block, "type", None) == "tool_use" and hasattr(block, "id"):
                                tool_inputs_by_id[block.id] = getattr(block, "input", {})

                    yield StreamChunk(
                        type="message_stop",
                        stop_reason=stop_reason,
                        input_tokens=final_msg.usage.input_tokens,
                        output_tokens=final_msg.usage.output_tokens,
                        tool_inputs_by_id=tool_inputs_by_id,
                    )

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
                # Mirror tool_calls logic: tool_result blocks first, then text if present
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
                # Preserve any user text content alongside tool results
                if msg.get("content"):
                    msg_content = msg["content"]
                    if isinstance(msg_content, str):
                        content.append({"type": "text", "text": msg_content})
                    elif isinstance(msg_content, list):
                        # Handle list of content blocks
                        for block in msg_content:
                            if isinstance(block, str):
                                content.append({"type": "text", "text": block})
                            elif isinstance(block, dict) and block.get("type") == "text":
                                content.append(block)
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
