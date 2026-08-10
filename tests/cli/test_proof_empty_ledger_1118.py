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

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.workspace import create_or_load_workspace

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
