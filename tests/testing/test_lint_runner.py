"""Tests for LintRunner - TDD approach (write tests first, must fail before implementation)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codeframe.core.models import LintResult
from codeframe.testing.lint_runner import LintRunner


# T085: Test ruff execution (subprocess call, JSON parsing)
@pytest.mark.asyncio
async def test_ruff_execution():
    """Test that ruff is executed correctly with proper arguments."""
    runner = LintRunner(Path("/fake/project"))

    mock_output = json.dumps(
        [
            {"code": "F401", "message": "unused import", "location": {"row": 1, "column": 0}},
            {"code": "E501", "message": "line too long", "location": {"row": 5, "column": 80}},
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        files = [Path("/fake/project/test.py")]
        result = await runner._run_ruff(files)

        # Verify subprocess called with correct args
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "ruff"
        assert args[1] == "check"
        assert "--output-format=json" in args

        # Verify result
        assert isinstance(result, LintResult)
        assert result.linter == "ruff"
        assert result.files_linted == 1


# T086: Test eslint execution (subprocess call, JSON parsing)
@pytest.mark.asyncio
async def test_eslint_execution():
    """Test that eslint is executed correctly with proper arguments."""
    runner = LintRunner(Path("/fake/project"))

    mock_output = json.dumps(
        [
            {"ruleId": "no-unused-vars", "severity": 2, "message": "unused variable", "line": 1},
            {"ruleId": "semi", "severity": 1, "message": "missing semicolon", "line": 5},
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        files = [Path("/fake/project/test.ts")]
        result = await runner._run_eslint(files)

        # Verify subprocess called with correct args
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "eslint"
        assert "--format=json" in args

        # Verify result
        assert isinstance(result, LintResult)
        assert result.linter == "eslint"
        assert result.files_linted == 1


# T087: Test ruff output parsing (JSON → LintResult)
@pytest.mark.asyncio
async def test_ruff_output_parsing():
    """Test that ruff JSON output is correctly parsed into LintResult."""
    runner = LintRunner(Path("/fake/project"))

    # Mock output with different severity levels
    mock_output = json.dumps(
        [
            {"code": "F401", "message": "unused import"},  # Critical (F prefix)
            {"code": "F811", "message": "redefinition"},  # Critical (F prefix)
            {"code": "E501", "message": "line too long"},  # Error (E prefix)
            {"code": "W291", "message": "trailing whitespace"},  # Warning (W prefix)
            {"code": "W292", "message": "no newline at end"},  # Warning (W prefix)
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        files = [Path("/fake/project/test.py")]
        result = await runner._run_ruff(files)

        # Critical (F) + Error (E) = 3 errors total
        assert result.error_count == 3
        # Warnings (W) = 2
        assert result.warning_count == 2
        assert result.files_linted == 1
        assert result.linter == "ruff"

        # Output should be stored as JSON string
        assert isinstance(result.output, str)
        parsed_output = json.loads(result.output)
        assert len(parsed_output) == 5


# T088: Test eslint output parsing (JSON → LintResult)
@pytest.mark.asyncio
async def test_eslint_output_parsing():
    """Test that eslint JSON output is correctly parsed into LintResult."""
    runner = LintRunner(Path("/fake/project"))

    # ESLint severity: 2 = error, 1 = warning
    mock_output = json.dumps(
        [
            {"ruleId": "no-unused-vars", "severity": 2, "message": "unused variable"},
            {"ruleId": "no-undef", "severity": 2, "message": "undefined variable"},
            {"ruleId": "semi", "severity": 1, "message": "missing semicolon"},
            {"ruleId": "quotes", "severity": 1, "message": "use single quotes"},
        ]
    )

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (mock_output.encode(), b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process

        files = [Path("/fake/project/test.ts")]
        result = await runner._run_eslint(files)

        # Severity 2 = errors = 2
        assert result.error_count == 2
        # Severity 1 = warnings = 2
        assert result.warning_count == 2
        assert result.files_linted == 1
        assert result.linter == "eslint"


# T089: Test quality gate blocking on critical errors
@pytest.mark.asyncio
async def test_quality_gate_blocks_critical_errors():
    """Test that quality gate blocks when critical errors are present."""
    runner = LintRunner(Path("/fake/project"))

    # Create lint results with critical errors
    results = [
        LintResult(
            linter="ruff", error_count=2, warning_count=5, files_linted=3, output="{}"  # Has errors
        ),
        LintResult(linter="eslint", error_count=0, warning_count=1, files_linted=2, output="{}"),
    ]

    # Should block because first result has errors
    assert runner.has_critical_errors(results) is True


# T090: Test quality gate allowing warnings
@pytest.mark.asyncio
async def test_quality_gate_allows_warnings():
    """Test that quality gate allows warnings without blocking."""
    runner = LintRunner(Path("/fake/project"))

    # Create lint results with only warnings (no errors)
    results = [
        LintResult(
            linter="ruff", error_count=0, warning_count=5, files_linted=3, output="{}"  # No errors
        ),
        LintResult(
            linter="eslint",
            error_count=0,  # No errors
            warning_count=2,
            files_linted=2,
            output="{}",
        ),
    ]

    # Should not block because no errors
    assert runner.has_critical_errors(results) is False


# T093: Test pyproject.toml config loading
def test_pyproject_toml_config_loading(tmp_path):
    """Test that pyproject.toml config is loaded correctly."""
    # Create a mock pyproject.toml
    config_content = """
[tool.ruff]
line-length = 100
select = ["E", "F", "W"]

[tool.ruff.lint]
ignore = ["E501"]
"""

    config_file = tmp_path / "pyproject.toml"
    config_file.write_text(config_content)

    runner = LintRunner(tmp_path)

    # Config should be loaded
    assert runner.config is not None
    assert "ruff" in runner.config or runner.config != {}


# T094: Test .eslintrc.json config loading
def test_eslintrc_config_loading(tmp_path):
    """Test that .eslintrc.json config is loaded correctly."""
    # Create a mock .eslintrc.json
    config_content = {
        "extends": ["eslint:recommended"],
        "rules": {"semi": ["error", "always"], "quotes": ["error", "single"]},
    }

    config_file = tmp_path / ".eslintrc.json"
    config_file.write_text(json.dumps(config_content))

    runner = LintRunner(tmp_path)

    # Config should be loaded
    assert runner.config is not None
    assert "eslint" in runner.config or runner.config != {}


# T095: Test linter not found graceful handling
@pytest.mark.asyncio
async def test_linter_not_found_graceful_handling():
    """Test that missing linters are handled gracefully."""
    runner = LintRunner(Path("/fake/project"))

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        # Simulate FileNotFoundError (linter not installed)
        mock_exec.side_effect = FileNotFoundError("ruff not found")

        files = [Path("/fake/project/test.py")]

        # Should not crash, should return empty result or handle gracefully
        try:
            result = await runner._run_ruff(files)
            # If it returns a result, it should indicate no files linted
            assert result.files_linted == 0 or result.error_count == 0
        except FileNotFoundError:
            # Or it might re-raise with a helpful message
            pass


# T096: Test invalid config fallback to defaults
def test_invalid_config_fallback_to_defaults(tmp_path):
    """Test that invalid config files fallback to default settings."""
    # Create an invalid pyproject.toml (malformed TOML)
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text("[[invalid toml syntax")

    runner = LintRunner(tmp_path)

    # Should fallback to default config (empty dict or default settings)
    assert runner.config is not None
    # Should not crash, config should be usable
    assert isinstance(runner.config, dict)


# Additional helper tests
def test_detect_language():
    """Test language detection from file extensions."""
    runner = LintRunner(Path("/fake/project"))

    assert runner.detect_language(Path("test.py")) == "python"
    assert runner.detect_language(Path("test.ts")) == "typescript"
    assert runner.detect_language(Path("test.tsx")) == "typescript"
    assert runner.detect_language(Path("test.js")) == "typescript"
    assert runner.detect_language(Path("test.jsx")) == "typescript"
    assert runner.detect_language(Path("test.txt")) == "unknown"


@pytest.mark.asyncio
async def test_run_lint_parallel_execution():
    """Test that run_lint executes ruff and eslint in parallel."""
    runner = LintRunner(Path("/fake/project"))

    with (
        patch.object(runner, "_run_ruff", new_callable=AsyncMock) as mock_ruff,
        patch.object(runner, "_run_eslint", new_callable=AsyncMock) as mock_eslint,
    ):

        mock_ruff.return_value = LintResult(
            linter="ruff", error_count=0, warning_count=0, files_linted=2, output="{}"
        )
        mock_eslint.return_value = LintResult(
            linter="eslint", error_count=0, warning_count=0, files_linted=1, output="{}"
        )

        files = [
            Path("/fake/project/test.py"),
            Path("/fake/project/main.py"),
            Path("/fake/project/app.ts"),
        ]

        results = await runner.run_lint(files)

        # Both linters should be called
        mock_ruff.assert_called_once()
        mock_eslint.assert_called_once()

        # Should return results from both
        assert len(results) == 2
        assert any(r.linter == "ruff" for r in results)
        assert any(r.linter == "eslint" for r in results)
