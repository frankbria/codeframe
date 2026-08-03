"""Anthropic's SDK-event -> StreamChunk translation had no coverage (#949).

``AnthropicProvider.async_stream`` is what every streaming surface in the
product runs on — the agent chat WebSocket, the SSE task stream, the ReAct
loop's tool calls. It maps ~5 SDK event shapes onto ``StreamChunk``, tracks an
open tool block across events, and rebuilds final tool inputs from the closing
message. None of it was executed by a test.

The events here are shaped like the real SDK's: ``sdk_event.type``,
``sdk_event.content_block.{type,id,name,input}``, ``sdk_event.delta.{type,text,
thinking}``, and a final message with ``.stop_reason``, ``.usage.{input,output}
_tokens`` and ``.content`` blocks. Only the transport is substituted; the
translation under test is the real one.
"""

import asyncio
from types import SimpleNamespace

import pytest

from codeframe.adapters.llm.anthropic import AnthropicProvider

pytestmark = pytest.mark.v2


# --------------------------------------------------------------------------
# SDK-shaped event builders
# --------------------------------------------------------------------------

def text_delta(text: str):
    return SimpleNamespace(
        type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=text)
    )


def thinking_delta(text: str):
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="thinking_delta", thinking=text),
    )


def input_json_delta(partial: str):
    """The SDK emits these; the translator deliberately drops them, rebuilding
    final inputs from message_stop instead."""
    return SimpleNamespace(
        type="content_block_delta",
        delta=SimpleNamespace(type="input_json_delta", partial_json=partial),
    )


def tool_start(tool_id: str, name: str, tool_input=None):
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(
            type="tool_use", id=tool_id, name=name, input=tool_input or {}
        ),
    )


def text_block_start():
    return SimpleNamespace(
        type="content_block_start", content_block=SimpleNamespace(type="text")
    )


def block_stop():
    return SimpleNamespace(type="content_block_stop")


def message_stop():
    return SimpleNamespace(type="message_stop")


def final_message(*, stop_reason="end_turn", tool_blocks=(), in_tokens=11, out_tokens=22):
    content = [
        SimpleNamespace(type="tool_use", id=tid, input=inp) for tid, inp in tool_blocks
    ]
    return SimpleNamespace(
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
        content=content,
    )


class _FakeStream:
    """Stands in for the SDK's async context-managed stream."""

    def __init__(self, events, final):
        self._events = events
        self._final = final
        self.get_final_message_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for event in self._events:
                yield event

        return gen()

    async def get_final_message(self):
        self.get_final_message_calls += 1
        return self._final


def _provider(events, final, *, capture: dict | None = None) -> AnthropicProvider:
    """A real provider whose SDK client returns a scripted stream."""
    provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")

    def make_stream(**kwargs):
        if capture is not None:
            capture.update(kwargs)
        return _FakeStream(events, final)

    provider._async_client = SimpleNamespace(
        messages=SimpleNamespace(stream=make_stream),
        beta=SimpleNamespace(messages=SimpleNamespace(stream=make_stream)),
    )
    return provider


async def _collect(provider, **kwargs):
    return [
        chunk
        async for chunk in provider.async_stream(
            messages=[{"role": "user", "content": "hi"}],
            system="sys",
            tools=[],
            model="claude-x",
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        )
    ]


class TestTextAndThinkingDeltas:
    @pytest.mark.asyncio
    async def test_text_deltas_become_text_delta_chunks(self):
        provider = _provider(
            [text_delta("Hel"), text_delta("lo"), message_stop()], final_message()
        )

        chunks = await _collect(provider)

        text = [c for c in chunks if c.type == "text_delta"]
        assert [c.text for c in text] == ["Hel", "lo"]

    @pytest.mark.asyncio
    async def test_thinking_deltas_read_the_thinking_attribute_not_text(self):
        """`delta.thinking`, not `delta.text` — the two shapes differ and
        reading the wrong one raises AttributeError mid-stream."""
        provider = _provider([thinking_delta("hmm"), message_stop()], final_message())

        chunks = await _collect(provider)

        thinking = [c for c in chunks if c.type == "thinking_delta"]
        assert [c.text for c in thinking] == ["hmm"]

    @pytest.mark.asyncio
    async def test_input_json_deltas_are_dropped(self):
        """Deliberate: final inputs come from message_stop, so forwarding these
        would double-report partial JSON to the UI."""
        provider = _provider(
            [input_json_delta('{"pa'), input_json_delta('th":1}'), message_stop()],
            final_message(),
        )

        chunks = await _collect(provider)

        assert [c.type for c in chunks] == ["message_stop"]

    @pytest.mark.asyncio
    async def test_a_text_content_block_start_emits_nothing(self):
        """Only tool_use blocks produce a start chunk."""
        provider = _provider([text_block_start(), message_stop()], final_message())

        chunks = await _collect(provider)

        assert [c.type for c in chunks] == ["message_stop"]


class TestToolBlocks:
    @pytest.mark.asyncio
    async def test_a_tool_block_start_carries_id_and_name(self):
        provider = _provider(
            [tool_start("toolu_1", "read_file"), block_stop(), message_stop()],
            final_message(tool_blocks=[("toolu_1", {"path": "a.py"})]),
        )

        chunks = await _collect(provider)

        start = next(c for c in chunks if c.type == "tool_use_start")
        assert start.tool_id == "toolu_1"
        assert start.tool_name == "read_file"

    @pytest.mark.asyncio
    async def test_the_block_is_closed_exactly_once(self):
        provider = _provider(
            [tool_start("toolu_1", "read_file"), block_stop(), message_stop()],
            final_message(tool_blocks=[("toolu_1", {})]),
        )

        chunks = await _collect(provider)

        assert [c.type for c in chunks].count("tool_use_stop") == 1

    @pytest.mark.asyncio
    async def test_an_unclosed_tool_block_is_flushed_at_message_stop(self):
        """The SDK can end a turn without a content_block_stop. Without the
        flush the UI keeps a tool call spinning forever."""
        provider = _provider(
            [tool_start("toolu_1", "read_file"), message_stop()],
            final_message(tool_blocks=[("toolu_1", {})]),
        )

        chunks = await _collect(provider)

        types = [c.type for c in chunks]
        assert types.index("tool_use_stop") < types.index("message_stop")

    @pytest.mark.asyncio
    async def test_a_stray_block_stop_without_an_open_tool_emits_nothing(self):
        """content_block_stop fires for TEXT blocks too. Emitting tool_use_stop
        there would close a tool call the UI never opened."""
        provider = _provider(
            [text_block_start(), block_stop(), message_stop()], final_message()
        )

        chunks = await _collect(provider)

        assert "tool_use_stop" not in [c.type for c in chunks]

    @pytest.mark.asyncio
    async def test_two_sequential_tools_each_get_their_own_pair(self):
        provider = _provider(
            [
                tool_start("toolu_1", "read_file"),
                block_stop(),
                tool_start("toolu_2", "write_file"),
                block_stop(),
                message_stop(),
            ],
            final_message(tool_blocks=[("toolu_1", {}), ("toolu_2", {})]),
        )

        chunks = await _collect(provider)

        types = [c.type for c in chunks]
        assert types == [
            "tool_use_start",
            "tool_use_stop",
            "tool_use_start",
            "tool_use_stop",
            "message_stop",
        ]


class TestMessageStop:
    @pytest.mark.asyncio
    async def test_usage_and_stop_reason_come_from_the_final_message(self):
        provider = _provider(
            [message_stop()],
            final_message(stop_reason="tool_use", in_tokens=1234, out_tokens=56),
        )

        stop = (await _collect(provider))[-1]

        assert stop.stop_reason == "tool_use"
        assert stop.input_tokens == 1234
        assert stop.output_tokens == 56

    @pytest.mark.asyncio
    async def test_a_null_stop_reason_defaults_to_end_turn(self):
        """`final_msg.stop_reason or "end_turn"` — None reaches consumers that
        branch on the string."""
        provider = _provider([message_stop()], final_message(stop_reason=None))

        assert (await _collect(provider))[-1].stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_final_tool_inputs_are_rebuilt_by_id(self):
        """The headline reason input_json_delta is dropped: this mapping is
        what the ReAct loop actually executes."""
        provider = _provider(
            [tool_start("toolu_1", "read_file"), block_stop(), message_stop()],
            final_message(tool_blocks=[("toolu_1", {"path": "a.py", "lines": 10})]),
        )

        stop = (await _collect(provider))[-1]

        assert stop.tool_inputs_by_id == {"toolu_1": {"path": "a.py", "lines": 10}}

    @pytest.mark.asyncio
    async def test_non_tool_content_blocks_are_not_in_the_map(self):
        final = final_message(tool_blocks=[("toolu_1", {"x": 1})])
        final.content.append(SimpleNamespace(type="text", text="ignored"))
        provider = _provider([message_stop()], final)

        stop = (await _collect(provider))[-1]

        assert set(stop.tool_inputs_by_id) == {"toolu_1"}


class TestInterruption:
    @pytest.mark.asyncio
    async def test_a_set_interrupt_event_stops_the_stream(self):
        """Checked per event, so a long generation can be cancelled. Nothing
        after the check should be yielded — including message_stop."""
        event = asyncio.Event()
        event.set()
        provider = _provider(
            [text_delta("never"), message_stop()], final_message()
        )

        chunks = await _collect(provider, interrupt_event=event)

        assert chunks == []

    @pytest.mark.asyncio
    async def test_an_unset_event_does_not_interfere(self):
        provider = _provider([text_delta("ok"), message_stop()], final_message())

        chunks = await _collect(provider, interrupt_event=asyncio.Event())

        assert [c.type for c in chunks] == ["text_delta", "message_stop"]


class TestExtendedThinkingRequestShape:
    @pytest.mark.asyncio
    async def test_thinking_is_requested_with_a_budget_below_max_tokens(self):
        capture: dict = {}
        provider = _provider([message_stop()], final_message(), capture=capture)

        await _collect(provider, extended_thinking=True, max_tokens=8192)

        assert capture["betas"] == ["interleaved-thinking-2025-05-14"]
        budget = capture["thinking"]["budget_tokens"]
        assert 1024 <= budget < 8192

    @pytest.mark.asyncio
    async def test_it_is_skipped_when_max_tokens_leaves_no_room(self):
        """budget_tokens must be >= 1024 AND < max_tokens, so a small cap
        cannot carry thinking at all."""
        capture: dict = {}
        provider = _provider([message_stop()], final_message(), capture=capture)

        await _collect(provider, extended_thinking=True, max_tokens=1024)

        assert "thinking" not in capture
        assert "betas" not in capture

    @pytest.mark.asyncio
    async def test_an_sdk_that_rejects_betas_degrades_instead_of_failing(self):
        """#766: a blanket except here swallowed the TypeError and silently
        dropped thinking every turn. Narrowed to TypeError — assert the
        fallback still produces a usable stream."""
        provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")
        calls = {"beta": 0, "plain": 0}

        def beta_stream(**kwargs):
            calls["beta"] += 1
            raise TypeError("unexpected keyword argument 'betas'")

        def plain_stream(**kwargs):
            calls["plain"] += 1
            assert "betas" not in kwargs, "the retry still sent betas"
            assert "thinking" not in kwargs
            return _FakeStream([message_stop()], final_message())

        provider._async_client = SimpleNamespace(
            messages=SimpleNamespace(stream=plain_stream),
            beta=SimpleNamespace(messages=SimpleNamespace(stream=beta_stream)),
        )

        chunks = await _collect(provider, extended_thinking=True, max_tokens=8192)

        assert calls == {"beta": 1, "plain": 1}
        assert [c.type for c in chunks] == ["message_stop"]

    @pytest.mark.asyncio
    async def test_a_type_error_without_thinking_is_not_swallowed(self):
        """The fallback exists only for the betas path. A TypeError on a plain
        stream is a real bug and must surface."""
        provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")

        def boom(**kwargs):
            raise TypeError("something genuinely wrong")

        provider._async_client = SimpleNamespace(
            messages=SimpleNamespace(stream=boom),
            beta=SimpleNamespace(messages=SimpleNamespace(stream=boom)),
        )

        with pytest.raises(TypeError):
            await _collect(provider, extended_thinking=False)


class TestAFullRealisticTurn:
    @pytest.mark.asyncio
    async def test_thinking_then_text_then_a_tool_call(self):
        """The event sequence a real extended-thinking turn produces."""
        provider = _provider(
            [
                thinking_delta("I should read the file."),
                text_delta("Let me check "),
                text_delta("that file."),
                tool_start("toolu_abc", "read_file"),
                input_json_delta('{"path"'),
                input_json_delta(': "main.py"}'),
                block_stop(),
                message_stop(),
            ],
            final_message(
                stop_reason="tool_use",
                tool_blocks=[("toolu_abc", {"path": "main.py"})],
                in_tokens=500,
                out_tokens=42,
            ),
        )

        chunks = await _collect(provider)

        assert [c.type for c in chunks] == [
            "thinking_delta",
            "text_delta",
            "text_delta",
            "tool_use_start",
            "tool_use_stop",
            "message_stop",
        ]
        stop = chunks[-1]
        assert stop.stop_reason == "tool_use"
        assert stop.tool_inputs_by_id == {"toolu_abc": {"path": "main.py"}}
        assert (stop.input_tokens, stop.output_tokens) == (500, 42)
