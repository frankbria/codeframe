"""Tests for tool installation manager.

This module tests:
- Install command generation for different tools and platforms
- Installation verification
- Platform detection
- Installation history tracking
"""

import json
from unittest.mock import MagicMock, patch


from codeframe.core.installer import (
    ToolInstaller,
    InstallResult,
    InstallStatus,
    PipInstaller,
    NpmInstaller,
    CargoInstaller,
    SystemInstaller,
    get_platform,
)


# =============================================================================
# Platform Detection Tests
# =============================================================================


class TestPlatformDetection:
    """Tests for platform detection."""

    def test_get_platform_linux(self):
        """Test detecting Linux platform."""
        with patch("platform.system", return_value="Linux"):
            assert get_platform() == "linux"

    def test_get_platform_macos(self):
        """Test detecting macOS platform."""
        with patch("platform.system", return_value="Darwin"):
            assert get_platform() == "darwin"

    def test_get_platform_windows(self):
        """Test detecting Windows platform."""
        with patch("platform.system", return_value="Windows"):
            assert get_platform() == "windows"


# =============================================================================
# InstallResult Tests
# =============================================================================


class TestInstallResult:
    """Tests for InstallResult dataclass."""

    def test_install_result_success(self):
        """Test creating a successful install result."""
        result = InstallResult(
            tool_name="pytest",
            status=InstallStatus.SUCCESS,
            message="Installation complete",
            command_used="pip install pytest",
        )
        assert result.success is True
        assert result.tool_name == "pytest"
        assert result.status == InstallStatus.SUCCESS

    def test_install_result_failure(self):
        """Test creating a failed install result."""
        result = InstallResult(
            tool_name="nonexistent",
            status=InstallStatus.FAILED,
            message="Package not found",
            command_used="pip install nonexistent",
            error_output="ERROR: Could not find package",
        )
        assert result.success is False
        assert result.status == InstallStatus.FAILED
        assert result.error_output is not None

    def test_install_result_skipped(self):
        """Test creating a skipped install result."""
        result = InstallResult(
            tool_name="pytest",
            status=InstallStatus.SKIPPED,
            message="Tool already installed",
        )
        assert result.success is True  # Skipped is still a success
        assert result.status == InstallStatus.SKIPPED


# =============================================================================
# ToolInstaller Base Tests
# =============================================================================


class TestToolInstaller:
    """Tests for base ToolInstaller class."""

    def test_can_install_known_tool(self):
        """Test checking if a known tool can be installed."""
        installer = ToolInstaller()
        # Should delegate to appropriate sub-installer
        with patch.object(installer, "_get_installer_for_tool") as mock:
            mock_sub = MagicMock()
            mock_sub.can_install.return_value = True
            mock.return_value = mock_sub

            assert installer.can_install("pytest") is True

    def test_can_install_unknown_tool(self):
        """Test checking if an unknown tool can be installed."""
        installer = ToolInstaller()
        with patch.object(installer, "_get_installer_for_tool", return_value=None):
            assert installer.can_install("unknown_xyz_tool") is False

    def test_get_install_command_pip_tool(self):
        """Test getting install command for pip-based tool."""
        installer = ToolInstaller()
        cmd = installer.get_install_command("pytest")
        assert "pip" in cmd or "uv" in cmd
        assert "pytest" in cmd

    def test_verify_installation_success(self):
        """Test verifying successful installation."""
        installer = ToolInstaller()
        with patch("shutil.which", return_value="/usr/bin/pytest"):
            assert installer.verify_installation("pytest") is True

    def test_verify_installation_failure(self):
        """Test verifying failed installation."""
        installer = ToolInstaller()
        with patch("shutil.which", return_value=None):
            assert installer.verify_installation("nonexistent") is False


# =============================================================================
# PipInstaller Tests
# =============================================================================


class TestPipInstaller:
    """Tests for Python pip/uv installer."""

    def test_can_install_python_tools(self):
        """Test that PipInstaller can install Python tools."""
        installer = PipInstaller()
        assert installer.can_install("pytest") is True
        assert installer.can_install("ruff") is True
        assert installer.can_install("mypy") is True
        assert installer.can_install("black") is True

    def test_cannot_install_non_python_tools(self):
        """Test that PipInstaller cannot install non-Python tools."""
        installer = PipInstaller()
        assert installer.can_install("npm") is False
        assert installer.can_install("cargo") is False
        assert installer.can_install("docker") is False

    def test_get_install_command_with_uv(self):
        """Test install command when uv is available."""
        installer = PipInstaller()
        with patch("shutil.which", return_value="/usr/bin/uv"):
            cmd = installer.get_install_command("pytest")
        assert "uv" in cmd
        assert "pytest" in cmd

    def test_get_install_command_with_pip(self):
        """Test install command when only pip is available."""
        installer = PipInstaller()
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/pip" if x == "pip" else None):
            cmd = installer.get_install_command("pytest")
        assert "pip" in cmd
        assert "pytest" in cmd

    def test_install_tool_success(self):
        """Test successful tool installation."""
        installer = PipInstaller()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed pytest-7.4.0"
        mock_result.stderr = ""

        # Mock which to return None (not installed) so installation proceeds
        with patch("shutil.which", return_value=None):
            with patch("subprocess.run", return_value=mock_result):
                result = installer.install_tool("pytest", confirm=False)

        assert result.status == InstallStatus.SUCCESS
        assert result.success is True

    def test_install_tool_failure(self):
        """Test failed tool installation."""
        installer = PipInstaller()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: Could not find package"

        with patch("subprocess.run", return_value=mock_result):
            result = installer.install_tool("nonexistent_package", confirm=False)

        assert result.status == InstallStatus.FAILED
        assert result.success is False

    def test_install_tool_already_installed(self):
        """Test installing tool that's already installed."""
        installer = PipInstaller()
        with patch("shutil.which", return_value="/usr/bin/pytest"):
            result = installer.install_tool("pytest", confirm=False, force=False)

        assert result.status == InstallStatus.SKIPPED
        assert "already installed" in result.message.lower()


# =============================================================================
# NpmInstaller Tests
# =============================================================================


class TestNpmInstaller:
    """Tests for JavaScript npm installer."""

    def test_can_install_js_tools(self):
        """Test that NpmInstaller can install JavaScript tools."""
        installer = NpmInstaller()
        assert installer.can_install("eslint") is True
        assert installer.can_install("prettier") is True
        assert installer.can_install("jest") is True

    def test_cannot_install_non_js_tools(self):
        """Test that NpmInstaller cannot install non-JavaScript tools."""
        installer = NpmInstaller()
        assert installer.can_install("pytest") is False
        assert installer.can_install("cargo") is False

    def test_get_install_command_global(self):
        """Test getting global install command."""
        installer = NpmInstaller()
        cmd = installer.get_install_command("eslint", global_install=True)
        assert "npm" in cmd
        assert "install" in cmd
        assert "-g" in cmd
        assert "eslint" in cmd

    def test_get_install_command_local(self):
        """Test getting local (dev dependency) install command."""
        installer = NpmInstaller()
        cmd = installer.get_install_command("eslint", global_install=False)
        assert "npm" in cmd
        assert "install" in cmd
        assert "-D" in cmd or "--save-dev" in cmd
        assert "eslint" in cmd


# =============================================================================
# CargoInstaller Tests
# =============================================================================


class TestCargoInstaller:
    """Tests for Rust cargo installer."""

    def test_can_install_rust_tools(self):
        """Test that CargoInstaller can install Rust tools."""
        installer = CargoInstaller()
        assert installer.can_install("clippy") is True
        assert installer.can_install("rustfmt") is True

    def test_cannot_install_non_rust_tools(self):
        """Test that CargoInstaller cannot install non-Rust tools."""
        installer = CargoInstaller()
        assert installer.can_install("pytest") is False
        assert installer.can_install("npm") is False

    def test_get_install_command_rustup_component(self):
        """Test install command for rustup component."""
        installer = CargoInstaller()
        cmd = installer.get_install_command("clippy")
        assert "rustup" in cmd
        assert "component" in cmd
        assert "add" in cmd
        assert "clippy" in cmd

    def test_get_install_command_cargo_install(self):
        """Test install command for cargo package."""
        installer = CargoInstaller()
        cmd = installer.get_install_command("ripgrep")
        assert "cargo" in cmd
        assert "install" in cmd
        assert "ripgrep" in cmd


# =============================================================================
# SystemInstaller Tests
# =============================================================================


class TestSystemInstaller:
    """Tests for system package manager installer."""

    def test_can_install_system_tools(self):
        """Test that SystemInstaller can install system tools."""
        installer = SystemInstaller()
        assert installer.can_install("git") is True
        assert installer.can_install("docker") is True
        assert installer.can_install("make") is True

    def test_get_install_command_linux(self):
        """Test install command on Linux."""
        installer = SystemInstaller()
        with patch("codeframe.core.installer.get_platform", return_value="linux"):
            cmd = installer.get_install_command("git")
        assert "apt" in cmd or "dnf" in cmd or "yum" in cmd
        assert "git" in cmd

    def test_get_install_command_macos(self):
        """Test install command on macOS."""
        installer = SystemInstaller()
        with patch("codeframe.core.installer.get_platform", return_value="darwin"):
            cmd = installer.get_install_command("git")
        assert "brew" in cmd
        assert "git" in cmd

    def test_get_install_command_windows(self):
        """Test install command on Windows."""
        installer = SystemInstaller()
        with patch("codeframe.core.installer.get_platform", return_value="windows"):
            cmd = installer.get_install_command("git")
        assert "choco" in cmd or "winget" in cmd
        assert "git" in cmd


# =============================================================================
# Installation History Tests
# =============================================================================


class TestInstallationHistory:
    """Tests for installation history tracking."""

    def test_record_installation(self, tmp_path):
        """Test recording an installation in history."""
        installer = ToolInstaller(history_dir=tmp_path)

        result = InstallResult(
            tool_name="pytest",
            status=InstallStatus.SUCCESS,
            message="Installation complete",
            command_used="pip install pytest",
        )

        installer.record_installation(result)

        history_file = tmp_path / "environment.json"
        assert history_file.exists()

        with open(history_file) as f:
            history = json.load(f)

        assert "pytest" in history["installations"]
        assert history["installations"]["pytest"]["status"] == "success"

    def test_get_installation_history(self, tmp_path):
        """Test retrieving installation history."""
        # Create history file
        history_file = tmp_path / "environment.json"
        history_data = {
            "installations": {
                "pytest": {
                    "status": "success",
                    "installed_at": "2024-01-01T12:00:00Z",
                    "command": "pip install pytest",
                }
            }
        }
        with open(history_file, "w") as f:
            json.dump(history_data, f)

        installer = ToolInstaller(history_dir=tmp_path)
        history = installer.get_installation_history()

        assert "pytest" in history
        assert history["pytest"]["status"] == "success"

    def test_clear_installation_history(self, tmp_path):
        """Test clearing installation history."""
        # Create history file
        history_file = tmp_path / "environment.json"
        history_data = {"installations": {"pytest": {"status": "success"}}}
        with open(history_file, "w") as f:
            json.dump(history_data, f)

        installer = ToolInstaller(history_dir=tmp_path)
        installer.clear_installation_history()

        history = installer.get_installation_history()
        assert len(history) == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestInstallerIntegration:
    """Integration tests for the installer workflow."""

    def test_full_installation_workflow(self, tmp_path):
        """Test the complete installation workflow."""
        installer = ToolInstaller(history_dir=tmp_path)

        # Mock subprocess to simulate successful installation
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed pytest-7.4.0"
        mock_result.stderr = ""

        def which_side_effect(cmd):
            """Mock shutil.which to handle tool and uv checks."""
            if cmd == "pytest":
                return None  # pytest not installed initially
            if cmd == "uv":
                return None  # uv not available, use pip
            return None

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", side_effect=which_side_effect):
                result = installer.install_tool("pytest", confirm=False)

        assert result.success is True

        # Check history was recorded
        history = installer.get_installation_history()
        assert "pytest" in history

    def test_batch_installation(self, tmp_path):
        """Test installing multiple tools."""
        installer = ToolInstaller(history_dir=tmp_path)

        tools = ["pytest", "ruff", "mypy"]
        results = []

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed"
        mock_result.stderr = ""

        def which_side_effect(cmd):
            """Mock shutil.which: tools not installed, uv not available."""
            if cmd in tools:
                return None  # Tool not installed
            if cmd == "uv":
                return None  # uv not available, use pip
            return None

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", side_effect=which_side_effect):
                for tool in tools:
                    result = installer.install_tool(tool, confirm=False)
                    results.append(result)

        assert all(r.success for r in results)
        assert len(results) == 3
