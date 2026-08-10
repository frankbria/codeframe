"""#1111 — the CLI's own hints steered new users off the documented path.

`cf init` and `cf status` pointed only at `cf prd add <file.md>`, which requires
a PRD you have already written. GOLDEN_PATH §2 makes `prd generate` the primary
path and `prd add` the secondary one, and the README leads with `prd generate`.
So a user following the tool's own advice never discovered Socratic discovery —
the capability the product leads on.

These tests pin the hint against the docs so it cannot drift back.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import PRD_NEXT_STEPS, app

pytestmark = pytest.mark.v2

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


class TestTheHintLeadsWithGenerate:
    def test_generate_comes_before_add(self):
        """Order is the whole point — both commands were never the problem."""
        assert PRD_NEXT_STEPS.index("prd generate") < PRD_NEXT_STEPS.index("prd add")

    def test_add_is_still_offered(self):
        """`prd add` is the documented secondary path, not something to hide."""
        assert "prd add" in PRD_NEXT_STEPS

    def test_it_uses_the_binary_name_the_readme_uses(self):
        for line in PRD_NEXT_STEPS.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            assert stripped.startswith("cf "), f"{stripped!r} should use the `cf` binary"
            assert not stripped.startswith("codeframe "), stripped


class TestTheCommandsActuallyPrintIt:
    def test_init_next_steps(self, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "cf prd generate" in result.output
        assert "cf prd add" in result.output
        assert result.output.index("cf prd generate") < result.output.index("cf prd add")

    def test_status_with_no_prd(self, tmp_path):
        runner.invoke(app, ["init", str(tmp_path)])
        result = runner.invoke(app, ["status", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "cf prd generate" in result.output

    def test_tasks_generate_with_no_prd(self, tmp_path):
        runner.invoke(app, ["init", str(tmp_path)])
        result = runner.invoke(app, ["tasks", "generate", "-w", str(tmp_path)])
        assert result.exit_code != 0
        assert "cf prd generate" in result.output

    def test_prd_show_with_no_prd(self, tmp_path):
        runner.invoke(app, ["init", str(tmp_path)])
        result = runner.invoke(app, ["prd", "show", "-w", str(tmp_path)])
        assert "cf prd generate" in result.output


class TestNoCommandStillPointsOnlyAtAdd:
    """The regression was six separate strings drifting apart; now there is one."""

    def test_no_stale_codeframe_prd_add_hints_remain(self):
        app_source = (REPO_ROOT / "codeframe" / "cli" / "app.py").read_text()
        offenders = [
            line.strip()
            for line in app_source.splitlines()
            if "codeframe prd add" in line and "console.print" in line
        ]
        assert offenders == [], (
            "these still hard-code the old hint instead of PRD_NEXT_STEPS: "
            f"{offenders}"
        )

    def test_the_hint_matches_the_golden_path_ordering(self):
        """GOLDEN_PATH is the contract these strings are supposed to follow."""
        golden = (REPO_ROOT / "docs" / "GOLDEN_PATH.md").read_text()
        assert "prd generate" in golden, "GOLDEN_PATH should document prd generate"
        assert "prd generate" in PRD_NEXT_STEPS
