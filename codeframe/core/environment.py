"""Environment validation and tool detection for CodeFRAME.

This module provides:
- Tool detection using shutil.which() and version checking
- Ecosystem-specific tool detectors (Python, JavaScript, Rust, Generic)
- Project type detection from manifest files
- Environment validation with health scoring
- Recommendations for missing or incompatible tools

Usage:
    from codeframe.core.environment import EnvironmentValidator

    validator = EnvironmentValidator()
    result = validator.validate_environment(Path("."))

    if not result.is_healthy:
        for rec in result.recommendations:
            print(rec)
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Constants
# =============================================================================


class ToolStatus(str, Enum):
    """Status of a detected tool."""

    AVAILABLE = "available"
    NOT_FOUND = "not_found"
    VERSION_INCOMPATIBLE = "version_incompatible"
    ERROR = "error"


# Minimum version requirements for common tools
MIN_VERSIONS: dict[str, str] = {
    "python": "3.8.0",
    "node": "16.0.0",
    "npm": "8.0.0",
    "pytest": "7.0.0",
    "ruff": "0.1.0",
    "git": "2.0.0",
    "cargo": "1.60.0",
    "rustc": "1.60.0",
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ToolInfo:
    """Information about a detected tool."""

    name: str
    path: Optional[str]
    version: Optional[str]
    status: ToolStatus

    @property
    def is_available(self) -> bool:
        """Check if tool is available and compatible."""
        return self.status == ToolStatus.AVAILABLE


@dataclass
class ValidationResult:
    """Result of environment validation."""

    project_type: str
    detected_tools: dict[str, ToolInfo]
    missing_tools: list[str]
    optional_missing: list[str]
    health_score: float
    recommendations: list[str]
    warnings: list[str]
    conflicts: list[str]

    @property
    def is_healthy(self) -> bool:
        """Check if environment is healthy (score >= 0.8)."""
        return self.health_score >= 0.8 and len(self.missing_tools) == 0

    def is_healthy_with_threshold(self, threshold: float) -> bool:
        """Check health against custom threshold."""
        return self.health_score >= threshold


# =============================================================================
# Version Utilities
# =============================================================================


def parse_version(version_str: str) -> Optional[tuple[int, ...]]:
    """Parse a version string into a tuple of integers.

    Supported formats:
    - Simple semver: "1.2.3", "1.2"
    - With 'v' prefix: "v1.2.3"
    - With tool name prefix: "Python 3.11.4", "pytest 7.4.0", "node v18.12.0"
    - With pre-release suffix: "1.2.3-rc1", "1.2.3-alpha.1"
    - With post-release suffix: "7.4.0.post1"
    - Git versions: "git version 2.39.0"

    Limitations (not fully supported):
    - Build metadata is ignored: "1.2.3+build.456" -> (1, 2, 3)
    - Pre-release ordering not considered: "1.2.3-alpha" == "1.2.3-beta" == "1.2.3"
    - Only first 3 version components used: "1.2.3.4" -> (1, 2, 3)

    Args:
        version_str: Version string to parse

    Returns:
        Tuple of (major, minor, patch) or None if parsing fails
    """
    if not version_str:
        return None

    # Remove common prefixes
    cleaned = version_str.strip()

    # Extract version-like pattern from the string
    # Match patterns like: 1.2.3, v1.2.3, 1.2
    pattern = r"(\d+)\.(\d+)(?:\.(\d+))?"
    match = re.search(pattern, cleaned)

    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0

    return (major, minor, patch)


def compare_versions(version1: str, version2: str) -> int:
    """Compare two version strings.

    Args:
        version1: First version string
        version2: Second version string

    Returns:
        -1 if version1 < version2
         0 if version1 == version2
         1 if version1 > version2
    """
    v1 = parse_version(version1)
    v2 = parse_version(version2)

    if v1 is None or v2 is None:
        return 0  # Can't compare, assume equal

    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    return 0


# =============================================================================
# Tool Detector Classes
# =============================================================================


class ToolDetector:
    """Base class for detecting tools in the environment."""

    # Tools this detector handles
    supported_tools: list[str] = []

    # Version command arguments by tool
    version_args: dict[str, list[str]] = {
        "default": ["--version"],
    }

    def detect_tool(self, tool_name: str) -> ToolInfo:
        """Detect a tool and get its information.

        Args:
            tool_name: Name of the tool to detect

        Returns:
            ToolInfo with detection results
        """
        path = shutil.which(tool_name)

        if path is None:
            return ToolInfo(
                name=tool_name,
                path=None,
                version=None,
                status=ToolStatus.NOT_FOUND,
            )

        # Get version
        version_args = self.version_args.get(tool_name, self.version_args["default"])
        version = self.get_version(path, version_args)

        # Check version compatibility
        min_version = MIN_VERSIONS.get(tool_name)
        if min_version and version:
            if compare_versions(version, min_version) < 0:
                return ToolInfo(
                    name=tool_name,
                    path=path,
                    version=version,
                    status=ToolStatus.VERSION_INCOMPATIBLE,
                )

        return ToolInfo(
            name=tool_name,
            path=path,
            version=version,
            status=ToolStatus.AVAILABLE,
        )

    def get_version(self, tool_path: str, version_args: list[str]) -> Optional[str]:
        """Get the version of a tool.

        Args:
            tool_path: Path to the tool executable
            version_args: Arguments to get version (e.g., ["--version"])

        Returns:
            Version string or None if extraction fails
        """
        try:
            result = subprocess.run(
                [tool_path] + version_args,
                capture_output=True,
                text=True,
                timeout=10,
            )

            output = result.stdout or result.stderr

            # Extract version from output
            parsed = parse_version(output)
            if parsed:
                return f"{parsed[0]}.{parsed[1]}.{parsed[2]}"

            return None

        except (subprocess.SubprocessError, OSError) as e:
            logger.debug(f"Failed to get version for {tool_path}: {e}")
            return None

    def check_version_compatibility(self, version: str, min_version: str) -> bool:
        """Check if a version meets the minimum requirement.

        Args:
            version: Detected version
            min_version: Minimum required version

        Returns:
            True if version >= min_version
        """
        return compare_versions(version, min_version) >= 0


class PythonToolDetector(ToolDetector):
    """Detector for Python ecosystem tools."""

    supported_tools = [
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "black",
        "uv",
        "pip",
        "poetry",
        "pipenv",
        "pyright",
    ]

    version_args = {
        "default": ["--version"],
        "python": ["--version"],
        "python3": ["--version"],
    }


class JavaScriptToolDetector(ToolDetector):
    """Detector for JavaScript ecosystem tools."""

    supported_tools = [
        "node",
        "npm",
        "pnpm",
        "yarn",
        "jest",
        "eslint",
        "prettier",
        "webpack",
        "vite",
        "bun",
    ]

    version_args = {
        "default": ["--version"],
        "node": ["--version"],
    }


class RustToolDetector(ToolDetector):
    """Detector for Rust ecosystem tools."""

    supported_tools = [
        "cargo",
        "rustc",
        "clippy",
        "rustfmt",
        "rust-analyzer",
    ]

    version_args = {
        "default": ["--version"],
        "cargo": ["--version"],
        "rustc": ["--version"],
    }


class GenericToolDetector(ToolDetector):
    """Detector for generic tools (git, docker, etc.)."""

    supported_tools = [
        "git",
        "docker",
        "make",
        "curl",
        "wget",
        "jq",
        "gh",
    ]

    version_args = {
        "default": ["--version"],
        "git": ["--version"],
        "docker": ["--version"],
    }


# =============================================================================
# Project Type Detector
# =============================================================================


class ProjectTypeDetector:
    """Detects project type from manifest files."""

    # Priority order for detection (first match wins)
    PROJECT_MARKERS = [
        ("pyproject.toml", "python"),
        ("setup.py", "python"),
        ("requirements.txt", "python"),
        ("package.json", "javascript"),
        ("Cargo.toml", "rust"),
        ("go.mod", "go"),
        ("pom.xml", "java"),
        ("build.gradle", "java"),
        ("Gemfile", "ruby"),
        ("composer.json", "php"),
    ]

    # Required tools by project type
    REQUIRED_TOOLS = {
        "python": ["python", "pip"],
        "javascript": ["node", "npm"],
        "rust": ["cargo", "rustc"],
        "go": ["go"],
        "java": ["java", "javac"],
        "ruby": ["ruby", "gem"],
        "php": ["php", "composer"],
        "unknown": ["git"],
    }

    # Optional tools by project type
    OPTIONAL_TOOLS = {
        "python": ["pytest", "ruff", "mypy", "black", "uv"],
        "javascript": ["jest", "eslint", "prettier"],
        "rust": ["clippy", "rustfmt"],
        "go": [],
        "java": ["mvn", "gradle"],
        "ruby": ["bundler", "rspec"],
        "php": [],
        "unknown": [],
    }

    def detect_project_type(self, project_dir: Path) -> str:
        """Detect the project type from manifest files.

        Args:
            project_dir: Path to project directory

        Returns:
            Project type string (e.g., "python", "javascript", "unknown")
        """
        for marker_file, project_type in self.PROJECT_MARKERS:
            if (project_dir / marker_file).exists():
                logger.debug(f"Detected {project_type} project from {marker_file}")
                return project_type

        logger.debug("Could not detect project type, returning 'unknown'")
        return "unknown"

    def get_required_tools(self, project_type: str) -> list[str]:
        """Get required tools for a project type.

        Args:
            project_type: Project type string

        Returns:
            List of required tool names
        """
        return self.REQUIRED_TOOLS.get(project_type, self.REQUIRED_TOOLS["unknown"])

    def get_optional_tools(self, project_type: str) -> list[str]:
        """Get optional tools for a project type.

        Args:
            project_type: Project type string

        Returns:
            List of optional tool names
        """
        return self.OPTIONAL_TOOLS.get(project_type, [])


# =============================================================================
# Environment Validator
# =============================================================================


class EnvironmentValidator:
    """Validates the development environment for a project."""

    def __init__(self):
        """Initialize the validator with all detectors."""
        self.project_detector = ProjectTypeDetector()
        self.detectors = {
            "python": PythonToolDetector(),
            "javascript": JavaScriptToolDetector(),
            "rust": RustToolDetector(),
            "generic": GenericToolDetector(),
        }

    def validate_environment(
        self,
        project_dir: Path,
        required_tools: Optional[list[str]] = None,
        optional_tools: Optional[list[str]] = None,
    ) -> ValidationResult:
        """Validate the environment for a project.

        Args:
            project_dir: Path to project directory
            required_tools: Override list of required tools
            optional_tools: Override list of optional tools

        Returns:
            ValidationResult with detection results and recommendations
        """
        # Detect project type
        project_type = self.project_detector.detect_project_type(project_dir)

        # Determine required and optional tools
        if required_tools is None:
            required_tools = self.project_detector.get_required_tools(project_type)
        if optional_tools is None:
            optional_tools = self.project_detector.get_optional_tools(project_type)

        # Always require git
        if "git" not in required_tools:
            required_tools = ["git"] + list(required_tools)

        # Detect all tools
        all_tools = list(set(required_tools + optional_tools))
        detected_tools = self._detect_all_tools(all_tools)

        # Find missing tools
        missing_tools = [
            tool for tool in required_tools
            if tool not in detected_tools or not detected_tools[tool].is_available
        ]
        optional_missing = [
            tool for tool in optional_tools
            if tool not in detected_tools or not detected_tools[tool].is_available
        ]

        # Calculate health score
        health_score = self.calculate_health_score(detected_tools, required_tools)

        # Generate recommendations
        recommendations = self.generate_recommendations(detected_tools, project_type)

        # Generate warnings
        warnings = self._generate_warnings(detected_tools, project_type)

        # Detect conflicts
        conflicts = self._detect_conflicts(detected_tools)

        return ValidationResult(
            project_type=project_type,
            detected_tools=detected_tools,
            missing_tools=missing_tools,
            optional_missing=optional_missing,
            health_score=health_score,
            recommendations=recommendations,
            warnings=warnings,
            conflicts=conflicts,
        )

    def _detect_all_tools(self, tools: list[str]) -> dict[str, ToolInfo]:
        """Detect all specified tools.

        Args:
            tools: List of tool names to detect

        Returns:
            Dictionary mapping tool names to ToolInfo
        """
        results = {}
        for tool in tools:
            detector = self._get_detector_for_tool(tool)
            results[tool] = detector.detect_tool(tool)
        return results

    def _get_detector_for_tool(self, tool_name: str) -> ToolDetector:
        """Get the appropriate detector for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Appropriate ToolDetector instance
        """
        for detector in self.detectors.values():
            if tool_name in detector.supported_tools:
                return detector
        return self.detectors["generic"]

    def calculate_health_score(
        self,
        detected_tools: dict[str, ToolInfo],
        required: list[str],
    ) -> float:
        """Calculate environment health score.

        Args:
            detected_tools: Dictionary of detected tools
            required: List of required tool names

        Returns:
            Health score from 0.0 to 1.0
        """
        if not required:
            return 1.0

        available_count = sum(
            1 for tool in required
            if tool in detected_tools and detected_tools[tool].is_available
        )

        return available_count / len(required)

    def generate_recommendations(
        self,
        detected_tools: dict[str, ToolInfo],
        project_type: str,
    ) -> list[str]:
        """Generate recommendations for improving the environment.

        Args:
            detected_tools: Dictionary of detected tools
            project_type: Type of project

        Returns:
            List of recommendation strings
        """
        recommendations = []

        for tool_name, tool_info in detected_tools.items():
            if tool_info.status == ToolStatus.NOT_FOUND:
                install_cmd = self._get_install_command(tool_name, project_type)
                recommendations.append(
                    f"Install {tool_name}: {install_cmd}"
                )
            elif tool_info.status == ToolStatus.VERSION_INCOMPATIBLE:
                min_ver = MIN_VERSIONS.get(tool_name, "latest")
                recommendations.append(
                    f"Upgrade {tool_name} to version {min_ver} or higher "
                    f"(current: {tool_info.version})"
                )

        return recommendations

    def _generate_warnings(
        self,
        detected_tools: dict[str, ToolInfo],
        project_type: str,
    ) -> list[str]:
        """Generate warnings about the environment.

        Args:
            detected_tools: Dictionary of detected tools
            project_type: Type of project

        Returns:
            List of warning strings
        """
        warnings = []

        # Check for critical missing tools
        critical_missing = [
            tool for tool, info in detected_tools.items()
            if not info.is_available and tool in ["git", "python", "node", "cargo"]
        ]
        if critical_missing:
            warnings.append(
                f"Critical tools missing: {', '.join(critical_missing)}"
            )

        return warnings

    def _detect_conflicts(self, detected_tools: dict[str, ToolInfo]) -> list[str]:
        """Detect tool conflicts.

        Args:
            detected_tools: Dictionary of detected tools

        Returns:
            List of conflict descriptions
        """
        conflicts = []

        # Example: Check for conflicting Python versions
        # (Could be expanded based on real-world conflicts)

        return conflicts

    def _get_install_command(self, tool_name: str, project_type: str) -> str:
        """Get install command for a tool.

        Args:
            tool_name: Name of the tool
            project_type: Type of project

        Returns:
            Install command string
        """
        # Python tools
        if tool_name in ["pytest", "ruff", "mypy", "black"]:
            return f"pip install {tool_name}"
        if tool_name == "uv":
            return "curl -LsSf https://astral.sh/uv/install.sh | sh"
        if tool_name == "pip":
            return "python -m ensurepip --upgrade"

        # JavaScript tools
        if tool_name in ["jest", "eslint", "prettier"]:
            return f"npm install -g {tool_name}"
        if tool_name == "node":
            return "See https://nodejs.org/ or use nvm"
        if tool_name == "npm":
            return "Installed with Node.js"

        # Rust tools
        if tool_name in ["cargo", "rustc"]:
            return "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        if tool_name in ["clippy", "rustfmt"]:
            return f"rustup component add {tool_name}"

        # Generic tools
        if tool_name == "git":
            return "apt install git / brew install git"
        if tool_name == "docker":
            return "See https://docs.docker.com/get-docker/"

        return f"Install {tool_name} using your system package manager"
