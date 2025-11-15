"""
Tests for LanguageDetector - multi-language detection system.
"""

import json
import tempfile
from pathlib import Path

import pytest

from codeframe.enforcement import LanguageDetector, LanguageInfo


class TestLanguageDetector:
    """Test language detection for various project types."""

    def test_detects_python_with_pyproject_toml(self, tmp_path):
        """Test detection of Python project via pyproject.toml"""
        # Create a minimal Python project
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.pytest.ini_options]
testpaths = ["tests"]
"""
        )

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "python"
        assert "pytest" in info.test_command or "unittest" in info.test_command
        assert info.confidence > 0.5

    def test_detects_javascript_with_package_json(self, tmp_path):
        """Test detection of JavaScript project via package.json"""
        package_json = {"name": "test-project", "devDependencies": {"jest": "^29.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "javascript"
        assert info.framework == "jest"
        assert "it.skip" in info.skip_patterns

    def test_detects_typescript_with_tsconfig(self, tmp_path):
        """Test detection of TypeScript project"""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        (tmp_path / "package.json").write_text('{"devDependencies": {"vitest": "^0.34.0"}}')

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "typescript"
        assert "*.test.ts" in info.test_patterns

    def test_detects_go_with_go_mod(self, tmp_path):
        """Test detection of Go project"""
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.21")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "go"
        assert info.framework == "go test"
        assert "go test" in info.test_command
        assert "t.Skip(" in info.skip_patterns

    def test_detects_rust_with_cargo_toml(self, tmp_path):
        """Test detection of Rust project"""
        (tmp_path / "Cargo.toml").write_text(
            """
[package]
name = "myapp"
version = "0.1.0"
"""
        )

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "rust"
        assert info.framework == "cargo test"
        assert "#[ignore]" in info.skip_patterns

    def test_detects_java_maven_with_pom_xml(self, tmp_path):
        """Test detection of Java Maven project"""
        (tmp_path / "pom.xml").write_text("<project></project>")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "java"
        assert info.framework == "maven"
        assert "mvn test" in info.test_command
        assert "@Ignore" in info.skip_patterns

    def test_detects_java_gradle_with_build_gradle(self, tmp_path):
        """Test detection of Java Gradle project"""
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "java"
        assert info.framework == "gradle"
        assert "@Disabled" in info.skip_patterns

    def test_detects_ruby_with_gemfile(self, tmp_path):
        """Test detection of Ruby project with RSpec"""
        (tmp_path / "Gemfile").write_text("gem 'rspec'")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "ruby"
        assert info.framework == "rspec"
        assert "skip" in info.skip_patterns

    def test_detects_csharp_with_csproj(self, tmp_path):
        """Test detection of C# .NET project"""
        (tmp_path / "MyApp.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"></Project>')

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "csharp"
        assert "dotnet test" in info.test_command
        assert "[Ignore]" in info.skip_patterns

    def test_returns_unknown_for_unrecognized_project(self, tmp_path):
        """Test fallback to unknown for unrecognized projects"""
        # Empty directory
        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.language == "unknown"
        assert info.confidence == 0.0

    def test_python_with_pytest_in_pyproject(self, tmp_path):
        """Test Python detection prefers pytest when configured"""
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.pytest.ini_options]
testpaths = ["tests"]

[project.optional-dependencies]
dev = ["pytest>=8.0.0"]
"""
        )

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.framework == "pytest"
        assert "pytest" in info.test_command


class TestLanguageDetectorConfidence:
    """Test confidence scoring system."""

    def test_high_confidence_with_multiple_markers(self, tmp_path):
        """Test high confidence when multiple markers present"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")
        (tmp_path / "pytest.ini").write_text("[pytest]")
        (tmp_path / "setup.py").write_text("from setuptools import setup")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        assert info.confidence > 0.8

    def test_lower_confidence_with_few_markers(self, tmp_path):
        """Test lower confidence with minimal markers"""
        (tmp_path / "requirements.txt").write_text("requests==2.0.0")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        # Should still detect Python but with lower confidence
        assert 0.5 < info.confidence < 0.9


class TestLanguageDetectorSkipPatterns:
    """Test skip pattern detection for each language."""

    def test_python_skip_patterns_comprehensive(self, tmp_path):
        """Test all Python skip patterns are included"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        expected_patterns = [
            "@skip",
            "@skipif",
            "@pytest.mark.skip",
            "@pytest.mark.skipif",
            "@unittest.skip",
        ]

        for pattern in expected_patterns:
            assert pattern in info.skip_patterns, f"Missing skip pattern: {pattern}"

    def test_javascript_skip_patterns_comprehensive(self, tmp_path):
        """Test all JavaScript skip patterns are included"""
        (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')

        detector = LanguageDetector(str(tmp_path))
        info = detector.detect()

        expected_patterns = ["it.skip", "test.skip", "describe.skip", "xit", "xtest", "xdescribe"]

        for pattern in expected_patterns:
            assert pattern in info.skip_patterns, f"Missing skip pattern: {pattern}"
