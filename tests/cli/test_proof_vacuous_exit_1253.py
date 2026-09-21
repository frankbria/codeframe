"""#1253 — `cf proof run` exited 0 when verification was impossible.

#1118 established the exit-code contract (0 pass / 1 fail / 2 nothing verified)
and applied 2 to an empty ledger. The other empty reasons kept falling through
to a bare `return`, and two of them are the same kind of lie:

- ``EXCLUDED_BY_CONFIG`` — requirements exist, are in scope, have obligations,
  and ``enabled_gates`` filtered every one out. The operator turned the gates
  off; nothing ran; the command reported success.
- ``NO_OBLIGATIONS`` — requirements exist but define nothing to run, so they can
  never be satisfied.

The four remaining reasons keep exiting 0 on purpose, and
``test_proof_empty_ledger_1118.py`` holds that line. The distinction is *whose
decision emptied the run*: a scope filter or an explicit ``--gate`` is the
caller getting what they asked for, while disabled gates and missing obligations
mean the gate could not do its job.

The decision keys off the diagnostics **buckets**, not the collapsed ``reason``.
``reason`` becomes ``MIXED`` as soon as two causes apply, so a reason-based rule
would let "2 out of scope + 1 excluded by disabled gates" exit 0 — the very case
this issue is about, hidden behind the collapse.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof.runner import ProofRunDiagnostics
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    return tmp_path


def _run(workspace_dir: Path, diagnostics: ProofRunDiagnostics, *extra: str):
    """Invoke `cf proof run` with the runner reporting `diagnostics` and no results.

    Patched rather than staged through a real workspace: reproducing each of
    these six empty states for real needs six different ledger+config+git
    setups, and what is under test is how the CLI *reports* an empty result.
    Patches `run_proof_with_diagnostics`, which is what the CLI calls (#1138).
    """
    with patch(
        "codeframe.core.proof.runner.run_proof_with_diagnostics",
        return_value=({}, diagnostics),
    ):
        return runner.invoke(app, ["proof", "run", "-w", str(workspace_dir), *extra])


# ── The two newly-non-zero reasons ────────────────────────────────────────


class TestDisabledGatesAreNotAPass:
    """AC1 — enabled_gates excluded every obligation."""

    DIAG = ProofRunDiagnostics(
        total_requirements=2, considered=2, config_filtered=["REQ-0001", "REQ-0002"]
    )

    def test_it_does_not_exit_zero(self, workspace_dir):
        result = _run(workspace_dir, self.DIAG)
        assert result.exit_code != 0, result.output

    def test_it_is_distinguishable_from_a_failure(self, workspace_dir):
        """2 is "nothing verified", 1 is "an obligation failed" — a CI script
        that retries on 1 must not retry forever on a config problem."""
        result = _run(workspace_dir, self.DIAG)
        assert result.exit_code == 2, result.output

    def test_it_still_points_at_enabled_gates(self, workspace_dir):
        """The #1137 hint text is hard-won; exiting must not replace it."""
        result = _run(workspace_dir, self.DIAG)
        assert "enabled_gates" in result.output

    def test_allow_empty_exits_zero(self, workspace_dir):
        result = _run(workspace_dir, self.DIAG, "--allow-empty")
        assert result.exit_code == 0, result.output

    def test_allow_empty_still_says_nothing_was_verified(self, workspace_dir):
        result = _run(workspace_dir, self.DIAG, "--allow-empty")
        assert "nothing was verified" in result.output.lower()


class TestRequirementsWithNoObligationsAreNotAPass:
    """AC2 — a requirement that defines nothing to run can never be satisfied."""

    DIAG = ProofRunDiagnostics(
        total_requirements=1, considered=1, no_obligations=["REQ-0001"]
    )

    def test_it_exits_two(self, workspace_dir):
        result = _run(workspace_dir, self.DIAG)
        assert result.exit_code == 2, result.output

    def test_it_still_says_to_add_obligations(self, workspace_dir):
        result = _run(workspace_dir, self.DIAG)
        assert "obligation" in result.output.lower()

    def test_allow_empty_exits_zero(self, workspace_dir):
        result = _run(workspace_dir, self.DIAG, "--allow-empty")
        assert result.exit_code == 0, result.output


# ── The reasons that must keep exiting 0 ──────────────────────────────────


class TestCallerDirectedEmptinessStillExitsZero:
    """Emptiness the caller asked for is not a vacuous pass.

    Duplicated in spirit in test_proof_empty_ledger_1118.py for scope; repeated
    here so a future change to the exit policy fails against the whole table at
    once rather than one reason at a time.
    """

    @pytest.mark.parametrize(
        "name,diagnostics",
        [
            (
                "out of scope",
                ProofRunDiagnostics(
                    total_requirements=1, considered=1, scope_skipped=["REQ-0001"]
                ),
            ),
            (
                "--gate filter",
                ProofRunDiagnostics(
                    total_requirements=1, considered=1, gate_filtered=["REQ-0001"]
                ),
            ),
            (
                "waived or satisfied",
                ProofRunDiagnostics(total_requirements=1, considered=0),
            ),
            (
                "gate x config combination",
                ProofRunDiagnostics(
                    total_requirements=1, considered=1, filter_combination=["REQ-0001"]
                ),
            ),
        ],
    )
    def test_exits_zero(self, workspace_dir, name, diagnostics):
        result = _run(workspace_dir, diagnostics)
        assert result.exit_code == 0, f"{name} must not fail CI: {result.output}"

    def test_it_still_reports_that_nothing_was_verified(self, workspace_dir):
        """Exit 0 is not the same as silence — the run still says so."""
        result = _run(
            workspace_dir,
            ProofRunDiagnostics(
                total_requirements=1, considered=1, scope_skipped=["REQ-0001"]
            ),
        )
        assert result.exit_code == 0
        assert "nothing was verified" in result.output.lower()


# ── MIXED: why the decision keys off buckets, not `reason` ────────────────


class TestMixedReasons:
    def test_a_config_component_inside_mixed_still_exits_two(self, workspace_dir):
        """`reason` collapses to MIXED here, so a reason-based rule would
        exit 0 — and an operator could hide disabled gates behind one
        out-of-scope requirement."""
        diagnostics = ProofRunDiagnostics(
            total_requirements=2,
            considered=2,
            scope_skipped=["REQ-0001"],
            config_filtered=["REQ-0002"],
        )
        from codeframe.core.proof.runner import EmptyReason

        assert diagnostics.reason is EmptyReason.MIXED, "precondition"

        result = _run(workspace_dir, diagnostics)
        assert result.exit_code == 2, result.output

    def test_a_no_obligations_component_inside_mixed_still_exits_two(self, workspace_dir):
        diagnostics = ProofRunDiagnostics(
            total_requirements=2,
            considered=2,
            gate_filtered=["REQ-0001"],
            no_obligations=["REQ-0002"],
        )
        result = _run(workspace_dir, diagnostics)
        assert result.exit_code == 2, result.output

    def test_mixed_of_only_caller_directed_reasons_exits_zero(self, workspace_dir):
        """Two reasons, both the caller's own narrowing — still not vacuous."""
        diagnostics = ProofRunDiagnostics(
            total_requirements=2,
            considered=2,
            scope_skipped=["REQ-0001"],
            gate_filtered=["REQ-0002"],
        )
        result = _run(workspace_dir, diagnostics)
        assert result.exit_code == 0, result.output
