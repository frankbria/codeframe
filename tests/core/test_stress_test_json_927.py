"""Stress-test JSON parsing silently reported a clean bill of health (#927 / P1.9).

``extract_goals`` did a raw ``json.loads`` and returned ``[]`` on failure;
``classify_and_decompose`` fell back to ``(ATOMIC, [], None, "Low")``. Neither
stripped ```json fences — although *every* sibling LLM-JSON consumer in this
repo does, in two subtly different ways.

Fenced JSON is routine on the OpenAI-compatible and local providers this command
explicitly supports, so the failure mode was a silent false pass: the CLI and web
UI reported "No ambiguities found — PRD is well-specified" **after the user paid
for the call**.

``recursive_decompose`` additionally walked an unbounded model-supplied
``children`` list with only a depth cap (API-settable to 10) and no cancellation
when the SSE client went away.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.v2

_FENCE = "```"


def _fenced(payload, lang: str = "json") -> str:
    return f"{_FENCE}{lang}\n{json.dumps(payload)}\n{_FENCE}"


# ---------------------------------------------------------------------------
# 1. The shared helper
# ---------------------------------------------------------------------------


class TestFenceStripping:
    def test_strips_a_json_fence(self):
        from codeframe.core.llm_json import parse_json_response

        assert parse_json_response(_fenced(["a", "b"])) == ["a", "b"]

    def test_strips_a_bare_fence(self):
        from codeframe.core.llm_json import parse_json_response

        assert parse_json_response(_fenced({"k": 1}, lang="")) == {"k": 1}

    def test_accepts_unfenced_json(self):
        from codeframe.core.llm_json import parse_json_response

        assert parse_json_response('["a"]') == ["a"]

    def test_tolerates_prose_around_the_fence(self):
        """Local models routinely add 'Here is the JSON:' before the block."""
        from codeframe.core.llm_json import parse_json_response

        raw = f"Sure! Here you go:\n{_fenced(['a'])}\nHope that helps."

        assert parse_json_response(raw) == ["a"]

    def test_raises_on_unparseable_content(self):
        """Silence is what produced the false pass — this must be loud."""
        from codeframe.core.llm_json import LLMJsonError, parse_json_response

        with pytest.raises(LLMJsonError):
            parse_json_response("I'm sorry, I can't do that.")

    def test_raises_on_empty_content(self):
        from codeframe.core.llm_json import LLMJsonError, parse_json_response

        with pytest.raises(LLMJsonError):
            parse_json_response("")


# ---------------------------------------------------------------------------
# 2. Goal extraction
# ---------------------------------------------------------------------------


class _Provider:
    def __init__(self, content: str):
        self._content = content
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1

        class _R:
            content = self._content

        return _R()


class TestExtractGoals:
    def test_a_fenced_response_yields_goals(self):
        """AC1. The headline case on every OpenAI-compatible provider."""
        from codeframe.core.prd_stress_test import extract_goals

        provider = _Provider(_fenced(["Ship auth", "Ship billing"]))

        assert extract_goals("prd", provider) == ["Ship auth", "Ship billing"]

    def test_an_unfenced_response_still_works(self):
        from codeframe.core.prd_stress_test import extract_goals

        provider = _Provider(json.dumps(["Ship auth"]))

        assert extract_goals("prd", provider) == ["Ship auth"]

    def test_zero_goals_raises_rather_than_reporting_a_clean_prd(self):
        """AC2. Returning [] made the caller print
        'No ambiguities found — PRD is well-specified'."""
        from codeframe.core.prd_stress_test import StressTestError, extract_goals

        with pytest.raises(StressTestError):
            extract_goals("prd", _Provider("not json at all"))

    def test_an_empty_list_also_raises(self):
        """A well-formed empty list is the same false pass by another route."""
        from codeframe.core.prd_stress_test import StressTestError, extract_goals

        with pytest.raises(StressTestError):
            extract_goals("prd", _Provider("[]"))


# ---------------------------------------------------------------------------
# 3. Bounded recursion
# ---------------------------------------------------------------------------


class TestRecursionIsBounded:
    def test_a_per_node_children_cap_exists(self):
        from codeframe.core import prd_stress_test

        assert prd_stress_test.MAX_CHILDREN_PER_NODE > 0

    def test_a_total_call_budget_exists(self):
        from codeframe.core import prd_stress_test

        assert prd_stress_test.MAX_LLM_CALLS > 0

    def test_the_budget_stops_the_walk(self):
        """AC3. A model returning children forever must terminate."""
        from codeframe.core.prd_stress_test import _Budget

        budget = _Budget(max_calls=3)

        assert budget.take() and budget.take() and budget.take()
        assert not budget.take()
        assert budget.exhausted

    def test_a_cancelled_walk_stops(self):
        """AC4. A disconnected SSE client must stop the work it is paying for."""
        from codeframe.core.prd_stress_test import _Budget

        budget = _Budget(max_calls=100, is_cancelled=lambda: True)

        assert not budget.take()

    def test_children_are_truncated_not_dropped(self):
        from codeframe.core import prd_stress_test

        children = [{"title": str(i)} for i in range(1000)]

        capped = prd_stress_test._cap_children(children)

        assert len(capped) == prd_stress_test.MAX_CHILDREN_PER_NODE
        assert capped[0]["title"] == "0"
