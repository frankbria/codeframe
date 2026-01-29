"""Tests for environment CLI commands.

This module tests:
- `codeframe env check` - Quick environment validation
- `codeframe env doctor` - Comprehensive health analysis
- `codeframe env install-missing` - Install specific tool
- `codeframe env auto-install` - Install all missing tools
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.env_commands import env_app
from codeframe.core.environment import (
    ToolInfo,
    ToolStatus,
    ValidationResult,
)
from codeframe.core.installer import InstallResult, InstallStatus


runner = CliRunner()


# =============================================================================
# env check Tests
# =============================================================================


class TestEnvCheck:
    """Tests for the env check command."""

    def test_check_healthy_environment(self, tmp_path):
        """Test check command with healthy environment."""
        mock_result = ValidationResult(
            project_type="python",
            detected_tools={
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
                "pip": ToolInfo("pip", "/usr/bin/pip", "23.0.0", ToolStatus.AVAILABLE),
                "git": ToolInfo("git", "/usr/bin/git", "2.39.0", ToolStatus.AVAILABLE),
            },
            missing_tools=[],
            optional_missing=[],
            health_score=1.0,
            recommendations=[],
            warnings=[],
            conflicts=[],
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_result

            with patch("codeframe.cli.env_commands.Path") as MockPath:
                MockPath.cwd.return_value = tmp_path
                result = runner.invoke(env_app, ["check"])

        assert result.exit_code == 0
        assert "healthy" in result.output.lower() or "100" in result.output

    def test_check_unhealthy_environment(self, tmp_path):
        """Test check command with missing tools."""
        mock_result = ValidationResult(
            project_type="python",
            detected_tools={
                "git": ToolInfo("git", "/usr/bin/git", "2.39.0", ToolStatus.AVAILABLE),
            },
            missing_tools=["python", "pip"],
            optional_missing=["pytest"],
            health_score=0.33,
            recommendations=["Install Python 3.8+", "Install pip"],
            warnings=["Critical tools missing"],
            conflicts=[],
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_result

            with patch("codeframe.cli.env_commands.Path") as MockPath:
                MockPath.cwd.return_value = tmp_path
                result = runner.invoke(env_app, ["check"])

        # Should indicate issues
        assert "python" in result.output.lower() or "missing" in result.output.lower()

    def test_check_with_project_path(self, tmp_path):
        """Test check command with explicit project path."""
        mock_result = ValidationResult(
            project_type="python",
            detected_tools={},
            missing_tools=[],
            optional_missing=[],
            health_score=1.0,
            recommendations=[],
            warnings=[],
            conflicts=[],
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_result

            result = runner.invoke(env_app, ["check", "--project", str(tmp_path)])

        # Should complete without error
        assert result.exit_code == 0


# =============================================================================
# env doctor Tests
# =============================================================================


class TestEnvDoctor:
    """Tests for the env doctor command."""

    def test_doctor_comprehensive_output(self, tmp_path):
        """Test doctor command shows detailed information."""
        mock_result = ValidationResult(
            project_type="python",
            detected_tools={
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
                "pytest": ToolInfo("pytest", "/usr/bin/pytest", "7.4.0", ToolStatus.AVAILABLE),
                "ruff": ToolInfo("ruff", None, None, ToolStatus.NOT_FOUND),
            },
            missing_tools=["ruff"],
            optional_missing=["mypy"],
            health_score=0.75,
            recommendations=["Install ruff: pip install ruff"],
            warnings=["Optional tool mypy not installed"],
            conflicts=[],
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_result

            with patch("codeframe.cli.env_commands.Path") as MockPath:
                MockPath.cwd.return_value = tmp_path
                result = runner.invoke(env_app, ["doctor"])

        # Exit code 1 is expected when there are missing tools
        assert result.exit_code == 1
        # Should show detailed diagnostics
        assert "python" in result.output.lower()

    def test_doctor_with_version_issues(self, tmp_path):
        """Test doctor command shows version incompatibilities."""
        mock_result = ValidationResult(
            project_type="python",
            detected_tools={
                "python": ToolInfo("python", "/usr/bin/python", "2.7.0", ToolStatus.VERSION_INCOMPATIBLE),
            },
            missing_tools=[],
            optional_missing=[],
            health_score=0.5,
            recommendations=["Upgrade Python to 3.8+"],
            warnings=["Python version 2.7 is incompatible"],
            conflicts=[],
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_result

            with patch("codeframe.cli.env_commands.Path") as MockPath:
                MockPath.cwd.return_value = tmp_path
                result = runner.invoke(env_app, ["doctor"])

        # Should mention version issue
        assert "upgrade" in result.output.lower() or "version" in result.output.lower()


# =============================================================================
# env install-missing Tests
# =============================================================================


class TestEnvInstallMissing:
    """Tests for the env install-missing command."""

    def test_install_missing_tool(self):
        """Test installing a specific missing tool."""
        mock_result = InstallResult(
            tool_name="pytest",
            status=InstallStatus.SUCCESS,
            message="Successfully installed pytest",
            command_used="pip install pytest",
        )

        with patch("codeframe.cli.env_commands.ToolInstaller") as MockInstaller:
            mock_installer = MockInstaller.return_value
            mock_installer.can_install.return_value = True
            mock_installer.install_tool.return_value = mock_result

            result = runner.invoke(env_app, ["install-missing", "pytest", "--yes"])

        assert result.exit_code == 0
        assert "success" in result.output.lower() or "installed" in result.output.lower()

    def test_install_unknown_tool(self):
        """Test attempting to install unknown tool."""
        with patch("codeframe.cli.env_commands.ToolInstaller") as MockInstaller:
            mock_installer = MockInstaller.return_value
            mock_installer.can_install.return_value = False

            result = runner.invoke(env_app, ["install-missing", "unknown_xyz"])

        assert result.exit_code != 0 or "cannot" in result.output.lower()

    def test_install_requires_confirmation(self):
        """Test that installation prompts for confirmation by default."""
        with patch("codeframe.cli.env_commands.ToolInstaller") as MockInstaller:
            mock_installer = MockInstaller.return_value
            mock_installer.can_install.return_value = True
            # Simulate user declining
            result = runner.invoke(env_app, ["install-missing", "pytest"], input="n\n")

        # Should either exit or show cancelled
        assert result.exit_code == 0 or "cancel" in result.output.lower()


# =============================================================================
# env auto-install Tests
# =============================================================================


class TestEnvAutoInstall:
    """Tests for the env auto-install command."""

    def test_auto_install_all_missing(self, tmp_path):
        """Test auto-installing all missing tools."""
        mock_validation = ValidationResult(
            project_type="python",
            detected_tools={
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
            },
            missing_tools=["pytest", "ruff"],
            optional_missing=[],
            health_score=0.5,
            recommendations=[],
            warnings=[],
            conflicts=[],
        )

        mock_install_result = InstallResult(
            tool_name="pytest",
            status=InstallStatus.SUCCESS,
            message="Installed",
            command_used="pip install pytest",
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_validation

            with patch("codeframe.cli.env_commands.ToolInstaller") as MockInstaller:
                mock_installer = MockInstaller.return_value
                mock_installer.can_install.return_value = True
                mock_installer.install_tool.return_value = mock_install_result

                with patch("codeframe.cli.env_commands.Path") as MockPath:
                    MockPath.cwd.return_value = tmp_path
                    result = runner.invoke(env_app, ["auto-install", "--yes"])

        assert result.exit_code == 0

    def test_auto_install_nothing_missing(self, tmp_path):
        """Test auto-install when nothing is missing."""
        mock_validation = ValidationResult(
            project_type="python",
            detected_tools={
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
            },
            missing_tools=[],
            optional_missing=[],
            health_score=1.0,
            recommendations=[],
            warnings=[],
            conflicts=[],
        )

        with patch("codeframe.cli.env_commands.EnvironmentValidator") as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_environment.return_value = mock_validation

            with patch("codeframe.cli.env_commands.Path") as MockPath:
                MockPath.cwd.return_value = tmp_path
                result = runner.invoke(env_app, ["auto-install", "--yes"])

        assert result.exit_code == 0
        assert "nothing" in result.output.lower() or "all" in result.output.lower()


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEnvCommandsEdgeCases:
    """Tests for edge cases and error handling."""

    def test_check_nonexistent_project(self):
        """Test check command with nonexistent project path."""
        result = runner.invoke(env_app, ["check", "--project", "/nonexistent/path/xyz"])

        # Should handle gracefully
        assert result.exit_code != 0 or "error" in result.output.lower() or "not found" in result.output.lower()

    def test_install_missing_installation_failure(self):
        """Test handling installation failure."""
        mock_result = InstallResult(
            tool_name="broken_package",
            status=InstallStatus.FAILED,
            message="Installation failed",
            error_output="Network error",
        )

        with patch("codeframe.cli.env_commands.ToolInstaller") as MockInstaller:
            mock_installer = MockInstaller.return_value
            mock_installer.can_install.return_value = True
            mock_installer.install_tool.return_value = mock_result

            result = runner.invoke(env_app, ["install-missing", "broken_package", "--yes"])

        # Should report failure
        assert "fail" in result.output.lower() or "error" in result.output.lower()
