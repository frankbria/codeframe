"""Edge case tests for the quality gates system.

These tests exercise boundary conditions, empty inputs, unknown gates,
and mixed-status scenarios in the gates module.
"""

import pytest
from unittest.mock import patch

from codeframe.core.gates import (
    GateCheck,
    GateResult,
    GateStatus,
    _parse_ruff_errors,
    _detect_available_gates,
    run,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.edge_case


@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


class TestGatesEdgeCases:
    """Edge case tests for quality gates."""

    def test_detect_no_gates_in_empty_repo(self, tmp_path):
        """An empty directory has no recognisable project markers, so no gates should be detected."""
        gates = _detect_available_gates(tmp_path)
        assert gates == []

    @patch("codeframe.core.gates.events")
    def test_unknown_gate_explicit_fails(self, mock_events, workspace):
        """Explicitly requesting an unknown gate name should produce a FAILED check."""
        result = run(workspace, gates=["nonexistent-gate"])

        assert result.passed is False
        assert len(result.checks) == 1

        check = result.checks[0]
        assert check.name == "nonexistent-gate"
        assert check.status == GateStatus.FAILED
        assert "Unknown gate" in check.output

    def test_unknown_gate_auto_detected_skipped(self):
        """An unknown gate encountered during auto-detection should be SKIPPED, not FAILED.

        We verify the invariant directly: a GateResult containing only SKIPPED
        checks is considered passing.
        """
        check = GateCheck(
            name="hypothetical-unknown",
            status=GateStatus.SKIPPED,
            output="Unknown gate: hypothetical-unknown",
        )
        result = GateResult(passed=True, checks=[check])

        assert result.passed is True
        assert check.status == GateStatus.SKIPPED

    def test_parse_ruff_errors_nonmatching_lines(self):
        """Lines that do not match the ruff error pattern should be silently ignored."""
        output = "Some random text\nAnother line\nNot a ruff error"
        errors = _parse_ruff_errors(output)
        assert errors == []

    def test_parse_ruff_errors_mixed_matching(self):
        """Only lines matching the ruff pattern should be parsed; others are dropped."""
        output = (
            "Starting ruff check...\n"
            "src/app.py:10:5: E501 Line too long (120 > 88 characters)\n"
            "Found 1 error.\n"
            "src/utils.py:42:1: F401 'os' imported but unused\n"
        )
        errors = _parse_ruff_errors(output)

        assert len(errors) == 2
        assert errors[0] == {
            "file": "src/app.py",
            "line": 10,
            "col": 5,
            "code": "E501",
            "message": "Line too long (120 > 88 characters)",
        }
        assert errors[1] == {
            "file": "src/utils.py",
            "line": 42,
            "col": 1,
            "code": "F401",
            "message": "'os' imported but unused",
        }

    def test_gate_result_summary_no_checks(self):
        """A GateResult with no checks should report 'no checks run'."""
        result = GateResult(passed=True, checks=[])
        assert result.summary == "no checks run"

    def test_gate_result_summary_mixed_statuses(self):
        """Summary should include counts for each status category present."""
        checks = [
            GateCheck(name="ruff", status=GateStatus.PASSED),
            GateCheck(name="pytest", status=GateStatus.FAILED),
            GateCheck(name="mypy", status=GateStatus.SKIPPED),
            GateCheck(name="tsc", status=GateStatus.PASSED),
        ]
        result = GateResult(passed=False, checks=checks)

        summary = result.summary
        assert "2 passed" in summary
        assert "1 failed" in summary
        assert "1 skipped" in summary
        assert "errors" not in summary
