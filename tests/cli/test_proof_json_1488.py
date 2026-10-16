"""#1488 — `--json` on the `cf proof` commands, for the proof9 plugin.

The plugin (#1469, #1470) reads these documents instead of parsing Rich
tables. The contract pinned here:

- stdout holds exactly one JSON document; progress, warnings, errors and
  prompts go to stderr;
- exit codes are the same with and without ``--json``;
- user text round-trips verbatim (no Rich escaping in the data).

`cf proof ratchet --json` runs a real pytest suite, so it is pinned in
tests/core/test_proof_json_ratchet_1488.py with the other ratchet tests.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.models import GateOutcome
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()

HOSTILE = "[bold red]pwn[/] \\[x] <script>alert(1)</script>"

_CAPTURE = [
    "--title", "Login rejects valid credentials",
    "--description", "Auth returns 401 for a correct password",
    "--where", "src/auth/login.py",
    "--severity", "high",
    "--source", "qa",
]


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    create_or_load_workspace(tmp_path)
    return tmp_path


def _cf(*args: str):
    return runner.invoke(app, ["proof", *args])


def _doc(result) -> dict:
    """The one JSON document on stdout; fails if anything else is there."""
    return json.loads(result.stdout)


def _capture(ws: Path, *extra: str):
    result = _cf("capture", "-w", str(ws), *_CAPTURE, *extra)
    assert result.exit_code == 0, result.output
    return result


class TestCapture:
    def test_the_created_requirement_is_the_document(self, ws):
        doc = _doc(_capture(ws, "--json"))
        req = doc["requirement"]
        assert req["id"] == "REQ-0001"
        assert req["title"] == "Login rejects valid credentials"
        assert req["status"] == "open"
        assert req["severity"] == "high"
        assert req["source"] == "qa"
        assert req["scope"]["files"] == ["src/auth/login.py"]
        assert [o["gate"] for o in req["obligations"]] == list(doc["stubs"])
        assert doc["workspace_created"] is False
        assert all(not Path(p).is_absolute() for p in doc["stubs"].values())

    def test_a_new_workspace_is_reported_in_the_document_and_on_stderr(self, tmp_path):
        import subprocess

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        result = _cf("capture", "-w", str(tmp_path), *_CAPTURE, "--json")
        assert result.exit_code == 0, result.output
        assert _doc(result)["workspace_created"] is True
        assert "Created .codeframe/" in result.stderr

    def test_a_hostile_title_round_trips_verbatim(self, ws):
        result = _cf(
            "capture", "-w", str(ws), "--title", HOSTILE, "--description", "d",
            "--where", "src/a.py", "--severity", "low", "--source", "qa", "--json",
        )
        assert result.exit_code == 0, result.output
        assert _doc(result)["requirement"]["title"] == HOSTILE

    def test_interactive_prompts_go_to_stderr(self, ws):
        result = runner.invoke(
            app, ["proof", "capture", "-w", str(ws), "--json"],
            input="Short title\nLonger description\nsrc/x.py\nmedium\nqa\n",
        )
        assert result.exit_code == 0, result.output
        assert _doc(result)["requirement"]["title"] == "Short title"
        assert "What happened?" in result.stderr

    def test_an_invalid_severity_exits_1_with_no_document(self, ws):
        args = [a if a != "high" else "urgent" for a in _CAPTURE]
        result = _cf("capture", "-w", str(ws), *args, "--json")
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "Invalid severity" in result.stderr


class TestList:
    def test_requirements_with_scope_and_gates(self, ws):
        _capture(ws)
        doc = _doc(_cf("list", "-w", str(ws), "--json"))
        [req] = doc["requirements"]
        assert req["id"] == "REQ-0001"
        assert req["scope"]["files"] == ["src/auth/login.py"]
        assert req["obligations"]

    def test_an_empty_ledger_is_an_empty_list(self, ws):
        result = _cf("list", "-w", str(ws), "--json")
        assert result.exit_code == 0
        assert _doc(result) == {"requirements": []}

    def test_the_status_filter_applies(self, ws):
        _capture(ws)
        assert _doc(_cf("list", "-w", str(ws), "--status", "waived", "--json")) == {
            "requirements": []
        }


class TestStatus:
    def test_an_empty_ledger_counts_zero(self, ws):
        result = _cf("status", "-w", str(ws), "--json")
        assert result.exit_code == 0
        doc = _doc(result)
        assert doc["counts"] == {
            "total": 0, "open": 0, "satisfied": 0, "waived": 0, "failing": 0, "locked": 0,
        }
        assert doc["expired_waivers"] == []

    @patch("codeframe.core.proof.runner._run_gate")
    def test_a_failed_obligation_counts_as_failing(self, mock_gate, ws):
        mock_gate.return_value = (GateOutcome.FAILED, "assertion failed")
        _capture(ws)
        assert _cf("run", "-w", str(ws), "--full").exit_code == 1
        counts = _doc(_cf("status", "-w", str(ws), "--json"))["counts"]
        assert counts["open"] == 1
        assert counts["failing"] == 1

    def test_a_waived_requirement_is_not_failing(self, ws):
        _capture(ws)
        assert _cf("waive", "REQ-0001", "-w", str(ws), "--reason", "later").exit_code == 0
        counts = _doc(_cf("status", "-w", str(ws), "--json"))["counts"]
        assert counts["waived"] == 1
        assert counts["failing"] == 0


class TestShow:
    @patch("codeframe.core.proof.runner._run_gate")
    def test_obligations_evidence_and_waiver(self, mock_gate, ws):
        mock_gate.return_value = (GateOutcome.PASSED, "ok")
        _capture(ws)
        assert _cf("run", "-w", str(ws), "--full").exit_code == 0
        assert _cf(
            "waive", "REQ-0001", "-w", str(ws), "--reason", "accepted", "--expires", "2099-01-01"
        ).exit_code == 0

        doc = _doc(_cf("show", "REQ-0001", "-w", str(ws), "--json"))
        req = doc["requirement"]
        assert req["status"] == "waived"
        assert req["waiver"]["reason"] == "accepted"
        assert req["waiver"]["expires"] == "2099-01-01"
        assert req["waiver"]["expired"] is False
        assert req["waiver"]["approved_by"]
        stored = ledger.list_evidence(create_or_load_workspace(ws), "REQ-0001")
        assert [e["artifact_checksum"] for e in doc["evidence"]] == [
            e.artifact_checksum for e in stored
        ]
        assert {e["status"] for e in doc["evidence"]} == {"passed"}

    def test_an_unknown_requirement_exits_1_with_no_document(self, ws):
        result = _cf("show", "REQ-9999", "-w", str(ws), "--json")
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "not found" in result.stderr


class TestRun:
    def test_an_empty_ledger_reports_why_and_keeps_exit_2(self, ws):
        result = _cf("run", "-w", str(ws), "--json")
        assert result.exit_code == 2
        doc = _doc(result)
        assert doc["requirements"] == []
        assert doc["passed"] is False
        assert doc["empty_reason"] == "no_requirements"
        assert doc["description"]

    def test_allow_empty_changes_only_the_exit_code(self, ws):
        result = _cf("run", "-w", str(ws), "--json", "--allow-empty")
        assert result.exit_code == 0
        assert _doc(result)["empty_reason"] == "no_requirements"

    @patch("codeframe.core.proof.runner._run_gate")
    def test_a_failure_names_the_requirement_gate_and_tests(self, mock_gate, ws):
        mock_gate.return_value = (GateOutcome.FAILED, "assertion failed")
        _capture(ws)
        result = _cf("run", "-w", str(ws), "--full", "--json")
        assert result.exit_code == 1
        doc = _doc(result)
        assert doc["passed"] is False
        assert doc["vacuous"] is False
        assert doc["mode"] == "full"
        assert doc["run_id"]
        [req] = doc["requirements"]
        assert req["id"] == "REQ-0001"
        assert req["title"] == "Login rejects valid credentials"
        assert req["status_before"] == "open"
        assert req["status_after"] == "open"
        assert req["gates"]
        assert {g["outcome"] for g in req["gates"]} == {"failed"}
        stored = ledger.get_requirement(create_or_load_workspace(ws), "REQ-0001")
        for g in req["gates"]:
            assert g["tests"] == [
                r.test_id for r in stored.evidence_rules if r.gate and r.gate.value == g["gate"]
            ]

    @patch("codeframe.core.proof.runner._run_gate")
    def test_a_pass_moves_the_requirement_to_satisfied(self, mock_gate, ws):
        mock_gate.return_value = (GateOutcome.PASSED, "ok")
        _capture(ws)
        result = _cf("run", "-w", str(ws), "--full", "--json")
        assert result.exit_code == 0
        doc = _doc(result)
        assert doc["passed"] is True
        assert doc["vacuous"] is False
        assert doc["requirements"][0]["status_after"] == "satisfied"

    @patch("codeframe.core.proof.runner._run_gate")
    def test_an_all_unverifiable_run_is_vacuous(self, mock_gate, ws):
        mock_gate.return_value = (GateOutcome.UNVERIFIABLE, "no runner")
        _capture(ws)
        result = _cf("run", "-w", str(ws), "--full", "--json")
        assert result.exit_code == 0
        doc = _doc(result)
        assert doc["passed"] is True
        assert doc["vacuous"] is True

    def test_progress_lines_stay_off_stdout(self, ws):
        result = _cf("run", "-w", str(ws), "--json")
        assert "Running proof obligations" in result.stderr
        assert "Running proof obligations" not in result.stdout


class TestExitCodesMatchTheTextOutput:
    @pytest.mark.parametrize("outcome", [GateOutcome.PASSED, GateOutcome.FAILED])
    def test_run(self, ws, outcome):
        _capture(ws)
        codes = []
        for extra in ([], ["--json"]):
            with patch("codeframe.core.proof.runner._run_gate", return_value=(outcome, "x")):
                codes.append(_cf("run", "-w", str(ws), "--full", *extra).exit_code)
        assert codes[0] == codes[1]

    @pytest.mark.parametrize("args", [
        ["run"], ["list"], ["status"], ["show", "REQ-0001"], ["show", "REQ-0404"],
    ])
    def test_others(self, ws, args):
        _capture(ws)
        plain = _cf(*args, "-w", str(ws)).exit_code
        assert _cf(*args, "-w", str(ws), "--json").exit_code == plain
