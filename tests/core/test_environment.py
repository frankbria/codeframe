"""Tests for environment validation and tool detection.

This module tests:
- Tool detection using shutil.which()
- Version parsing and compatibility checking
- Environment validation for different project types
- Health score calculation
- Recommendations generation
"""

import subprocess
from unittest.mock import MagicMock, patch


from codeframe.core.environment import (
    ToolInfo,
    ToolStatus,
    ToolDetector,
    PythonToolDetector,
    JavaScriptToolDetector,
    RustToolDetector,
    GenericToolDetector,
    ProjectTypeDetector,
    EnvironmentValidator,
    ValidationResult,
    parse_version,
    compare_versions,
)


# =============================================================================
# ToolInfo Tests
# =============================================================================


class TestToolInfo:
    """Tests for ToolInfo dataclass."""

    def test_tool_info_creation(self):
        """Test creating a ToolInfo instance with all fields."""
        info = ToolInfo(
            name="pytest",
            path="/usr/bin/pytest",
            version="7.4.0",
            status=ToolStatus.AVAILABLE,
        )
        assert info.name == "pytest"
        assert info.path == "/usr/bin/pytest"
        assert info.version == "7.4.0"
        assert info.status == ToolStatus.AVAILABLE

    def test_tool_info_missing(self):
        """Test ToolInfo for a missing tool."""
        info = ToolInfo(
            name="nonexistent",
            path=None,
            version=None,
            status=ToolStatus.NOT_FOUND,
        )
        assert info.name == "nonexistent"
        assert info.path is None
        assert info.version is None
        assert info.status == ToolStatus.NOT_FOUND

    def test_tool_info_is_available(self):
        """Test is_available property."""
        available = ToolInfo("pytest", "/usr/bin/pytest", "7.4.0", ToolStatus.AVAILABLE)
        missing = ToolInfo("missing", None, None, ToolStatus.NOT_FOUND)
        incompatible = ToolInfo("old", "/usr/bin/old", "1.0.0", ToolStatus.VERSION_INCOMPATIBLE)

        assert available.is_available is True
        assert missing.is_available is False
        assert incompatible.is_available is False


# =============================================================================
# Version Parsing Tests
# =============================================================================


class TestVersionParsing:
    """Tests for version parsing and comparison utilities."""

    def test_parse_version_simple(self):
        """Test parsing simple version strings."""
        assert parse_version("1.0.0") == (1, 0, 0)
        assert parse_version("7.4.3") == (7, 4, 3)
        assert parse_version("10.20.30") == (10, 20, 30)

    def test_parse_version_two_parts(self):
        """Test parsing version with two parts."""
        assert parse_version("3.11") == (3, 11, 0)
        assert parse_version("18.0") == (18, 0, 0)

    def test_parse_version_with_prefix(self):
        """Test parsing version with common prefixes."""
        assert parse_version("v1.2.3") == (1, 2, 3)
        assert parse_version("Python 3.11.4") == (3, 11, 4)
        assert parse_version("pytest 7.4.0") == (7, 4, 0)

    def test_parse_version_with_suffix(self):
        """Test parsing version with suffixes."""
        assert parse_version("1.2.3-rc1") == (1, 2, 3)
        assert parse_version("7.4.0.post1") == (7, 4, 0)
        assert parse_version("3.11.4+") == (3, 11, 4)

    def test_parse_version_invalid(self):
        """Test parsing invalid version strings."""
        assert parse_version("invalid") is None
        assert parse_version("") is None
        assert parse_version("abc.def.ghi") is None

    def test_compare_versions(self):
        """Test version comparison."""
        # Equal versions
        assert compare_versions("1.0.0", "1.0.0") == 0

        # Greater than
        assert compare_versions("2.0.0", "1.0.0") > 0
        assert compare_versions("1.1.0", "1.0.0") > 0
        assert compare_versions("1.0.1", "1.0.0") > 0

        # Less than
        assert compare_versions("1.0.0", "2.0.0") < 0
        assert compare_versions("1.0.0", "1.1.0") < 0
        assert compare_versions("1.0.0", "1.0.1") < 0

    def test_compare_versions_with_prefixes(self):
        """Test comparison with version prefixes."""
        assert compare_versions("v1.2.3", "1.2.3") == 0
        assert compare_versions("pytest 7.4.0", "7.4.0") == 0


# =============================================================================
# ToolDetector Tests
# =============================================================================


class TestToolDetector:
    """Tests for base ToolDetector class."""

    def test_detect_tool_found(self):
        """Test detecting a tool that exists (git is commonly available)."""
        detector = ToolDetector()
        # We'll mock shutil.which to ensure consistent behavior
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/git"
            with patch.object(detector, "get_version", return_value="2.39.0"):
                info = detector.detect_tool("git")

        assert info.name == "git"
        assert info.path == "/usr/bin/git"
        assert info.version == "2.39.0"
        assert info.status == ToolStatus.AVAILABLE

    def test_detect_tool_not_found(self):
        """Test detecting a tool that doesn't exist."""
        detector = ToolDetector()
        with patch("shutil.which", return_value=None):
            info = detector.detect_tool("nonexistent_tool_xyz")

        assert info.name == "nonexistent_tool_xyz"
        assert info.path is None
        assert info.version is None
        assert info.status == ToolStatus.NOT_FOUND

    def test_get_version_success(self):
        """Test getting version from a tool."""
        detector = ToolDetector()
        mock_result = MagicMock()
        mock_result.stdout = "git version 2.39.0\n"
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            version = detector.get_version("/usr/bin/git", ["--version"])

        assert version == "2.39.0"

    def test_get_version_failure(self):
        """Test version extraction when command fails."""
        detector = ToolDetector()
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("Command failed")):
            version = detector.get_version("/nonexistent", ["--version"])

        assert version is None

    def test_check_version_compatibility_satisfied(self):
        """Test version compatibility check when satisfied."""
        detector = ToolDetector()
        assert detector.check_version_compatibility("7.4.0", "7.0.0") is True
        assert detector.check_version_compatibility("2.0.0", "1.5.0") is True
        assert detector.check_version_compatibility("1.0.0", "1.0.0") is True

    def test_check_version_compatibility_not_satisfied(self):
        """Test version compatibility check when not satisfied."""
        detector = ToolDetector()
        assert detector.check_version_compatibility("1.0.0", "2.0.0") is False
        assert detector.check_version_compatibility("7.3.0", "7.4.0") is False


# =============================================================================
# Ecosystem-Specific Detector Tests
# =============================================================================


class TestPythonToolDetector:
    """Tests for Python ecosystem tool detection."""

    def test_detect_pytest(self):
        """Test detecting pytest."""
        detector = PythonToolDetector()
        with patch("shutil.which", return_value="/usr/bin/pytest"):
            with patch.object(detector, "get_version", return_value="7.4.0"):
                info = detector.detect_tool("pytest")

        assert info.name == "pytest"
        assert info.status == ToolStatus.AVAILABLE

    def test_detect_ruff(self):
        """Test detecting ruff."""
        detector = PythonToolDetector()
        with patch("shutil.which", return_value="/usr/bin/ruff"):
            with patch.object(detector, "get_version", return_value="0.1.0"):
                info = detector.detect_tool("ruff")

        assert info.name == "ruff"
        assert info.status == ToolStatus.AVAILABLE

    def test_detect_uv(self):
        """Test detecting uv package manager."""
        detector = PythonToolDetector()
        with patch("shutil.which", return_value="/home/user/.cargo/bin/uv"):
            with patch.object(detector, "get_version", return_value="0.1.24"):
                info = detector.detect_tool("uv")

        assert info.name == "uv"
        assert info.status == ToolStatus.AVAILABLE

    def test_supported_tools(self):
        """Test that Python detector knows its supported tools."""
        detector = PythonToolDetector()
        expected_tools = {"pytest", "ruff", "mypy", "black", "uv", "pip", "poetry", "python"}
        assert set(detector.supported_tools) >= expected_tools


class TestJavaScriptToolDetector:
    """Tests for JavaScript ecosystem tool detection."""

    def test_detect_npm(self):
        """Test detecting npm."""
        detector = JavaScriptToolDetector()
        with patch("shutil.which", return_value="/usr/bin/npm"):
            with patch.object(detector, "get_version", return_value="10.2.4"):
                info = detector.detect_tool("npm")

        assert info.name == "npm"
        assert info.status == ToolStatus.AVAILABLE

    def test_detect_node(self):
        """Test detecting node."""
        detector = JavaScriptToolDetector()
        with patch("shutil.which", return_value="/usr/bin/node"):
            with patch.object(detector, "get_version", return_value="20.10.0"):
                info = detector.detect_tool("node")

        assert info.name == "node"
        assert info.status == ToolStatus.AVAILABLE

    def test_supported_tools(self):
        """Test that JavaScript detector knows its supported tools."""
        detector = JavaScriptToolDetector()
        expected_tools = {"npm", "node", "jest", "eslint", "prettier", "pnpm", "yarn"}
        assert set(detector.supported_tools) >= expected_tools


class TestRustToolDetector:
    """Tests for Rust ecosystem tool detection."""

    def test_detect_cargo(self):
        """Test detecting cargo."""
        detector = RustToolDetector()
        with patch("shutil.which", return_value="/usr/bin/cargo"):
            with patch.object(detector, "get_version", return_value="1.75.0"):
                info = detector.detect_tool("cargo")

        assert info.name == "cargo"
        assert info.status == ToolStatus.AVAILABLE

    def test_supported_tools(self):
        """Test that Rust detector knows its supported tools."""
        detector = RustToolDetector()
        expected_tools = {"cargo", "rustc", "clippy", "rustfmt"}
        assert set(detector.supported_tools) >= expected_tools


class TestGenericToolDetector:
    """Tests for generic tool detection (git, docker, etc.)."""

    def test_detect_git(self):
        """Test detecting git."""
        detector = GenericToolDetector()
        with patch("shutil.which", return_value="/usr/bin/git"):
            with patch.object(detector, "get_version", return_value="2.39.0"):
                info = detector.detect_tool("git")

        assert info.name == "git"
        assert info.status == ToolStatus.AVAILABLE

    def test_detect_docker(self):
        """Test detecting docker."""
        detector = GenericToolDetector()
        with patch("shutil.which", return_value="/usr/bin/docker"):
            with patch.object(detector, "get_version", return_value="24.0.7"):
                info = detector.detect_tool("docker")

        assert info.name == "docker"
        assert info.status == ToolStatus.AVAILABLE

    def test_supported_tools(self):
        """Test that Generic detector knows its supported tools."""
        detector = GenericToolDetector()
        expected_tools = {"git", "docker", "make", "curl", "wget"}
        assert set(detector.supported_tools) >= expected_tools


# =============================================================================
# ProjectTypeDetector Tests
# =============================================================================


class TestProjectTypeDetector:
    """Tests for project type detection from files."""

    def test_detect_python_project_pyproject(self, tmp_path):
        """Test detecting Python project from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "python"

    def test_detect_python_project_requirements(self, tmp_path):
        """Test detecting Python project from requirements.txt."""
        (tmp_path / "requirements.txt").write_text("pytest\nrequests\n")

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "python"

    def test_detect_javascript_project_package_json(self, tmp_path):
        """Test detecting JavaScript project from package.json."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "javascript"

    def test_detect_rust_project_cargo(self, tmp_path):
        """Test detecting Rust project from Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text("[package]\nname = 'test'\n")

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "rust"

    def test_detect_go_project(self, tmp_path):
        """Test detecting Go project from go.mod."""
        (tmp_path / "go.mod").write_text("module example.com/test\n")

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "go"

    def test_detect_unknown_project(self, tmp_path):
        """Test handling unknown project type."""
        # Empty directory
        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "unknown"

    def test_detect_multiple_markers_priority(self, tmp_path):
        """Test priority when multiple project markers exist."""
        # Both Python and JavaScript files - pyproject.toml takes precedence
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text("{}")

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        # Python should take precedence in this codebase's context
        assert project_type == "python"

    def test_get_required_tools_python(self):
        """Test getting required tools for Python project."""
        detector = ProjectTypeDetector()
        tools = detector.get_required_tools("python")

        assert "python" in tools
        assert "pip" in tools  # pip is required for Python projects

    def test_get_required_tools_javascript(self):
        """Test getting required tools for JavaScript project."""
        detector = ProjectTypeDetector()
        tools = detector.get_required_tools("javascript")

        assert "node" in tools
        assert "npm" in tools or "pnpm" in tools or "yarn" in tools


# =============================================================================
# EnvironmentValidator Tests
# =============================================================================


class TestEnvironmentValidator:
    """Tests for the environment validation engine."""

    def test_validate_environment_all_tools_present(self, tmp_path):
        """Test validation when all required tools are present."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()

        # Mock all tools as available (including pip which is required for Python)
        with patch.object(validator, "_detect_all_tools") as mock_detect:
            mock_detect.return_value = {
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
                "pip": ToolInfo("pip", "/usr/bin/pip", "23.0.0", ToolStatus.AVAILABLE),
                "pytest": ToolInfo("pytest", "/usr/bin/pytest", "7.4.0", ToolStatus.AVAILABLE),
                "git": ToolInfo("git", "/usr/bin/git", "2.39.0", ToolStatus.AVAILABLE),
            }
            result = validator.validate_environment(tmp_path)

        assert result.is_healthy is True
        assert len(result.missing_tools) == 0
        assert result.health_score >= 0.8

    def test_validate_environment_missing_required_tools(self, tmp_path):
        """Test validation when required tools are missing."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()

        with patch.object(validator, "_detect_all_tools") as mock_detect:
            mock_detect.return_value = {
                "python": ToolInfo("python", None, None, ToolStatus.NOT_FOUND),
                "git": ToolInfo("git", "/usr/bin/git", "2.39.0", ToolStatus.AVAILABLE),
            }
            result = validator.validate_environment(tmp_path)

        assert result.is_healthy is False
        assert "python" in result.missing_tools
        assert result.health_score < 0.8

    def test_calculate_health_score(self):
        """Test health score calculation."""
        validator = EnvironmentValidator()

        # All tools available
        all_available = {
            "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
            "pytest": ToolInfo("pytest", "/usr/bin/pytest", "7.4.0", ToolStatus.AVAILABLE),
        }
        score = validator.calculate_health_score(all_available, required=["python", "pytest"])
        assert score == 1.0

        # Half tools available
        half_available = {
            "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
            "pytest": ToolInfo("pytest", None, None, ToolStatus.NOT_FOUND),
        }
        score = validator.calculate_health_score(half_available, required=["python", "pytest"])
        assert score == 0.5

    def test_generate_recommendations_missing_tool(self):
        """Test recommendation generation for missing tools."""
        validator = EnvironmentValidator()

        tools = {
            "pytest": ToolInfo("pytest", None, None, ToolStatus.NOT_FOUND),
        }
        recommendations = validator.generate_recommendations(tools, project_type="python")

        assert len(recommendations) > 0
        # Should recommend installing pytest
        assert any("pytest" in r.lower() or "install" in r.lower() for r in recommendations)

    def test_generate_recommendations_version_incompatible(self):
        """Test recommendation generation for version issues."""
        validator = EnvironmentValidator()

        tools = {
            "python": ToolInfo("python", "/usr/bin/python", "2.7.0", ToolStatus.VERSION_INCOMPATIBLE),
        }
        recommendations = validator.generate_recommendations(tools, project_type="python")

        assert len(recommendations) > 0
        # Should recommend upgrading
        assert any("upgrade" in r.lower() or "version" in r.lower() for r in recommendations)


# =============================================================================
# ValidationResult Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_healthy(self):
        """Test creating a healthy validation result."""
        result = ValidationResult(
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

        assert result.is_healthy is True
        assert result.project_type == "python"
        assert len(result.detected_tools) == 1

    def test_validation_result_unhealthy(self):
        """Test creating an unhealthy validation result."""
        result = ValidationResult(
            project_type="python",
            detected_tools={},
            missing_tools=["python", "pytest"],
            optional_missing=["ruff"],
            health_score=0.0,
            recommendations=["Install Python 3.8+"],
            warnings=["Critical tools missing"],
            conflicts=[],
        )

        assert result.is_healthy is False
        assert len(result.missing_tools) == 2
        assert len(result.recommendations) > 0

    def test_validation_result_with_threshold(self):
        """Test is_healthy with custom threshold."""
        result = ValidationResult(
            project_type="python",
            detected_tools={
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
            },
            missing_tools=["pytest"],
            optional_missing=[],
            health_score=0.75,
            recommendations=[],
            warnings=[],
            conflicts=[],
        )

        # Default threshold is 0.8
        assert result.is_healthy is False
        # With lower threshold
        assert result.is_healthy_with_threshold(0.7) is True


# =============================================================================
# Integration Tests
# =============================================================================


class TestEnvironmentValidationIntegration:
    """Integration tests for the full validation workflow."""

    def test_full_validation_workflow(self, tmp_path):
        """Test the complete validation workflow."""
        # Create a Python project structure
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-project"
version = "0.1.0"
dependencies = ["pytest", "ruff"]
""")
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()

        validator = EnvironmentValidator()

        # Mock tool detection for consistent testing (include all required tools)
        with patch.object(validator, "_detect_all_tools") as mock_detect:
            mock_detect.return_value = {
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
                "pip": ToolInfo("pip", "/usr/bin/pip", "23.0.0", ToolStatus.AVAILABLE),
                "pytest": ToolInfo("pytest", "/usr/bin/pytest", "7.4.0", ToolStatus.AVAILABLE),
                "ruff": ToolInfo("ruff", "/usr/bin/ruff", "0.1.0", ToolStatus.AVAILABLE),
                "git": ToolInfo("git", "/usr/bin/git", "2.39.0", ToolStatus.AVAILABLE),
            }
            result = validator.validate_environment(tmp_path)

        assert result.project_type == "python"
        assert result.is_healthy is True
        assert result.health_score >= 0.8

    def test_validation_with_custom_required_tools(self, tmp_path):
        """Test validation with custom required tools list."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()
        custom_required = ["python", "pytest", "docker"]

        with patch.object(validator, "_detect_all_tools") as mock_detect:
            mock_detect.return_value = {
                "python": ToolInfo("python", "/usr/bin/python", "3.11.0", ToolStatus.AVAILABLE),
                "pytest": ToolInfo("pytest", "/usr/bin/pytest", "7.4.0", ToolStatus.AVAILABLE),
                "docker": ToolInfo("docker", None, None, ToolStatus.NOT_FOUND),
            }
            result = validator.validate_environment(tmp_path, required_tools=custom_required)

        assert "docker" in result.missing_tools
        assert result.is_healthy is False
