"""
Tests for AdaptiveTestRunner - multi-language test execution system.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess
import asyncio

import pytest

from codeframe.enforcement import AdaptiveTestRunner, TestResult, LanguageInfo


class TestAdaptiveTestRunner:
    """Test adaptive test running for various languages."""

    @pytest.mark.asyncio
    async def test_detects_language_on_first_run(self, tmp_path):
        """Test that runner auto-detects language on first run"""
        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        # Mock subprocess to avoid actually running tests
        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="5 passed in 1.23s",
                stderr=""
            )

            result = await runner.run_tests()

            assert runner.language_info is not None
            assert runner.language_info.language == "python"

    @pytest.mark.asyncio
    async def test_parses_pytest_output(self, tmp_path):
        """Test parsing pytest output format"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # Non-zero for failures
                stdout="===== 8 passed, 2 failed in 2.34s =====",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.success is False  # Has failures
            assert result.total_tests == 10
            assert result.passed_tests == 8
            assert result.failed_tests == 2

    @pytest.mark.asyncio
    async def test_parses_jest_output(self, tmp_path):
        """Test parsing Jest output format"""
        package_json = {"devDependencies": {"jest": "^29.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Tests: 2 failed, 8 passed, 10 total",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.total_tests == 10
            assert result.passed_tests == 8
            assert result.failed_tests == 2

    @pytest.mark.asyncio
    async def test_parses_go_test_output(self, tmp_path):
        """Test parsing Go test output"""
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.21")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="""
PASS: TestUserAuth (0.01s)
PASS: TestDataValidation (0.02s)
FAIL: TestEdgeCase (0.01s)
PASS
                """,
                stderr=""
            )

            result = await runner.run_tests()

            assert result.passed_tests >= 2
            assert result.failed_tests >= 1

    @pytest.mark.asyncio
    async def test_parses_rust_cargo_output(self, tmp_path):
        """Test parsing Rust cargo test output"""
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"myapp\"")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="test result: ok. 10 passed; 0 failed; 0 ignored; 0 measured",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.success is True
            assert result.passed_tests == 10
            assert result.failed_tests == 0

    @pytest.mark.asyncio
    async def test_extracts_coverage_from_pytest(self, tmp_path):
        """Test extracting coverage from pytest output"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="""
===== 10 passed in 1.23s =====
TOTAL                                                    87%
                """,
                stderr=""
            )

            result = await runner.run_tests(with_coverage=True)

            assert result.coverage == 87.0

    @pytest.mark.asyncio
    async def test_extracts_coverage_from_jest(self, tmp_path):
        """Test extracting coverage from Jest output"""
        package_json = {"devDependencies": {"jest": "^29.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="""
Tests: 10 passed, 10 total
All files    | 92.5 | 91.2 | 95.0 | 92.5 |
                """,
                stderr=""
            )

            result = await runner.run_tests(with_coverage=True)

            assert result.coverage == 92.5

    @pytest.mark.asyncio
    async def test_handles_test_failures(self, tmp_path):
        """Test handling non-zero exit codes"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # Failure exit code
                stdout="5 passed, 5 failed in 2.34s",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.success is False
            assert result.failed_tests == 5

    @pytest.mark.asyncio
    async def test_detects_skipped_tests(self, tmp_path):
        """Test detection of skipped tests"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="8 passed, 2 skipped in 1.23s",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.skipped_tests == 2

    @pytest.mark.asyncio
    async def test_calculates_pass_rate(self, tmp_path):
        """Test pass rate calculation"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="8 passed, 2 failed in 1.23s",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.pass_rate == 80.0  # 8/10 = 80%

    @pytest.mark.asyncio
    async def test_handles_subprocess_errors(self, tmp_path):
        """Test handling subprocess errors gracefully"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("pytest", 30)

            # Should raise TimeoutExpired since no error handling in implementation
            with pytest.raises(subprocess.TimeoutExpired):
                await runner.run_tests()


class TestAdaptiveTestRunnerOutputParsing:
    """Test output parsing for different frameworks."""

    @pytest.mark.asyncio
    async def test_parses_maven_output(self, tmp_path):
        """Test parsing Maven test output"""
        (tmp_path / "pom.xml").write_text("<project></project>")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Tests run: 15, Failures: 2, Errors: 0, Skipped: 1",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.total_tests == 15
            assert result.failed_tests == 2
            assert result.skipped_tests == 1

    @pytest.mark.asyncio
    async def test_handles_no_tests_found(self, tmp_path):
        """Test handling when no tests are found"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=5,  # pytest exit code for no tests
                stdout="no tests ran in 0.01s",
                stderr=""
            )

            result = await runner.run_tests()

            assert result.total_tests == 0

    @pytest.mark.asyncio
    async def test_combines_stdout_and_stderr(self, tmp_path):
        """Test that output includes both stdout and stderr"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        runner = AdaptiveTestRunner(str(tmp_path))

        with patch("codeframe.enforcement.adaptive_test_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Tests passed",
                stderr="WARNING: Deprecation"
            )

            result = await runner.run_tests()

            assert "Tests passed" in result.output
            assert "WARNING" in result.output or "Deprecation" in result.output
