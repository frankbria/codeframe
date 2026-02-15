"""Tests for gate observability enhancements."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from codeframe.core.gates import (
    GateCheck,
    GateResult,
    GateStatus,
    LinterConfig,
    LINTER_REGISTRY,
    _find_linter_for_file,
    _parse_ruff_errors,
    run_autofix_on_file,
    run_lint_on_file,
)


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


class TestRunLintOnFile:
    """Tests for the language-aware per-file lint gate."""

    def test_python_file_uses_ruff(self, tmp_path):
        """run_lint_on_file selects ruff for .py files."""
        py_file = tmp_path / "bad.py"
        py_file.write_text("import os\n")  # unused import → F401

        check = run_lint_on_file(py_file, tmp_path)
        # ruff is available in our dev env
        assert check.name == "ruff"
        assert check.status in (GateStatus.PASSED, GateStatus.FAILED)

    def test_clean_python_file_passes(self, tmp_path):
        """A lint-clean Python file produces PASSED status."""
        py_file = tmp_path / "clean.py"
        py_file.write_text("x = 1\n")

        check = run_lint_on_file(py_file, tmp_path)
        assert check.name == "ruff"
        assert check.status == GateStatus.PASSED

    def test_non_python_file_skips(self, tmp_path):
        """Non-Python files with no configured linter are SKIPPED."""
        md_file = tmp_path / "README.md"
        md_file.write_text("# Hello\n")

        check = run_lint_on_file(md_file, tmp_path)
        assert check.status == GateStatus.SKIPPED
        assert "No linter configured" in check.output

    def test_pyi_file_uses_ruff(self, tmp_path):
        """Stub files (.pyi) are linted with ruff."""
        pyi_file = tmp_path / "types.pyi"
        pyi_file.write_text("x: int\n")

        check = run_lint_on_file(pyi_file, tmp_path)
        assert check.name == "ruff"

    def test_failed_python_file_has_detailed_errors(self, tmp_path):
        """A Python file with lint errors populates detailed_errors."""
        py_file = tmp_path / "bad.py"
        py_file.write_text("import os\nimport sys\n")  # unused imports

        check = run_lint_on_file(py_file, tmp_path)
        if check.status == GateStatus.FAILED:
            assert check.detailed_errors is not None
            assert len(check.detailed_errors) >= 1
            assert check.detailed_errors[0]["code"] == "F401"

    def test_js_file_maps_to_eslint(self):
        """_find_linter_for_file maps .js to eslint."""
        cfg = _find_linter_for_file(Path("app.js"))
        assert cfg is not None
        assert cfg.name == "eslint"

    def test_ts_file_maps_to_eslint(self):
        """_find_linter_for_file maps .ts/.tsx to eslint."""
        for ext in (".ts", ".tsx", ".jsx"):
            cfg = _find_linter_for_file(Path(f"app{ext}"))
            assert cfg is not None
            assert cfg.name == "eslint"

    def test_rs_file_has_no_per_file_linter(self):
        """Rust files have no per-file linter (clippy is whole-project)."""
        cfg = _find_linter_for_file(Path("main.rs"))
        assert cfg is None

    def test_unknown_extension_returns_none(self):
        """_find_linter_for_file returns None for unsupported extensions."""
        assert _find_linter_for_file(Path("data.csv")) is None
        assert _find_linter_for_file(Path("image.png")) is None

    @patch("codeframe.core.gates.shutil.which", return_value=None)
    def test_missing_linter_binary_skips(self, mock_which, tmp_path):
        """If the linter binary is not installed, return SKIPPED."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")

        check = run_lint_on_file(py_file, tmp_path)
        assert check.status == GateStatus.SKIPPED

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_uv_run_missing_tool_returns_skipped(self, mock_which, mock_run, tmp_path):
        """When uv run fails because the linter isn't a project dependency, return SKIPPED."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")

        # ruff not on PATH but uv is → gates proceeds with 'uv run ruff'
        mock_which.side_effect = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None

        # Simulate uv failing to spawn ruff (exit code 2)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["uv", "run", "ruff", "check", str(py_file)],
            returncode=2,
            stdout="",
            stderr="error: Failed to spawn: `ruff`\nCaused by: No such file or directory (os error 2)",
        )

        check = run_lint_on_file(py_file, tmp_path)
        assert check.status == GateStatus.SKIPPED
        assert "not found" in check.output.lower()


class TestAutofixSupport:
    """Tests for autofix_cmd on LinterConfig and run_autofix_on_file."""

    def test_linter_config_has_autofix_cmd(self):
        """LinterConfig accepts an optional autofix_cmd field."""
        cfg = LinterConfig(
            name="test",
            extensions={".py"},
            cmd=["test", "{file}"],
            autofix_cmd=["test", "--fix", "{file}"],
        )
        assert cfg.autofix_cmd == ["test", "--fix", "{file}"]

    def test_linter_config_autofix_cmd_defaults_none(self):
        """autofix_cmd defaults to None when not specified."""


class TestDependencyPreFlight:
    """Tests for dependency installation pre-flight checks."""

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_python_deps_missing_auto_installs(self, mock_which, mock_run, tmp_path):
        """When requirements.txt exists but no venv, auto-install deps if enabled."""
        from codeframe.core.gates import _ensure_dependencies_installed

        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\n")

        # uv is available
        mock_which.side_effect = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None

        # Mock successful installation
        mock_run.return_value = subprocess.CompletedProcess(
            args=["uv", "pip", "install", "-r", "requirements.txt"],
            returncode=0,
            stdout="Successfully installed pytest-7.0.0",
            stderr="",
        )

        success, message = _ensure_dependencies_installed(tmp_path, auto_install=True)

        assert success is True
        assert "installed" in message.lower() or "success" in message.lower()
        mock_run.assert_called_once()

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_node_deps_missing_auto_installs(self, mock_which, mock_run, tmp_path):
        """When package.json exists but no node_modules, auto-install deps."""
        from codeframe.core.gates import _ensure_dependencies_installed

        # Create package.json
        (tmp_path / "package.json").write_text('{"name": "test", "dependencies": {"jest": "^29.0.0"}}')

        # npm is available
        mock_which.side_effect = lambda cmd: "/usr/bin/npm" if cmd == "npm" else None

        # Mock successful installation
        mock_run.return_value = subprocess.CompletedProcess(
            args=["npm", "install"],
            returncode=0,
            stdout="added 100 packages",
            stderr="",
        )

        success, message = _ensure_dependencies_installed(tmp_path, auto_install=True)

        assert success is True
        mock_run.assert_called_once()

    def test_venv_exists_skips_python_install(self, tmp_path):
        """When .venv exists, skip Python dependency installation."""
        from codeframe.core.gates import _ensure_dependencies_installed

        # Create requirements.txt and .venv directory
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\n")
        (tmp_path / ".venv").mkdir()

        success, message = _ensure_dependencies_installed(tmp_path, auto_install=True)

        assert success is True
        assert "skip" in message.lower() or "already" in message.lower()

    def test_node_modules_exists_skips_npm_install(self, tmp_path):
        """When node_modules exists, skip npm install."""
        from codeframe.core.gates import _ensure_dependencies_installed

        # Create package.json and node_modules directory
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "node_modules").mkdir()

        success, message = _ensure_dependencies_installed(tmp_path, auto_install=True)

        assert success is True

    def test_auto_install_disabled_skips_installation(self, tmp_path):
        """When auto_install=False, skip installation and return skip message."""
        from codeframe.core.gates import _ensure_dependencies_installed

        # Create requirements.txt without venv
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\n")

        success, message = _ensure_dependencies_installed(tmp_path, auto_install=False)

        assert success is True
        assert "disabled" in message.lower() or "skip" in message.lower()

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_installation_failure_returns_false(self, mock_which, mock_run, tmp_path):
        """When dependency installation fails, return (False, error_message)."""
        from codeframe.core.gates import _ensure_dependencies_installed

        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("nonexistent-package==99.99.99\n")

        # uv is available
        mock_which.side_effect = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None

        # Mock failed installation
        mock_run.return_value = subprocess.CompletedProcess(
            args=["uv", "pip", "install", "-r", "requirements.txt"],
            returncode=1,
            stdout="",
            stderr="ERROR: Could not find a version that satisfies the requirement",
        )

        success, message = _ensure_dependencies_installed(tmp_path, auto_install=True)

        assert success is False
        assert "error" in message.lower() or "fail" in message.lower()


class TestTypeScriptTypeCheckGate:
    """Tests for TypeScript type-check gate (tsc)."""

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_tsc_gate_runs_type_check_script(self, mock_which, mock_run, tmp_path):
        """When package.json has type-check script, use it instead of tsc directly."""
        from codeframe.core.gates import _run_tsc

        # Create tsconfig.json and package.json with type-check script
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
        (tmp_path / "package.json").write_text('{"scripts": {"type-check": "tsc --noEmit"}}')

        # npm is available
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock successful type check
        mock_run.return_value = subprocess.CompletedProcess(
            args=["npm", "run", "type-check"],
            returncode=0,
            stdout="",
            stderr="",
        )

        check = _run_tsc(tmp_path, verbose=False)

        assert check.name == "tsc"
        assert check.status == GateStatus.PASSED
        # Verify it used npm run type-check, not npx tsc
        mock_run.assert_called_once()
        assert "npm" in mock_run.call_args[0][0]

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_tsc_gate_fallback_to_npx(self, mock_which, mock_run, tmp_path):
        """When no type-check script, fallback to npx tsc --noEmit."""
        from codeframe.core.gates import _run_tsc

        # Create tsconfig.json without type-check script
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        (tmp_path / "package.json").write_text('{"name": "test"}')

        # npx is available
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock successful type check
        mock_run.return_value = subprocess.CompletedProcess(
            args=["npx", "tsc", "--noEmit"],
            returncode=0,
            stdout="",
            stderr="",
        )

        check = _run_tsc(tmp_path, verbose=False)

        assert check.status == GateStatus.PASSED
        # Verify it used npx tsc --noEmit
        assert "npx" in mock_run.call_args[0][0]
        assert "--noEmit" in mock_run.call_args[0][0]

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_tsc_gate_detects_type_errors(self, mock_which, mock_run, tmp_path):
        """Type errors from tsc should return FAILED status with structured errors."""
        from codeframe.core.gates import _run_tsc

        (tmp_path / "tsconfig.json").write_text('{}')

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock type error output
        mock_run.return_value = subprocess.CompletedProcess(
            args=["npx", "tsc", "--noEmit"],
            returncode=2,
            stdout=(
                "src/api.ts(15,10): error TS2339: Property 'completed' does not exist on type 'CreateTodoRequest'.\n"
                "src/api.ts(20,5): error TS2322: Type 'string' is not assignable to type 'number'.\n"
            ),
            stderr="",
        )

        check = _run_tsc(tmp_path, verbose=False)

        assert check.status == GateStatus.FAILED
        assert check.exit_code == 2
        assert "TS2339" in check.output
        # Check for structured errors
        assert check.detailed_errors is not None
        assert len(check.detailed_errors) == 2
        assert check.detailed_errors[0]["code"] == "TS2339"
        assert check.detailed_errors[0]["file"] == "src/api.ts"
        assert check.detailed_errors[0]["line"] == 15

    def test_tsc_gate_skipped_no_tsconfig(self, tmp_path):
        """Without tsconfig.json, tsc gate is SKIPPED."""
        from codeframe.core.gates import _run_tsc

        check = _run_tsc(tmp_path, verbose=False)

        assert check.status == GateStatus.SKIPPED
        assert "tsconfig.json" in check.output.lower()

    @patch("codeframe.core.gates.shutil.which", return_value=None)
    def test_tsc_gate_skipped_no_npx(self, mock_which, tmp_path):
        """Without npx available, tsc gate is SKIPPED."""
        from codeframe.core.gates import _run_tsc

        (tmp_path / "tsconfig.json").write_text('{}')

        check = _run_tsc(tmp_path, verbose=False)

        assert check.status == GateStatus.SKIPPED
        assert "npx" in check.output.lower()

    def test_tsc_gate_auto_detected(self, tmp_path):
        """tsc gate is auto-detected when tsconfig.json exists."""
        from codeframe.core.gates import _detect_available_gates

        (tmp_path / "tsconfig.json").write_text('{}')

        gates = _detect_available_gates(tmp_path)

        assert "tsc" in gates


class TestPytestGateHardening:
    """Tests for hardened pytest gate with collection error detection."""

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_pytest_collection_error_fails_gate(self, mock_which, mock_run, tmp_path):
        """pytest collection errors (exit code 2/3/4) should FAIL the gate."""
        from codeframe.core.gates import _run_pytest

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock collection error (exit code 4 = usage error, often import issues)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "-v", "--tb=short"],
            returncode=4,
            stdout=(
                "ERROR: not found: /path/to/tests/test_api.py::test_init_db\n"
                "ERROR: file or directory not found: tests/test_api.py\n"
            ),
            stderr="ERROR collecting tests/test_api.py",
        )

        check = _run_pytest(tmp_path, verbose=False)

        assert check.status == GateStatus.FAILED
        assert check.exit_code == 4
        assert "ERROR" in check.output

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_pytest_import_error_during_collection_fails(self, mock_which, mock_run, tmp_path):
        """ImportError during collection (exit code 2) should FAIL the gate."""
        from codeframe.core.gates import _run_pytest

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock import error during collection
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "-v", "--tb=short"],
            returncode=2,
            stdout=(
                "ImportError while importing test module 'tests/test_db.py'.\n"
                "ERROR: ModuleNotFoundError: No module named 'sqlalchemy'\n"
            ),
            stderr="",
        )

        check = _run_pytest(tmp_path, verbose=False)

        assert check.status == GateStatus.FAILED
        assert "ImportError" in check.output or "ModuleNotFoundError" in check.output

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_pytest_no_tests_collected_passes(self, mock_which, mock_run, tmp_path):
        """Exit code 5 with 'no tests collected' should PASS (acceptable empty suite)."""
        from codeframe.core.gates import _run_pytest

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock no tests collected (exit code 5, but clean)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "-v", "--tb=short"],
            returncode=5,
            stdout="collected 0 items\n\nno tests ran in 0.01s\n",
            stderr="",
        )

        check = _run_pytest(tmp_path, verbose=False)

        assert check.status == GateStatus.PASSED
        assert "no tests ran" in check.output.lower()

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_pytest_exit_code_5_with_error_fails(self, mock_which, mock_run, tmp_path):
        """Exit code 5 with ERROR messages should FAIL (collection error, not empty suite)."""
        from codeframe.core.gates import _run_pytest

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock exit code 5 but with collection errors
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "-v", "--tb=short"],
            returncode=5,
            stdout=(
                "ERROR collecting tests/test_api.py\n"
                "collected 0 items\n"
            ),
            stderr="ImportError: cannot import name 'app' from 'main'",
        )

        check = _run_pytest(tmp_path, verbose=False)

        assert check.status == GateStatus.FAILED
        assert "ERROR" in check.output or "ImportError" in check.output

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_pytest_exit_code_1_test_failures(self, mock_which, mock_run, tmp_path):
        """Exit code 1 (tests failed) should FAIL the gate."""
        from codeframe.core.gates import _run_pytest

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"

        # Mock test failures
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "-v", "--tb=short"],
            returncode=1,
            stdout="tests/test_api.py::test_foo FAILED\n\n1 failed, 0 passed in 0.5s\n",
            stderr="",
        )

        check = _run_pytest(tmp_path, verbose=False)

        assert check.status == GateStatus.FAILED
        assert check.exit_code == 1
        cfg = LinterConfig(
            name="test",
            extensions={".py"},
            cmd=["test", "{file}"],
        )
        assert cfg.autofix_cmd is None

    def test_ruff_registry_has_autofix_cmd(self):
        """LINTER_REGISTRY ruff entry has autofix_cmd set."""
        ruff_cfg = next(c for c in LINTER_REGISTRY if c.name == "ruff")
        assert ruff_cfg.autofix_cmd is not None
        assert "ruff" in ruff_cfg.autofix_cmd
        assert "--fix" in ruff_cfg.autofix_cmd

    def test_eslint_registry_has_autofix_cmd(self):
        """LINTER_REGISTRY eslint entry has autofix_cmd set."""
        eslint_cfg = next(c for c in LINTER_REGISTRY if c.name == "eslint")
        assert eslint_cfg.autofix_cmd is not None
        assert "--fix" in eslint_cfg.autofix_cmd

    def test_run_autofix_on_file_no_linter(self, tmp_path):
        """run_autofix_on_file returns SKIPPED for files with no linter."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello\n")

        check = run_autofix_on_file(txt_file, tmp_path)
        assert check.name == "autofix"
        assert check.status == GateStatus.SKIPPED

    @patch("codeframe.core.gates._find_linter_for_file")
    def test_run_autofix_on_file_skipped_when_no_cmd(self, mock_find, tmp_path):
        """run_autofix_on_file returns SKIPPED when linter has no autofix_cmd."""
        mock_find.return_value = LinterConfig(
            name="nofixer",
            extensions={".py"},
            cmd=["nofixer", "{file}"],
            autofix_cmd=None,
        )
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")

        check = run_autofix_on_file(py_file, tmp_path)
        assert check.name == "autofix"
        assert check.status == GateStatus.SKIPPED

    @patch("codeframe.core.gates.subprocess.run")
    @patch("codeframe.core.gates.shutil.which")
    def test_run_autofix_on_python_file(self, mock_which, mock_run, tmp_path):
        """run_autofix_on_file calls ruff --fix on Python files."""
        py_file = tmp_path / "bad.py"
        py_file.write_text("import os\n")

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        mock_run.return_value = subprocess.CompletedProcess(
            args=["uv", "run", "ruff", "check", "--fix", str(py_file)],
            returncode=0,
            stdout="Fixed 1 error.\n",
            stderr="",
        )

        check = run_autofix_on_file(py_file, tmp_path)
        assert check.name == "autofix-ruff"
        assert check.status == GateStatus.PASSED
        # Verify the command included --fix
        call_args = mock_run.call_args
        cmd_list = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert "--fix" in cmd_list

    @patch("codeframe.core.gates.shutil.which", return_value=None)
    def test_run_autofix_missing_binary_skips(self, mock_which, tmp_path):
        """run_autofix_on_file returns SKIPPED when binary is not installed."""
        py_file = tmp_path / "test.py"
        py_file.write_text("x = 1\n")

        check = run_autofix_on_file(py_file, tmp_path)
        assert check.status == GateStatus.SKIPPED
