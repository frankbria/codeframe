"""Streaming chat adapter for Anthropic SDK.

Wraps ``anthropic.AsyncAnthropic().messages.stream()`` and emits typed
``ChatEvent`` objects for consumption by the WebSocket relay layer.

Supports:
- Token-by-token text streaming (TEXT_DELTA)
- Extended thinking tokens (THINKING)
- Safe read-only tool calls: read_file, list_files, search_codebase
- Interrupt via asyncio.Event
- Message persistence to session_messages after each complete turn
- Context-window management via tiktoken token counting
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Optional

from codeframe.adapters.llm.base import Tool, ToolCall, ToolResult
from codeframe.core.tools import (
    execute_tool,
    _READ_FILE_SCHEMA,
    _LIST_FILES_SCHEMA,
    _SEARCH_CODEBASE_SCHEMA,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model (matches DEFAULT_PLANNING_MODEL in base.py)
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Maximum token budget for conversation history passed to the API.
# claude-sonnet-4 context window is 200k; leave 20k for response headroom.
_MAX_HISTORY_TOKENS = 180_000

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class ChatEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_USE_START = "tool_use_start"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    COST_UPDATE = "cost_update"
    DONE = "done"
    ERROR = "error"


@dataclass
class ChatEvent:
    type: ChatEventType
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    cost_usd: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    def to_dict(self) -> dict:
        """Serialise to a dict suitable for JSON transmission."""
        d: dict = {"type": self.type.value}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_name is not None:
            d["tool_name"] = self.tool_name
        if self.tool_input is not None:
            d["tool_input"] = self.tool_input
        if self.cost_usd is not None:
            d["cost_usd"] = self.cost_usd
        if self.input_tokens is not None:
            d["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            d["output_tokens"] = self.output_tokens
        return d


# ---------------------------------------------------------------------------
# Safe read-only tool set for interactive sessions
# ---------------------------------------------------------------------------

STREAMING_SAFE_TOOLS: list[Tool] = [
    Tool(
        name="read_file",
        description=(
            "Read the contents of a file from the workspace. "
            "Supports optional line range selection."
        ),
        input_schema=_READ_FILE_SCHEMA,
    ),
    Tool(
        name="list_files",
        description=(
            "List files in the workspace directory. "
            "Respects standard ignore rules. Returns file paths with sizes."
        ),
        input_schema=_LIST_FILES_SCHEMA,
    ),
    Tool(
        name="search_codebase",
        description=(
            "Search for a regex pattern across the codebase. "
            "Returns matching lines with file paths and line numbers."
        ),
        input_schema=_SEARCH_CODEBASE_SCHEMA,
    ),
]

_TOOLS_FOR_API: list[dict] = [
    {
        "name": t.name,
        "description": t.description,
        "input_schema": t.input_schema,
    }
    for t in STREAMING_SAFE_TOOLS
]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class StreamingChatAdapter:
    """Async streaming adapter over ``anthropic.AsyncAnthropic().messages.stream()``.

    Each call to :meth:`send_message` is a single conversational turn.
    History is loaded from the DB at call time and persisted after the turn
    completes.

    Only read-only tools (read_file, list_files, search_codebase) are exposed
    to the model. Write operations and shell execution are intentionally
    excluded from interactive sessions.
    """

    def __init__(
        self,
        session_id: str,
        db_repo,
        workspace_path: Path,
        model: str = _DEFAULT_MODEL,
        api_key: Optional[str] = None,
    ) -> None:
        """Initialise the adapter.

        Args:
            session_id: ID of the interactive session (used for DB access).
            db_repo: ``InteractiveSessionRepository`` instance.
            workspace_path: Absolute path used to scope file-system tool calls.
            model: Anthropic model identifier.
            api_key: Override API key (falls back to ``ANTHROPIC_API_KEY`` env var).

        Raises:
            ValueError: If no Anthropic API key is available.
        """
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. "
                "Set the environment variable or pass api_key to StreamingChatAdapter."
            )

        self._session_id = session_id
        self._db_repo = db_repo
        self._workspace_path = workspace_path
        self._model = model

        # Lazily initialised — avoids importing anthropic at module import time
        self._async_client = None
        self._api_key = resolved_key

    @property
    def _client(self):
        if self._async_client is None:
            from anthropic import AsyncAnthropic
            self._async_client = AsyncAnthropic(api_key=self._api_key)
        return self._async_client

    # ------------------------------------------------------------------
    # History helpers
    # ------------------------------------------------------------------

    def _load_history(self) -> list[dict]:
        """Load conversation history from the DB for this session.

        Returns:
            List of ``{"role": str, "content": str}`` dicts in chronological order.
        """
        rows = self._db_repo.get_messages(self._session_id)
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def _truncate_history(self, messages: list[dict]) -> list[dict]:
        """Drop oldest messages when the history exceeds the token budget.

        Uses tiktoken for counting. If tiktoken is unavailable (e.g., in CI),
        falls back to a character-based estimate (4 chars ≈ 1 token).

        Args:
            messages: Full message list (oldest first).

        Returns:
            Trimmed message list that fits within ``_MAX_HISTORY_TOKENS``.
        """
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")

            def _count(msgs: list[dict]) -> int:
                return sum(
                    len(enc.encode(m.get("content") or ""))
                    for m in msgs
                )
        except Exception:
            def _count(msgs: list[dict]) -> int:
                return sum(len(m.get("content") or "") // 4 for m in msgs)

        while messages and _count(messages) > _MAX_HISTORY_TOKENS:
            messages = messages[1:]

        return messages

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_turn(self, user_content: str, assistant_content: str) -> None:
        """Persist user message and assistant response to session_messages.

        Args:
            user_content: The user's message text.
            assistant_content: The complete assistant response accumulated
                across all TEXT_DELTA events in this turn.
        """
        await asyncio.to_thread(
            self._db_repo.add_message,
            session_id=self._session_id,
            role="user",
            content=user_content,
        )
        await asyncio.to_thread(
            self._db_repo.add_message,
            session_id=self._session_id,
            role="assistant",
            content=assistant_content,
        )

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a safe tool call in a thread pool and return the result string.

        Only tools in ``STREAMING_SAFE_TOOLS`` are permitted. Any attempt to
        call an unlisted tool returns an error string.

        Args:
            tool_call: The tool call object from the LLM.

        Returns:
            String result of the tool execution (may start with "Error:" on
            failure — the caller should still include it as a tool result so
            the model can react).
        """
        allowed = {t.name for t in STREAMING_SAFE_TOOLS}
        if tool_call.name not in allowed:
            return f"Error: tool '{tool_call.name}' is not available in interactive sessions."

        result: ToolResult = await asyncio.to_thread(
            execute_tool, tool_call, self._workspace_path
        )
        return result.content

    # ------------------------------------------------------------------
    # Main streaming entry point
    # ------------------------------------------------------------------

    async def send_message(
        self,
        content: str,
        history: list[dict],
        interrupt_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Stream a single conversational turn.

        Yields ``ChatEvent`` objects as the model generates.  The caller is
        responsible for forwarding these to the WebSocket client.

        The method loops internally to handle tool calls (tool_use → tool_result
        → re-enter stream) until ``stop_reason == "end_turn"`` or the interrupt
        fires.

        Args:
            content: The user's message for this turn.
            history: Prior messages to include as context.  If empty, history
                is loaded from the DB automatically.
            interrupt_event: Optional event; when set the stream stops within
                the current chunk iteration.

        Yields:
            ``ChatEvent`` with types from ``ChatEventType``.
        """
        # Load history from DB if caller didn't supply it
        if not history:
            history = self._load_history()

        # Build the message list for this turn
        messages: list[dict] = list(history) + [{"role": "user", "content": content}]
        messages = self._truncate_history(messages)

        accumulated_text = ""

        try:
            async for event in self._stream_turn(
                messages=messages,
                interrupt_event=interrupt_event,
            ):
                if event.type == ChatEventType.TEXT_DELTA and event.content:
                    accumulated_text += event.content
                yield event

        except Exception as exc:
            logger.error("StreamingChatAdapter error: %s", exc, exc_info=True)
            yield ChatEvent(type=ChatEventType.ERROR, content=str(exc))
            return

        # Persist the turn (errors are logged, not raised)
        try:
            await self._persist_turn(content, accumulated_text)
        except Exception as exc:
            logger.error("StreamingChatAdapter persistence error: %s", exc)

    async def _stream_turn(
        self,
        messages: list[dict],
        interrupt_event: Optional[asyncio.Event],
    ) -> AsyncIterator[ChatEvent]:
        """Execute one API turn, handling tool loops internally.

        Yields ``ChatEvent`` objects for all events in the turn, including
        any tool sub-turns.
        """
        current_messages = list(messages)

        while True:
            # Track tool calls seen in this API turn for the follow-up message
            pending_tool_calls: list[dict] = []  # {id, name, input, result}
            active_tool: dict | None = None  # buffering the current tool_use block
            stop_reason = "end_turn"

            async with self._client.messages.stream(
                model=self._model,
                messages=current_messages,
                tools=_TOOLS_FOR_API,
                max_tokens=4096,
            ) as stream:
                async for sdk_event in stream:
                    # Honour interrupt between chunks
                    if interrupt_event and interrupt_event.is_set():
                        return

                    event_type = sdk_event.type

                    if event_type == "content_block_start":
                        block = sdk_event.content_block
                        if block.type == "tool_use":
                            active_tool = {
                                "id": block.id,
                                "name": block.name,
                                "input": getattr(block, "input", {}),
                            }
                            yield ChatEvent(
                                type=ChatEventType.TOOL_USE_START,
                                tool_name=block.name,
                                tool_input=getattr(block, "input", {}),
                            )

                    elif event_type == "content_block_delta":
                        delta = sdk_event.delta
                        if delta.type == "text_delta":
                            yield ChatEvent(
                                type=ChatEventType.TEXT_DELTA,
                                content=delta.text,
                            )
                        elif delta.type == "thinking_delta":
                            yield ChatEvent(
                                type=ChatEventType.THINKING,
                                content=delta.thinking,
                            )
                        elif delta.type == "input_json_delta" and active_tool is not None:
                            # The SDK may stream tool input as JSON deltas; accumulate
                            pass  # Full input is available on content_block_stop via final msg

                    elif event_type == "content_block_stop":
                        if active_tool is not None:
                            pending_tool_calls.append(active_tool)
                            active_tool = None

                    elif event_type == "message_stop":
                        # Flush any tool block that didn't get a content_block_stop
                        if active_tool is not None:
                            pending_tool_calls.append(active_tool)
                            active_tool = None

                        # Collect final usage stats
                        final_msg = stream.get_final_message()
                        stop_reason = final_msg.stop_reason or "end_turn"

                        # Rebuild tool inputs from final message (more reliable than streaming)
                        if pending_tool_calls and hasattr(final_msg, "content"):
                            _rebuild_tool_inputs(final_msg.content, pending_tool_calls)

                        yield ChatEvent(
                            type=ChatEventType.COST_UPDATE,
                            input_tokens=final_msg.usage.input_tokens,
                            output_tokens=final_msg.usage.output_tokens,
                            cost_usd=_estimate_cost(
                                final_msg.usage.input_tokens,
                                final_msg.usage.output_tokens,
                                self._model,
                            ),
                        )

            if stop_reason == "end_turn" or not pending_tool_calls:
                yield ChatEvent(type=ChatEventType.DONE)
                return

            # Execute pending tool calls and loop for another API turn
            tool_result_blocks = []
            for tc in pending_tool_calls:
                if interrupt_event and interrupt_event.is_set():
                    yield ChatEvent(type=ChatEventType.DONE)
                    return

                tool_call = ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    input=tc.get("input") or {},
                )
                result_text = await self._execute_tool(tool_call)

                yield ChatEvent(
                    type=ChatEventType.TOOL_RESULT,
                    tool_name=tc["name"],
                    content=result_text,
                )

                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result_text,
                    }
                )

            # Append the tool results as a user message for the next turn
            current_messages = current_messages + [
                {"role": "user", "content": tool_result_blocks}
            ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rebuild_tool_inputs(content_blocks, pending_tool_calls: list[dict]) -> None:
    """Back-fill tool inputs from the final message content blocks.

    The streaming API may emit input_json_delta events that are tricky to
    reconstruct incrementally. Reading inputs off the final message is simpler
    and more reliable.
    """
    by_id = {tc["id"]: tc for tc in pending_tool_calls}
    for block in content_blocks:
        block_id = getattr(block, "id", None)
        if block_id and block_id in by_id and getattr(block, "type", None) == "tool_use":
            by_id[block_id]["input"] = getattr(block, "input", {})


def _estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Rough cost estimate in USD.

    Uses approximate pricing for claude-sonnet-4. Returns 0.0 for unknown models
    rather than raising — cost tracking is best-effort.
    """
    # Per-million-token pricing (approximate, as of mid-2025)
    _PRICING: dict[str, tuple[float, float]] = {
        "claude-sonnet-4-20250514": (3.0, 15.0),
        "claude-opus-4-20250514": (15.0, 75.0),
        "claude-3-5-haiku-20241022": (0.8, 4.0),
    }
    # Match by prefix to handle minor model variant suffixes
    for prefix, (in_price, out_price) in _PRICING.items():
        if model.startswith(prefix):
            return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    return 0.0
