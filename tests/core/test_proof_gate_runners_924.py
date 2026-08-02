"""Six of nine PROOF9 gates could never be satisfied (#924 / P1.6).

``_run_gate`` looked up ``_GATE_TO_CORE`` — which maps only UNIT, CONTRACT and
SEC — and returned UNVERIFIABLE *before* consulting evidence rules. But the
machinery directly below that short-circuit already runs any ``test_``-prefixed
rule through a scoped pytest, and ``TEST_ID_PREFIXES`` gives every gate except
MANUAL exactly such a prefix.

So a developer who captured an A11Y glitch, got a generated ``test_a11y_*``
stub, and *implemented it* still saw UNVERIFIABLE forever. Per ``OBLIGATION_MAP``
five of seven glitch types include at least one such gate, so most captured
glitches could never be satisfied — only waived. The product's headline
differentiator was half-built.

MANUAL stays UNVERIFIABLE by design: its rules are ``manual_check_``-prefixed,
a human has to look, and a machine saying FAILED would be a lie in the other
direction.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


def _rule(test_id: str, gate):
    from codeframe.core.proof.models import EvidenceRule

    return EvidenceRule(test_id=test_id, must_pass=True, gate=gate)


# ---------------------------------------------------------------------------
# 1. Runner-less gates run their evidence rules
# ---------------------------------------------------------------------------


class TestRunnerlessGatesUseTheirRules:
    @pytest.mark.parametrize(
        "gate_name,prefix",
        [("A11Y", "test_a11y_"), ("PERF", "test_perf_"),
         ("VISUAL", "test_visual_"), ("E2E", "test_e2e_"), ("DEMO", "test_demo_")],
    )
    def test_a_gate_with_rules_is_not_short_circuited(
        self, workspace, monkeypatch, gate_name, prefix
    ):
        """The short-circuit fired before rules were ever looked at."""
        from codeframe.core.proof.models import Gate, GateOutcome
        from codeframe.core.proof.runner import _run_gate

        gate = getattr(Gate, gate_name)
        ran: list[str] = []

        def _fake_run(ws, gates=None, verbose=False, test_selector=None, **kw):
            ran.append(test_selector or "whole-suite")
            return _passing_result()

        monkeypatch.setattr(
            "codeframe.core.gates.run", _fake_run, raising=False
        )

        outcome, output = _run_gate(
            workspace, gate, rules=[_rule(f"{prefix}thing", gate)]
        )

        assert ran == [f"{prefix}thing"], (
            f"{gate_name} never ran its evidence rule — it short-circuited to "
            "UNVERIFIABLE before the rules were consulted"
        )
        assert outcome == GateOutcome.PASSED

    def test_a_failing_rule_fails_the_gate(self, workspace, monkeypatch):
        from codeframe.core.proof.models import Gate, GateOutcome
        from codeframe.core.proof.runner import _run_gate

        monkeypatch.setattr(
            "codeframe.core.gates.run",
            lambda *a, **k: _failing_result(),
            raising=False,
        )

        outcome, _ = _run_gate(
            workspace, Gate.A11Y, rules=[_rule("test_a11y_contrast", Gate.A11Y)]
        )

        assert outcome == GateOutcome.FAILED

    def test_a_missing_named_test_fails_rather_than_passes(
        self, workspace, monkeypatch
    ):
        """exit code 5 is pytest's "nothing collected" — a stub never written."""
        from codeframe.core.proof.models import Gate, GateOutcome
        from codeframe.core.proof.runner import _run_gate

        monkeypatch.setattr(
            "codeframe.core.gates.run",
            lambda *a, **k: _failing_result(code=5),
            raising=False,
        )

        outcome, output = _run_gate(
            workspace, Gate.PERF, rules=[_rule("test_perf_budget", Gate.PERF)]
        )

        assert outcome == GateOutcome.FAILED
        assert "missing" in output.lower()


# ---------------------------------------------------------------------------
# 2. Honest UNVERIFIABLE where it is genuinely unverifiable
# ---------------------------------------------------------------------------


class TestStillUnverifiableWhenItShouldBe:
    def test_a_runnerless_gate_with_no_rules_is_unverifiable(self, workspace):
        from codeframe.core.proof.models import Gate, GateOutcome
        from codeframe.core.proof.runner import _run_gate

        outcome, output = _run_gate(workspace, Gate.A11Y, rules=[])

        assert outcome == GateOutcome.UNVERIFIABLE
        assert "no automated runner" in output.lower()

    def test_the_manual_gate_stays_unverifiable(self, workspace):
        """MANUAL's rules are `manual_check_`-prefixed. A human must look, and
        reporting FAILED would be a lie in the other direction."""
        from codeframe.core.proof.models import Gate, GateOutcome
        from codeframe.core.proof.runner import _run_gate

        outcome, _ = _run_gate(
            workspace, Gate.MANUAL,
            rules=[_rule("manual_check_the_thing", Gate.MANUAL)],
        )

        assert outcome == GateOutcome.UNVERIFIABLE


# ---------------------------------------------------------------------------
# 3. The issue's own scenario
# ---------------------------------------------------------------------------


class TestA11yGlitchIsSatisfiable:
    def test_an_a11y_glitch_produces_runnable_obligations(self):
        """AC3. Capture an A11Y_BUG and assert its obligations are runnable —
        not merely created and then permanently unverifiable."""
        from codeframe.core.proof.models import GlitchType
        from codeframe.core.proof.obligations import (
            TEST_ID_PREFIXES,
            get_obligations,
            suggest_evidence_rules,
        )

        obligations = get_obligations(GlitchType.A11Y_BUG)
        assert obligations, "A11Y_BUG must produce obligations"

        for obl in obligations:
            rules = suggest_evidence_rules(obl.gate, "contrast too low")
            assert rules, f"{obl.gate.value} produced no evidence rules"
            prefix = TEST_ID_PREFIXES[obl.gate]
            assert all(r.test_id.startswith(prefix) for r in rules)
            assert prefix.startswith("test_"), (
                f"{obl.gate.value} rules are not pytest-enforceable, so this "
                "obligation can never be satisfied — only waived"
            )

    def test_every_mapped_gate_is_reachable(self):
        """No glitch type may include a gate that can never be satisfied."""
        from codeframe.core.proof.obligations import OBLIGATION_MAP, TEST_ID_PREFIXES
        from codeframe.core.proof.runner import _GATE_TO_CORE

        for glitch_type, gates in OBLIGATION_MAP.items():
            for gate in gates:
                runnable = (
                    gate in _GATE_TO_CORE
                    or TEST_ID_PREFIXES.get(gate, "").startswith("test_")
                )
                assert runnable, (
                    f"{glitch_type.value} includes {gate.value}, which has "
                    "neither a runner nor pytest-enforceable rules"
                )


# ---------------------------------------------------------------------------
# 4. Documentation must match (AC2)
# ---------------------------------------------------------------------------


class TestDocsStateWhatIsEnforced:
    def test_the_readme_explains_gate_enforcement(self):
        from pathlib import Path

        readme = Path("README.md").read_text()

        assert "proof" in readme.lower()
        # The claim "9-gate evidence-based quality system" is only honest if the
        # reader is told how each gate is actually verified.
        assert "evidence rule" in readme.lower() or "test_a11y" in readme, (
            "README advertises 9 gates without saying how the six without "
            "dedicated runners are enforced"
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _passing_result():
    from codeframe.core import gates as core_gates

    class _Check:
        name = "pytest"
        status = core_gates.GateStatus.PASSED
        exit_code = 0

    class _Result:
        checks = [_Check()]
        notes: list[str] = []
        passed = True

    return _Result()


def _failing_result(code: int = 1):
    from codeframe.core import gates as core_gates

    class _Check:
        name = "pytest"
        status = core_gates.GateStatus.FAILED
        exit_code = code

    class _Result:
        checks = [_Check()]
        notes: list[str] = []
        passed = False

    return _Result()
