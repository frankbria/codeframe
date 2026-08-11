"""#1118 — `cf proof run` exited 0 on an empty ledger, so PROVE was a vacuous pass.

The quickstart's last step, on the product's stated differentiator, printed
"No applicable obligations found." in green and exited 0. A user reads that as
"PROOF9 quality gates passed". Nothing had been verified — and every new
workspace is in exactly that state, including after a full agent run had written
code and tests.

An empty ledger is now its own outcome: exit 2, distinct from pass (0) and fail
(1), so CI cannot be green on it and a script can tell the two apart.
"""

from pathlib import Path
import re
from unittest.mock import patch


import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace

def _flat(text: str) -> str:
    """Rich hard-wraps console output, so assertions must ignore line breaks."""
    return re.sub(r"\s+", " ", text)


pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    return tmp_path


class TestAnEmptyLedgerIsNotAPass:
    """AC: zero applicable obligations is reported distinctly from a pass."""

    def test_it_does_not_exit_zero(self, workspace_dir):
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])
        assert result.exit_code != 0, (
            "exit 0 on an empty ledger is what made PROVE a vacuous pass"
        )

    def test_it_is_distinguishable_from_a_failure(self, workspace_dir):
        """AC: distinct in the exit code — 2, not 1.

        A failed obligation and an absent one need different responses, so they
        need different codes.
        """
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])
        assert result.exit_code == 2

    def test_it_does_not_claim_anything_passed(self, workspace_dir):
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])
        lowered = result.output.lower()
        assert "nothing was verified" in lowered
        assert "not a pass" in lowered

    def test_it_says_how_to_get_a_first_obligation(self, workspace_dir):
        """AC: tell a new user how to proceed, not that the gate was satisfied."""
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])
        assert "cf proof capture" in result.output


class TestTheEscapeHatch:
    """AC: an explicit flag, defaulting to the safe behaviour."""

    def test_allow_empty_exits_zero(self, workspace_dir):
        result = runner.invoke(
            app, ["proof", "run", "-w", str(workspace_dir), "--allow-empty"]
        )
        assert result.exit_code == 0

    def test_allow_empty_still_says_nothing_was_verified(self, workspace_dir):
        """Opting into exit 0 must not also silence the explanation."""
        result = runner.invoke(
            app, ["proof", "run", "-w", str(workspace_dir), "--allow-empty"]
        )
        assert "nothing was verified" in result.output.lower()

    def test_the_safe_behaviour_is_the_default(self, workspace_dir):
        """The flag has to be asked for; empty is not silently green."""
        assert (
            runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)]).exit_code
            != 0
        )


class TestStatusSaysTheSameThing:
    """The two surfaces should not disagree about what an empty ledger means."""

    def test_status_frames_it_as_unverified(self, workspace_dir):
        result = runner.invoke(app, ["proof", "status", "-w", str(workspace_dir)])
        lowered = result.output.lower()
        assert "nothing" in lowered and "verified" in lowered
        assert "cf proof capture" in result.output


class TestAScopeFilteredRunIsNotAnEmptyLedger:
    """Raised in review, and a real regression in my first version.

    `run_proof` returning {} is ambiguous: the ledger may be empty, or it may
    hold requirements none of which intersect the changed scope. Only the first
    is the #1118 vacuous pass. Conflating them told a user with three
    requirements that their ledger was empty, and failed CI on a doc-only PR
    because its scope matched nothing — a new bug in the name of fixing one.
    """

    def _capture_req(self, workspace_dir: Path, scope_path: str) -> None:
        """A real requirement scoped to a path the run will not touch."""
        result = runner.invoke(
            app,
            [
                "proof", "capture",
                "--title", "Login must not 500",
                "--description", "Expected 200, got 500 on POST /login",
                "--where", scope_path,
                "--severity", "high",
                "--source", "production",
                "-w", str(workspace_dir),
            ],
        )
        assert result.exit_code == 0, result.output

    def _run_with_nothing_in_scope(self, workspace_dir: Path):
        """The runner returns ({}, scope-skipped) — everything was out of scope.

        Patched rather than staged through git: with no working-tree changes the
        detector fails closed and runs every requirement, so the real filter
        cannot produce this state here. The ambiguity under test is in how the
        CLI reports an empty result, not in scope detection.

        Patches `run_proof_with_diagnostics`, which is what the CLI calls since
        #1138. Patching the old `run_proof` here did not fail loudly — the real
        run just went ahead and these tests started asserting on a live result.
        """
        from codeframe.core.proof.runner import ProofRunDiagnostics

        diagnostics = ProofRunDiagnostics(
            total_requirements=1, considered=1, scope_skipped=["REQ-0001"]
        )
        with patch(
            "codeframe.core.proof.runner.run_proof_with_diagnostics",
            return_value=({}, diagnostics),
        ):
            return runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])

    def test_it_does_not_claim_the_ledger_is_empty(self, workspace_dir):
        self._capture_req(workspace_dir, "src/auth/login.py")

        result = self._run_with_nothing_in_scope(workspace_dir)

        assert "no proof obligations in this workspace" not in result.output.lower()
        assert "cf proof capture" not in result.output, (
            "telling someone with requirements to capture their first one is wrong"
        )

    def test_it_does_not_fail_ci_on_an_out_of_scope_change(self, workspace_dir):
        """A doc-only PR must not be failed by the scope filter working."""
        self._capture_req(workspace_dir, "src/auth/login.py")

        result = self._run_with_nothing_in_scope(workspace_dir)

        assert result.exit_code == 0, result.output

    def test_it_still_says_nothing_was_verified(self, workspace_dir):
        """Accurate either way — it just is not the vacuous-pass case."""
        self._capture_req(workspace_dir, "src/auth/login.py")

        result = self._run_with_nothing_in_scope(workspace_dir)

        assert "nothing was verified" in result.output.lower()
        assert "--full" in result.output, "point at the way to check them anyway"

    def test_a_truly_empty_ledger_still_exits_two(self, workspace_dir):
        """The two paths must not have been collapsed the other way."""
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])
        assert result.exit_code == 2

    def test_full_mode_does_not_offer_full_as_the_remedy(self, workspace_dir):
        """--full never consults scope, so re-running it changes nothing.

        No patch needed since #1138: `--gate perf` genuinely excludes every
        obligation of a captured requirement, so this is a real empty run whose
        real reason is the gate filter.
        """
        self._capture_req(workspace_dir, "src/auth/login.py")

        result = runner.invoke(
            app, ["proof", "run", "-w", str(workspace_dir), "--full", "--gate", "perf"]
        )

        assert result.exit_code == 0, result.output
        assert "--full" not in _flat(result.output)


class TestTheReasonIsNamedNotGuessed:
    """#1138 finished what #1137's four review rounds kept failing at.

    `run_proof` returning {} has six causes, and the CLI could not tell them
    apart because the runner computed the reasons and threw them away. It ended
    up listing candidates — honest, and useless. `run_proof_with_diagnostics`
    now returns the reason, so every case below asserts the ACTUAL cause is
    named and the wrong ones are absent.

    Almost none of these need a patch any more: a waived ledger, a gate filter
    that matches nothing, and a requirement with no obligations are all states
    the CLI can be driven into for real.
    """

    def _capture(self, workspace_dir: Path) -> None:
        result = runner.invoke(
            app,
            [
                "proof", "capture",
                "--title", "Login must not 500",
                "--description", "Expected 200, got 500",
                "--where", "src/auth/login.py",
                "--severity", "high",
                "--source", "production",
                "-w", str(workspace_dir),
            ],
        )
        assert result.exit_code == 0, result.output

    def _req_id(self, workspace_dir: Path) -> str:
        from codeframe.core.proof import ledger
        from codeframe.core.workspace import get_workspace

        return ledger.list_requirements(get_workspace(workspace_dir))[0].id

    def test_a_waived_only_ledger_is_not_blamed_on_scope(self, workspace_dir):
        """The scoped path: run_proof short-circuits before scope is computed."""
        self._capture(workspace_dir)
        waive = runner.invoke(
            app,
            [
                "proof", "waive", self._req_id(workspace_dir),
                "--reason", "accepted risk for now",
                "-w", str(workspace_dir),
            ],
        )
        assert waive.exit_code == 0, waive.output

        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])

        flat = _flat(result.output)
        assert result.exit_code == 0, result.output
        assert "changed files" not in flat and "out of scope" not in flat, (
            "scope was never evaluated — the requirement was excluded by status"
        )
        assert "waived" in flat

    def test_the_gate_filter_is_named_as_the_reason_not_a_candidate(self, workspace_dir):
        """A real run: `--gate perf` excludes every obligation capture created."""
        self._capture(workspace_dir)

        result = runner.invoke(
            app, ["proof", "run", "-w", str(workspace_dir), "--gate", "perf"]
        )

        flat = _flat(result.output)
        assert result.exit_code == 0, result.output
        assert "--gate" in flat
        assert "Possible reasons" not in flat, "the cause is known now, not guessed"
        assert "out of scope" not in flat, "scope was not what excluded them"

    def test_scope_is_named_when_scope_is_the_reason(self, workspace_dir):
        """Still patched: with no working-tree changes the detector fails closed
        and runs everything, so the real filter cannot produce this state."""
        from codeframe.core.proof.runner import ProofRunDiagnostics

        self._capture(workspace_dir)
        diagnostics = ProofRunDiagnostics(
            total_requirements=1, considered=1, scope_skipped=[self._req_id(workspace_dir)]
        )

        with patch(
            "codeframe.core.proof.runner.run_proof_with_diagnostics",
            return_value=({}, diagnostics),
        ):
            result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])

        flat = _flat(result.output)
        assert result.exit_code == 0, result.output
        assert "out of scope" in flat
        assert "--full" in flat, "point at the way to check them anyway"
        assert "--gate" not in flat, "no gate filter was used; it cannot be the cause"

    def test_an_empty_ledger_is_still_the_vacuous_pass_case(self, workspace_dir):
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])
        assert result.exit_code == 2
        assert "cf proof capture" in result.output

    def test_no_wrong_remedy_is_offered_when_no_gate_was_passed(self, workspace_dir):
        """Only the actual cause is named, so --gate must not appear."""
        from codeframe.core.proof.runner import ProofRunDiagnostics

        self._capture(workspace_dir)
        diagnostics = ProofRunDiagnostics(
            total_requirements=1, considered=1, scope_skipped=["REQ-0001"]
        )

        with patch(
            "codeframe.core.proof.runner.run_proof_with_diagnostics",
            return_value=({}, diagnostics),
        ):
            result = runner.invoke(app, ["proof", "run", "-w", str(workspace_dir)])

        assert "--gate" not in _flat(result.output)
