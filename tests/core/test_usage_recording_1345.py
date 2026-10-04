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
