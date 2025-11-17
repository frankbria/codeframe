"""Integration tests for linting workflows (T097-T099)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from codeframe.testing.lint_runner import LintRunner


# T097: Python linting workflow (detect → ruff → block/pass)
@pytest.mark.asyncio
async def test_python_linting_workflow(tmp_path):
    """Test complete Python linting workflow from detection to blocking/passing."""
    # Create a Python file with lint errors
    python_file = tmp_path / "test.py"
    python_file.write_text(
        """
import os  # F401: unused import
import sys  # F401: unused import

def hello():
    x = 1  # F841: unused variable
    print("Hello, World!")
"""
    )

    runner = LintRunner(tmp_path)

    # Mock ruff execution to return known errors
    mock_output = json.dumps(
        [
            {"code": "F401", "message": "unused import 'os'"},
            {"code": "F401", "message": "unused import 'sys'"},
            {"code": "F841", "message": "unused variable 'x'"},
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 1  # ruff returns non-zero on errors
        mock_exec.return_value = mock_process

        # Run lint on Python file
        results = await runner.run_lint([python_file])

        # Should detect Python and run ruff
        assert len(results) == 1
        assert results[0].linter == "ruff"
        assert results[0].error_count == 3  # All F-codes are critical

        # Quality gate should block
        assert runner.has_critical_errors(results) is True


# T098: TypeScript linting workflow (detect → eslint → block/pass)
@pytest.mark.asyncio
async def test_typescript_linting_workflow(tmp_path):
    """Test complete TypeScript linting workflow from detection to blocking/passing."""
    # Create a TypeScript file with lint errors
    ts_file = tmp_path / "test.ts"
    ts_file.write_text(
        """
const x = 1;  // no-unused-vars: unused variable
const y = 2;  // no-unused-vars: unused variable

function hello() {
    console.log("Hello")  // semi: missing semicolon
}
"""
    )

    runner = LintRunner(tmp_path)

    # Mock eslint execution to return known errors
    mock_output = json.dumps(
        [
            {
                "ruleId": "no-unused-vars",
                "severity": 2,
                "message": "unused variable 'x'",
                "line": 2,
            },
            {
                "ruleId": "no-unused-vars",
                "severity": 2,
                "message": "unused variable 'y'",
                "line": 3,
            },
            {"ruleId": "semi", "severity": 1, "message": "missing semicolon", "line": 6},
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 1  # eslint returns non-zero on errors
        mock_exec.return_value = mock_process

        # Run lint on TypeScript file
        results = await runner.run_lint([ts_file])

        # Should detect TypeScript and run eslint
        assert len(results) == 1
        assert results[0].linter == "eslint"
        assert results[0].error_count == 2  # Severity 2
        assert results[0].warning_count == 1  # Severity 1

        # Quality gate should block (has errors)
        assert runner.has_critical_errors(results) is True


# T099: Parallel linting (ruff + eslint concurrently)
@pytest.mark.asyncio
async def test_parallel_linting_workflow(tmp_path):
    """Test that ruff and eslint run concurrently for mixed codebases."""
    # Create both Python and TypeScript files
    python_file = tmp_path / "backend.py"
    python_file.write_text(
        """
def calculate():
    result = 42
    return result
"""
    )

    ts_file = tmp_path / "frontend.ts"
    ts_file.write_text(
        """
function calculate(): number {
    const result = 42;
    return result;
}
"""
    )

    runner = LintRunner(tmp_path)

    # Mock both linters (simplified - focus on functionality not timing)
    ruff_output = json.dumps([])  # Clean Python code
    eslint_output = json.dumps([])  # Clean TypeScript code

    async def mock_exec_side_effect(*args, **kwargs):
        mock_process = AsyncMock()
        if args[0] == "ruff":
            mock_process.communicate.return_value = (ruff_output.encode(), b"")
        elif args[0] == "eslint":
            mock_process.communicate.return_value = (eslint_output.encode(), b"")
        mock_process.returncode = 0
        return mock_process

    with patch("asyncio.create_subprocess_exec", side_effect=mock_exec_side_effect):
        # Run lint on both files
        files = [python_file, ts_file]
        results = await runner.run_lint(files)

        # Should return results from both linters
        assert len(results) == 2
        linters = {r.linter for r in results}
        assert "ruff" in linters
        assert "eslint" in linters

        # Both should pass (no errors)
        assert not runner.has_critical_errors(results)

        # Verify both linters processed their files
        ruff_result = next(r for r in results if r.linter == "ruff")
        eslint_result = next(r for r in results if r.linter == "eslint")

        assert ruff_result.files_linted == 1
        assert eslint_result.files_linted == 1


@pytest.mark.asyncio
async def test_lint_workflow_with_warnings_only(tmp_path):
    """Test that warnings don't block the workflow."""
    python_file = tmp_path / "test.py"
    python_file.write_text("print('hello')  # Some code")

    runner = LintRunner(tmp_path)

    # Mock ruff to return only warnings
    mock_output = json.dumps(
        [
            {"code": "W291", "message": "trailing whitespace"},
            {"code": "W292", "message": "no newline at end of file"},
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 0  # ruff returns 0 for warnings only
        mock_exec.return_value = mock_process

        results = await runner.run_lint([python_file])

        # Should have warnings but no errors
        assert results[0].error_count == 0
        assert results[0].warning_count == 2

        # Quality gate should NOT block
        assert runner.has_critical_errors(results) is False


@pytest.mark.asyncio
async def test_lint_workflow_with_mixed_results(tmp_path):
    """Test workflow with one linter passing, one failing."""
    python_file = tmp_path / "backend.py"
    python_file.write_text("import os\n")  # Unused import

    ts_file = tmp_path / "frontend.ts"
    ts_file.write_text("const x = 1;\n")  # Clean code

    runner = LintRunner(tmp_path)

    # Mock ruff with errors, eslint clean
    ruff_output = json.dumps([{"code": "F401", "message": "unused import"}])
    eslint_output = json.dumps([])

    async def mock_exec_side_effect(*args, **kwargs):
        mock_process = AsyncMock()
        if args[0] == "ruff":
            mock_process.communicate.return_value = (ruff_output.encode(), b"")
            mock_process.returncode = 1
        elif args[0] == "eslint":
            mock_process.communicate.return_value = (eslint_output.encode(), b"")
            mock_process.returncode = 0
        return mock_process

    with patch("asyncio.create_subprocess_exec", side_effect=mock_exec_side_effect):
        results = await runner.run_lint([python_file, ts_file])

        # Should have both results
        assert len(results) == 2

        # Ruff should have errors, eslint should be clean
        ruff_result = next(r for r in results if r.linter == "ruff")
        eslint_result = next(r for r in results if r.linter == "eslint")

        assert ruff_result.error_count > 0
        assert eslint_result.error_count == 0

        # Quality gate should block (ruff has errors)
        assert runner.has_critical_errors(results) is True
