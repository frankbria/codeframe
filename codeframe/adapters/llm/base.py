"""Base LLM adapter interface.

Defines the protocol that all LLM providers must implement,
along with shared data structures for requests and responses.
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Iterator, Optional


# ---------------------------------------------------------------------------
# Common exception hierarchy
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for LLM provider errors."""


class LLMAuthError(LLMError):
    """Authentication failure (bad key, expired token, etc.)."""


class LLMRateLimitError(LLMError):
    """Rate limit exceeded — caller may retry after a backoff."""


class LLMConnectionError(LLMError):
    """Network or connection error."""


class Purpose(str, Enum):
    """Purpose of an LLM call, used for model selection."""

    PLANNING = "planning"  # Complex reasoning, architecture decisions
    EXECUTION = "execution"  # Code generation, editing
    GENERATION = "generation"  # Simple text generation, summaries
    CORRECTION = "correction"  # Self-correction after errors (uses stronger model)
    SUPERVISION = "supervision"  # Supervisor decisions (blocker triage, tactical resolution)


# Default model aliases (use valid Anthropic model identifiers)
DEFAULT_PLANNING_MODEL = "claude-sonnet-4-20250514"
DEFAULT_EXECUTION_MODEL = "claude-sonnet-4-20250514"
DEFAULT_GENERATION_MODEL = "claude-3-5-haiku-20241022"
DEFAULT_CORRECTION_MODEL = "claude-opus-4-20250514"  # Step up for fixing errors
DEFAULT_SUPERVISION_MODEL = "claude-opus-4-20250514"  # Strong model for supervisor decisions


@dataclass
class ModelSelector:
    """Task-based model selection heuristics.

    Maps operation purposes to appropriate models. Model names can be
    overridden via environment variables:
    - CODEFRAME_PLANNING_MODEL
    - CODEFRAME_EXECUTION_MODEL
    - CODEFRAME_GENERATION_MODEL
    - CODEFRAME_CORRECTION_MODEL
    - CODEFRAME_SUPERVISION_MODEL
    """

    planning_model: str = ""
    execution_model: str = ""
    generation_model: str = ""
    correction_model: str = ""
    supervision_model: str = ""

    def __post_init__(self):
        """Load model names from environment or use defaults.

        Only assigns from environment/defaults when the field is empty/falsy,
        respecting any explicit constructor overrides.
        """
        if not self.planning_model:
            self.planning_model = os.getenv(
                "CODEFRAME_PLANNING_MODEL", DEFAULT_PLANNING_MODEL
            )
        if not self.execution_model:
            self.execution_model = os.getenv(
                "CODEFRAME_EXECUTION_MODEL", DEFAULT_EXECUTION_MODEL
            )
        if not self.generation_model:
            self.generation_model = os.getenv(
                "CODEFRAME_GENERATION_MODEL", DEFAULT_GENERATION_MODEL
            )
        if not self.correction_model:
            self.correction_model = os.getenv(
                "CODEFRAME_CORRECTION_MODEL", DEFAULT_CORRECTION_MODEL
            )
        if not self.supervision_model:
            self.supervision_model = os.getenv(
                "CODEFRAME_SUPERVISION_MODEL", DEFAULT_SUPERVISION_MODEL
            )

    def for_purpose(self, purpose: Purpose) -> str:
        """Get the model for a given purpose.

        Args:
            purpose: The purpose of the LLM call

        Returns:
            Model identifier string
        """
        if purpose == Purpose.PLANNING:
            return self.planning_model
        elif purpose == Purpose.EXECUTION:
            return self.execution_model
        elif purpose == Purpose.GENERATION:
            return self.generation_model
        elif purpose == Purpose.CORRECTION:
            return self.correction_model
        elif purpose == Purpose.SUPERVISION:
            return self.supervision_model
        else:
            return self.execution_model  # Default fallback


@dataclass
class StreamChunk:
    """A normalized chunk from a streaming LLM response.

    Provider-specific streaming formats are translated into this common type
    by each :class:`LLMProvider` implementation.

    Attributes:
        type: Event type — one of ``"text_delta"``, ``"thinking_delta"``,
            ``"tool_use_start"``, ``"tool_use_stop"``, ``"message_stop"``.
        text: Text content for ``text_delta`` and ``thinking_delta`` types.
        tool_id: Tool call ID for ``tool_use_start``.
        tool_name: Tool name for ``tool_use_start``.
        tool_input: Tool input dict for ``tool_use_start`` (may be empty;
            final inputs are provided in the ``message_stop`` chunk).
        input_tokens: Input token count, populated for ``message_stop``.
        output_tokens: Output token count, populated for ``message_stop``.
        stop_reason: Why the model stopped, populated for ``message_stop``.
        tool_inputs_by_id: Mapping of tool_id → final input dict, populated
            for ``message_stop``.  More reliable than streaming incremental
            input deltas.
    """

    type: str
    text: Optional[str] = None
    tool_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    stop_reason: Optional[str] = None
    tool_inputs_by_id: Optional[dict] = None


@dataclass
class ToolCall:
    """Represents a tool call requested by the LLM.

    Attributes:
        id: Unique identifier for this tool call
        name: Name of the tool to call
        input: Input arguments for the tool (as dict)
    """

    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    """Result of executing a tool call.

    Attributes:
        tool_call_id: ID of the tool call this is responding to
        content: Result content (string or structured data)
        is_error: Whether this result represents an error
    """

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class LLMResponse:
    """Response from an LLM completion.

    Attributes:
        content: Text content of the response (may be empty if tool calls)
        tool_calls: List of tool calls requested by the model
        stop_reason: Why the model stopped generating
        model: Model that generated this response
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
    """

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


@dataclass
class Message:
    """A message in a conversation.

    Attributes:
        role: Message role ("user", "assistant", "system")
        content: Message content
        tool_calls: Tool calls (for assistant messages)
        tool_results: Tool results (for user messages responding to tool calls)
    """

    role: str
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dict format for API calls."""
        result = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in self.tool_calls
            ]
        if self.tool_results:
            result["tool_results"] = [
                {
                    "tool_call_id": tr.tool_call_id,
                    "content": tr.content,
                    "is_error": tr.is_error,
                }
                for tr in self.tool_results
            ]
        return result


@dataclass
class Tool:
    """Definition of a tool the LLM can use.

    Attributes:
        name: Tool name
        description: What the tool does
        input_schema: JSON schema for tool input
    """

    name: str
    description: str
    input_schema: dict


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations must provide complete() and optionally stream().
    Model selection is handled via the purpose parameter.
    """

    def __init__(self, model_selector: Optional[ModelSelector] = None):
        """Initialize the provider.

        Args:
            model_selector: Custom model selector (uses defaults if None)
        """
        self.model_selector = model_selector or ModelSelector()

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        tools: Optional[list[Tool]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a completion.

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
        pass

    def stream(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> Iterator[str]:
        """Stream a completion token by token.

        Default implementation falls back to complete() and yields full response.
        Override for true streaming support.

        Args:
            messages: Conversation messages
            purpose: Purpose of call (for model selection)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system: System prompt

        Yields:
            Text chunks as they are generated
        """
        response = self.complete(
            messages=messages,
            purpose=purpose,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )
        yield response.content

    async def async_complete(
        self,
        messages: list[dict],
        purpose: Purpose = Purpose.EXECUTION,
        tools: Optional[list["Tool"]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> "LLMResponse":
        """Async completion.

        Default implementation wraps the synchronous :meth:`complete` in a
        thread-pool executor so it never blocks the event loop.  Subclasses
        should override this with a truly async implementation when the
        underlying SDK supports it.

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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.complete(messages, purpose, tools, max_tokens, temperature, system),
        )

    def supports(self, capability: str) -> bool:
        """Check whether this provider supports an optional capability.

        Args:
            capability: Capability name, e.g. ``"extended_thinking"``.

        Returns:
            ``True`` if the capability is supported, ``False`` otherwise.
        """
        return False

    async def async_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        model: str,
        max_tokens: int,
        interrupt_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator["StreamChunk"]:
        """Stream a completion as normalized :class:`StreamChunk` objects.

        Subclasses should override this with a provider-specific implementation.
        The default raises :exc:`NotImplementedError`.

        Args:
            messages: Conversation messages in the provider's expected format.
            system: System prompt string.
            tools: Already-serialized tool definitions (list of dicts).
            model: Model identifier to use for this call.
            max_tokens: Maximum output tokens.
            interrupt_event: When set, the stream should stop at the next
                opportunity.

        Yields:
            :class:`StreamChunk` objects in order of generation.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement async_stream(). "
            "Override this method in your provider subclass."
        )
        if False:  # pragma: no cover  # makes this an async generator
            yield  # type: ignore[misc]

    def get_model(self, purpose: Purpose) -> str:
        """Get the model for a given purpose.

        Args:
            purpose: The purpose of the LLM call

        Returns:
            Model identifier string
        """
        return self.model_selector.for_purpose(purpose)
