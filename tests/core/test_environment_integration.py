"""Integration tests for environment validation and tool detection.

These tests exercise real system operations:
- Actual tool detection using shutil.which()
- Real subprocess calls for version extraction
- Project type detection with real file structures
- Environment validation with actual installed tools

Run with: pytest -m integration tests/core/test_environment_integration.py
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from codeframe.core.environment import (
    EnvironmentValidator,
    GenericToolDetector,
    JavaScriptToolDetector,
    ProjectTypeDetector,
    PythonToolDetector,
    RustToolDetector,
    ToolDetector,
    ToolInfo,
    ToolStatus,
    compare_versions,
    parse_version,
)


# Mark all tests as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.v2]


# =============================================================================
# Real Tool Detection Tests
# =============================================================================


class TestRealToolDetection:
    """Integration tests for real tool detection on the system."""

    def test_detect_git_real(self, available_system_tools):
        """Detect git using real system check."""
        if not available_system_tools.get("git"):
            pytest.skip("git not available on system")

        detector = GenericToolDetector()
        info = detector.detect_tool("git")

        assert info.name == "git"
        assert info.path is not None
        assert info.status == ToolStatus.AVAILABLE
        # Git should have a version
        assert info.version is not None

    def test_detect_python_real(self, available_system_tools):
        """Detect python using real system check."""
        if not available_system_tools.get("python") and not available_system_tools.get("python3"):
            pytest.skip("python not available on system")

        detector = PythonToolDetector()

        # Try python3 first, then python
        for python_name in ["python3", "python"]:
            if shutil.which(python_name):
                info = detector.detect_tool(python_name)
                break
        else:
            pytest.skip("No python found")

        assert info.path is not None
        assert info.status == ToolStatus.AVAILABLE
        assert info.version is not None
        # Version should be 3.x
        parsed = parse_version(info.version)
        assert parsed is not None
        assert parsed[0] == 3

    def test_detect_pytest_real(self, available_system_tools):
        """Detect pytest using real system check."""
        if not available_system_tools.get("pytest"):
            pytest.skip("pytest not available on system")

        detector = PythonToolDetector()
        info = detector.detect_tool("pytest")

        assert info.name == "pytest"
        assert info.path is not None
        assert info.status == ToolStatus.AVAILABLE
        assert info.version is not None

    def test_detect_ruff_real(self, available_system_tools):
        """Detect ruff using real system check."""
        if not shutil.which("ruff"):
            pytest.skip("ruff not available on system")

        detector = PythonToolDetector()
        info = detector.detect_tool("ruff")

        assert info.name == "ruff"
        assert info.path is not None
        assert info.status == ToolStatus.AVAILABLE

    def test_detect_nonexistent_tool(self):
        """Verify detection of non-existent tool returns NOT_FOUND."""
        detector = ToolDetector()
        info = detector.detect_tool("definitely_not_a_real_tool_xyz123")

        assert info.name == "definitely_not_a_real_tool_xyz123"
        assert info.path is None
        assert info.version is None
        assert info.status == ToolStatus.NOT_FOUND

    def test_detect_uv_if_available(self):
        """Detect uv package manager if available."""
        if not shutil.which("uv"):
            pytest.skip("uv not available on system")

        detector = PythonToolDetector()
        info = detector.detect_tool("uv")

        assert info.name == "uv"
        assert info.path is not None
        assert info.status == ToolStatus.AVAILABLE


class TestRealVersionExtraction:
    """Integration tests for extracting versions from real tools."""

    def test_git_version_format(self, available_system_tools):
        """Verify git version can be parsed from real output."""
        if not available_system_tools.get("git"):
            pytest.skip("git not available on system")

        git_path = shutil.which("git")
        result = subprocess.run(
            [git_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Output format: "git version 2.39.0" or similar
        version_str = result.stdout.strip()
        parsed = parse_version(version_str)

        assert parsed is not None
        assert len(parsed) == 3
        # Git version should be at least 2.x
        assert parsed[0] >= 2

    def test_python_version_format(self, available_system_tools):
        """Verify python version can be parsed from real output."""
        python_cmd = None
        for cmd in ["python3", "python"]:
            if shutil.which(cmd):
                python_cmd = cmd
                break

        if not python_cmd:
            pytest.skip("python not available on system")

        python_path = shutil.which(python_cmd)
        result = subprocess.run(
            [python_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Output format: "Python 3.11.4" or similar
        # Note: Some Python versions may output to stderr instead of stdout
        version_str = (result.stdout or result.stderr).strip()
        parsed = parse_version(version_str)

        assert parsed is not None
        assert parsed[0] == 3  # Python 3

    def test_pytest_version_format(self, available_system_tools):
        """Verify pytest version can be parsed from real output."""
        if not available_system_tools.get("pytest"):
            pytest.skip("pytest not available on system")

        pytest_path = shutil.which("pytest")
        result = subprocess.run(
            [pytest_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Output format: "pytest 7.4.0" or similar
        version_str = result.stdout.strip()
        parsed = parse_version(version_str)

        assert parsed is not None
        assert parsed[0] >= 7  # pytest 7+


class TestRealVersionComparison:
    """Integration tests for version comparison with real version strings."""

    @pytest.mark.parametrize("version1,version2,expected", [
        ("2.39.0", "2.38.0", 1),  # Greater
        ("2.38.0", "2.39.0", -1),  # Less
        ("2.39.0", "2.39.0", 0),  # Equal
        ("git version 2.39.0", "2.39.0", 0),  # With prefix
        ("Python 3.11.4", "3.11.4", 0),  # With Python prefix
        ("v1.2.3", "1.2.3", 0),  # With v prefix
    ])
    def test_compare_real_version_formats(self, version1, version2, expected):
        """Compare version strings in formats from real tool outputs."""
        result = compare_versions(version1, version2)

        if expected > 0:
            assert result > 0
        elif expected < 0:
            assert result < 0
        else:
            assert result == 0


# =============================================================================
# Project Type Detection Integration Tests
# =============================================================================


class TestRealProjectTypeDetection:
    """Integration tests for project type detection with real file structures."""

    def test_detect_python_project_pyproject(self, real_python_project: Path):
        """Detect Python project from realistic pyproject.toml structure."""
        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(real_python_project)

        assert project_type == "python"

    def test_detect_javascript_project(self, real_js_project: Path):
        """Detect JavaScript project from realistic package.json structure."""
        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(real_js_project)

        assert project_type == "javascript"

    def test_detect_rust_project(self, real_rust_project: Path):
        """Detect Rust project from realistic Cargo.toml structure."""
        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(real_rust_project)

        assert project_type == "rust"

    def test_detect_go_project(self, tmp_path: Path):
        """Detect Go project from go.mod."""
        (tmp_path / "go.mod").write_text("""module github.com/example/myproject

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
)
""")

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        assert project_type == "go"

    def test_detect_empty_directory(self, tmp_path: Path):
        """Handle empty directory gracefully."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(empty_dir)

        assert project_type == "unknown"

    def test_required_tools_for_python(self):
        """Get required tools list for Python project."""
        detector = ProjectTypeDetector()
        tools = detector.get_required_tools("python")

        assert "python" in tools
        assert "pip" in tools

    def test_required_tools_for_javascript(self):
        """Get required tools list for JavaScript project."""
        detector = ProjectTypeDetector()
        tools = detector.get_required_tools("javascript")

        assert "node" in tools
        assert "npm" in tools

    def test_optional_tools_for_python(self):
        """Get optional tools list for Python project."""
        detector = ProjectTypeDetector()
        tools = detector.get_optional_tools("python")

        assert "pytest" in tools
        assert "ruff" in tools

    def test_priority_with_multiple_markers(self, tmp_path: Path):
        """Python takes priority when both pyproject.toml and package.json exist."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'mixed'\n")
        (tmp_path / "package.json").write_text('{"name": "mixed"}')

        detector = ProjectTypeDetector()
        project_type = detector.detect_project_type(tmp_path)

        # pyproject.toml comes before package.json in PROJECT_MARKERS
        assert project_type == "python"


# =============================================================================
# Environment Validator Integration Tests
# =============================================================================


class TestRealEnvironmentValidation:
    """Integration tests for full environment validation workflow."""

    def test_validate_python_project_with_real_tools(
        self, real_python_project: Path, available_system_tools
    ):
        """Validate environment for Python project with real tool detection."""
        if not available_system_tools.get("git"):
            pytest.skip("git not available on system")

        validator = EnvironmentValidator()
        result = validator.validate_environment(real_python_project)

        assert result.project_type == "python"
        # git should always be detected if available
        assert "git" in result.detected_tools
        if available_system_tools.get("git"):
            assert result.detected_tools["git"].status == ToolStatus.AVAILABLE

    def test_health_score_calculation_real(self, tmp_path: Path, available_system_tools):
        """Calculate health score with real detected tools."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()
        result = validator.validate_environment(tmp_path)

        # Health score should be between 0 and 1
        assert 0 <= result.health_score <= 1

        # If git and python are available, score should be reasonable
        available_count = sum(1 for t in ["git", "python", "pip"]
                              if available_system_tools.get(t))
        if available_count >= 2:
            assert result.health_score >= 0.5

    def test_recommendations_for_missing_tools(self, tmp_path: Path):
        """Generate recommendations when tools are missing."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()
        # Use custom required tools that likely don't exist
        result = validator.validate_environment(
            tmp_path,
            required_tools=["some_fake_tool_xyz", "another_fake_tool_abc"],
        )

        # Should have recommendations for missing tools
        assert len(result.recommendations) > 0
        assert any("some_fake_tool_xyz" in r for r in result.recommendations)

    def test_warnings_for_critical_missing_tools(self, tmp_path: Path):
        """Generate warnings when critical tools are missing."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()
        # Force detection to think git is missing
        result = validator.validate_environment(
            tmp_path,
            required_tools=["git", "definitely_missing_tool"],
        )

        # If git is actually missing, should have warning
        if "git" in result.missing_tools:
            assert len(result.warnings) > 0

    def test_optional_tools_tracked_separately(
        self, real_python_project: Path, available_system_tools
    ):
        """Optional missing tools are tracked separately from required."""
        validator = EnvironmentValidator()
        result = validator.validate_environment(
            real_python_project,
            optional_tools=["definitely_missing_optional_tool"],
        )

        # Should be in optional_missing, not missing_tools
        assert "definitely_missing_optional_tool" in result.optional_missing

    def test_validation_result_properties(self, real_python_project: Path):
        """Verify ValidationResult properties work correctly."""
        validator = EnvironmentValidator()
        result = validator.validate_environment(real_python_project)

        # is_healthy should be consistent with health_score and missing_tools
        if result.health_score >= 0.8 and len(result.missing_tools) == 0:
            assert result.is_healthy is True
        elif result.health_score < 0.8 or len(result.missing_tools) > 0:
            assert result.is_healthy is False

        # Custom threshold should work
        assert result.is_healthy_with_threshold(0.0) is True
        assert result.is_healthy_with_threshold(1.1) is False


# =============================================================================
# Ecosystem Detector Integration Tests
# =============================================================================


class TestEcosystemDetectors:
    """Integration tests for ecosystem-specific tool detectors."""

    def test_python_detector_supported_tools(self):
        """Python detector knows all expected tools."""
        detector = PythonToolDetector()
        expected = {"python", "python3", "pytest", "ruff", "mypy", "black", "uv", "pip"}
        assert expected.issubset(set(detector.supported_tools))

    def test_javascript_detector_supported_tools(self):
        """JavaScript detector knows all expected tools."""
        detector = JavaScriptToolDetector()
        expected = {"node", "npm", "pnpm", "yarn", "jest", "eslint"}
        assert expected.issubset(set(detector.supported_tools))

    def test_rust_detector_supported_tools(self):
        """Rust detector knows all expected tools."""
        detector = RustToolDetector()
        expected = {"cargo", "rustc", "clippy", "rustfmt"}
        assert expected.issubset(set(detector.supported_tools))

    def test_generic_detector_supported_tools(self):
        """Generic detector knows all expected tools."""
        detector = GenericToolDetector()
        expected = {"git", "docker", "make", "curl", "wget"}
        assert expected.issubset(set(detector.supported_tools))


# =============================================================================
# Version Parsing Integration Tests
# =============================================================================


class TestVersionParsingReal:
    """Integration tests for parsing real tool version outputs."""

    @pytest.mark.parametrize("version_str,expected", [
        # Git formats
        ("git version 2.39.0", (2, 39, 0)),
        ("git version 2.39.2.windows.1", (2, 39, 2)),
        # Python formats
        ("Python 3.11.4", (3, 11, 4)),
        ("Python 3.13.3", (3, 13, 3)),
        # Pytest formats
        ("pytest 7.4.0", (7, 4, 0)),
        ("pytest 8.0.0", (8, 0, 0)),
        # npm formats
        ("10.2.4", (10, 2, 4)),
        ("9.8.1", (9, 8, 1)),
        # Node formats
        ("v20.10.0", (20, 10, 0)),
        ("v18.12.1", (18, 12, 1)),
        # Ruff formats
        ("ruff 0.1.0", (0, 1, 0)),
        ("0.3.5", (0, 3, 5)),
        # Cargo/Rust formats
        ("cargo 1.75.0 (1d8b05cdd 2023-11-20)", (1, 75, 0)),
        ("rustc 1.75.0 (82e1608df 2023-12-21)", (1, 75, 0)),
    ])
    def test_parse_real_version_formats(self, version_str, expected):
        """Parse version strings from real tool outputs."""
        parsed = parse_version(version_str)

        assert parsed == expected

    def test_parse_version_handles_edge_cases(self):
        """Handle edge cases in version parsing."""
        # Two-part version
        assert parse_version("3.11") == (3, 11, 0)

        # Pre-release suffix
        assert parse_version("1.0.0-alpha") == (1, 0, 0)
        assert parse_version("1.0.0-rc1") == (1, 0, 0)

        # Post-release suffix
        assert parse_version("7.4.0.post1") == (7, 4, 0)

        # Build metadata
        assert parse_version("1.2.3+build.456") == (1, 2, 3)


# =============================================================================
# Tool Detection Edge Cases
# =============================================================================


class TestToolDetectionEdgeCases:
    """Edge case tests for tool detection."""

    def test_tool_with_slow_version_command_timeout(self):
        """Handle tools that timeout when getting version."""
        from unittest.mock import patch

        detector = ToolDetector()

        # Mock subprocess.run to raise TimeoutExpired
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="slow-tool", timeout=10)

            version = detector.get_version("/usr/bin/slow-tool", ["--version"])

            # Should return None on timeout (graceful degradation)
            assert version is None

    def test_version_extraction_from_stderr(self):
        """Extract version from stderr when stdout is empty."""
        from unittest.mock import patch, MagicMock

        detector = ToolDetector()

        # Mock subprocess.run to return version in stderr
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "some-tool version 1.2.3"

        with patch("subprocess.run", return_value=mock_result):
            version = detector.get_version("/usr/bin/some-tool", ["--version"])

            # Should extract version from stderr when stdout is empty
            assert version == "1.2.3"

    def test_version_extraction_subprocess_error(self):
        """Handle subprocess errors gracefully."""
        from unittest.mock import patch

        detector = ToolDetector()

        # Mock subprocess.run to raise SubprocessError
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("Command failed")

            version = detector.get_version("/usr/bin/failing-tool", ["--version"])

            # Should return None on subprocess error
            assert version is None

    def test_detect_tool_version_incompatible(self):
        """Test version incompatibility detection."""
        detector = ToolDetector()

        # check_version_compatibility should work correctly
        assert detector.check_version_compatibility("7.4.0", "7.0.0") is True
        assert detector.check_version_compatibility("7.0.0", "7.0.0") is True  # Equal
        assert detector.check_version_compatibility("6.9.0", "7.0.0") is False
        assert detector.check_version_compatibility("1.0.0", "2.0.0") is False


# =============================================================================
# Full Workflow Integration Tests
# =============================================================================


class TestFullWorkflowIntegration:
    """End-to-end integration tests for the full environment validation workflow."""

    def test_complete_python_project_workflow(
        self, real_python_project: Path, available_system_tools
    ):
        """Complete workflow: detect project, validate environment, get recommendations."""
        # Step 1: Detect project type
        project_detector = ProjectTypeDetector()
        project_type = project_detector.detect_project_type(real_python_project)
        assert project_type == "python"

        # Step 2: Get required and optional tools
        required = project_detector.get_required_tools(project_type)
        optional = project_detector.get_optional_tools(project_type)
        assert "python" in required
        assert "pytest" in optional

        # Step 3: Validate environment
        validator = EnvironmentValidator()
        result = validator.validate_environment(real_python_project)

        # Step 4: Check results
        assert result.project_type == "python"
        assert isinstance(result.health_score, float)
        assert isinstance(result.missing_tools, list)
        assert isinstance(result.recommendations, list)

    def test_environment_report_structure(self, real_python_project: Path):
        """Verify environment validation produces complete report structure."""
        validator = EnvironmentValidator()
        result = validator.validate_environment(real_python_project)

        # All expected fields should be present and correct types
        assert isinstance(result.project_type, str)
        assert isinstance(result.detected_tools, dict)
        assert isinstance(result.missing_tools, list)
        assert isinstance(result.optional_missing, list)
        assert isinstance(result.health_score, float)
        assert isinstance(result.recommendations, list)
        assert isinstance(result.warnings, list)
        assert isinstance(result.conflicts, list)

        # Health score should be in valid range
        assert 0.0 <= result.health_score <= 1.0

        # All detected tools should be ToolInfo objects
        for tool_name, tool_info in result.detected_tools.items():
            assert isinstance(tool_info, ToolInfo)
            assert tool_info.name == tool_name

    def test_custom_tools_override(self, tmp_path: Path):
        """Validate with custom required tools list."""
        (tmp_path / "pyproject.toml").write_text("[project]")

        validator = EnvironmentValidator()
        result = validator.validate_environment(
            tmp_path,
            required_tools=["git", "custom_required_tool"],
            optional_tools=["custom_optional_tool"],
        )

        # Custom required tool should be in missing if not found
        if not shutil.which("custom_required_tool"):
            assert "custom_required_tool" in result.missing_tools

        # Custom optional tool should be in optional_missing if not found
        if not shutil.which("custom_optional_tool"):
            assert "custom_optional_tool" in result.optional_missing
