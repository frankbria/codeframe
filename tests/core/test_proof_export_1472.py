"""#1472 — `cf proof export --format pdf|html|json`: the evidence report.

A presentation layer over what the ledger already stores, made to be handed
to someone who has never seen CodeFRAME. JSON is the source, HTML renders it,
PDF prints the HTML. The report never upgrades a status: evidence that fails
verification is shown as failing.
"""

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.export import export_document, render_html, render_pdf
from codeframe.core.proof.models import GateOutcome, Waiver
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

runner = CliRunner()

HOSTILE = '<script>alert("x")</script> & <b>bold</b>'


def _capture(path: Path, title: str) -> None:
    result = runner.invoke(app, [
        "proof", "capture", "-w", str(path), "--title", title, "--description", "d",
        "--where", "src/a.py", "--severity", "high", "--source", "qa",
    ])
    assert result.exit_code == 0, result.output


@pytest.fixture()
def ws(tmp_path: Path):
    """Satisfied (with evidence), open, waived, expired-waiver, a vacuous run, an override."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    workspace = create_or_load_workspace(tmp_path)
    _capture(tmp_path, HOSTILE)                            # REQ-0001 → satisfied
    with patch("codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.PASSED, "ok")):
        assert runner.invoke(app, ["proof", "run", "-w", str(tmp_path), "--full"]).exit_code == 0
    _capture(tmp_path, "Export keeps the header")          # REQ-0002 → open
    _capture(tmp_path, "Legacy importer")                  # REQ-0003 → waived
    ledger.waive_requirement(workspace, "REQ-0003", Waiver(reason="sunset", approved_by="alice"))
    _capture(tmp_path, "Old flaky test")                   # REQ-0004 → waiver expired
    ledger.waive_requirement(
        workspace, "REQ-0004", Waiver(reason="later", expires=date(2000, 1, 1), approved_by="bob"),
    )
    ledger.check_expired_waivers(workspace)
    with patch("codeframe.core.proof.runner._run_gate", return_value=(GateOutcome.UNVERIFIABLE, "x")):
        runner.invoke(app, ["proof", "run", "-w", str(tmp_path), "--full", "--gate", "manual"])
    ledger.save_merge_override(workspace, 42, "carol", "hotfix", [{"id": "REQ-0002", "title": "Export keeps the header"}])
    return workspace, tmp_path


def _req(doc, req_id):
    return next(r for r in doc["requirements"] if r["id"] == req_id)


class TestTheJsonSource:
    def test_provenance(self, ws):
        workspace, path = ws
        doc = export_document(workspace)
        prov = doc["provenance"]
        assert prov["repository"] == str(path)
        assert prov["tool_version"]
        assert prov["generated_at"]
        assert "commit" in prov

    def test_every_case_is_present_and_distinct(self, ws):
        workspace, _ = ws
        doc = export_document(workspace)
        assert _req(doc, "REQ-0001")["state"] == "satisfied"
        assert _req(doc, "REQ-0002")["state"] == "open"
        assert _req(doc, "REQ-0003")["state"] == "waived"
        assert _req(doc, "REQ-0004")["state"] == "waiver expired"
        assert _req(doc, "REQ-0004")["waiver"]["approved_by"] == "bob"
        assert any(run["vacuous"] for run in doc["runs"])
        assert doc["merge_overrides"][0]["actor"] == "carol"
        assert doc["merge_overrides"][0]["bypassed"] == [{"id": "REQ-0002", "title": "Export keeps the header"}]

    def test_checksums_match_the_stored_artifacts(self, ws):
        workspace, _ = ws
        doc = export_document(workspace)
        exported = [e["artifact_checksum"] for e in _req(doc, "REQ-0001")["evidence"]]
        assert exported
        assert exported == [e.artifact_checksum for e in ledger.list_evidence(workspace, "REQ-0001")]
        assert all(e["verified"] for e in _req(doc, "REQ-0001")["evidence"])

    def test_tampered_evidence_is_shown_failing_not_upgraded(self, ws):
        workspace, _ = ws
        [first, *_] = ledger.list_evidence(workspace, "REQ-0001")
        Path(first.artifact_path).write_text("forged")
        doc = export_document(workspace)
        tampered = next(e for e in _req(doc, "REQ-0001")["evidence"] if e["artifact_checksum"] == first.artifact_checksum)
        assert tampered["verified"] is False
        assert "html" not in tampered  # data only; rendering is the HTML's job
        assert "FAILS VERIFICATION" in render_html(doc)

    def test_an_empty_ledger_says_so(self, tmp_path):
        doc = export_document(create_or_load_workspace(tmp_path))
        assert doc["requirements"] == []
        assert "No requirements in the ledger" in render_html(doc)


class TestTheHtml:
    def test_each_case_is_labelled_distinctly(self, ws):
        workspace, _ = ws
        html = render_html(export_document(workspace))
        for label in ("SATISFIED", "OPEN", "WAIVED", "WAIVER EXPIRED", "VACUOUS", "MERGE OVERRIDE"):
            assert label in html, label

    def test_hostile_markup_cannot_inject(self, ws):
        workspace, _ = ws
        html = render_html(export_document(workspace))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<b>bold</b>" not in html

    def test_it_is_a_standalone_page_with_a_cover(self, ws):
        workspace, path = ws
        html = render_html(export_document(workspace))
        assert html.lstrip().lower().startswith("<!doctype html>")
        assert "PROOF9 evidence report" in html
        assert str(path) in html
        assert "<link" not in html and "src=\"http" not in html  # nothing fetched when printed


class TestThePdf:
    @pytest.mark.skipif(
        not any(shutil.which(b) for b in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")),
        reason="no headless Chrome/Chromium on this machine",
    )
    def test_the_html_prints_to_a_pdf(self, ws, tmp_path):
        workspace, _ = ws
        out = tmp_path / "report.pdf"
        render_pdf(render_html(export_document(workspace)), out)
        assert out.read_bytes().startswith(b"%PDF")

    def test_without_a_browser_it_says_what_to_do(self, ws, tmp_path, monkeypatch):
        workspace, _ = ws
        monkeypatch.setattr("codeframe.core.proof.export.shutil.which", lambda _name: None)
        with pytest.raises(RuntimeError, match="--format html"):
            render_pdf(render_html(export_document(workspace)), tmp_path / "r.pdf")


class TestTheCommand:
    @pytest.mark.parametrize("fmt", ["json", "html"])
    def test_writes_the_report_where_asked(self, ws, tmp_path, fmt):
        _, path = ws
        out = tmp_path / f"report.{fmt}"
        result = runner.invoke(app, ["proof", "export", "-w", str(path), "--format", fmt, "--output", str(out)])
        assert result.exit_code == 0, result.output
        text = out.read_text()
        if fmt == "json":
            assert json.loads(text)["requirements"]
        else:
            assert "PROOF9 evidence report" in text

    def test_an_unknown_format_exits_1(self, ws, tmp_path):
        _, path = ws
        result = runner.invoke(app, ["proof", "export", "-w", str(path), "--format", "docx", "--output", str(tmp_path / "x")])
        assert result.exit_code == 1
