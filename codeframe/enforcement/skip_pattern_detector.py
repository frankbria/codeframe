"""
Multi-Language Skip Pattern Detector

Detects skip/ignore patterns across multiple programming languages.
This is the language-agnostic version of scripts/detect-skip-abuse.py.

Supports:
- Python: @skip, @pytest.mark.skip, @unittest.skip
- JavaScript/TypeScript: it.skip, test.skip, describe.skip, xit, xtest
- Go: t.Skip(), testing.Skip(), build tags
- Rust: #[ignore]
- Java: @Ignore, @Disabled
- Ruby: skip, pending, xit
- C#: [Ignore], [Skip]
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict
import ast

from .language_detector import LanguageDetector, LanguageInfo


@dataclass
class SkipViolation:
    """Represents a detected skip pattern."""

    file: str  # File path
    line: int  # Line number
    pattern: str  # The skip pattern found (e.g., "@skip", "it.skip")
    context: str  # Surrounding code context
    reason: Optional[str]  # Reason if provided
    severity: str  # "error" or "warning"


class SkipPatternDetector:
    """
    Detects skip patterns across multiple languages.

    Usage:
        detector = SkipPatternDetector(project_path="/path/to/project")
        violations = detector.detect_all()

        for v in violations:
            print(f"{v.file}:{v.line} - {v.pattern}")
    """

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.language_detector = LanguageDetector(project_path)
        self.language_info: Optional[LanguageInfo] = None

    def detect_all(self) -> List[SkipViolation]:
        """
        Detect all skip violations in the project.

        Returns:
            List of SkipViolation objects
        """
        # Detect language first
        if not self.language_info:
            self.language_info = self.language_detector.detect()

        violations = []

        # Find test files based on language patterns
        test_files = self._find_test_files()

        # Check each test file
        for test_file in test_files:
            file_violations = self._check_file(test_file)
            violations.extend(file_violations)

        return violations

    def _find_test_files(self) -> List[Path]:
        """Find test files based on detected language patterns."""
        if not self.language_info:
            return []

        test_files = []

        for pattern in self.language_info.test_patterns:
            # Handle glob patterns
            if "**" in pattern:
                test_files.extend(self.project_path.rglob(pattern.replace("**", "*")))
            else:
                test_files.extend(self.project_path.glob(pattern))

        return test_files

    def _check_file(self, file_path: Path) -> List[SkipViolation]:
        """
        Check a single file for skip patterns.

        Args:
            file_path: Path to file to check

        Returns:
            List of violations found in this file
        """
        if not self.language_info:
            return []

        language = self.language_info.language

        # Use language-specific checker
        if language == "python":
            return self._check_python_file(file_path)
        elif language in ["javascript", "typescript"]:
            return self._check_javascript_file(file_path)
        elif language == "go":
            return self._check_go_file(file_path)
        elif language == "rust":
            return self._check_rust_file(file_path)
        elif language == "java":
            return self._check_java_file(file_path)
        elif language == "ruby":
            return self._check_ruby_file(file_path)
        elif language == "csharp":
            return self._check_csharp_file(file_path)
        else:
            # Generic regex-based checking
            return self._check_generic_file(file_path)

    def _check_python_file(self, file_path: Path) -> List[SkipViolation]:
        """Check Python file using AST parsing."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))

            # Use AST visitor to find decorators
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        skip_info = self._check_python_decorator(decorator)
                        if skip_info:
                            violations.append(
                                SkipViolation(
                                    file=str(file_path),
                                    line=node.lineno,
                                    pattern=skip_info["pattern"],
                                    context=node.name,
                                    reason=skip_info.get("reason"),
                                    severity="error",
                                )
                            )

        except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_python_decorator(self, decorator: ast.expr) -> Optional[Dict]:
        """Check if a Python decorator is a skip decorator."""
        # Case 1: @skip or @skipif
        if isinstance(decorator, ast.Name):
            if decorator.id in ("skip", "skipif"):
                return {"pattern": f"@{decorator.id}", "reason": None}

        # Case 2: @skip(reason="...") or @skipif(...)
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                if decorator.func.id in ("skip", "skipif"):
                    reason = self._extract_reason_python(decorator)
                    return {"pattern": f"@{decorator.func.id}", "reason": reason}

            # Case 3: @pytest.mark.skip or @unittest.skip
            elif isinstance(decorator.func, ast.Attribute):
                if self._is_skip_attribute(decorator.func):
                    reason = self._extract_reason_python(decorator)
                    return {
                        "pattern": f"@{self._get_full_name(decorator.func)}",
                        "reason": reason,
                    }

        # Case 4: @pytest.mark.skip (without call)
        elif isinstance(decorator, ast.Attribute):
            if self._is_skip_attribute(decorator):
                return {"pattern": f"@{self._get_full_name(decorator)}", "reason": None}

        return None

    def _is_skip_attribute(self, attr: ast.Attribute) -> bool:
        """Check if attribute is a skip-related attribute."""
        if attr.attr in ("skip", "skipif"):
            # Check for pytest.mark.skip, unittest.skip
            if isinstance(attr.value, ast.Attribute):
                return True
            elif isinstance(attr.value, ast.Name):
                return attr.value.id in ("pytest", "unittest")
        return False

    def _get_full_name(self, attr: ast.Attribute) -> str:
        """Get full name of attribute (e.g., pytest.mark.skip)."""
        parts = [attr.attr]
        current = attr.value

        while isinstance(current, ast.Attribute):
            parts.insert(0, current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.insert(0, current.id)

        return ".".join(parts)

    def _extract_reason_python(self, call: ast.Call) -> Optional[str]:
        """Extract reason from Python skip decorator."""
        for keyword in call.keywords:
            if keyword.arg == "reason":
                if isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
        return None

    def _check_javascript_file(self, file_path: Path) -> List[SkipViolation]:
        """Check JavaScript/TypeScript file for skip patterns."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            patterns = [
                r"\bit\.skip\s*\(",
                r"\btest\.skip\s*\(",
                r"\bdescribe\.skip\s*\(",
                r"\bxit\s*\(",
                r"\bxtest\s*\(",
                r"\bxdescribe\s*\(",
            ]

            for line_num, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        violations.append(
                            SkipViolation(
                                file=str(file_path),
                                line=line_num,
                                pattern=pattern.replace(r"\b", "").replace(r"\s*\(", ""),
                                context=line.strip(),
                                reason=self._extract_reason_from_line(line),
                                severity="error",
                            )
                        )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_go_file(self, file_path: Path) -> List[SkipViolation]:
        """Check Go file for skip patterns."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            patterns = [
                r"t\.Skip\s*\(",
                r"testing\.Skip\s*\(",
                r"//\s*\+build\s+ignore",
            ]

            for line_num, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        violations.append(
                            SkipViolation(
                                file=str(file_path),
                                line=line_num,
                                pattern=pattern.replace(r"\s*\(", ""),
                                context=line.strip(),
                                reason=self._extract_reason_from_line(line),
                                severity="error",
                            )
                        )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_rust_file(self, file_path: Path) -> List[SkipViolation]:
        """Check Rust file for #[ignore] attribute."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            pattern = r"#\s*\[\s*ignore\s*\]"

            for line_num, line in enumerate(lines, start=1):
                if re.search(pattern, line):
                    violations.append(
                        SkipViolation(
                            file=str(file_path),
                            line=line_num,
                            pattern="#[ignore]",
                            context=line.strip(),
                            reason=None,
                            severity="error",
                        )
                    )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_java_file(self, file_path: Path) -> List[SkipViolation]:
        """Check Java file for @Ignore or @Disabled annotations."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            patterns = [r"@Ignore", r"@Disabled"]

            for line_num, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        violations.append(
                            SkipViolation(
                                file=str(file_path),
                                line=line_num,
                                pattern=pattern,
                                context=line.strip(),
                                reason=self._extract_reason_from_line(line),
                                severity="error",
                            )
                        )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_ruby_file(self, file_path: Path) -> List[SkipViolation]:
        """Check Ruby/RSpec file for skip patterns."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            patterns = [r"\bskip\s+", r"\bpending\s+", r"\bxit\s+"]

            for line_num, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        violations.append(
                            SkipViolation(
                                file=str(file_path),
                                line=line_num,
                                pattern=pattern.replace(r"\b", "").replace(r"\s+", ""),
                                context=line.strip(),
                                reason=self._extract_reason_from_line(line),
                                severity="error",
                            )
                        )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_csharp_file(self, file_path: Path) -> List[SkipViolation]:
        """Check C# file for [Ignore] or [Skip] attributes."""
        violations = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            patterns = [r"\[Ignore\]", r"\[Skip\]"]

            for line_num, line in enumerate(lines, start=1):
                for pattern in patterns:
                    if re.search(pattern, line):
                        violations.append(
                            SkipViolation(
                                file=str(file_path),
                                line=line_num,
                                pattern=pattern,
                                context=line.strip(),
                                reason=self._extract_reason_from_line(line),
                                severity="error",
                            )
                        )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _check_generic_file(self, file_path: Path) -> List[SkipViolation]:
        """Generic check using configured skip patterns."""
        violations = []

        if not self.language_info:
            return violations

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, start=1):
                for pattern in self.language_info.skip_patterns:
                    if pattern in line:
                        violations.append(
                            SkipViolation(
                                file=str(file_path),
                                line=line_num,
                                pattern=pattern,
                                context=line.strip(),
                                reason=None,
                                severity="warning",  # Lower severity for generic
                            )
                        )

        except (FileNotFoundError, UnicodeDecodeError):
            pass

        return violations

    def _extract_reason_from_line(self, line: str) -> Optional[str]:
        """Extract reason string from a line of code."""
        # Look for strings in quotes
        string_match = re.search(r'["\']([^"\']+)["\']', line)
        if string_match:
            return string_match.group(1)
        return None
