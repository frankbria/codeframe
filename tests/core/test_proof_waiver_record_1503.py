"""#1503 — reverting a lapsed waiver keeps the waiver's record.

`check_expired_waivers` reverted with `SET status = 'open', waiver = NULL`, and
it runs on every `cf proof run` and `cf proof status`. So the first look at the
ledger after a waiver lapsed deleted who accepted the risk, why, and until
when, which is the audit record attributable waivers exist for (#1466). It also
made the evidence export's "lapsed waivers marked expired" (#1472) impossible.

The requirement still reopens: every reader keys on status (the runner, the
merge gate, the counts, the API, the TUI, the proof9 plugin), so a retained
waiver on an OPEN requirement is history, not a waiver in force.
"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import list_blocking_requirements
from codeframe.core.proof.models import GateOutcome, ReqStatus, Waiver
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture()
def ws(tmp_path: Path):
    workspace = create_or_load_workspace(tmp_path)
    result = runner.invoke(app, [
        "proof", "capture", "-w", str(tmp_path), "--title", "t", "--description", "d",
        "--where", "src/a.py", "--severity", "low", "--source", "qa",
    ])
    assert result.exit_code == 0, result.output
    ledger.waive_requirement(
        workspace, "REQ-0001",
        Waiver(reason="vendor fix pending", expires=date(2000, 1, 1), approved_by="alice"),
    )
    return workspace, tmp_path


def test_the_revert_reopens_but_keeps_reason_approver_and_expiry(ws):
    workspace, _ = ws

    [reverted] = ledger.check_expired_waivers(workspace)

    stored = ledger.get_requirement(workspace, "REQ-0001")
    assert reverted.id == "REQ-0001"
    assert stored.status == ReqStatus.OPEN
    assert stored.waiver is not None
    assert stored.waiver.reason == "vendor fix pending"
    assert stored.waiver.approved_by == "alice"
    assert stored.waiver.expires == date(2000, 1, 1)


def test_a_proof_run_then_show_still_reports_the_lapsed_waiver(ws):
    _, path = ws
    with patch("codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.FAILED, "x")):
        runner.invoke(app, ["proof", "run", "-w", str(path), "--full"])

    doc = json.loads(runner.invoke(app, ["proof", "show", "REQ-0001", "-w", str(path), "--json"]).stdout)

    assert doc["requirement"]["status"] == "open"
    assert doc["requirement"]["waiver"]["reason"] == "vendor fix pending"
    assert doc["requirement"]["waiver"]["approved_by"] == "alice"
    assert doc["requirement"]["waiver"]["expired"] is True


def test_the_reopened_requirement_is_not_treated_as_waived(ws):
    workspace, path = ws
    ledger.check_expired_waivers(workspace)

    counts = json.loads(runner.invoke(app, ["proof", "status", "-w", str(path), "--json"]).stdout)["counts"]
    assert counts["open"] == 1
    assert counts["waived"] == 0
    assert "REQ-0001" in {r.id for r in list_blocking_requirements(workspace)}
    assert ledger.check_expired_waivers(workspace) == []  # not reverted twice


def test_waiving_it_again_records_the_new_waiver(ws):
    workspace, _ = ws
    ledger.check_expired_waivers(workspace)

    ledger.waive_requirement(workspace, "REQ-0001", Waiver(reason="extended", approved_by="bob"))

    stored = ledger.get_requirement(workspace, "REQ-0001")
    assert stored.status == ReqStatus.WAIVED
    assert stored.waiver.reason == "extended"
    assert stored.waiver.approved_by == "bob"


def test_cf_proof_show_labels_a_lapsed_waiver_as_no_longer_in_force(ws):
    workspace, path = ws
    ledger.check_expired_waivers(workspace)

    out = " ".join(runner.invoke(app, ["proof", "show", "REQ-0001", "-w", str(path)]).output.split())

    assert "Waiver (expired, no longer in force):" in out
    assert "vendor fix pending" in out
