"""Tests for PROOF9 quality memory system.

Covers models, ledger CRUD, obligation mapping, scope intersection,
evidence attachment, capture flow, runner, waivers, and CLI commands.
"""

import pytest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from codeframe.core.workspace import Workspace, create_or_load_workspace


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return create_or_load_workspace(tmp_path)


# --- Model Tests ---


class TestModels:
    def test_gate_enum(self):
        from codeframe.core.proof.models import Gate
        assert Gate.UNIT == "unit"
        assert Gate.MANUAL == "manual"
        assert len(Gate) == 9

    def test_glitch_type_enum(self):
        from codeframe.core.proof.models import GlitchType
        assert GlitchType.LOGIC_BUG == "logic_bug"
        assert GlitchType.SECURITY_ISSUE == "security_issue"

    def test_requirement_creation(self):
        from codeframe.core.proof.models import (
            Requirement, Gate, Severity, Source, ReqStatus,
            RequirementScope, Obligation,
        )
        req = Requirement(
            id="REQ-0001",
            title="Login rejects empty password",
            description="Empty passwords should be rejected",
            severity=Severity.HIGH,
            source=Source.QA,
            scope=RequirementScope(files=["src/auth/login.py"]),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
        )
        assert req.id == "REQ-0001"
        assert req.status == ReqStatus.OPEN
        assert len(req.obligations) == 1

    def test_waiver_with_expiry(self):
        from codeframe.core.proof.models import Waiver
        waiver = Waiver(
            reason="No automated test yet",
            expires=date(2026, 4, 1),
            approved_by="frank",
        )
        assert waiver.expires == date(2026, 4, 1)


# --- Ledger Tests ---


class TestLedger:
    def test_init_tables(self, workspace):
        from codeframe.core.proof.ledger import init_proof_tables
        init_proof_tables(workspace)
        # Should not raise

    def test_save_and_get_requirement(self, workspace):
        from codeframe.core.proof.ledger import save_requirement, get_requirement
        from codeframe.core.proof.models import (
            Requirement, Gate, Severity, Source,
            RequirementScope, Obligation, GlitchType,
        )

        req = Requirement(
            id="REQ-0001",
            title="Test requirement",
            description="A test",
            severity=Severity.MEDIUM,
            source=Source.QA,
            scope=RequirementScope(files=["src/test.py"]),
            obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
            created_at=datetime.now(timezone.utc),
            glitch_type=GlitchType.LOGIC_BUG,
        )
        save_requirement(workspace, req)
        loaded = get_requirement(workspace, "REQ-0001")

        assert loaded is not None
        assert loaded.id == "REQ-0001"
        assert loaded.severity == Severity.MEDIUM
        assert loaded.glitch_type == GlitchType.LOGIC_BUG
        assert len(loaded.obligations) == 1
        assert loaded.obligations[0].gate == Gate.UNIT

    def test_list_requirements(self, workspace):
        from codeframe.core.proof.ledger import save_requirement, list_requirements
        from codeframe.core.proof.models import (
            Requirement, Severity, Source, RequirementScope,
        )

        for i in range(3):
            req = Requirement(
                id=f"REQ-{i:04d}",
                title=f"Req {i}",
                description=f"Desc {i}",
                severity=Severity.MEDIUM,
                source=Source.QA,
                scope=RequirementScope(),
                obligations=[],
                evidence_rules=[],
                created_at=datetime.now(timezone.utc),
            )
            save_requirement(workspace, req)

        all_reqs = list_requirements(workspace)
        assert len(all_reqs) == 3

    def test_list_requirements_by_status(self, workspace):
        from codeframe.core.proof.ledger import save_requirement, list_requirements
        from codeframe.core.proof.models import (
            Requirement, Severity, Source, RequirementScope, ReqStatus,
        )

        req_open = Requirement(
            id="REQ-0001", title="Open", description="Open req",
            severity=Severity.HIGH, source=Source.QA,
            scope=RequirementScope(), obligations=[], evidence_rules=[],
            created_at=datetime.now(timezone.utc), status=ReqStatus.OPEN,
        )
        req_sat = Requirement(
            id="REQ-0002", title="Satisfied", description="Done req",
            severity=Severity.LOW, source=Source.QA,
            scope=RequirementScope(), obligations=[], evidence_rules=[],
            created_at=datetime.now(timezone.utc), status=ReqStatus.SATISFIED,
        )
        save_requirement(workspace, req_open)
        save_requirement(workspace, req_sat)

        open_reqs = list_requirements(workspace, status=ReqStatus.OPEN)
        assert len(open_reqs) == 1
        assert open_reqs[0].id == "REQ-0001"

    def test_next_req_id(self, workspace):
        from codeframe.core.proof.ledger import next_req_id, save_requirement
        from codeframe.core.proof.models import (
            Requirement, Severity, Source, RequirementScope,
        )

        assert next_req_id(workspace) == "REQ-0001"

        req = Requirement(
            id="REQ-0001", title="First", description="First req",
            severity=Severity.LOW, source=Source.QA,
            scope=RequirementScope(), obligations=[], evidence_rules=[],
            created_at=datetime.now(timezone.utc),
        )
        save_requirement(workspace, req)
        assert next_req_id(workspace) == "REQ-0002"

    def test_save_and_list_evidence(self, workspace):
        from codeframe.core.proof.ledger import save_evidence, list_evidence
        from codeframe.core.proof.models import Evidence, Gate

        ev = Evidence(
            req_id="REQ-0001", gate=Gate.UNIT, satisfied=True,
            artifact_path="/tmp/test.txt", artifact_checksum="abc123",
            timestamp=datetime.now(timezone.utc), run_id="run-1",
        )
        save_evidence(workspace, ev)

        evidence = list_evidence(workspace, "REQ-0001")
        assert len(evidence) == 1
        assert evidence[0].gate == Gate.UNIT
        assert evidence[0].satisfied is True

    def test_waive_requirement(self, workspace):
        from codeframe.core.proof.ledger import (
            save_requirement, waive_requirement, get_requirement,
        )
        from codeframe.core.proof.models import (
            Requirement, Severity, Source, RequirementScope, Waiver, ReqStatus,
        )

        req = Requirement(
            id="REQ-0001", title="Test", description="Test",
            severity=Severity.MEDIUM, source=Source.QA,
            scope=RequirementScope(), obligations=[], evidence_rules=[],
            created_at=datetime.now(timezone.utc),
        )
        save_requirement(workspace, req)

        waiver = Waiver(reason="No test yet", expires=date(2026, 4, 1))
        waive_requirement(workspace, "REQ-0001", waiver)

        loaded = get_requirement(workspace, "REQ-0001")
        assert loaded.status == ReqStatus.WAIVED
        assert loaded.waiver.reason == "No test yet"

    def test_expired_waivers_revert(self, workspace):
        from codeframe.core.proof.ledger import (
            save_requirement, waive_requirement, check_expired_waivers, get_requirement,
        )
        from codeframe.core.proof.models import (
            Requirement, Severity, Source, RequirementScope, Waiver, ReqStatus,
        )

        req = Requirement(
            id="REQ-0001", title="Test", description="Test",
            severity=Severity.MEDIUM, source=Source.QA,
            scope=RequirementScope(), obligations=[], evidence_rules=[],
            created_at=datetime.now(timezone.utc),
        )
        save_requirement(workspace, req)

        # Waive with past expiry
        waiver = Waiver(reason="Expired", expires=date(2020, 1, 1))
        waive_requirement(workspace, "REQ-0001", waiver)

        expired = check_expired_waivers(workspace)
        assert len(expired) == 1

        loaded = get_requirement(workspace, "REQ-0001")
        assert loaded.status == ReqStatus.OPEN


# --- Obligation Tests ---


class TestObligations:
    def test_classify_logic_bug(self):
        from codeframe.core.proof.obligations import classify_glitch
        from codeframe.core.proof.models import GlitchType

        result = classify_glitch("The calculation returns wrong values")
        assert result == GlitchType.LOGIC_BUG

    def test_classify_security_issue(self):
        from codeframe.core.proof.obligations import classify_glitch
        from codeframe.core.proof.models import GlitchType

        result = classify_glitch("XSS vulnerability in the login form via injection")
        assert result == GlitchType.SECURITY_ISSUE

    def test_classify_perf_regression(self):
        from codeframe.core.proof.obligations import classify_glitch
        from codeframe.core.proof.models import GlitchType

        result = classify_glitch("API response is slow, high latency under load")
        assert result == GlitchType.PERF_REGRESSION

    def test_classify_a11y_bug(self):
        from codeframe.core.proof.obligations import classify_glitch
        from codeframe.core.proof.models import GlitchType

        result = classify_glitch("Screen reader cannot read the aria labels")
        assert result == GlitchType.A11Y_BUG

    def test_classify_default(self):
        from codeframe.core.proof.obligations import classify_glitch
        from codeframe.core.proof.models import GlitchType

        result = classify_glitch("something vague happened")
        assert result == GlitchType.LOGIC_BUG  # default

    def test_get_obligations(self):
        from codeframe.core.proof.obligations import get_obligations
        from codeframe.core.proof.models import GlitchType, Gate

        obls = get_obligations(GlitchType.LOGIC_BUG)
        gates = [o.gate for o in obls]
        assert Gate.UNIT in gates
        assert Gate.CONTRACT in gates

    def test_obligation_map_completeness(self):
        from codeframe.core.proof.obligations import OBLIGATION_MAP
        from codeframe.core.proof.models import GlitchType

        for gt in GlitchType:
            assert gt in OBLIGATION_MAP, f"Missing mapping for {gt}"

    def test_suggest_evidence_rules(self):
        from codeframe.core.proof.obligations import suggest_evidence_rules
        from codeframe.core.proof.models import Gate

        rules = suggest_evidence_rules(Gate.UNIT, "Login rejects empty password")
        assert len(rules) == 1
        assert rules[0].test_id.startswith("test_unit_")
        assert rules[0].must_pass is True


# --- Scope Tests ---


class TestScope:
    def test_build_scope_from_file(self):
        from codeframe.core.proof.scope import build_scope_from_capture

        scope = build_scope_from_capture("src/auth/login.py")
        assert "src/auth/login.py" in scope.files

    def test_build_scope_from_route(self):
        from codeframe.core.proof.scope import build_scope_from_capture

        scope = build_scope_from_capture("/login")
        assert "/login" in scope.routes

    def test_build_scope_from_api(self):
        from codeframe.core.proof.scope import build_scope_from_capture

        scope = build_scope_from_capture("POST /auth/login")
        assert "POST /auth/login" in scope.apis

    def test_build_scope_from_tag(self):
        from codeframe.core.proof.scope import build_scope_from_capture

        scope = build_scope_from_capture("authentication")
        assert "authentication" in scope.tags

    def test_intersects_files(self):
        from codeframe.core.proof.scope import intersects
        from codeframe.core.proof.models import RequirementScope

        req_scope = RequirementScope(files=["src/auth/login.py"])
        changed_scope = RequirementScope(files=["src/auth/login.py"])
        assert intersects(req_scope, changed_scope) is True

    def test_no_directory_expansion(self):
        from codeframe.core.proof.scope import intersects
        from codeframe.core.proof.models import RequirementScope

        req_scope = RequirementScope(files=["src/auth/login.py"])
        changed_scope = RequirementScope(files=["src/auth/validator.py"])
        assert intersects(req_scope, changed_scope) is False  # exact match only

    def test_no_intersection(self):
        from codeframe.core.proof.scope import intersects
        from codeframe.core.proof.models import RequirementScope

        req_scope = RequirementScope(files=["src/auth/login.py"])
        changed_scope = RequirementScope(files=["src/billing/invoice.py"])
        assert intersects(req_scope, changed_scope) is False

    def test_intersects_routes(self):
        from codeframe.core.proof.scope import intersects
        from codeframe.core.proof.models import RequirementScope

        req_scope = RequirementScope(routes=["/login"])
        changed_scope = RequirementScope(routes=["/login"])
        assert intersects(req_scope, changed_scope) is True


# --- Evidence Tests ---


class TestEvidence:
    def test_attach_evidence(self, workspace, tmp_path):
        from codeframe.core.proof.evidence import attach_evidence
        from codeframe.core.proof.models import Gate
        from codeframe.core.proof import ledger

        # Create artifact file
        artifact = tmp_path / "test_output.txt"
        artifact.write_text("All tests passed")

        ev = attach_evidence(
            workspace, "REQ-0001", Gate.UNIT,
            str(artifact), True, "run-1",
        )
        assert ev.satisfied is True
        assert ev.artifact_checksum != ""
        assert len(ev.artifact_checksum) == 64  # SHA-256

        # Verify persisted
        evidence_list = ledger.list_evidence(workspace, "REQ-0001")
        assert len(evidence_list) == 1

    def test_check_obligation_satisfied(self, workspace, tmp_path):
        from codeframe.core.proof.evidence import attach_evidence, check_obligation_satisfied
        from codeframe.core.proof.models import (
            Gate, Requirement, Severity, Source, RequirementScope, Obligation,
        )

        req = Requirement(
            id="REQ-0001", title="Test", description="Test",
            severity=Severity.MEDIUM, source=Source.QA,
            scope=RequirementScope(), obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
        )

        # No evidence yet
        assert check_obligation_satisfied(workspace, req, Gate.UNIT) is False

        # Attach passing evidence
        artifact = tmp_path / "out.txt"
        artifact.write_text("passed")
        attach_evidence(workspace, "REQ-0001", Gate.UNIT, str(artifact), True, "run-1")

        assert check_obligation_satisfied(workspace, req, Gate.UNIT) is True


# --- Stub Tests ---


class TestStubs:
    def test_generate_unit_stub(self):
        from codeframe.core.proof.stubs import generate_stubs
        from codeframe.core.proof.models import (
            Requirement, Gate, Severity, Source, RequirementScope, Obligation,
        )

        req = Requirement(
            id="REQ-0001", title="Login rejects empty password",
            description="Empty passwords should fail validation",
            severity=Severity.HIGH, source=Source.QA,
            scope=RequirementScope(), obligations=[Obligation(gate=Gate.UNIT)],
            evidence_rules=[],
        )
        stubs = generate_stubs(req)
        assert Gate.UNIT in stubs
        assert "REQ-0001" in stubs[Gate.UNIT]
        assert "def test_" in stubs[Gate.UNIT]

    def test_generate_multiple_stubs(self):
        from codeframe.core.proof.stubs import generate_stubs
        from codeframe.core.proof.models import (
            Requirement, Gate, Severity, Source, RequirementScope, Obligation,
        )

        req = Requirement(
            id="REQ-0001", title="Test",
            description="Description",
            severity=Severity.HIGH, source=Source.QA,
            scope=RequirementScope(),
            obligations=[Obligation(gate=Gate.UNIT), Obligation(gate=Gate.E2E)],
            evidence_rules=[],
        )
        stubs = generate_stubs(req)
        assert Gate.UNIT in stubs
        assert Gate.E2E in stubs


# --- Capture Tests ---


class TestCapture:
    def test_capture_requirement(self, workspace):
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.models import Severity, Source
        from codeframe.core.proof import ledger

        req, stubs = capture_requirement(
            workspace,
            title="Login rejects empty password",
            description="Empty passwords crash the auth handler with exception",
            where="src/auth/login.py",
            severity=Severity.HIGH,
            source=Source.QA,
        )

        assert req.id == "REQ-0001"
        assert req.glitch_type is not None
        assert len(req.obligations) > 0
        assert len(stubs) > 0

        # Verify persisted
        loaded = ledger.get_requirement(workspace, "REQ-0001")
        assert loaded is not None
        assert loaded.title == "Login rejects empty password"

    def test_capture_sequential_ids(self, workspace):
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.models import Severity, Source

        req1, _ = capture_requirement(
            workspace, title="First", description="First bug",
            where="src/a.py", severity=Severity.LOW, source=Source.QA,
        )
        req2, _ = capture_requirement(
            workspace, title="Second", description="Second bug",
            where="src/b.py", severity=Severity.LOW, source=Source.QA,
        )
        assert req1.id == "REQ-0001"
        assert req2.id == "REQ-0002"


# --- Runner Tests ---


class TestRunner:
    @patch("codeframe.core.proof.runner._run_gate")
    def test_run_proof_full(self, mock_run_gate, workspace):
        from codeframe.core.proof.runner import run_proof
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.models import Severity, Source

        # Capture a requirement first
        capture_requirement(
            workspace, title="Test bug", description="Logic error in calculation",
            where="src/calc.py", severity=Severity.MEDIUM, source=Source.QA,
        )

        mock_run_gate.return_value = (True, "All tests passed")

        results = run_proof(workspace, full=True)
        assert len(results) == 1
        req_id = list(results.keys())[0]
        assert all(passed for _, passed in results[req_id])

    @patch("codeframe.core.proof.runner._run_gate")
    def test_run_proof_with_failure(self, mock_run_gate, workspace):
        from codeframe.core.proof.runner import run_proof
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.models import Severity, Source

        capture_requirement(
            workspace, title="Test bug", description="Logic error",
            where="src/calc.py", severity=Severity.MEDIUM, source=Source.QA,
        )

        mock_run_gate.return_value = (False, "Tests failed")

        results = run_proof(workspace, full=True)
        assert len(results) == 1
        req_id = list(results.keys())[0]
        assert not all(passed for _, passed in results[req_id])


# --- CLI Tests ---


class TestCLI:
    def test_proof_help(self):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["proof", "--help"])
        assert result.exit_code == 0
        assert "proof" in result.output.lower()

    def test_proof_status_empty(self, workspace, tmp_path):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["proof", "status", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "No proof requirements" in result.output

    def test_proof_list_empty(self, workspace, tmp_path):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, ["proof", "list", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "No requirements found" in result.output

    def test_proof_capture_with_args(self, workspace, tmp_path):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        result = runner.invoke(app, [
            "proof", "capture", "-w", str(tmp_path),
            "--title", "Test bug",
            "--description", "Something went wrong with the logic",
            "--where", "src/test.py",
            "--severity", "medium",
            "--source", "qa",
        ])
        assert result.exit_code == 0
        assert "REQ-0001" in result.output

    def test_proof_show(self, workspace, tmp_path):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        # Capture first
        runner.invoke(app, [
            "proof", "capture", "-w", str(tmp_path),
            "--title", "Test bug",
            "--description", "Logic error in auth",
            "--where", "src/auth.py",
            "--severity", "high",
            "--source", "qa",
        ])
        # Show it
        result = runner.invoke(app, ["proof", "show", "REQ-0001", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "REQ-0001" in result.output
        assert "Test bug" in result.output

    def test_proof_status_with_reqs(self, workspace, tmp_path):
        from typer.testing import CliRunner
        from codeframe.cli.app import app

        runner = CliRunner()
        runner.invoke(app, [
            "proof", "capture", "-w", str(tmp_path),
            "--title", "Bug 1",
            "--description", "Error in logic",
            "--where", "src/a.py",
            "--severity", "medium",
            "--source", "qa",
        ])

        result = runner.invoke(app, ["proof", "status", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "1" in result.output  # 1 requirement
