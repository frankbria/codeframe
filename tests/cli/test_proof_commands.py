"""Integration tests for 'cf proof' CLI commands.

Exercises all PROOF9 CLI commands through the Typer CliRunner against a real
SQLite workspace — no mocks except _run_gate (which shells out to pytest/ruff).

AC coverage:
  AC1 — cf proof capture  creates a REQ and persists it
  AC2 — cf proof run      evaluates workspace against open REQs
  AC3 — cf proof waive    marks a REQ waived with expiry
  AC4 — cf proof status   shows correct summary
  AC5 — closed loop: capture → run (fail) → run (pass) → status reflects it
"""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.models import ReqStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()

_CAPTURE_ARGS = [
    "--title", "Login rejects valid credentials",
    "--description", "Auth module returns 401 for correct password after cache flush",
    "--where", "src/auth/login.py",
    "--severity", "high",
    "--source", "qa",
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ws(tmp_path: Path):
    """Initialised workspace — returns (workspace_object, workspace_path)."""
    workspace = create_or_load_workspace(tmp_path)
    return workspace, tmp_path


@pytest.fixture()
def ws_with_req(ws):
    """Workspace that already has one captured requirement (REQ-0001)."""
    workspace, workspace_path = ws
    runner.invoke(app, ["proof", "capture", "-w", str(workspace_path)] + _CAPTURE_ARGS)
    return workspace, workspace_path


# ---------------------------------------------------------------------------
# AC1 — cf proof capture
# ---------------------------------------------------------------------------


class TestCapture:
    def test_capture_creates_req_and_persists(self, ws):
        """capture should create REQ-0001, print it, and write it to the DB."""
        workspace, workspace_path = ws
        result = runner.invoke(
            app, ["proof", "capture", "-w", str(workspace_path)] + _CAPTURE_ARGS
        )

        assert result.exit_code == 0, result.output
        assert "REQ-0001" in result.output

        # Verify persistence — read straight from ledger, not from output
        req = ledger.get_requirement(workspace, "REQ-0001")
        assert req is not None
        assert req.title == "Login rejects valid credentials"
        assert req.status == ReqStatus.OPEN

    def test_capture_second_req_increments_id(self, ws_with_req):
        """A second capture should produce REQ-0002."""
        workspace, workspace_path = ws_with_req
        result = runner.invoke(app, [
            "proof", "capture", "-w", str(workspace_path),
            "--title", "Second bug",
            "--description", "Another issue",
            "--where", "src/util.py",
            "--severity", "low",
            "--source", "dogfooding",
        ])
        assert result.exit_code == 0, result.output
        assert "REQ-0002" in result.output

    def test_capture_invalid_severity_exits_nonzero(self, ws):
        """Invalid severity should print error and exit 1."""
        _, workspace_path = ws
        result = runner.invoke(app, [
            "proof", "capture", "-w", str(workspace_path),
            "--title", "Bug", "--description", "Desc",
            "--where", "src/x.py", "--severity", "extreme", "--source", "qa",
        ])
        assert result.exit_code != 0
        assert "Invalid severity" in result.output

    def test_capture_invalid_source_exits_nonzero(self, ws):
        """Invalid source should print error and exit 1."""
        _, workspace_path = ws
        result = runner.invoke(app, [
            "proof", "capture", "-w", str(workspace_path),
            "--title", "Bug", "--description", "Desc",
            "--where", "src/x.py", "--severity", "high", "--source", "unknown_source",
        ])
        assert result.exit_code != 0
        assert "Invalid source" in result.output


# ---------------------------------------------------------------------------
# AC2 — cf proof run
# ---------------------------------------------------------------------------


class TestRun:
    @patch("codeframe.core.proof.runner._run_gate")
    def test_run_with_passing_obligations(self, mock_run_gate, ws_with_req):
        """run --full with all gates passing should exit 0 and print PASS."""
        mock_run_gate.return_value = (True, "All tests passed")
        _, workspace_path = ws_with_req

        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_path), "--full"])

        assert result.exit_code == 0, result.output
        assert "PASS" in result.output
        assert "All obligations satisfied" in result.output

    @patch("codeframe.core.proof.runner._run_gate")
    def test_run_with_failing_obligations(self, mock_run_gate, ws_with_req):
        """run --full with any gate failing should exit 1 and print FAIL."""
        mock_run_gate.return_value = (False, "assertion failed")
        _, workspace_path = ws_with_req

        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_path), "--full"])

        assert result.exit_code == 1, result.output
        assert "FAIL" in result.output

    def test_run_no_requirements_exits_zero(self, ws):
        """run on an empty workspace should exit 0 and say no obligations."""
        _, workspace_path = ws
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_path), "--full"])
        assert result.exit_code == 0, result.output
        assert "No applicable obligations found" in result.output

    def test_run_invalid_gate_exits_nonzero(self, ws):
        """run with an unrecognised --gate should exit non-zero and print error."""
        _, workspace_path = ws
        result = runner.invoke(app, [
            "proof", "run", "-w", str(workspace_path), "--gate", "nonexistent",
        ])
        assert result.exit_code != 0
        assert "Unknown gate" in result.output


# ---------------------------------------------------------------------------
# AC3 — cf proof waive
# ---------------------------------------------------------------------------


class TestWaive:
    def test_waive_marks_req_waived_with_expiry(self, ws_with_req):
        """waive should set status=WAIVED and persist reason + expiry."""
        workspace, workspace_path = ws_with_req

        result = runner.invoke(app, [
            "proof", "waive", "REQ-0001",
            "-w", str(workspace_path),
            "--reason", "No automated test yet",
            "--expires", "2027-01-01",
        ])

        assert result.exit_code == 0, result.output
        assert "waived" in result.output.lower()

        # Verify persistence
        req = ledger.get_requirement(workspace, "REQ-0001")
        assert req.status == ReqStatus.WAIVED
        assert req.waiver is not None
        assert req.waiver.reason == "No automated test yet"
        assert req.waiver.expires == date(2027, 1, 1)

    def test_waive_without_expiry(self, ws_with_req):
        """waive without --expires should still succeed."""
        workspace, workspace_path = ws_with_req

        result = runner.invoke(app, [
            "proof", "waive", "REQ-0001",
            "-w", str(workspace_path),
            "--reason", "Accepted risk for Q1",
        ])

        assert result.exit_code == 0, result.output
        req = ledger.get_requirement(workspace, "REQ-0001")
        assert req.status == ReqStatus.WAIVED
        assert req.waiver.expires is None

    def test_waive_nonexistent_req_exits_nonzero(self, ws):
        """waive on a REQ that was never captured should exit 1."""
        _, workspace_path = ws
        result = runner.invoke(app, [
            "proof", "waive", "REQ-9999",
            "-w", str(workspace_path),
            "--reason", "Does not exist",
        ])
        assert result.exit_code == 1

    def test_waive_invalid_date_exits_nonzero(self, ws_with_req):
        """waive with a non-ISO expires value should exit 1 and explain format."""
        _, workspace_path = ws_with_req
        result = runner.invoke(app, [
            "proof", "waive", "REQ-0001",
            "-w", str(workspace_path),
            "--reason", "Bad date",
            "--expires", "next-tuesday",
        ])
        assert result.exit_code == 1
        assert "Invalid date format" in result.output


# ---------------------------------------------------------------------------
# AC4 — cf proof status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_empty_workspace(self, ws):
        """status on a fresh workspace should say no requirements."""
        _, workspace_path = ws
        result = runner.invoke(app, ["proof", "status", "-w", str(workspace_path)])
        assert result.exit_code == 0, result.output
        assert "No proof requirements" in result.output

    def test_status_shows_open_count(self, ws_with_req):
        """status after one capture should show Open: 1."""
        _, workspace_path = ws_with_req
        result = runner.invoke(app, ["proof", "status", "-w", str(workspace_path)])
        assert result.exit_code == 0, result.output
        assert "Open" in result.output
        assert "1" in result.output

    def test_status_shows_waived_count(self, ws_with_req):
        """status after waiving a REQ should show Waived: 1."""
        _, workspace_path = ws_with_req
        runner.invoke(app, [
            "proof", "waive", "REQ-0001", "-w", str(workspace_path),
            "--reason", "Accepted",
        ])
        result = runner.invoke(app, ["proof", "status", "-w", str(workspace_path)])
        assert result.exit_code == 0, result.output
        assert "Waived" in result.output
        assert "1" in result.output

    def test_status_expired_waiver_reverts_to_open(self, ws_with_req):
        """A waiver with a past expiry should be reverted and noted in status."""
        workspace, workspace_path = ws_with_req

        # Inject waiver with past expiry directly via ledger (not CLI date validation)
        from codeframe.core.proof.models import Waiver
        past_waiver = Waiver(reason="Old waiver", expires=date(2020, 1, 1), approved_by="test")
        ledger.waive_requirement(workspace, "REQ-0001", past_waiver)

        result = runner.invoke(app, ["proof", "status", "-w", str(workspace_path)])
        assert result.exit_code == 0, result.output
        assert "Expired" in result.output


# ---------------------------------------------------------------------------
# AC5 — Closed loop: capture → run (fail) → run (pass) → status reflects it
# ---------------------------------------------------------------------------


class TestClosedLoop:
    @patch("codeframe.core.proof.runner._run_gate")
    def test_capture_run_enforced_then_satisfied(self, mock_run_gate, ws):
        """Full loop: capture → fail run → pass run → status shows satisfied."""
        workspace, workspace_path = ws

        # Step 1 — capture
        result = runner.invoke(
            app, ["proof", "capture", "-w", str(workspace_path)] + _CAPTURE_ARGS
        )
        assert result.exit_code == 0, result.output
        assert "REQ-0001" in result.output

        # Step 2 — run with obligations failing
        mock_run_gate.return_value = (False, "assertion failed")
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_path), "--full"])
        assert result.exit_code == 1, result.output
        assert "FAIL" in result.output
        assert "REQ-0001" in result.output

        # Step 3 — status: still open (run failure doesn't auto-satisfy)
        result = runner.invoke(app, ["proof", "status", "-w", str(workspace_path)])
        assert result.exit_code == 0, result.output
        assert "Open" in result.output

        # Step 4 — run with all obligations passing
        mock_run_gate.return_value = (True, "all green")
        result = runner.invoke(app, ["proof", "run", "-w", str(workspace_path), "--full"])
        assert result.exit_code == 0, result.output
        assert "PASS" in result.output
        assert "All obligations satisfied" in result.output

        # Step 5 — verify evidence was recorded via ledger
        evidence = ledger.list_evidence(workspace, "REQ-0001")
        assert len(evidence) >= 1
        assert any(ev.satisfied for ev in evidence)
