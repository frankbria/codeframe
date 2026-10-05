"""#1430: a skipped evidence test is not evidence.

Since #1401 the runner decides a rule from the JUnit cases named exactly as
the rule. A case that was only skipped (``@pytest.mark.skip``, ``skipif``,
``pytest.skip()``, or an ``xfail``, which JUnit reports as skipped) counted as
passing, so marking the generated stub ``skip`` satisfied the requirement and
unblocked the merge gate, the #909 class. Through ``run_proof``.
"""

from __future__ import annotations

import pytest

from codeframe.core.proof.models import GateOutcome
from tests.core.test_proof_exact_test_selection_1401 import _unit_outcome

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

TESTS = '''\
import pytest


@pytest.mark.skip(reason="not now")
def test_unit_skipped():
    assert True


@pytest.mark.xfail(reason="known broken")
def test_unit_xfailed():
    assert False


def test_unit_skips_itself():
    pytest.skip("later")


@pytest.mark.parametrize("n", [1, pytest.param(2, marks=pytest.mark.skip)])
def test_unit_half_skipped(n):
    assert n
'''


@pytest.fixture
def ws(tmp_path):
    from codeframe.core.proof.ledger import init_proof_tables
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_rules.py").write_text(TESTS, encoding="utf-8")
    w = create_or_load_workspace(repo)
    init_proof_tables(w)
    return w


@pytest.mark.parametrize("test_id", ["test_unit_skipped", "test_unit_xfailed", "test_unit_skips_itself"])
def test_a_test_that_only_skipped_does_not_satisfy_its_rule(ws, test_id):
    assert _unit_outcome(ws, test_id) == GateOutcome.FAILED


def test_one_passing_case_with_a_skipped_one_still_satisfies_it(ws):
    assert _unit_outcome(ws, "test_unit_half_skipped") == GateOutcome.PASSED


def test_the_recorded_evidence_says_it_was_skipped(ws):
    """The verdict's reason must reach what is persisted and shown: it was
    summarised away and the runner recorded "FAILED (failed)", the same as an
    assertion failure (GLM review)."""
    from codeframe.core.proof.models import EvidenceRule, Gate
    from codeframe.core.proof.runner import _run_gate

    outcome, output = _run_gate(ws, Gate.UNIT, [EvidenceRule(test_id="test_unit_skipped", gate=Gate.UNIT)])

    assert outcome == GateOutcome.FAILED
    assert "test_unit_skipped: FAILED — skipped, not run: a skip is not evidence" in output, output
