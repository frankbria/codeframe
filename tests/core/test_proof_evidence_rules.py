"""Tests for EvidenceRule.test_id/must_pass enforcement (issue #729).

A requirement's obligation is only satisfied when its named proving tests
actually run and pass — a missing named test is a failed obligation, even
when the broader suite is green.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from codeframe.core.gates import GateCheck, GateResult, GateStatus
from codeframe.core.proof.models import (
    EvidenceRule,
    Gate,
    GateOutcome,
    Obligation,
    Requirement,
    RequirementScope,
    ReqStatus,
    Severity,
    Source,
)
from codeframe.core.workspace import Workspace, create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


def _gate_result(status: GateStatus, exit_code: int, output: str = "") -> GateResult:
    return GateResult(
        passed=status in (GateStatus.PASSED, GateStatus.SKIPPED),
        checks=[GateCheck(name="pytest", status=status, exit_code=exit_code, output=output)],
    )


# --- Model / capture / ledger plumbing ---


class TestEvidenceRuleGateField:
    def test_evidence_rule_defaults_gate_none(self):
        rule = EvidenceRule(test_id="test_unit_foo")
        assert rule.gate is None
        assert rule.must_pass is True

    def test_suggest_evidence_rules_stamps_gate(self):
        from codeframe.core.proof.obligations import suggest_evidence_rules

        rules = suggest_evidence_rules(Gate.UNIT, "Login rejects empty password")
        assert rules[0].gate == Gate.UNIT
        rules = suggest_evidence_rules(Gate.CONTRACT, "API returns 404")
        assert rules[0].gate == Gate.CONTRACT

    def test_ledger_round_trips_gate(self, workspace):
        from codeframe.core.proof import ledger

        req = Requirement(
            id="REQ-0001",
            title="t",
            description="d",
            severity=Severity.LOW,
            source=Source.QA,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[EvidenceRule(test_id="test_unit_foo", gate=Gate.UNIT)],
            created_at=datetime.now(timezone.utc),
        )
        ledger.save_requirement(workspace, req)
        loaded = ledger.get_requirement(workspace, "REQ-0001")
        assert loaded.evidence_rules[0].gate == Gate.UNIT

    def test_legacy_rules_derive_gate_from_prefix(self):
        from codeframe.core.proof.ledger import _evidence_rules_from_json

        raw = json.dumps(
            [
                {"test_id": "test_unit_foo", "must_pass": True},
                {"test_id": "test_contract_bar", "must_pass": True},
                {"test_id": "weird_name", "must_pass": True},
            ]
        )
        rules = _evidence_rules_from_json(raw)
        assert rules[0].gate == Gate.UNIT
        assert rules[1].gate == Gate.CONTRACT
        assert rules[2].gate is None


# --- gates.py selector threading ---


class TestPytestSelector:
    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which", return_value="/usr/bin/uv")
    def test_selector_appended_to_command(self, _which, mock_run):
        from codeframe.core.gates import _run_pytest

        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "1 passed"
        mock_run.return_value.stderr = ""
        check = _run_pytest(Path("/tmp"), test_selector="test_unit_foo")
        cmd = mock_run.call_args[0][0]
        assert "-k" in cmd
        assert cmd[cmd.index("-k") + 1] == "test_unit_foo"
        assert check.status == GateStatus.PASSED

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which", return_value="/usr/bin/uv")
    def test_exit_5_with_selector_is_failed(self, _which, mock_run):
        from codeframe.core.gates import _run_pytest

        mock_run.return_value.returncode = 5
        mock_run.return_value.stdout = "no tests ran"
        mock_run.return_value.stderr = ""
        check = _run_pytest(Path("/tmp"), test_selector="test_unit_missing")
        assert check.status == GateStatus.FAILED
        assert check.exit_code == 5

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which", return_value="/usr/bin/uv")
    def test_exit_5_without_selector_still_passes(self, _which, mock_run):
        from codeframe.core.gates import _run_pytest

        mock_run.return_value.returncode = 5
        mock_run.return_value.stdout = "no tests ran"
        mock_run.return_value.stderr = ""
        check = _run_pytest(Path("/tmp"))
        assert check.status == GateStatus.PASSED

    @patch("codeframe.core.gates._ensure_dependencies_installed", return_value=(True, "ok"))
    @patch("codeframe.core.gates._run_pytest")
    def test_run_dispatcher_forwards_selector(self, mock_pytest, _deps, workspace):
        from codeframe.core.gates import run

        mock_pytest.return_value = GateCheck(name="pytest", status=GateStatus.PASSED)
        run(workspace, gates=["pytest"], test_selector="test_unit_foo")
        assert mock_pytest.call_args.kwargs.get("test_selector") == "test_unit_foo"


# --- runner enforcement ---


class TestRunGateEnforcement:
    def _rule(self, test_id="test_unit_foo", must_pass=True, gate=Gate.UNIT):
        return EvidenceRule(test_id=test_id, must_pass=must_pass, gate=gate)

    @patch("codeframe.core.gates.run")
    def test_missing_named_test_fails(self, mock_run, workspace):
        from codeframe.core.proof.runner import _run_gate

        mock_run.return_value = _gate_result(GateStatus.FAILED, 5, "no tests ran")
        outcome, output = _run_gate(workspace, Gate.UNIT, [self._rule()])
        assert outcome == GateOutcome.FAILED
        assert "missing" in output.lower()
        assert "test_unit_foo" in output
        assert mock_run.call_args.kwargs.get("test_selector") == "test_unit_foo"

    @patch("codeframe.core.gates.run")
    def test_passing_named_test_passes(self, mock_run, workspace):
        from codeframe.core.proof.runner import _run_gate

        mock_run.return_value = _gate_result(GateStatus.PASSED, 0, "1 passed")
        outcome, output = _run_gate(workspace, Gate.UNIT, [self._rule()])
        assert outcome == GateOutcome.PASSED
        assert "test_unit_foo" in output

    @patch("codeframe.core.gates.run")
    def test_failing_named_test_fails(self, mock_run, workspace):
        from codeframe.core.proof.runner import _run_gate

        mock_run.return_value = _gate_result(GateStatus.FAILED, 1, "1 failed")
        outcome, output = _run_gate(workspace, Gate.UNIT, [self._rule()])
        assert outcome == GateOutcome.FAILED
        assert "test_unit_foo" in output

    @patch("codeframe.core.gates.run")
    def test_must_pass_false_does_not_gate(self, mock_run, workspace):
        from codeframe.core.proof.runner import _run_gate

        # Only informational rules → whole-suite behavior, rule never enforced
        mock_run.return_value = _gate_result(GateStatus.PASSED, 0)
        outcome, _ = _run_gate(
            workspace, Gate.UNIT, [self._rule(must_pass=False)]
        )
        assert outcome == GateOutcome.PASSED
        # No scoped invocation for informational rules
        assert mock_run.call_args.kwargs.get("test_selector") is None

    @patch("codeframe.core.gates.run")
    def test_no_rules_runs_whole_suite(self, mock_run, workspace):
        from codeframe.core.proof.runner import _run_gate

        mock_run.return_value = _gate_result(GateStatus.PASSED, 0)
        outcome, _ = _run_gate(workspace, Gate.UNIT, [])
        assert outcome == GateOutcome.PASSED
        assert mock_run.call_args.kwargs.get("test_selector") is None

    @patch("codeframe.core.gates.run")
    def test_one_missing_one_passing_fails(self, mock_run, workspace):
        from codeframe.core.proof.runner import _run_gate

        mock_run.side_effect = [
            _gate_result(GateStatus.PASSED, 0),
            _gate_result(GateStatus.FAILED, 5),
        ]
        outcome, output = _run_gate(
            workspace,
            Gate.UNIT,
            [self._rule("test_unit_a"), self._rule("test_unit_b")],
        )
        assert outcome == GateOutcome.FAILED
        assert "test_unit_a" in output
        assert "test_unit_b" in output

    @patch("codeframe.core.gates.run")
    def test_sec_gate_enforces_pytest_rule_alongside_ruff(self, mock_run, workspace):
        """A SEC requirement is NOT satisfied by a green ruff run alone when
        its named test_sec_* regression test is missing."""
        from codeframe.core.proof.runner import _run_gate

        def fake_run(ws, gates=None, verbose=False, test_selector=None, **kw):
            if test_selector:  # scoped pytest run for the rule → missing
                return _gate_result(GateStatus.FAILED, 5, "no tests ran")
            return _gate_result(GateStatus.PASSED, 0, "ruff clean")

        mock_run.side_effect = fake_run
        outcome, output = _run_gate(
            workspace, Gate.SEC, [self._rule("test_sec_xss", gate=Gate.SEC)]
        )
        assert outcome == GateOutcome.FAILED
        assert "test_sec_xss" in output
        # Both the scoped pytest run and the ruff run happened
        called_gates = [c.kwargs.get("gates") or c.args[1] for c in mock_run.call_args_list]
        assert ["pytest"] in called_gates
        assert ["ruff"] in called_gates

    def test_unit_stub_name_matches_evidence_rule(self):
        """The generated UNIT stub must define the exact function the
        evidence rule enforces (issue #729 review finding)."""
        from codeframe.core.proof.obligations import suggest_evidence_rules
        from codeframe.core.proof.stubs import generate_stubs

        title = "Login rejects empty password when the user profile is incomplete"
        req = Requirement(
            id="REQ-0001",
            title=title,
            description="d",
            severity=Severity.LOW,
            source=Source.QA,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.UNIT), Obligation(gate=Gate.SEC)],
            evidence_rules=[],
        )
        stubs = generate_stubs(req)
        for gate in (Gate.UNIT, Gate.SEC):
            rule = suggest_evidence_rules(gate, title)[0]
            assert f"def {rule.test_id}(" in stubs[gate]

    def test_unmapped_gate_still_unverifiable(self, workspace):
        from codeframe.core.proof.runner import _run_gate

        outcome, _ = _run_gate(workspace, Gate.E2E, [self._rule(gate=Gate.E2E)])
        assert outcome == GateOutcome.UNVERIFIABLE


class TestRunProofEnforcement:
    @patch("codeframe.core.gates.run")
    def test_green_suite_but_missing_named_test_not_satisfied(self, mock_run, workspace):
        """The core of #729: a green whole-suite run must NOT satisfy a
        requirement whose named regression test was never written."""
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.runner import run_proof

        capture_requirement(
            workspace, title="Bug", description="Logic error in calculation",
            where="src/calc.py", severity=Severity.MEDIUM, source=Source.QA,
        )
        # Every scoped run reports "no tests matched" (the named tests don't exist)
        mock_run.return_value = _gate_result(GateStatus.FAILED, 5, "no tests ran")

        results = run_proof(workspace, full=True)
        req_id = list(results.keys())[0]
        assert any(o == GateOutcome.FAILED for _, o in results[req_id])

        from codeframe.core.proof import ledger

        req = ledger.get_requirement(workspace, req_id)
        assert req.status == ReqStatus.OPEN

    @patch("codeframe.core.gates.run")
    def test_gate_none_rules_are_ignored_not_errored(self, mock_run, workspace):
        """A rule whose gate could not be resolved (legacy, unknown prefix) is
        skipped: whole-suite behavior, no enforcement, no crash."""
        from codeframe.core.proof import ledger
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.runner import run_proof

        req, _ = capture_requirement(
            workspace, title="Bug", description="Logic error in calculation",
            where="src/calc.py", severity=Severity.MEDIUM, source=Source.QA,
        )
        # Unknown prefix → prefix-derivation on load also yields None
        for i, rule in enumerate(req.evidence_rules):
            rule.gate = None
            rule.test_id = f"regression_check_{i}"
        ledger.save_requirement(workspace, req)

        mock_run.return_value = _gate_result(GateStatus.PASSED, 0, "suite green")
        results = run_proof(workspace, full=True)
        assert all(o == GateOutcome.PASSED for _, o in results[req.id])
        # No scoped runs happened — every call was a whole-suite invocation
        assert all(
            c.kwargs.get("test_selector") is None for c in mock_run.call_args_list
        )

    @patch("codeframe.core.gates.run")
    def test_named_tests_passing_satisfies(self, mock_run, workspace):
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.runner import run_proof

        capture_requirement(
            workspace, title="Bug", description="Logic error in calculation",
            where="src/calc.py", severity=Severity.MEDIUM, source=Source.QA,
        )
        mock_run.return_value = _gate_result(GateStatus.PASSED, 0, "1 passed")

        results = run_proof(workspace, full=True)
        req_id = list(results.keys())[0]
        assert all(o == GateOutcome.PASSED for _, o in results[req_id])

        from codeframe.core.proof import ledger

        req = ledger.get_requirement(workspace, req_id)
        assert req.status == ReqStatus.SATISFIED
