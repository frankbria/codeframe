"""Tool installation manager for CodeFRAME.

This module provides:
- Platform-specific tool installation
- Installation verification
- Installation history tracking
- Rollback capabilities

Usage:
    from codeframe.core.installer import ToolInstaller

    installer = ToolInstaller()
    if installer.can_install("pytest"):
        result = installer.install_tool("pytest", confirm=True)
        if result.success:
            print(f"Installed {result.tool_name}")
"""

import json
import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================


def get_platform() -> str:
    """Get the current platform.

    Returns:
        'linux', 'darwin', or 'windows'
    """
    system = platform.system()
    if system == "Linux":
        return "linux"
    elif system == "Darwin":
        return "darwin"
    elif system == "Windows":
        return "windows"
    logger.warning(f"Unknown platform '{system}', defaulting to 'linux'")
    return "linux"


# =============================================================================
# Enums and Data Classes
# =============================================================================


class InstallStatus(str, Enum):
    """Status of an installation attempt."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass
class InstallResult:
    """Result of an installation attempt."""

    tool_name: str
    status: InstallStatus
    message: str
    command_used: Optional[str] = None
    error_output: Optional[str] = None
    installed_version: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if installation was successful or skipped."""
        return self.status in (InstallStatus.SUCCESS, InstallStatus.SKIPPED)


# =============================================================================
# Sub-Installers
# =============================================================================


class PipInstaller:
    """Installer for Python packages via pip/uv."""

    SUPPORTED_TOOLS = {
        "pytest",
        "ruff",
        "mypy",
        "black",
        "flake8",
        "pylint",
        "isort",
        "bandit",
        "coverage",
        "pre-commit",
        "httpx",
        "requests",
    }

    def can_install(self, tool_name: str) -> bool:
        """Check if this installer can install the tool."""
        return tool_name in self.SUPPORTED_TOOLS

    def get_install_command(self, tool_name: str) -> str:
        """Get the install command for a tool (display string).

        Prefers uv if available, falls back to pip.
        """
        if shutil.which("uv"):
            return f"uv pip install {tool_name}"
        return f"pip install {tool_name}"

    def _get_install_cmd_parts(self, tool_name: str) -> list[str]:
        """Get the install command as a list of arguments.

        Args:
            tool_name: Name of the package to install

        Returns:
            List of command arguments for subprocess
        """
        if shutil.which("uv"):
            return ["uv", "pip", "install", tool_name]
        return ["pip", "install", tool_name]

    def install_tool(
        self,
        tool_name: str,
        confirm: bool = True,
        force: bool = False,
    ) -> InstallResult:
        """Install a Python package.

        Args:
            tool_name: Name of the package to install
            confirm: Whether to prompt for confirmation
            force: Reinstall even if already installed

        Returns:
            InstallResult with status and details
        """
        # Check if already installed
        if not force and shutil.which(tool_name):
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.SKIPPED,
                message=f"{tool_name} is already installed",
            )

        command = self.get_install_command(tool_name)
        cmd_parts = self._get_install_cmd_parts(tool_name)

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode == 0:
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.SUCCESS,
                    message=f"Successfully installed {tool_name}",
                    command_used=command,
                )
            else:
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.FAILED,
                    message=f"Failed to install {tool_name}",
                    command_used=command,
                    error_output=result.stderr,
                )

        except subprocess.TimeoutExpired:
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.FAILED,
                message=f"Installation of {tool_name} timed out",
                command_used=command,
            )
        except Exception as e:
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.FAILED,
                message=f"Installation error: {e}",
                command_used=command,
                error_output=str(e),
            )


class NpmInstaller:
    """Installer for JavaScript packages via npm."""

    SUPPORTED_TOOLS = {
        "eslint",
        "prettier",
        "jest",
        "typescript",
        "ts-node",
        "webpack",
        "vite",
        "vitest",
        "mocha",
        "chai",
    }

    def can_install(self, tool_name: str) -> bool:
        """Check if this installer can install the tool."""
        return tool_name in self.SUPPORTED_TOOLS

    def get_install_command(self, tool_name: str, global_install: bool = True) -> str:
        """Get the install command for a tool (display string).

        Args:
            tool_name: Name of the package
            global_install: Install globally (-g) or as dev dependency (-D)
        """
        if global_install:
            return f"npm install -g {tool_name}"
        return f"npm install -D {tool_name}"

    def _get_install_cmd_parts(
        self, tool_name: str, global_install: bool = True
    ) -> list[str]:
        """Get the install command as a list of arguments.

        Args:
            tool_name: Name of the package
            global_install: Install globally (-g) or as dev dependency (-D)

        Returns:
            List of command arguments for subprocess
        """
        if global_install:
            return ["npm", "install", "-g", tool_name]
        return ["npm", "install", "-D", tool_name]

    def install_tool(
        self,
        tool_name: str,
        confirm: bool = True,
        force: bool = False,
        global_install: bool = True,
    ) -> InstallResult:
        """Install a JavaScript package.

        Args:
            tool_name: Name of the package to install
            confirm: Whether to prompt for confirmation
            force: Reinstall even if already installed
            global_install: Install globally or locally

        Returns:
            InstallResult with status and details
        """
        # Check if already installed (only for global installs)
        if global_install and not force and shutil.which(tool_name):
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.SKIPPED,
                message=f"{tool_name} is already installed",
            )

        command = self.get_install_command(tool_name, global_install)
        cmd_parts = self._get_install_cmd_parts(tool_name, global_install)

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode == 0:
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.SUCCESS,
                    message=f"Successfully installed {tool_name}",
                    command_used=command,
                )
            else:
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.FAILED,
                    message=f"Failed to install {tool_name}",
                    command_used=command,
                    error_output=result.stderr,
                )

        except Exception as e:
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.FAILED,
                message=f"Installation error: {e}",
                command_used=command,
                error_output=str(e),
            )


class CargoInstaller:
    """Installer for Rust tools via cargo/rustup."""

    # Tools installed via rustup component add
    RUSTUP_COMPONENTS = {
        "clippy",
        "rustfmt",
        "rust-analyzer",
        "rust-src",
    }

    # Tools installed via cargo install
    CARGO_PACKAGES = {
        "ripgrep",
        "fd-find",
        "bat",
        "tokei",
        "cargo-edit",
        "cargo-watch",
    }

    # Mapping from package name to binary name (when different)
    BINARY_NAMES: dict[str, str] = {
        "ripgrep": "rg",
        "fd-find": "fd",
        "clippy": "cargo-clippy",
        "cargo-edit": "cargo-add",
    }

    def can_install(self, tool_name: str) -> bool:
        """Check if this installer can install the tool."""
        return tool_name in self.RUSTUP_COMPONENTS or tool_name in self.CARGO_PACKAGES

    def _get_binary_name(self, tool_name: str) -> str:
        """Get the binary name for a tool (may differ from package name)."""
        return self.BINARY_NAMES.get(tool_name, tool_name)

    def get_install_command(self, tool_name: str) -> str:
        """Get the install command for a tool (display string)."""
        if tool_name in self.RUSTUP_COMPONENTS:
            return f"rustup component add {tool_name}"
        return f"cargo install {tool_name}"

    def _get_install_cmd_parts(self, tool_name: str) -> list[str]:
        """Get the install command as a list of arguments.

        Args:
            tool_name: Name of the tool to install

        Returns:
            List of command arguments for subprocess
        """
        if tool_name in self.RUSTUP_COMPONENTS:
            return ["rustup", "component", "add", tool_name]
        return ["cargo", "install", tool_name]

    def install_tool(
        self,
        tool_name: str,
        confirm: bool = True,
        force: bool = False,
    ) -> InstallResult:
        """Install a Rust tool.

        Args:
            tool_name: Name of the tool to install
            confirm: Whether to prompt for confirmation
            force: Reinstall even if already installed

        Returns:
            InstallResult with status and details
        """
        # Check if already installed (use binary name which may differ from package)
        # Note: rust-src has no binary, skip check for it
        if not force and tool_name != "rust-src":
            binary_name = self._get_binary_name(tool_name)
            if shutil.which(binary_name):
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.SKIPPED,
                    message=f"{tool_name} is already installed",
                )

        command = self.get_install_command(tool_name)
        cmd_parts = self._get_install_cmd_parts(tool_name)

        try:
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=600,  # Cargo builds can take a while
            )

            if result.returncode == 0:
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.SUCCESS,
                    message=f"Successfully installed {tool_name}",
                    command_used=command,
                )
            else:
                return InstallResult(
                    tool_name=tool_name,
                    status=InstallStatus.FAILED,
                    message=f"Failed to install {tool_name}",
                    command_used=command,
                    error_output=result.stderr,
                )

        except Exception as e:
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.FAILED,
                message=f"Installation error: {e}",
                command_used=command,
                error_output=str(e),
            )


class SystemInstaller:
    """Installer for system packages."""

    SUPPORTED_TOOLS = {
        "git",
        "docker",
        "make",
        "curl",
        "wget",
        "jq",
        "gh",
    }

    def can_install(self, tool_name: str) -> bool:
        """Check if this installer can install the tool."""
        return tool_name in self.SUPPORTED_TOOLS

    def get_install_command(self, tool_name: str) -> str:
        """Get the install command for a tool based on platform."""
        platform = get_platform()

        if platform == "darwin":
            return f"brew install {tool_name}"
        elif platform == "windows":
            return f"choco install {tool_name}"
        else:  # linux
            return f"sudo apt install -y {tool_name}"

    def install_tool(
        self,
        tool_name: str,
        confirm: bool = True,
        force: bool = False,
    ) -> InstallResult:
        """Install a system tool.

        Note: System installations typically require elevated privileges.

        Args:
            tool_name: Name of the tool to install
            confirm: Whether to prompt for confirmation
            force: Reinstall even if already installed

        Returns:
            InstallResult with status and details
        """
        command = self.get_install_command(tool_name)

        # For system tools, we return the command but don't execute
        # automatically as it requires elevated privileges
        return InstallResult(
            tool_name=tool_name,
            status=InstallStatus.CANCELLED,
            message=f"System installation requires manual execution: {command}",
            command_used=command,
        )


# =============================================================================
# Main Tool Installer
# =============================================================================


class ToolInstaller:
    """Main installer that delegates to specialized sub-installers."""

    def __init__(self, history_dir: Optional[Path] = None):
        """Initialize the installer.

        Args:
            history_dir: Directory to store installation history
        """
        self.history_dir = history_dir or Path(".codeframe")
        self.history_file = self.history_dir / "environment.json"

        # Initialize sub-installers
        self._pip_installer = PipInstaller()
        self._npm_installer = NpmInstaller()
        self._cargo_installer = CargoInstaller()
        self._system_installer = SystemInstaller()

    def _get_installer_for_tool(self, tool_name: str):
        """Get the appropriate installer for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Sub-installer instance or None
        """
        if self._pip_installer.can_install(tool_name):
            return self._pip_installer
        if self._npm_installer.can_install(tool_name):
            return self._npm_installer
        if self._cargo_installer.can_install(tool_name):
            return self._cargo_installer
        if self._system_installer.can_install(tool_name):
            return self._system_installer
        return None

    def can_install(self, tool_name: str) -> bool:
        """Check if a tool can be installed.

        Args:
            tool_name: Name of the tool

        Returns:
            True if installation is supported
        """
        return self._get_installer_for_tool(tool_name) is not None

    def get_install_command(self, tool_name: str) -> str:
        """Get the install command for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Install command string or empty string if unsupported
        """
        installer = self._get_installer_for_tool(tool_name)
        if installer:
            return installer.get_install_command(tool_name)
        return ""

    def verify_installation(self, tool_name: str) -> bool:
        """Verify that a tool is installed.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool is available in PATH
        """
        return shutil.which(tool_name) is not None

    def install_tool(
        self,
        tool_name: str,
        confirm: bool = True,
        force: bool = False,
    ) -> InstallResult:
        """Install a tool.

        Args:
            tool_name: Name of the tool to install
            confirm: Whether to prompt for confirmation
            force: Reinstall even if already installed

        Returns:
            InstallResult with status and details
        """
        installer = self._get_installer_for_tool(tool_name)
        if not installer:
            return InstallResult(
                tool_name=tool_name,
                status=InstallStatus.FAILED,
                message=f"No installer available for {tool_name}",
            )

        result = installer.install_tool(tool_name, confirm=confirm, force=force)

        # Record in history
        if result.success:
            self.record_installation(result)

        return result

    def record_installation(self, result: InstallResult) -> None:
        """Record an installation in the history file.

        Args:
            result: Installation result to record
        """
        self.history_dir.mkdir(parents=True, exist_ok=True)

        # Load existing history
        history = {"installations": {}}
        if self.history_file.exists():
            try:
                with open(self.history_file) as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                pass

        # Add new entry
        history["installations"][result.tool_name] = {
            "status": result.status.value,
            "installed_at": datetime.now(UTC).isoformat(),
            "command": result.command_used,
            "message": result.message,
        }

        # Save history
        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2)

    def get_installation_history(self) -> dict:
        """Get the installation history.

        Returns:
            Dictionary of tool installations
        """
        if not self.history_file.exists():
            return {}

        try:
            with open(self.history_file) as f:
                data = json.load(f)
            return data.get("installations", {})
        except (json.JSONDecodeError, IOError):
            return {}

    def clear_installation_history(self) -> None:
        """Clear the installation history."""
        if self.history_file.exists():
            with open(self.history_file, "w") as f:
                json.dump({"installations": {}}, f)
