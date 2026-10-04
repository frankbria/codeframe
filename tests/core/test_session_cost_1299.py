"""Interactive-session cost comes from the one price table (#1299).

`streaming_chat._estimate_cost` kept its own table and returned 0.0 for any
model it did not know. The session UI defaults to claude-sonnet-4-6, which it
did not know, so every turn was stored as $0.00; its Opus 4.5 and Haiku 4.5
rows disagreed with MODEL_PRICING; and it ignored CODEFRAME_MODEL_PRICING.
The #932 rule applies here too: an unpriced call is unknown, never $0.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from codeframe.adapters.llm.base import StreamChunk
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core.adapters import streaming_chat
from codeframe.core.adapters.streaming_chat import ChatEventType, StreamingChatAdapter
from codeframe.lib.metrics_tracker import MODEL_PRICING

pytestmark = [pytest.mark.v2, pytest.mark.asyncio]

REPO = Path(__file__).resolve().parents[2]
MILLION = 1_000_000


async def _turn_cost(model: str, tmp_path, input_tokens=MILLION, output_tokens=MILLION):
    from unittest.mock import MagicMock

    repo = MagicMock()
    repo.get_messages.return_value = []
    repo.get_recent_messages.return_value = []
    provider = MockProvider()
    provider.add_stream_chunks([
        StreamChunk(type="text_delta", text="ok"),
        StreamChunk(type="message_stop", stop_reason="end_turn",
                    input_tokens=input_tokens, output_tokens=output_tokens, tool_inputs_by_id={}),
    ])
    adapter = StreamingChatAdapter(
        session_id="s1", db_repo=repo, workspace_path=tmp_path, model=model, provider=provider
    )
    [event] = [e async for e in adapter.send_message("hi", []) if e.type == ChatEventType.COST_UPDATE]
    return event


async def test_the_session_ui_default_model_is_priced(tmp_path):
    event = await _turn_cost("claude-sonnet-4-6", tmp_path)
    assert event.cost_usd == pytest.approx(3.00 + 15.00)


async def test_rates_come_from_model_pricing(tmp_path):
    # The private table had Opus 4.5 at 15/75 and Haiku 4.5 at 0.8/4.
    assert (await _turn_cost("claude-opus-4-5", tmp_path)).cost_usd == pytest.approx(5.00 + 25.00)
    assert (await _turn_cost("claude-haiku-4-5", tmp_path)).cost_usd == pytest.approx(1.00 + 5.00)


async def test_an_unpriced_model_is_unknown_not_zero(tmp_path):
    event = await _turn_cost("some-model-nobody-priced", tmp_path)
    assert event.cost_usd is None
    # Sent as an explicit null, so a client can show "unknown" rather than
    # keeping or zeroing the last figure.
    assert "cost_usd" in event.to_dict() and event.to_dict()["cost_usd"] is None


async def test_the_pricing_override_applies_to_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "CODEFRAME_MODEL_PRICING", json.dumps({"local-coder": {"input": 0.5, "output": 1.0}})
    )
    assert (await _turn_cost("local-coder", tmp_path)).cost_usd == pytest.approx(1.5)


def test_streaming_chat_keeps_no_price_table_of_its_own():
    assert not hasattr(streaming_chat, "_estimate_cost")


def test_every_model_the_session_ui_offers_has_a_price():
    """The models NewSessionModal offers must be in MODEL_PRICING, or every
    turn of a session started from the UI is unpriced."""
    tsx = (REPO / "web-ui/src/components/sessions/NewSessionModal.tsx").read_text()
    block = re.search(r"MODEL_OPTIONS\s*=\s*\[(.*?)\]", tsx, re.S)
    assert block, "MODEL_OPTIONS not found in NewSessionModal.tsx"
    offered = re.findall(r"'([^']+)'", block.group(1))
    assert offered, "no model ids parsed from MODEL_OPTIONS"
    missing = [m for m in offered if m not in MODEL_PRICING]
    assert not missing, f"session models without a price: {missing}"
