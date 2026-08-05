"""Cost accounting must not report $0.00 by default (#932).

Three separate ways the shipped product under-reported spend:

1. `MODEL_PRICING` had three entries and `DEFAULT_GENERATION_MODEL`
   ("claude-haiku-4-5") was not one of them, so the default generation path
   priced every call at $0.
2. `calculate_cost` returned 0.0 for anything unpriced, so a gpt-4o/ollama call
   summed into totals as if it were free rather than as unknown.
3. The builtin (react/plan) adapters never populated `AgentResult.token_usage`,
   so engine stats and the Costs page showed 0 tokens for the *default* engine.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.adapters.llm import base as llm_base
from codeframe.lib.metrics_tracker import MODEL_PRICING, MetricsTracker

pytestmark = pytest.mark.v2


DEFAULT_MODEL_CONSTANTS = [
    name for name in dir(llm_base)
    if name.startswith("DEFAULT_") and name.endswith("_MODEL")
]


class TestShippedDefaultsArePriced:
    def test_every_default_model_constant_exists(self):
        """Guard the guard: if the constants are renamed this test must not pass vacuously."""
        assert len(DEFAULT_MODEL_CONSTANTS) >= 5, DEFAULT_MODEL_CONSTANTS

    @pytest.mark.parametrize("const_name", DEFAULT_MODEL_CONSTANTS)
    def test_default_model_has_a_real_price(self, const_name):
        """Every shipped default must price non-zero — including future bumps."""
        model = getattr(llm_base, const_name)

        cost = MetricsTracker.calculate_cost(model, 1_000_000, 1_000_000)

        assert cost is not None, f"{const_name} = {model!r} has no pricing entry"
        assert cost > 0, f"{const_name} = {model!r} priced at ${cost}"

    def test_default_generation_model_specifically(self):
        """The one named in the issue."""
        cost = MetricsTracker.calculate_cost(llm_base.DEFAULT_GENERATION_MODEL, 1000, 500)

        assert cost is not None and cost > 0


class TestUnknownModelsAreUnpricedNotFree:
    def test_unknown_model_returns_none(self):
        assert MetricsTracker.calculate_cost("totally-made-up-model", 1000, 500) is None

    def test_known_model_still_returns_a_float(self):
        cost = MetricsTracker.calculate_cost("claude-sonnet-4-5", 1000, 500)

        assert isinstance(cost, float)
        assert cost == pytest.approx(0.0105, abs=1e-6)

    def test_date_suffix_still_normalizes(self):
        assert MetricsTracker.calculate_cost("claude-sonnet-4-5-20250514", 1000, 500) is not None

    def test_zero_tokens_on_a_priced_model_is_zero_not_none(self):
        """$0.00 must mean 'free', never 'unknown'."""
        assert MetricsTracker.calculate_cost("claude-sonnet-4-5", 0, 0) == 0.0


class TestPricingIsConfigurable:
    def test_env_override_adds_a_model(self, monkeypatch):
        monkeypatch.setenv(
            "CODEFRAME_MODEL_PRICING",
            json.dumps({"my-local-model": {"input": 1.0, "output": 2.0}}),
        )

        cost = MetricsTracker.calculate_cost("my-local-model", 1_000_000, 1_000_000)

        assert cost == pytest.approx(3.0)

    def test_env_override_can_replace_a_builtin_rate(self, monkeypatch):
        monkeypatch.setenv(
            "CODEFRAME_MODEL_PRICING",
            json.dumps({"claude-sonnet-4-5": {"input": 0.0, "output": 0.0}}),
        )

        assert MetricsTracker.calculate_cost("claude-sonnet-4-5", 1000, 500) == 0.0

    def test_malformed_override_is_ignored_not_fatal(self, monkeypatch, caplog):
        monkeypatch.setenv("CODEFRAME_MODEL_PRICING", "{not json")

        cost = MetricsTracker.calculate_cost("claude-sonnet-4-5", 1000, 500)

        assert cost is not None, "a bad override must not break pricing entirely"

    def test_builtin_table_is_not_mutated_by_an_override(self, monkeypatch):
        monkeypatch.setenv(
            "CODEFRAME_MODEL_PRICING",
            json.dumps({"ephemeral-model": {"input": 1.0, "output": 1.0}}),
        )
        MetricsTracker.calculate_cost("ephemeral-model", 10, 10)

        assert "ephemeral-model" not in MODEL_PRICING


class TestBuiltinAdapterReportsTokens:
    def test_react_adapter_attaches_token_usage(self, tmp_path: Path):
        """AC2 — the default engine must not report 0 tokens."""
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        from codeframe.core.agent import AgentStatus
        from codeframe.core.workspace import create_or_load_workspace

        workspace = create_or_load_workspace(tmp_path)
        adapter = BuiltinReactAdapter(workspace=workspace, llm_provider=MagicMock())

        fake_agent = MagicMock()
        fake_agent.run.return_value = AgentStatus.COMPLETED
        fake_agent.get_total_tokens.return_value = {
            "input_tokens": 1200,
            "output_tokens": 340,
            "total_tokens": 1540,
            "estimated_cost_usd": 0.0123,
        }
        fake_agent.get_token_usage.return_value = [
            {"model": "claude-sonnet-4-5", "input_tokens": 1200, "output_tokens": 340}
        ]

        with patch(
            "codeframe.core.react_agent.ReactAgent", return_value=fake_agent
        ):
            result = adapter.run("task-1", "do the thing", tmp_path)

        assert result.status == "completed"
        assert result.token_usage is not None, "builtin react adapter reported no tokens"
        assert result.token_usage.input_tokens == 1200
        assert result.token_usage.output_tokens == 340
        assert result.token_usage.total_tokens == 1540
        assert result.token_usage.cost_usd == pytest.approx(0.0123)

    def test_token_usage_absent_when_the_agent_recorded_nothing(self, tmp_path: Path):
        from codeframe.core.adapters.builtin import BuiltinReactAdapter
        from codeframe.core.agent import AgentStatus
        from codeframe.core.workspace import create_or_load_workspace

        workspace = create_or_load_workspace(tmp_path)
        adapter = BuiltinReactAdapter(workspace=workspace, llm_provider=MagicMock())

        fake_agent = MagicMock()
        fake_agent.run.return_value = AgentStatus.COMPLETED
        fake_agent.get_total_tokens.return_value = {
            "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "estimated_cost_usd": 0.0,
        }
        fake_agent.get_token_usage.return_value = []

        with patch("codeframe.core.react_agent.ReactAgent", return_value=fake_agent):
            result = adapter.run("task-1", "do the thing", tmp_path)

        assert result.token_usage is None, "a zero-token run should not claim usage"


class TestRecordTokenUsageDocstring:
    """AC4 — the docstring must match behaviour.

    Checked structurally (no `Raises:` section) *and* behaviourally (it really
    does not raise), so the pair cannot drift apart again.
    """

    def test_documented_valueerror_is_actually_raised(self):
        """The docstring's ValueError must be real, and only for what it says."""
        doc = MetricsTracker.record_token_usage.__doc__ or ""

        assert "negative" in doc, "the ValueError's real trigger is not documented"

    @pytest.mark.asyncio
    async def test_negative_tokens_raise_as_documented(self):
        tracker = MetricsTracker(MagicMock())

        with pytest.raises(ValueError, match="negative"):
            await tracker.record_token_usage(
                task_id="t1", agent_id="a1", project_id=1,
                model_name="claude-sonnet-4-5",
                input_tokens=-1, output_tokens=0,
            )

    @pytest.mark.asyncio
    async def test_unknown_model_does_not_raise_and_stores_null_cost(self):
        db = MagicMock()
        db.save_token_usage = MagicMock(return_value=42)
        tracker = MetricsTracker(db)

        usage_id = await tracker.record_token_usage(
            task_id="t1",
            agent_id="a1",
            project_id=1,
            model_name="totally-made-up-model",
            input_tokens=100,
            output_tokens=50,
        )

        assert usage_id == 42
        recorded = db.save_token_usage.call_args.args[0]
        assert recorded.estimated_cost_usd is None, (
            "an unpriced call must store NULL, not 0.0 — otherwise it sums as free"
        )

    @pytest.mark.asyncio
    async def test_priced_model_stores_a_real_cost(self):
        db = MagicMock()
        db.save_token_usage = MagicMock(return_value=7)
        tracker = MetricsTracker(db)

        await tracker.record_token_usage(
            task_id="t1",
            agent_id="a1",
            project_id=1,
            model_name="claude-haiku-4-5",
            input_tokens=1_000_000,
            output_tokens=0,
        )

        recorded = db.save_token_usage.call_args.args[0]
        assert recorded.estimated_cost_usd == pytest.approx(1.00)


class TestAggregatorsToleratNullCosts:
    """Raised by `codex review`: unpriced rows now persist NULL, and the Python
    aggregators added the raw value — so viewing metrics after an ollama run
    raised TypeError instead of excluding the unknown spend."""

    @pytest.fixture
    def tracker_with_mixed_records(self):
        from codeframe.core.models import CallType

        db = MagicMock()
        db.get_token_usage_iter = MagicMock(return_value=[
            {"estimated_cost_usd": 0.01, "input_tokens": 100, "output_tokens": 50,
             "agent_id": "a1", "model_name": "claude-sonnet-4-5", "project_id": 1,
             "call_type": CallType.OTHER.value, "timestamp": "2026-08-01T00:00:00+00:00"},
            {"estimated_cost_usd": None, "input_tokens": 200, "output_tokens": 80,
             "agent_id": "a1", "model_name": "some-local-model", "project_id": 1,
             "call_type": CallType.OTHER.value, "timestamp": "2026-08-01T00:00:00+00:00"},
        ])
        return MetricsTracker(db)

    @pytest.mark.asyncio
    async def test_project_costs_excludes_unpriced_and_counts_it(
        self, tracker_with_mixed_records
    ):
        result = await tracker_with_mixed_records.get_project_costs(project_id=1)

        assert result["total_cost_usd"] == pytest.approx(0.01), (
            "unpriced spend must be excluded, not summed as free"
        )
        assert result["total_tokens"] == 430, "tokens are still counted"
        assert result.get("unpriced_calls") == 1, (
            "the gap must be reported so the UI can render 'unpriced'"
        )


class TestExplicitlyFreePricingIsMeasured:
    """Raised by `codex review`: a local model priced 0/0 is measured at $0,
    which is different from having no pricing — the cost cap must not abort."""

    def test_zero_priced_model_is_not_unpriced(self, monkeypatch, tmp_path):
        from codeframe.core.react_agent import ReactAgent
        from codeframe.core.workspace import create_or_load_workspace

        monkeypatch.setenv(
            "CODEFRAME_MODEL_PRICING",
            json.dumps({"my-free-local": {"input": 0.0, "output": 0.0}}),
        )
        agent = ReactAgent(
            workspace=create_or_load_workspace(tmp_path), llm_provider=MagicMock()
        )
        agent._max_cost_usd = 5.0
        agent._token_records.append({
            "model": "my-free-local", "input_tokens": 100000,
            "output_tokens": 50000, "call_type": "execution", "iteration": 1,
        })

        assert agent._has_unpriced_records() is False
        assert agent._cost_cap_message() is None, (
            "an explicitly free model was treated as unmeasurable and aborted"
        )


class TestUnpricedCallsIsAlwaysReported:
    """The bot review noted the key was emitted inconsistently across
    aggregators — present only when an unpriced record existed in two of them,
    zero-initialized in the third. A caller should not have to guess."""

    @pytest.mark.asyncio
    async def test_project_costs_reports_zero_when_all_priced(self):
        from codeframe.core.models import CallType

        db = MagicMock()
        db.get_token_usage_iter = MagicMock(return_value=[
            {"estimated_cost_usd": 0.02, "input_tokens": 10, "output_tokens": 5,
             "agent_id": "a1", "model_name": "claude-sonnet-4-5", "project_id": 1,
             "call_type": CallType.OTHER.value,
             "timestamp": "2026-08-01T00:00:00+00:00"},
        ])

        result = await MetricsTracker(db).get_project_costs(project_id=1)

        assert result["unpriced_calls"] == 0

    @pytest.mark.asyncio
    async def test_project_costs_reports_zero_with_no_records_at_all(self):
        db = MagicMock()
        db.get_token_usage_iter = MagicMock(return_value=[])

        result = await MetricsTracker(db).get_project_costs(project_id=1)

        assert result["unpriced_calls"] == 0
