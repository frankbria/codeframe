"""OpenAI-compatible LLM provider implementation.

Provides access to OpenAI and any OpenAI-compatible endpoint
(Ollama, vLLM, LM Studio, Groq, Together, etc.) via the openai SDK.
"""

import json
import os
from typing import TYPE_CHECKING, Iterator, Optional

import openai

from codeframe.adapters.llm.base import (
    LLMProvider,
    LLMResponse,
    ModelSelector,
    Purpose,
    Tool,
    ToolCall,
)

if TYPE_CHECKING:
    from codeframe.core.credentials import CredentialManager

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
