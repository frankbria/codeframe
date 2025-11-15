"""
Language Detection System

Detects the programming language and testing framework of a project
by analyzing project files and structure.

Supports:
- Python (pytest, unittest)
- JavaScript/TypeScript (Jest, Vitest, Mocha)
- Go (go test)
- Rust (cargo test)
- Java (JUnit, Maven, Gradle)
- Ruby (RSpec)
- C# (.NET test)
- And more...
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import json


@dataclass
class LanguageInfo:
    """Information about detected language and testing framework."""

    language: str  # "python", "javascript", "typescript", "go", "rust", etc.
    framework: Optional[str]  # "pytest", "jest", "go test", "cargo", etc.
    test_command: str  # Command to run tests
    coverage_command: Optional[str]  # Command to get coverage
    test_patterns: List[str]  # File patterns for test files
    skip_patterns: List[str]  # Patterns that indicate skip/ignore
    confidence: float  # 0.0 to 1.0


class LanguageDetector:
    """
    Detects programming language and testing framework.

    Strategy:
    1. Check for framework-specific config files (package.json, Cargo.toml, etc.)
    2. Analyze file extensions (.py, .js, .go, .rs, etc.)
    3. Check for test directories (tests/, __tests__/, test/)
    4. Return LanguageInfo with appropriate commands
    """

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)

    def detect(self) -> LanguageInfo:
        """
        Detect language and return configuration.

        Returns:
            LanguageInfo with detected language and test commands
        """
        # Try each detection strategy in order of specificity
        # TypeScript before JavaScript (TypeScript is more specific)
        detectors = [
            self._detect_python,
            self._detect_typescript,  # Check TypeScript before JavaScript
            self._detect_javascript,
            self._detect_go,
            self._detect_rust,
            self._detect_java,
            self._detect_ruby,
            self._detect_csharp,
        ]

        for detector in detectors:
            result = detector()
            if result and result.confidence > 0.0:  # Lower threshold
                return result

        # Default fallback
        return LanguageInfo(
            language="unknown",
            framework=None,
            test_command="echo 'No test framework detected'",
            coverage_command=None,
            test_patterns=["test_*.py", "*_test.py", "*.test.js"],
            skip_patterns=[],
            confidence=0.0,
        )

    def _detect_python(self) -> Optional[LanguageInfo]:
        """Detect Python projects with pytest or unittest."""
        markers = [
            ("pyproject.toml", 1.0),
            ("setup.py", 0.9),
            ("requirements.txt", 0.7),
            ("pytest.ini", 1.0),
            (".pytest.ini", 1.0),
        ]

        confidence = self._calculate_confidence(markers)

        if confidence > 0.0:
            # Check if pytest is available
            has_pytest = (
                self._file_contains("pyproject.toml", "pytest") or
                (self.project_path / "pytest.ini").exists() or
                (self.project_path / ".pytest.ini").exists()
            )

            return LanguageInfo(
                language="python",
                framework="pytest" if has_pytest else "unittest",
                test_command="pytest -v" if has_pytest else "python -m unittest",
                coverage_command="pytest --cov" if has_pytest else "coverage run -m unittest",
                test_patterns=["test_*.py", "*_test.py", "tests/**/*.py"],
                skip_patterns=[
                    "@skip",
                    "@skipif",
                    "@pytest.mark.skip",
                    "@pytest.mark.skipif",
                    "@unittest.skip",
                ],
                confidence=confidence,
            )

        return None

    def _detect_javascript(self) -> Optional[LanguageInfo]:
        """Detect JavaScript projects with Jest, Vitest, or Mocha."""
        package_json = self.project_path / "package.json"

        if not package_json.exists():
            return None

        try:
            with open(package_json, "r") as f:
                data = json.load(f)

            dev_deps = data.get("devDependencies", {})
            deps = data.get("dependencies", {})
            all_deps = {**deps, **dev_deps}

            # Detect framework
            if "jest" in all_deps:
                framework = "jest"
                test_cmd = "npm test"
                cov_cmd = "npm test -- --coverage"
            elif "vitest" in all_deps:
                framework = "vitest"
                test_cmd = "npm test"
                cov_cmd = "npm test -- --coverage"
            elif "mocha" in all_deps:
                framework = "mocha"
                test_cmd = "npm test"
                cov_cmd = "nyc npm test"
            else:
                framework = None
                test_cmd = "npm test"
                cov_cmd = None

            return LanguageInfo(
                language="javascript",
                framework=framework,
                test_command=test_cmd,
                coverage_command=cov_cmd,
                test_patterns=["*.test.js", "*.spec.js", "__tests__/**/*.js"],
                skip_patterns=[
                    "it.skip",
                    "test.skip",
                    "describe.skip",
                    "xit",
                    "xtest",
                    "xdescribe",
                ],
                confidence=0.9,
            )

        except (json.JSONDecodeError, IOError):
            return None

    def _detect_typescript(self) -> Optional[LanguageInfo]:
        """Detect TypeScript projects."""
        tsconfig = self.project_path / "tsconfig.json"
        package_json = self.project_path / "package.json"

        if not tsconfig.exists():
            return None

        # TypeScript uses same frameworks as JavaScript
        js_info = self._detect_javascript()

        if js_info:
            js_info.language = "typescript"
            js_info.test_patterns = [
                "*.test.ts",
                "*.spec.ts",
                "__tests__/**/*.ts",
            ]
            return js_info

        return LanguageInfo(
            language="typescript",
            framework=None,
            test_command="npm test",
            coverage_command=None,
            test_patterns=["*.test.ts", "*.spec.ts", "__tests__/**/*.ts"],
            skip_patterns=[
                "it.skip",
                "test.skip",
                "describe.skip",
                "xit",
                "xtest",
            ],
            confidence=0.8,
        )

    def _detect_go(self) -> Optional[LanguageInfo]:
        """Detect Go projects."""
        go_mod = self.project_path / "go.mod"

        if go_mod.exists():
            return LanguageInfo(
                language="go",
                framework="go test",
                test_command="go test ./... -v",
                coverage_command="go test ./... -cover",
                test_patterns=["*_test.go"],
                skip_patterns=["t.Skip(", "testing.Skip(", "// +build ignore"],
                confidence=1.0,
            )

        return None

    def _detect_rust(self) -> Optional[LanguageInfo]:
        """Detect Rust projects."""
        cargo_toml = self.project_path / "Cargo.toml"

        if cargo_toml.exists():
            return LanguageInfo(
                language="rust",
                framework="cargo test",
                test_command="cargo test",
                coverage_command="cargo tarpaulin --out Xml",
                test_patterns=["tests/**/*.rs", "src/**/*.rs"],
                skip_patterns=["#[ignore]", "#[cfg(test)]"],
                confidence=1.0,
            )

        return None

    def _detect_java(self) -> Optional[LanguageInfo]:
        """Detect Java projects with Maven or Gradle."""
        pom_xml = self.project_path / "pom.xml"
        build_gradle = self.project_path / "build.gradle"

        if pom_xml.exists():
            return LanguageInfo(
                language="java",
                framework="maven",
                test_command="mvn test",
                coverage_command="mvn jacoco:report",
                test_patterns=["**/Test*.java", "**/*Test.java"],
                skip_patterns=["@Ignore", "@Disabled"],
                confidence=1.0,
            )

        if build_gradle.exists():
            return LanguageInfo(
                language="java",
                framework="gradle",
                test_command="./gradlew test",
                coverage_command="./gradlew jacocoTestReport",
                test_patterns=["**/Test*.java", "**/*Test.java"],
                skip_patterns=["@Ignore", "@Disabled"],
                confidence=1.0,
            )

        return None

    def _detect_ruby(self) -> Optional[LanguageInfo]:
        """Detect Ruby projects with RSpec."""
        gemfile = self.project_path / "Gemfile"

        if gemfile.exists() and self._file_contains("Gemfile", "rspec"):
            return LanguageInfo(
                language="ruby",
                framework="rspec",
                test_command="bundle exec rspec",
                coverage_command="bundle exec rspec --format documentation",
                test_patterns=["spec/**/*_spec.rb"],
                skip_patterns=["skip", "pending", "xit"],
                confidence=0.9,
            )

        return None

    def _detect_csharp(self) -> Optional[LanguageInfo]:
        """Detect C# .NET projects."""
        csproj_files = list(self.project_path.glob("*.csproj"))

        if csproj_files:
            return LanguageInfo(
                language="csharp",
                framework="dotnet test",
                test_command="dotnet test",
                coverage_command="dotnet test /p:CollectCoverage=true",
                test_patterns=["**/*Tests.cs", "**/Test*.cs"],
                skip_patterns=["[Ignore]", "[Skip]"],
                confidence=1.0,
            )

        return None

    def _calculate_confidence(self, markers: List[tuple]) -> float:
        """
        Calculate confidence based on presence of marker files.

        Strategy: Return the highest weight of any found marker,
        with a bonus for multiple markers.

        Args:
            markers: List of (filename, weight) tuples

        Returns:
            Confidence score 0.0 to 1.0
        """
        found_markers = []

        for filename, weight in markers:
            if (self.project_path / filename).exists():
                found_markers.append(weight)

        if not found_markers:
            return 0.0

        # Base confidence is the highest marker weight
        base_confidence = max(found_markers)

        # Bonus for multiple markers (up to +0.2)
        marker_bonus = min(0.2, (len(found_markers) - 1) * 0.1)

        return min(1.0, base_confidence + marker_bonus)

    def _file_contains(self, filename: str, text: str) -> bool:
        """Check if a file contains specific text."""
        file_path = self.project_path / filename

        if not file_path.exists():
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return text in f.read()
        except (IOError, UnicodeDecodeError):
            return False
