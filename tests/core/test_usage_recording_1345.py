"""THINK-stage LLM calls are recorded where the daily spend limit reads (#1345).

Only ReactAgent wrote token_usage, so PRD stress-test/refine, discovery and
task generation spent tokens the limit never saw. UsageRecordingProvider
records each completion into the workspace's token_usage, the ledger
spend_limit sums.
"""

import pytest

from codeframe.adapters.llm.base import LLMResponse
from codeframe.adapters.llm.mock import MockProvider
from codeframe.core import spend_limit
from codeframe.core.models import CallType
from codeframe.core.usage_recording import UsageRecordingProvider, record_llm_usage
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def ws(tmp_path):
    return create_or_load_workspace(tmp_path)


def _rows(ws):
    import sqlite3

    conn = sqlite3.connect(str(ws.db_path))
    try:
        return conn.execute(
            "SELECT model_name, input_tokens, output_tokens, estimated_cost_usd, call_type, task_id FROM token_usage"
        ).fetchall()
    finally:
        conn.close()


def test_a_completion_is_recorded_as_spend_the_limit_counts(ws):
    inner = MockProvider()
    inner.add_response(LLMResponse(content="ok", model="claude-sonnet-4-5", input_tokens=1_000_000, output_tokens=0))
    provider = UsageRecordingProvider(inner, ws, CallType.PLANNING)

    assert provider.complete(messages=[{"role": "user", "content": "hi"}]).content == "ok"

    [(model, inp, out, cost, call_type, task_id)] = _rows(ws)
    assert (model, inp, out, call_type, task_id) == ("claude-sonnet-4-5", 1_000_000, 0, "planning", None)
    assert cost == pytest.approx(3.0)
    assert spend_limit.spend_today_usd([ws.repo_path]) == pytest.approx(3.0)


def test_everything_else_is_the_inner_providers(ws):
    inner = MockProvider()
    provider = UsageRecordingProvider(inner, ws, CallType.PLANNING)
    inner.api_key = "sk-test"
    assert provider.api_key == "sk-test"
    assert provider.add_response == inner.add_response


def test_a_recording_failure_never_breaks_the_call(ws, monkeypatch):
    """Recording is bookkeeping: losing a row is logged, losing the user's
    answer is not acceptable."""
    import codeframe.core.usage_recording as ur

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(ur, "record_llm_usage", boom)
    inner = MockProvider()
    inner.add_response(LLMResponse(content="ok", model="m", input_tokens=1, output_tokens=1))
    assert UsageRecordingProvider(inner, ws, CallType.PLANNING).complete(messages=[]).content == "ok"


def test_an_unpriced_model_is_recorded_without_a_cost(ws):
    record_llm_usage(ws, model="model-nobody-priced", input_tokens=5, output_tokens=5, call_type=CallType.SESSION_CHAT)
    [(model, inp, out, cost, call_type, _)] = _rows(ws)
    assert (model, inp, out, call_type) == ("model-nobody-priced", 5, 5, "session_chat")


# --- the reserved budget bounds a whole planning run (codex P1) ----------


def _priced(inner, n, tokens=1_000_000):
    for _ in range(n):
        inner.add_response(LLMResponse(content="ok", model="claude-sonnet-4-5", input_tokens=tokens, output_tokens=0))


def test_a_planning_run_stops_once_its_budget_is_spent(ws):
    """A stress test is many calls; an entry-only check let it run on past
    the ceiling. Each call costs $3 here; a $5 budget allows two."""
    from codeframe.core.spend_limit import SpendLimitExceeded
    from codeframe.core.usage_recording import spend_budget

    inner = MockProvider()
    _priced(inner, 3)
    provider = UsageRecordingProvider(inner, ws, CallType.PLANNING)
    with spend_budget(5.0):
        provider.complete(messages=[])
        provider.complete(messages=[])
        with pytest.raises(SpendLimitExceeded):
            provider.complete(messages=[])
    assert len(_rows(ws)) == 2


def test_an_unpriced_model_cannot_keep_spending_under_a_limit(ws):
    """Unmetered spend is not countable, so under a limit it is refused after
    the first call, as a delegated engine is (#1303)."""
    from codeframe.core.spend_limit import SpendLimitExceeded
    from codeframe.core.usage_recording import spend_budget

    inner = MockProvider()
    inner.add_response(LLMResponse(content="ok", model="model-nobody-priced", input_tokens=5, output_tokens=5))
    inner.add_response(LLMResponse(content="ok", model="model-nobody-priced", input_tokens=5, output_tokens=5))
    provider = UsageRecordingProvider(inner, ws, CallType.PLANNING)
    with spend_budget(5.0):
        provider.complete(messages=[])
        with pytest.raises(SpendLimitExceeded, match="CODEFRAME_MODEL_PRICING"):
            provider.complete(messages=[])


def test_no_budget_means_no_ceiling(ws):
    from codeframe.core.usage_recording import spend_budget

    inner = MockProvider()
    _priced(inner, 3)
    provider = UsageRecordingProvider(inner, ws, CallType.PLANNING)
    with spend_budget(None):
        for _ in range(3):
            provider.complete(messages=[])


# --- codex pass 2: chat tool loops, and unpriced spend across requests ----


async def test_a_chat_turn_stops_calling_the_model_once_its_budget_is_spent(ws, tmp_path):
    """One user message can make several model calls (tool continuations);
    the turn's budget is enforced between them. $3 per call, $5 budget."""
    from unittest.mock import MagicMock

    from codeframe.adapters.llm.base import StreamChunk
    from codeframe.core.adapters.streaming_chat import ChatEventType, StreamingChatAdapter
    from codeframe.core.usage_recording import spend_budget

    (tmp_path / "a.py").write_text("x = 1\n")
    provider = MockProvider()
    for i in range(3):
        tool_id, tool_input = f"t{i}", {"path": "a.py"}
        provider.add_stream_chunks([
            StreamChunk(type="tool_use_start", tool_id=tool_id, tool_name="read_file", tool_input=tool_input),
            StreamChunk(type="tool_use_stop"),
            StreamChunk(type="message_stop", stop_reason="tool_use", input_tokens=1_000_000,
                        output_tokens=0, tool_inputs_by_id={tool_id: tool_input}),
        ])
    repo = MagicMock()
    repo.get_messages.return_value = []
    repo.get_recent_messages.return_value = []
    adapter = StreamingChatAdapter(session_id="s", db_repo=repo, workspace_path=tmp_path,
                                   model="claude-sonnet-4-5", provider=provider)
    with spend_budget(5.0):
        events = [e async for e in adapter.send_message("go", [])]

    assert [e.type for e in events].count(ChatEventType.COST_UPDATE) == 2
    assert events[-1].type == ChatEventType.ERROR
    assert "spend limit" in (events[-1].content or "")


def test_unpriced_spend_today_refuses_new_work_while_a_limit_is_on(ws, monkeypatch):
    """The unmetered flag lived in one request, so the next one started fresh
    and NULL-cost rows never counted: repeated single-call requests spent
    without limit (codex). An unpriced call recorded today now refuses."""
    from codeframe.core.spend_limit import SpendLimitExceeded, remaining_today_usd

    record_llm_usage(ws, model="model-nobody-priced", input_tokens=5, output_tokens=5, call_type=CallType.PLANNING)
    assert remaining_today_usd([ws.repo_path]) is None  # no limit: unaffected
    monkeypatch.setenv("CODEFRAME_USER_DAILY_COST_LIMIT_USD", "10")
    with pytest.raises(SpendLimitExceeded, match="CODEFRAME_MODEL_PRICING"):
        remaining_today_usd([ws.repo_path])


def test_a_budget_is_settled_only_after_its_last_call_records(tmp_path):
    """An SSE disconnect ended the stream while its worker thread was still in
    a model call, and the hold was released before that call was recorded
    (codex P1)."""
    import contextvars
    import threading

    from codeframe.core.usage_recording import spend_budget

    ws = create_or_load_workspace(tmp_path)
    entered, go = threading.Event(), threading.Event()

    class Slow:
        def complete(self, *a, **k):
            entered.set()
            go.wait(5)
            return LLMResponse(content="ok", model="claude-sonnet-4-5", input_tokens=10, output_tokens=10)

    provider = UsageRecordingProvider(Slow(), ws, CallType.PLANNING)
    settled = []
    with spend_budget(5.0, on_settled=lambda: settled.append(len(_rows(ws)))):
        worker = threading.Thread(target=contextvars.copy_context().run, args=(provider.complete,))
        worker.start()
        entered.wait(5)
    assert settled == []  # the stream is gone, but its call is not
    go.set()
    worker.join(5)
    assert settled == [1]  # released once, after the call was recorded
