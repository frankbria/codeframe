"""The streaming tool loop must be provider-neutral (#918).

`StreamingChatAdapter` is documented provider-agnostic and always offers tools,
but after executing them it re-entered the stream with **Anthropic-format**
`tool_use` / `tool_result` blocks. `OpenAIProvider._convert_messages` only
special-cases the internal neutral keys (`tool_calls` / `tool_results`), so those
blocks fell through to the passthrough branch and raw Anthropic content was
POSTed to Chat Completions — a 400 for every interactive session on
openai/ollama/vllm as soon as the model called a tool.

Both providers already translate the neutral keys, so the fix belongs in the one
place that emits them rather than as a second translation layer.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.v2


def _continuation_messages() -> list[dict]:
    """The two messages the tool loop appends after executing a tool call.

    Built by driving the adapter's own continuation builder so this test tracks
    the production shape rather than a copy of it.
    """
    from codeframe.core.adapters.streaming_chat import build_tool_continuation

    return build_tool_continuation(
        assistant_text="Let me check that file.",
        tool_calls=[{"id": "call_1", "name": "read_file", "input": {"path": "a.py"}}],
        tool_results=[{"tool_call_id": "call_1", "content": "print('hi')"}],
    )


class TestNeutralContinuationShape:
    def test_the_assistant_turn_uses_the_neutral_tool_calls_key(self) -> None:
        assistant, _ = _continuation_messages()

        assert assistant["role"] == "assistant"
        assert assistant["tool_calls"] == [
            {"id": "call_1", "name": "read_file", "input": {"path": "a.py"}}
        ]
        # Not Anthropic blocks — those are what OpenAI's passthrough branch
        # forwarded verbatim and the API rejected.
        assert not isinstance(assistant["content"], list)

    def test_the_tool_result_turn_uses_the_neutral_tool_results_key(self) -> None:
        _, results = _continuation_messages()

        assert results["tool_results"] == [
            {"tool_call_id": "call_1", "content": "print('hi')"}
        ]
        assert not isinstance(results["content"], list)


class TestOpenAIPath:
    """AC1/AC2 — one tool round-trip through the OpenAI conversion."""

    def _converted(self) -> list[dict]:
        from codeframe.adapters.llm.openai import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)  # no client/network needed
        messages = [{"role": "user", "content": "read a.py"}] + _continuation_messages()
        return provider._convert_messages(messages)

    def test_the_assistant_turn_becomes_openai_tool_calls(self) -> None:
        converted = self._converted()

        assistant = next(m for m in converted if m["role"] == "assistant")
        assert "tool_calls" in assistant, (
            "assistant turn did not convert — raw Anthropic blocks would be POSTed"
        )
        call = assistant["tool_calls"][0]
        assert call["type"] == "function"
        assert call["id"] == "call_1"
        assert call["function"]["name"] == "read_file"
        # OpenAI wants a JSON *string* for arguments, not a dict.
        assert json.loads(call["function"]["arguments"]) == {"path": "a.py"}

    def test_the_tool_result_becomes_a_role_tool_message(self) -> None:
        converted = self._converted()

        tool_msgs = [m for m in converted if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_1"
        assert tool_msgs[0]["content"] == "print('hi')"

    def test_no_anthropic_block_survives_into_the_payload(self) -> None:
        """The actual 400 cause: Anthropic block dicts reaching Chat Completions."""
        payload = json.dumps(self._converted())

        for leaked in ("tool_use", "tool_result", "tool_use_id"):
            assert leaked not in payload, f"{leaked!r} leaked into the OpenAI payload"


class TestAnthropicPathUnchanged:
    """The neutral keys must round-trip on Anthropic too — no regression."""

    def _converted(self) -> list[dict]:
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider.__new__(AnthropicProvider)
        messages = [{"role": "user", "content": "read a.py"}] + _continuation_messages()
        return provider._convert_messages(messages)

    def test_the_assistant_turn_becomes_a_tool_use_block(self) -> None:
        converted = self._converted()

        assistant = next(m for m in converted if m["role"] == "assistant")
        blocks = assistant["content"]
        assert {"type": "text", "text": "Let me check that file."} in blocks
        assert {
            "type": "tool_use",
            "id": "call_1",
            "name": "read_file",
            "input": {"path": "a.py"},
        } in blocks

    def test_the_tool_result_becomes_a_tool_result_block(self) -> None:
        converted = self._converted()

        # Anthropic rejects a tool_result that is not immediately preceded by the
        # assistant message carrying the matching tool_use.
        assert converted[-2]["role"] == "assistant"
        assert converted[-1]["role"] == "user"
        block = converted[-1]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "call_1"
        assert block["content"] == "print('hi')"


class TestMultipleToolCalls:
    def test_every_call_and_result_is_paired(self) -> None:
        from codeframe.adapters.llm.openai import OpenAIProvider
        from codeframe.core.adapters.streaming_chat import build_tool_continuation

        messages = build_tool_continuation(
            assistant_text="",
            tool_calls=[
                {"id": "c1", "name": "read_file", "input": {"path": "a.py"}},
                {"id": "c2", "name": "list_files", "input": {}},
            ],
            tool_results=[
                {"tool_call_id": "c1", "content": "a"},
                {"tool_call_id": "c2", "content": "b"},
            ],
        )

        provider = OpenAIProvider.__new__(OpenAIProvider)
        converted = provider._convert_messages(messages)

        assistant = next(m for m in converted if m["role"] == "assistant")
        assert [c["id"] for c in assistant["tool_calls"]] == ["c1", "c2"]
        assert [m["tool_call_id"] for m in converted if m["role"] == "tool"] == ["c1", "c2"]

    def test_an_empty_assistant_text_still_produces_a_valid_turn(self) -> None:
        """A model that calls a tool with no prose must not emit a null content."""
        from codeframe.core.adapters.streaming_chat import build_tool_continuation

        assistant, _ = build_tool_continuation(
            assistant_text="",
            tool_calls=[{"id": "c1", "name": "t", "input": {}}],
            tool_results=[{"tool_call_id": "c1", "content": "r"}],
        )
        assert assistant["content"] == ""
        assert assistant["tool_calls"]
