"""#1348 — the Sonnet-tier defaults move off claude-sonnet-4-5 before it retires.

claude-sonnet-4-5 reaches end of life on 2026-11-30. Planning, execution,
correction and supervision default to claude-sonnet-5-5; generation stays on
claude-haiku-4-5 until that model has a retirement date.

A default the pricing table does not know is recorded at $0 (#932, which is what
happened to claude-haiku-4-5), and that would also blind the spend limit, so
every default and every current model must carry a price.
"""

import pytest

from codeframe.adapters.llm import base
from codeframe.lib.metrics_tracker import MODEL_PRICING

pytestmark = pytest.mark.v2

SONNET_TIER = [
    "DEFAULT_PLANNING_MODEL",
    "DEFAULT_EXECUTION_MODEL",
    "DEFAULT_CORRECTION_MODEL",
    "DEFAULT_SUPERVISION_MODEL",
]


@pytest.mark.parametrize("name", SONNET_TIER)
def test_sonnet_tier_defaults_are_sonnet_5_5(name):
    assert getattr(base, name) == "claude-sonnet-5-5"


def test_generation_stays_on_haiku_4_5_until_it_has_a_retirement_date():
    assert base.DEFAULT_GENERATION_MODEL == "claude-haiku-4-5"


@pytest.mark.parametrize("name", SONNET_TIER + ["DEFAULT_GENERATION_MODEL"])
def test_every_default_model_is_priced(name):
    assert getattr(base, name) in MODEL_PRICING, f"{name} would be recorded at $0 (#932)"


# Prices from the Claude API reference (cached 2026-10-06), $ per 1M tokens.
@pytest.mark.parametrize(
    "model, input_rate, output_rate",
    [
        ("claude-sonnet-5-5", 2.00, 10.00),
        ("claude-opus-5-5", 4.00, 20.00),
        ("claude-haiku-5-5", 0.10, 0.50),
        ("claude-fable-5-1", 10.00, 50.00),
    ],
)
def test_current_models_carry_their_published_price(model, input_rate, output_rate):
    assert MODEL_PRICING[model] == {"input": input_rate, "output": output_rate}
