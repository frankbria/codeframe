"""Mock LLM provider for testing.

Provides predictable responses without making API calls.
Supports configurable responses and call tracking.
"""

import asyncio
from typing import AsyncIterator, Callable, Iterator, Optional

from codeframe.adapters.llm.base import (
    LLMProvider,
    LLMResponse,
    ModelSelector,
    Purpose,
    StreamChunk,
    Tool,
    ToolCall,
)


class MockProvider(LLMProvider):
    """Mock LLM provider for testing.

    Tracks all calls and returns configurable responses.
    Useful for unit tests and development without API costs.
    """

    def __init__(
        self,
        default_response: str = "Mock response",
        model_selector: Optional[ModelSelector] = None,
    ):
        """Initialize the mock provider.

        Args:
            default_response: Default response text
            model_selector: Custom model selector
        """
        super().__init__(model_selector)
        self.default_response = default_response
        self.calls: list[dict] = []
        self.responses: list[LLMResponse] = []
        self.response_index = 0
        self.response_handler: Optional[Callable[[list[dict]], LLMResponse]] = None
        self.stream_chunks: list[list[StreamChunk]] = []
        self.stream_index = 0

    def add_response(self, response: LLMResponse) -> None:
        """Add a canned response to the queue.

        Responses are returned in order for subsequent calls.

        Args:
            response: Response to add to queue
        """
        self.responses.append(response)

    def add_text_response(self, content: str) -> None:
        """Add a simple text response to the queue.

        Args:
            content: Text content for the response
        """
        self.responses.append(LLMResponse(content=content))

    def add_tool_response(self, tool_calls: list[ToolCall], content: str = "") -> None:
        """Add a response with tool calls.

        Args:
            tool_calls: Tool calls to include
            content: Optional text content
        """
        self.responses.append(
            LLMResponse(
                content=content,
                tool_calls=tool_calls,
                stop_reason="tool_use",
            )
        )

    def set_response_handler(
        self, handler: Callable[[list[dict]], LLMResponse]
    ) -> None:
        """Set a custom handler for generating responses.

        The handler receives the messages and returns a response.
        Takes precedence over queued responses.

        Args:
            handler: Function that takes messages and returns LLMResponse
        """
        self.response_handler = handler

    def complete(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        tools: Optional[list[Tool]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """Return a mock completion.

        Tracks the call and returns from queue or default.

        Args:
            messages: Conversation messages
            purpose: Purpose of call (for model selection)
            tools: Available tools (tracked but not used)
            max_tokens: Maximum tokens (tracked but not used)
            temperature: Temperature (tracked but not used)
            system: System prompt (tracked but not used)

        Returns:
            Queued response, handler result, or default response
        """
        model = self.get_model(purpose)

        # Track the call
        self.calls.append(
            {
                "messages": messages,
                "purpose": purpose,
                "tools": tools,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "model": model,
            }
        )

        # Custom handler takes precedence
        if self.response_handler:
            return self.response_handler(messages)

        # Return queued response if available
        if self.response_index < len(self.responses):
            response = self.responses[self.response_index]
            self.response_index += 1
            return response

        # Default response
        return LLMResponse(
            content=self.default_response,
            model=model,
            input_tokens=len(str(messages)),
            output_tokens=len(self.default_response),
        )

    def stream(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream mock response word by word.

        Args:
            messages: Conversation messages
            purpose: Purpose of call
            max_tokens: Maximum tokens
            temperature: Temperature
            system: System prompt

        Yields:
            Words from the response
        """
        response = self.complete(
            messages=messages,
            purpose=purpose,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )
        # Simulate streaming by yielding words
        for word in response.content.split():
            yield word + " "

    def add_stream_chunks(self, chunks: list[StreamChunk]) -> None:
        """Add a sequence of StreamChunks for the next async_stream() call.

        Args:
            chunks: Ordered list of StreamChunk objects to yield.
        """
        self.stream_chunks.append(chunks)

    async def async_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        model: str,
        max_tokens: int,
        interrupt_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Yield pre-configured StreamChunk sequences for testing.

        Falls back to a minimal text_delta + message_stop pair when no
        stream chunks have been configured via add_stream_chunks().
        """
        if self.stream_index < len(self.stream_chunks):
            chunks = self.stream_chunks[self.stream_index]
            self.stream_index += 1
        else:
            # Default: simple text response followed by message_stop
            chunks = [
                StreamChunk(type="text_delta", text=self.default_response),
                StreamChunk(
                    type="message_stop",
                    stop_reason="end_turn",
                    input_tokens=len(str(messages)),
                    output_tokens=len(self.default_response),
                    tool_inputs_by_id={},
                ),
            ]
        for chunk in chunks:
            if interrupt_event and interrupt_event.is_set():
                return
            yield chunk

    def reset(self) -> None:
        """Reset call tracking and response queue."""
        self.calls.clear()
        self.responses.clear()
        self.response_index = 0
        self.response_handler = None
        self.stream_chunks.clear()
        self.stream_index = 0

    @property
    def call_count(self) -> int:
        """Number of calls made to this provider."""
        return len(self.calls)

    @property
    def last_call(self) -> Optional[dict]:
        """The most recent call, or None if no calls made."""
        return self.calls[-1] if self.calls else None

    def get_call(self, index: int) -> Optional[dict]:
        """Get a specific call by index.

        Args:
            index: Call index (0-based)

        Returns:
            Call dict or None if index out of range
        """
        if 0 <= index < len(self.calls):
            return self.calls[index]
        return None
