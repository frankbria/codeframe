"""Tests for gate observability enhancements."""

import pytest
from codeframe.core.gates import GateCheck, GateResult, GateStatus, _parse_ruff_errors


class TestParseRuffErrors:
    """Tests for ruff output parsing into structured errors."""

    def test_parse_single_error(self):
        """Parses a single ruff error line."""
        output = "src/main.py:10:5: E501 Line too long (120 > 79)"
        errors = _parse_ruff_errors(output)
        assert len(errors) == 1
        assert errors[0]["file"] == "src/main.py"
        assert errors[0]["line"] == 10
        assert errors[0]["col"] == 5
        assert errors[0]["code"] == "E501"
        assert "Line too long" in errors[0]["message"]

    def test_parse_multiple_errors(self):
        """Parses multiple ruff error lines."""
        output = (
            "src/main.py:10:5: E501 Line too long\n"
            "src/utils.py:25:1: F401 `os` imported but unused\n"
            "src/main.py:3:1: I001 Import block is un-sorted\n"
        )
        errors = _parse_ruff_errors(output)
        assert len(errors) == 3
        assert errors[1]["file"] == "src/utils.py"
        assert errors[1]["code"] == "F401"

    def test_parse_empty_output(self):
        """Returns empty list for empty output."""
        assert _parse_ruff_errors("") == []
        assert _parse_ruff_errors("All checks passed!") == []

    def test_parse_mixed_output(self):
        """Handles output with non-error lines mixed in."""
        output = (
            "Found 2 errors.\n"
            "src/main.py:10:5: E501 Line too long\n"
            "[*] 1 fixable with `ruff check --fix`.\n"
            "src/utils.py:1:1: F401 unused import\n"
        )
        errors = _parse_ruff_errors(output)
        assert len(errors) == 2

    def test_parse_multi_letter_rule_codes(self):
        """Parses ruff codes with multi-letter prefixes like ANN, PLR, SIM."""
        output = (
            "src/api.py:5:1: ANN401 Dynamically typed expressions not allowed\n"
            "src/utils.py:12:5: PLR2004 Magic value used in comparison\n"
            "src/main.py:8:1: SIM118 Use `key in dict` instead of `key in dict.keys()`\n"
            "src/config.py:3:1: UP035 `typing.Dict` is deprecated, use `dict` instead\n"
        )
        errors = _parse_ruff_errors(output)
        assert len(errors) == 4
        assert errors[0]["code"] == "ANN401"
        assert errors[1]["code"] == "PLR2004"
        assert errors[2]["code"] == "SIM118"
        assert errors[3]["code"] == "UP035"


class TestGateCheckDetailedErrors:
    """Tests for detailed_errors field on GateCheck."""

    def test_gatecheck_has_detailed_errors_field(self):
        """GateCheck has optional detailed_errors field."""
        check = GateCheck(
            name="ruff",
            status=GateStatus.FAILED,
            output="src/main.py:1:1: F401 unused",
            detailed_errors=[
                {
                    "file": "src/main.py",
                    "line": 1,
                    "col": 1,
                    "code": "F401",
                    "message": "unused",
                }
            ],
        )
        assert check.detailed_errors is not None
        assert len(check.detailed_errors) == 1

    def test_gatecheck_detailed_errors_default_none(self):
        """detailed_errors defaults to None."""
        check = GateCheck(name="ruff", status=GateStatus.PASSED)
        assert check.detailed_errors is None


class TestGateResultErrorMethods:
    """Tests for GateResult error summary and grouping methods."""

    @pytest.fixture
    def failed_gate_result(self):
        """GateResult with failed ruff check and detailed errors."""
        check = GateCheck(
            name="ruff",
            status=GateStatus.FAILED,
            exit_code=1,
            output=(
                "src/main.py:10:5: E501 Line too long\n"
                "src/utils.py:1:1: F401 unused import"
            ),
            detailed_errors=[
                {
                    "file": "src/main.py",
                    "line": 10,
                    "col": 5,
                    "code": "E501",
                    "message": "Line too long",
                },
                {
                    "file": "src/utils.py",
                    "line": 1,
                    "col": 1,
                    "code": "F401",
                    "message": "unused import",
                },
            ],
        )
        return GateResult(
            passed=False,
            checks=[check],
        )

    def test_get_error_summary(self, failed_gate_result):
        """get_error_summary returns formatted string of all errors."""
        summary = failed_gate_result.get_error_summary()
        assert "E501" in summary
        assert "F401" in summary
        assert "src/main.py" in summary

    def test_get_errors_by_file(self, failed_gate_result):
        """get_errors_by_file groups errors by file path."""
        by_file = failed_gate_result.get_errors_by_file()
        assert "src/main.py" in by_file
        assert "src/utils.py" in by_file
        assert len(by_file["src/main.py"]) == 1
        assert "E501" in by_file["src/main.py"][0]

    def test_get_error_summary_no_errors(self):
        """get_error_summary handles no errors gracefully."""
        result = GateResult(
            passed=True,
            checks=[
                GateCheck(name="ruff", status=GateStatus.PASSED),
            ],
        )
        summary = result.get_error_summary()
        assert summary == "" or "no errors" in summary.lower()

    def test_get_errors_by_file_no_errors(self):
        """get_errors_by_file returns empty dict when no errors."""
        result = GateResult(
            passed=True,
            checks=[
                GateCheck(name="ruff", status=GateStatus.PASSED),
            ],
        )
        assert result.get_errors_by_file() == {}
