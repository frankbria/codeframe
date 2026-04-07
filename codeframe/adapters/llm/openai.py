"""OpenAI-compatible LLM provider implementation.

Provides access to OpenAI and any OpenAI-compatible endpoint
(Ollama, vLLM, LM Studio, Groq, Together, etc.) via the openai SDK.
"""

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, AsyncIterator, Iterator, Optional

import openai

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

logger = logging.getLogger(__name__)

_STOP_REASON_MAP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
}


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider.

    Uses the openai Python SDK to make API calls.
    A configurable base_url covers the entire OpenAI-compatible ecosystem:
    OpenAI, Ollama, vLLM, LM Studio, Groq, Together, etc.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        model_selector: Optional[ModelSelector] = None,
        credential_manager: Optional["CredentialManager"] = None,
    ):
        """Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Default model to use for all purposes
            base_url: Custom endpoint URL for OpenAI-compatible APIs
            model_selector: Optional model selector; when provided, defers to it for per-purpose routing
            credential_manager: Optional credential manager for secure key retrieval

        Raises:
            ValueError: If no API key is available
        """
        self._has_custom_selector = model_selector is not None
        super().__init__(model_selector)

        self.model = model
        self.base_url = base_url
        self.api_key = api_key

        if not self.api_key and credential_manager:
            from codeframe.core.credentials import CredentialProvider
            self.api_key = credential_manager.get_credential(CredentialProvider.LLM_OPENAI)

        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. "
                "Set the environment variable, pass api_key parameter, "
                "or configure via 'codeframe auth setup --provider openai'."
            )

        self._client = None
        self._async_client = None

    def get_model(self, purpose: Purpose) -> str:
        """Return the model for a given purpose.

        When an explicit model_selector was provided, defers to it so callers
        can route PLANNING/EXECUTION/GENERATION to different OpenAI models.
        Otherwise returns self.model for all purposes (single-model mode).
        """
        if self._has_custom_selector:
            return self.model_selector.for_purpose(purpose)
        return self.model

    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None:
            self._client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
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
        """Generate a completion using an OpenAI-compatible API.

        Args:
            messages: Conversation messages
            purpose: Purpose of call (for model selection — always returns self.model)
            tools: Available tools for the model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt

        Returns:
            LLMResponse with content and/or tool calls
        """
        converted = self._convert_messages(messages)

        if system:
            converted = [{"role": "system", "content": system}] + converted

        kwargs = {
            "model": self.get_model(purpose),
            "max_tokens": max_tokens,
            "messages": converted,
            "temperature": temperature,
        }

        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise ValueError(f"OpenAI authentication failed: {exc}") from exc
        except openai.RateLimitError as exc:
            raise ValueError(f"OpenAI rate limit exceeded: {exc}") from exc
        except openai.NotFoundError as exc:
            raise ValueError(f"OpenAI model not found: {exc}") from exc

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
        """True async completion via openai.AsyncOpenAI.

        Raises LLMAuthError / LLMRateLimitError / LLMConnectionError on failure.
        """
        import openai as _openai
        from codeframe.adapters.llm.base import (
            LLMAuthError,
            LLMRateLimitError,
            LLMConnectionError,
        )

        if self._async_client is None:
            self._async_client = _openai.AsyncOpenAI(
                api_key=self.api_key, base_url=self.base_url
            )

        converted = self._convert_messages(messages)
        if system:
            converted = [{"role": "system", "content": system}] + converted

        kwargs: dict = {
            "model": self.get_model(purpose),
            "max_tokens": max_tokens,
            "messages": converted,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        try:
            response = await self._async_client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except _openai.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except _openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except _openai.APIConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc

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
        """Stream using OpenAI async client, yielding StreamChunk objects.

        Translates OpenAI SSE chunks into the normalized StreamChunk format.
        Tool calls are emitted as tool_use_start chunks (deferred until both
        id and name are known); final inputs are collected and emitted in the
        message_stop chunk via tool_inputs_by_id.

        ``extended_thinking`` is silently ignored — OpenAI-compatible endpoints
        do not support Anthropic extended thinking.
        """
        import openai as _openai
        from codeframe.adapters.llm.base import (
            LLMAuthError,
            LLMConnectionError,
            LLMRateLimitError,
        )

        if self._async_client is None:
            self._async_client = _openai.AsyncOpenAI(
                api_key=self.api_key, base_url=self.base_url
            )

        converted = self._convert_messages(messages)
        if system:
            converted = [{"role": "system", "content": system}] + converted

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": converted,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if tools:
            kwargs["tools"] = self._convert_raw_tools(tools)
            kwargs["tool_choice"] = "auto"

        # Track partial tool calls across chunks (OpenAI streams them incrementally).
        # key: index → {id, name, arguments_parts, emitted_start}
        partial_tool_calls: dict[int, dict] = {}
        usage_input: int = 0
        usage_output: int = 0
        stop_reason: str = "end_turn"

        try:
            async for chunk in await self._async_client.chat.completions.create(**kwargs):
                if interrupt_event and interrupt_event.is_set():
                    return

                # Usage is in the final chunk when stream_options.include_usage is set
                if chunk.usage is not None:
                    usage_input = chunk.usage.prompt_tokens or 0
                    usage_output = chunk.usage.completion_tokens or 0

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                if choice.finish_reason:
                    stop_reason = _STOP_REASON_MAP.get(choice.finish_reason, choice.finish_reason)

                if delta.content:
                    yield StreamChunk(type="text_delta", text=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in partial_tool_calls:
                            partial_tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "name": (tc_delta.function.name if tc_delta.function else ""),
                                "arguments_parts": [],
                                "emitted_start": False,
                            }
                        else:
                            # Accumulate id/name as they arrive across deltas
                            if tc_delta.id:
                                partial_tool_calls[idx]["id"] = tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                partial_tool_calls[idx]["name"] = tc_delta.function.name

                        if tc_delta.function and tc_delta.function.arguments:
                            partial_tool_calls[idx]["arguments_parts"].append(
                                tc_delta.function.arguments
                            )

                        # Defer tool_use_start until both id and name are known
                        tc_info = partial_tool_calls[idx]
                        if not tc_info["emitted_start"] and tc_info["id"] and tc_info["name"]:
                            yield StreamChunk(
                                type="tool_use_start",
                                tool_id=tc_info["id"],
                                tool_name=tc_info["name"],
                                tool_input={},
                            )
                            tc_info["emitted_start"] = True

        except _openai.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except _openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except _openai.APIConnectionError as exc:
            raise LLMConnectionError(str(exc)) from exc

        # Build tool_inputs_by_id from accumulated partial tool calls
        tool_inputs_by_id: dict = {}
        for tc in partial_tool_calls.values():
            raw_args = "".join(tc["arguments_parts"]) or "{}"
            try:
                tool_inputs_by_id[tc["id"]] = json.loads(raw_args)
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse tool arguments for tool '%s' (id=%s): %r",
                    tc["name"],
                    tc["id"],
                    raw_args,
                )
                tool_inputs_by_id[tc["id"]] = {}
            # Emit tool_use_stop for each completed tool call
            yield StreamChunk(type="tool_use_stop")

        yield StreamChunk(
            type="message_stop",
            stop_reason=stop_reason,
            input_tokens=usage_input,
            output_tokens=usage_output,
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
            purpose: Purpose of call
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt

        Yields:
            Text chunks as they are generated
        """
        converted = self._convert_messages(messages)

        if system:
            converted = [{"role": "system", "content": system}] + converted

        kwargs = {
            "model": self.get_model(purpose),
            "max_tokens": max_tokens,
            "messages": converted,
            "stream": True,
            "temperature": temperature,
        }

        for chunk in self.client.chat.completions.create(**kwargs):
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert internal message format to OpenAI Chat Completions format.

        OpenAI differences from internal format:
        - Tool results must be separate messages with role='tool'
        - Tool calls on assistant messages use a specific nested format
        """
        converted = []
        for msg in messages:
            if msg.get("tool_results"):
                # Each tool result becomes its own role='tool' message
                for tr in msg["tool_results"]:
                    converted.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["content"],
                    })
            elif msg.get("tool_calls"):
                # Assistant message with tool calls
                converted.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["input"]),
                            },
                        }
                        for tc in msg["tool_calls"]
                    ],
                })
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return converted

    def _convert_tools(self, tools: list[Tool]) -> list[dict]:
        """Convert Tool objects to OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def _convert_raw_tools(self, tools: list[dict]) -> list[dict]:
        """Convert already-serialized tool dicts (Anthropic-style) to OpenAI format.

        The ``async_stream()`` interface receives tools as ``list[dict]`` with an
        ``input_schema`` key (Anthropic API format).  This helper converts them to
        the OpenAI ``function`` calling format, mirroring :meth:`_convert_tools`
        for raw dicts instead of :class:`Tool` objects.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

    def _parse_response(self, response) -> LLMResponse:
        """Parse OpenAI ChatCompletion into LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        content = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=json.loads(tc.function.arguments),
                    )
                )

        stop_reason = _STOP_REASON_MAP.get(choice.finish_reason, choice.finish_reason)

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )
