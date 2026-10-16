"""#1491 — `cf proof status --json` reports recent runs for the proof9 pane.

The pane draws run history and the last run, and computes nothing the CLI does
not report, so the runs come from the CLI: newest first, with the runner's own
`overall_passed` and `vacuous_pass`.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof.models import GateOutcome
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    result = runner.invoke(app, [
        "proof", "capture", "-w", str(tmp_path), "--title", "t", "--description", "d",
        "--where", "src/a.py", "--severity", "low", "--source", "qa",
    ])
    assert result.exit_code == 0, result.output
    return tmp_path


def _runs(ws: Path) -> list[dict]:
    return json.loads(runner.invoke(app, ["proof", "status", "-w", str(ws), "--json"]).stdout)["runs"]


def test_runs_are_listed_newest_first_with_the_runners_verdict(ws):
    for outcome in (GateOutcome.FAILED, GateOutcome.PASSED, GateOutcome.UNVERIFIABLE):
        with patch("codeframe.core.proof.runner._run_gate", return_value=(outcome, "x")):
            runner.invoke(app, ["proof", "run", "-w", str(ws), "--full"])

    runs = _runs(ws)

    assert [(r["passed"], r["vacuous"]) for r in runs] == [(True, True), (True, False), (False, False)]
    assert all(r["run_id"] and r["started_at"] for r in runs)
    assert all(isinstance(r["duration_ms"], int) for r in runs)


def test_no_runs_is_an_empty_list(ws):
    assert _runs(ws) == []
