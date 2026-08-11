"""#1138 — run_proof reports why it produced no results.

`run_proof` returned `dict[req_id, [(gate, outcome)]]` and nothing else. An
empty dict has six causes, all computed inside the runner and then discarded —
`scope_skipped` got as far as a log line. So `cf proof run` had to guess, and
four consecutive review rounds on #1137 caught it guessing wrong, each time
about a different cause.

One test per reason, as the issue asks. Where a state can be produced for real
it is; only the scope filter is patched, because with no working-tree changes
the detector fails closed and evaluates everything, so a genuinely empty scope
cannot be staged here.
"""

from pathlib import Path

import pytest

from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import (
    PROOF_CONFIG_FILENAME,
    Gate,
    Severity,
    Source,
    Waiver,
)
from codeframe.core.proof.runner import (
    EmptyReason,
    ProofRunDiagnostics,
    run_proof,
    run_proof_with_diagnostics,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path):
    return create_or_load_workspace(tmp_path)


def _capture(workspace, where: str = "src/auth/login.py"):
    req, _ = capture_requirement(
        workspace,
        title="Login must not 500",
        description="Expected 200, got 500 on POST /login",
        where=where,
        severity=Severity.HIGH,
        source=Source.PRODUCTION,
    )
    return req


class TestEachReasonIsReported:
    def test_an_empty_ledger(self, workspace):
        results, diagnostics = run_proof_with_diagnostics(workspace)

        assert results == {}
        assert diagnostics.reason is EmptyReason.NO_REQUIREMENTS
        assert diagnostics.total_requirements == 0

    def test_excluded_by_status(self, workspace):
        """WAIVED is excluded from every run — an accepted risk is not re-checked."""
        req = _capture(workspace)
        ledger.waive_requirement(
            workspace, req.id, Waiver(reason="accepted risk", approved_by="test")
        )

        results, diagnostics = run_proof_with_diagnostics(workspace)

        assert results == {}
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_STATUS
        # The distinguishing pair: requirements exist, none were eligible.
        assert diagnostics.total_requirements == 1
        assert diagnostics.considered == 0

    def test_excluded_by_scope(self, workspace, monkeypatch):
        req = _capture(workspace)
        # An empty changed-scope that is not None: detection succeeded and found
        # nothing relevant. None means "failed to detect" and runs everything.
        monkeypatch.setattr(
            "codeframe.core.proof.runner.intersects", lambda scope, changed: False
        )
        monkeypatch.setattr(
            "codeframe.core.proof.runner.get_changed_scope", lambda ws: object()
        )

        results, diagnostics = run_proof_with_diagnostics(workspace)

        assert results == {}
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_SCOPE
        assert diagnostics.scope_skipped == [req.id]

    def test_excluded_by_gate_filter(self, workspace):
        """`--gate perf` against a requirement whose obligations are elsewhere."""
        req = _capture(workspace)
        assert Gate.PERF not in {o.gate for o in req.obligations}, (
            "pick a gate the captured requirement genuinely lacks"
        )

        results, diagnostics = run_proof_with_diagnostics(
            workspace, full=True, gate_filter=Gate.PERF
        )

        assert results == {}
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_GATE_FILTER
        assert diagnostics.gate_filtered == [req.id]

    def test_excluded_by_config(self, workspace):
        """enabled_gates in proof_config.json, not the CLI flag."""
        req = _capture(workspace)
        config = workspace.state_dir / PROOF_CONFIG_FILENAME
        config.write_text('{"enabled_gates": ["perf"], "strictness": "strict"}')

        results, diagnostics = run_proof_with_diagnostics(workspace, full=True)

        assert results == {}
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_CONFIG
        assert diagnostics.config_filtered == [req.id]

    def test_no_obligations_defined(self, workspace):
        req = _capture(workspace)
        req.obligations = []
        ledger.save_requirement(workspace, req)

        results, diagnostics = run_proof_with_diagnostics(workspace, full=True)

        assert results == {}
        assert diagnostics.reason is EmptyReason.NO_OBLIGATIONS
        assert diagnostics.no_obligations == [req.id]

    def test_a_run_that_produced_results_has_nothing_to_explain(self, workspace):
        _capture(workspace)

        results, diagnostics = run_proof_with_diagnostics(workspace, full=True)

        assert results, "the captured requirement should have run"
        assert diagnostics.reason is EmptyReason.NOT_EMPTY
        assert diagnostics.evaluated == len(results)


class TestTheGateFilterOutranksTheConfig:
    """Both can exclude the same obligation. --gate is the user's explicit
    flag, so it is the one to name — telling someone to edit a config file when
    their own flag caused it sends them to the wrong place."""

    def test_the_explicit_flag_is_blamed(self, workspace):
        req = _capture(workspace)
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            '{"enabled_gates": ["perf"], "strictness": "strict"}'
        )

        _, diagnostics = run_proof_with_diagnostics(
            workspace, full=True, gate_filter=Gate.PERF
        )

        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_GATE_FILTER
        assert diagnostics.gate_filtered == [req.id]
        assert diagnostics.config_filtered == []


class TestTheTwoFiltersCanExcludeJointly:
    """Review finding on the first version.

    With obligations {unit, sec}, `--gate unit` and `enabled_gates: ["sec"]`,
    NEITHER filter excludes everything on its own — so both `all(...)` checks
    were false and the requirement fell into no bucket at all, surfacing as an
    unclassified MIXED with no hint. Each filter is now tested for sufficiency
    separately, and the joint case gets its own reason.
    """

    def _obligation_gates(self, req):
        return {o.gate for o in req.obligations}

    def test_the_joint_case_is_classified(self, workspace):
        req = _capture(workspace)
        gates = self._obligation_gates(req)
        assert len(gates) >= 2, "this case needs a requirement with two gates"
        first, second = sorted(gates, key=lambda g: g.value)[:2]
        (workspace.state_dir / PROOF_CONFIG_FILENAME).write_text(
            '{"enabled_gates": ["%s"], "strictness": "strict"}' % second.value
        )

        results, diagnostics = run_proof_with_diagnostics(
            workspace, full=True, gate_filter=first
        )

        assert results == {}
        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_FILTER_COMBINATION
        assert diagnostics.filter_combination == [req.id]
        # Neither alone is the cause, so neither may be blamed alone.
        assert diagnostics.gate_filtered == []
        assert diagnostics.config_filtered == []

    def test_it_says_both_filters_are_involved(self, workspace):
        diagnostics = ProofRunDiagnostics(
            total_requirements=1, considered=1, filter_combination=["REQ-0001"]
        )

        described = diagnostics.describe()

        assert "--gate" in described
        assert "enabled_gates" in described

    def test_a_filter_that_is_sufficient_alone_is_still_blamed_alone(self, workspace):
        """The joint bucket must not swallow the simple cases."""
        req = _capture(workspace)
        assert Gate.PERF not in self._obligation_gates(req)

        _, diagnostics = run_proof_with_diagnostics(
            workspace, full=True, gate_filter=Gate.PERF
        )

        assert diagnostics.reason is EmptyReason.EXCLUDED_BY_GATE_FILTER
        assert diagnostics.filter_combination == []


class TestMixedCausesAreNotCollapsedIntoALie:
    """Two requirements dropped for two reasons: naming either one is wrong."""

    def test_it_reports_mixed(self, workspace):
        a = _capture(workspace, where="src/auth/login.py")
        b = _capture(workspace, where="src/billing/charge.py")
        b.obligations = []
        ledger.save_requirement(workspace, b)

        _, diagnostics = run_proof_with_diagnostics(
            workspace, full=True, gate_filter=Gate.PERF
        )

        assert diagnostics.reason is EmptyReason.MIXED
        assert diagnostics.gate_filtered == [a.id]
        assert diagnostics.no_obligations == [b.id]

    def test_the_description_names_both(self, workspace):
        diagnostics = ProofRunDiagnostics(
            total_requirements=2,
            considered=2,
            scope_skipped=["REQ-0001"],
            no_obligations=["REQ-0002"],
        )

        described = diagnostics.describe()

        assert "out of scope" in described
        assert "no obligations" in described


class TestTheOldSignatureStillWorks:
    """~60 call sites take the dict. Widening the return type was the cost the
    issue flagged; the wrapper is what avoids it."""

    def test_run_proof_returns_only_the_results(self, workspace):
        _capture(workspace)

        results = run_proof(workspace, full=True)

        assert isinstance(results, dict)
        assert results

    def test_it_is_the_same_dict_the_detailed_call_returns(self, workspace):
        _capture(workspace)

        plain = run_proof(workspace, full=True)
        detailed, _ = run_proof_with_diagnostics(workspace, full=True)

        assert set(plain) == set(detailed)


class TestScopeSkippedIsStillLogged:
    """AC: `_report_scope_skipped` keeps working. #922 added it because a
    silently dropped requirement let overall_passed=True coexist with a merge
    gate blocking on that very requirement."""

    def test_the_warning_still_fires(self, workspace, monkeypatch, caplog):
        _capture(workspace)
        monkeypatch.setattr(
            "codeframe.core.proof.runner.intersects", lambda scope, changed: False
        )
        monkeypatch.setattr(
            "codeframe.core.proof.runner.get_changed_scope", lambda ws: object()
        )

        with caplog.at_level("WARNING"):
            run_proof_with_diagnostics(workspace)

        assert any("not evaluated" in r.message for r in caplog.records), caplog.text
