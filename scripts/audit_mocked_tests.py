#!/usr/bin/env python3
"""
Test Mocking Audit Script

Scans all test files to identify excessive mocking patterns and generates
a report categorizing tests by their mocking severity.

Categories:
- HIGH: Tests that mock core functionality being tested (false positives)
- MEDIUM: Tests with heavy mocking that may hide integration issues
- LOW: Tests with appropriate mocking of external services only

Usage:
    python scripts/audit_mocked_tests.py [--output report.md] [--json]
"""

import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MockPattern:
    """Represents a detected mock pattern in a test."""

    name: str
    line_number: int
    mock_type: str  # 'patch', 'Mock', 'MagicMock', 'AsyncMock', 'patch.object'
    target: str  # What is being mocked
    severity: str  # 'high', 'medium', 'low'
    reason: str


@dataclass
class TestInfo:
    """Information about a single test function."""

    name: str
    class_name: str | None
    file_path: str
    line_number: int
    mock_patterns: list[MockPattern] = field(default_factory=list)
    severity: str = "low"
    recommendation: str = ""


@dataclass
class AuditResult:
    """Complete audit result for all test files."""

    tests: list[TestInfo] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    files_analyzed: int = 0


# Patterns that indicate excessive mocking (mocking core functionality)
CORE_FUNCTIONALITY_PATTERNS = [
    # Database operations - should use real in-memory database
    ("codeframe.persistence.database.Database", "database operations"),
    ("db.create_", "database creation methods"),
    ("db.get_", "database retrieval methods"),
    ("db.update_", "database update methods"),
    ("db.save_", "database save methods"),
    # Agent core methods - should test actual implementation
    ("execute_task", "task execution (core agent functionality)"),
    ("_record_token_usage", "token tracking"),
    ("assign_task", "task assignment"),
    ("apply_file_changes", "file operations"),
    # Quality gates - should test actual subprocess calls in integration
    ("subprocess.run", "quality gate subprocess execution"),
    ("run_tests_gate", "quality gate methods"),
    ("run_type_check_gate", "quality gate methods"),
    ("run_all_gates", "quality gate methods"),
]

# Patterns that are acceptable to mock (external services)
ACCEPTABLE_MOCK_PATTERNS = [
    ("AsyncAnthropic", "external LLM API"),
    ("anthropic.AsyncAnthropic", "external LLM API"),
    ("AnthropicProvider", "external LLM API"),
    ("AsyncOpenAI", "external LLM API"),
    ("openai.AsyncOpenAI", "external LLM API"),
    ("github.Github", "external GitHub API"),
    ("requests.", "external HTTP requests"),
    ("httpx.", "external HTTP requests"),
    ("aiohttp.", "external HTTP requests"),
    ("smtp", "external email service"),
    ("os.environ", "environment variables"),
    ("ANTHROPIC_API_KEY", "API key environment variable"),
]

# Tests that mock implementation being tested (false positives)
FALSE_POSITIVE_INDICATORS = [
    "patch.object",  # Mocking the method being tested
    "return_value",  # Setting return value of what should be tested
]


class TestMockAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze mock usage in test files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.current_class: str | None = None
        self.current_function: str | None = None
        self.tests: list[TestInfo] = []
        self.current_test_mocks: list[MockPattern] = []
        self.imports: dict[str, str] = {}  # alias -> full name

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            self.imports[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = node.module or ""
        for alias in node.names:
            name = alias.asname if alias.asname else alias.name
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imports[name] = full_name
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test_"):
            self.generic_visit(node)
            return

        self.current_function = node.name
        self.current_test_mocks = []

        # Check decorators for patches
        for decorator in node.decorator_list:
            self._analyze_decorator(decorator)

        # Visit function body for with statements and Mock usage
        self.generic_visit(node)

        # Create test info
        test_info = TestInfo(
            name=node.name,
            class_name=self.current_class,
            file_path=self.file_path,
            line_number=node.lineno,
            mock_patterns=self.current_test_mocks.copy(),
        )

        # Calculate severity based on mock patterns
        test_info.severity, test_info.recommendation = self._calculate_severity(test_info)
        self.tests.append(test_info)

        self.current_function = None
        self.current_test_mocks = []

    def _analyze_decorator(self, decorator: ast.expr) -> None:
        """Analyze a decorator for mock patterns."""
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Attribute):
                if func.attr == "patch":
                    self._handle_patch_decorator(decorator)
            elif isinstance(func, ast.Name) and func.id == "patch":
                self._handle_patch_decorator(decorator)

    def _handle_patch_decorator(self, call: ast.Call) -> None:
        """Handle @patch decorator."""
        if call.args:
            target = self._get_string_value(call.args[0])
            if target:
                pattern = self._create_mock_pattern(target, call.lineno, "patch")
                self.current_test_mocks.append(pattern)

    def visit_With(self, node: ast.With) -> Any:
        """Analyze with statements for patch context managers."""
        for item in node.items:
            self._analyze_with_item(item)
        self.generic_visit(node)

    def _analyze_with_item(self, item: ast.withitem) -> None:
        """Analyze a single with item."""
        if isinstance(item.context_expr, ast.Call):
            call = item.context_expr
            func = call.func

            # Check for patch()
            if isinstance(func, ast.Attribute):
                if func.attr in ("patch", "object"):
                    target = self._get_patch_target(call)
                    if target:
                        pattern = self._create_mock_pattern(
                            target, call.lineno, f"patch.{func.attr}"
                        )
                        self.current_test_mocks.append(pattern)
            elif isinstance(func, ast.Name) and func.id == "patch":
                target = self._get_patch_target(call)
                if target:
                    pattern = self._create_mock_pattern(target, call.lineno, "patch")
                    self.current_test_mocks.append(pattern)

    def _get_patch_target(self, call: ast.Call) -> str | None:
        """Extract the target string from a patch call."""
        if call.args:
            return self._get_string_value(call.args[0])
        return None

    def _get_string_value(self, node: ast.expr) -> str | None:
        """Extract string value from an AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def visit_Call(self, node: ast.Call) -> Any:
        """Analyze function calls for Mock/MagicMock/AsyncMock usage."""
        if self.current_function and self.current_function.startswith("test_"):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in ("Mock", "MagicMock", "AsyncMock"):
                    pattern = MockPattern(
                        name=func.id,
                        line_number=node.lineno,
                        mock_type=func.id,
                        target="unspecified",
                        severity="medium",
                        reason="Direct Mock object creation",
                    )
                    self.current_test_mocks.append(pattern)
            elif isinstance(func, ast.Attribute):
                if func.attr in ("Mock", "MagicMock", "AsyncMock"):
                    pattern = MockPattern(
                        name=func.attr,
                        line_number=node.lineno,
                        mock_type=func.attr,
                        target="unspecified",
                        severity="medium",
                        reason="Direct Mock object creation",
                    )
                    self.current_test_mocks.append(pattern)

        self.generic_visit(node)

    def _create_mock_pattern(self, target: str, line_number: int, mock_type: str) -> MockPattern:
        """Create a MockPattern with appropriate severity."""
        severity = "low"
        reason = "Acceptable external service mock"

        # Check if it's mocking core functionality
        for pattern, desc in CORE_FUNCTIONALITY_PATTERNS:
            if pattern in target:
                severity = "high"
                reason = f"Mocking core functionality: {desc}"
                break

        # Check if it's acceptable
        if severity != "high":
            is_acceptable = False
            for pattern, desc in ACCEPTABLE_MOCK_PATTERNS:
                if pattern in target:
                    is_acceptable = True
                    reason = f"Acceptable mock: {desc}"
                    break

            if not is_acceptable and severity != "high":
                severity = "medium"
                reason = f"Potentially excessive mock: {target}"

        return MockPattern(
            name=target.split(".")[-1],
            line_number=line_number,
            mock_type=mock_type,
            target=target,
            severity=severity,
            reason=reason,
        )

    def _calculate_severity(self, test: TestInfo) -> tuple[str, str]:
        """Calculate overall test severity and recommendation."""
        if not test.mock_patterns:
            return "low", "No mocking detected - good unit test"

        high_count = sum(1 for p in test.mock_patterns if p.severity == "high")
        medium_count = sum(1 for p in test.mock_patterns if p.severity == "medium")

        if high_count > 0:
            return "high", "Rewrite as integration test with real implementations"
        elif medium_count > 2:
            return "medium", "Consider reducing mocking or converting to integration test"
        elif medium_count > 0:
            return "low", "Acceptable mocking level for unit test"
        else:
            return "low", "Only mocking external services - good practice"


def analyze_file(file_path: Path) -> list[TestInfo]:
    """Analyze a single test file for mock patterns."""
    try:
        source = file_path.read_text()
        tree = ast.parse(source)
        analyzer = TestMockAnalyzer(str(file_path))
        analyzer.visit(tree)
        return analyzer.tests
    except SyntaxError as e:
        print(f"Syntax error in {file_path}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}", file=sys.stderr)
        return []


def scan_test_directory(test_dir: Path) -> AuditResult:
    """Scan all test files in a directory."""
    result = AuditResult()
    result.summary = {"high": 0, "medium": 0, "low": 0, "total_tests": 0, "total_mocks": 0}

    test_files = list(test_dir.rglob("test_*.py")) + list(test_dir.rglob("*_test.py"))
    result.files_analyzed = len(test_files)

    for file_path in sorted(test_files):
        tests = analyze_file(file_path)
        result.tests.extend(tests)

        for test in tests:
            result.summary[test.severity] += 1
            result.summary["total_tests"] += 1
            result.summary["total_mocks"] += len(test.mock_patterns)

    return result


def generate_markdown_report(result: AuditResult) -> str:
    """Generate a markdown report from audit results."""
    lines = [
        "# Test Mocking Audit Report",
        "",
        "## Summary",
        "",
        f"- **Files Analyzed**: {result.files_analyzed}",
        f"- **Total Tests**: {result.summary['total_tests']}",
        f"- **Total Mock Patterns**: {result.summary['total_mocks']}",
        "",
        "### Severity Distribution",
        "",
        f"- **HIGH** (needs rewrite): {result.summary['high']}",
        f"- **MEDIUM** (review needed): {result.summary['medium']}",
        f"- **LOW** (acceptable): {result.summary['low']}",
        "",
        "---",
        "",
    ]

    # Group tests by severity
    high_tests = [t for t in result.tests if t.severity == "high"]
    medium_tests = [t for t in result.tests if t.severity == "medium"]

    if high_tests:
        lines.extend([
            "## HIGH Severity Tests (Needs Rewrite)",
            "",
            "These tests mock core functionality and should be rewritten as integration tests.",
            "",
        ])
        for test in high_tests:
            lines.extend(_format_test_entry(test))

    if medium_tests:
        lines.extend([
            "## MEDIUM Severity Tests (Review Needed)",
            "",
            "These tests have heavy mocking that may hide integration issues.",
            "",
        ])
        for test in medium_tests:
            lines.extend(_format_test_entry(test))

    lines.extend([
        "",
        "---",
        "",
        "## Recommendations",
        "",
        "### For HIGH Severity Tests:",
        "1. Convert to integration tests in `tests/integration/`",
        "2. Use real database fixtures (`:memory:` SQLite)",
        "3. Use real file operations in temp directories",
        "4. Only mock external APIs (Anthropic, OpenAI, GitHub)",
        "",
        "### For MEDIUM Severity Tests:",
        "1. Review if mocking is necessary",
        "2. Consider using real implementations where possible",
        "3. Document why mocking is needed if kept",
        "",
        "### General Guidelines:",
        "- Unit tests: Focus on logic, mock external I/O only",
        "- Integration tests: Use real components, mock only external services",
        "- Never mock `execute_task()`, database operations, or quality gates in unit tests",
        "",
    ])

    return "\n".join(lines)


def _format_test_entry(test: TestInfo) -> list[str]:
    """Format a single test entry for the report."""
    class_prefix = f"{test.class_name}." if test.class_name else ""
    lines = [
        f"### `{class_prefix}{test.name}`",
        f"- **File**: `{test.file_path}:{test.line_number}`",
        f"- **Recommendation**: {test.recommendation}",
        "- **Mock Patterns**:",
    ]

    for pattern in test.mock_patterns:
        severity_marker = {"high": "**", "medium": "", "low": ""}.get(pattern.severity, "")
        lines.append(
            f"  - {severity_marker}`{pattern.target}`{severity_marker} "
            f"({pattern.mock_type}, line {pattern.line_number}): {pattern.reason}"
        )

    lines.append("")
    return lines


def generate_json_report(result: AuditResult) -> str:
    """Generate a JSON report from audit results."""
    data = {
        "summary": result.summary,
        "files_analyzed": result.files_analyzed,
        "tests": [
            {
                "name": t.name,
                "class_name": t.class_name,
                "file_path": t.file_path,
                "line_number": t.line_number,
                "severity": t.severity,
                "recommendation": t.recommendation,
                "mock_patterns": [
                    {
                        "target": p.target,
                        "mock_type": p.mock_type,
                        "line_number": p.line_number,
                        "severity": p.severity,
                        "reason": p.reason,
                    }
                    for p in t.mock_patterns
                ],
            }
            for t in result.tests
        ],
    }
    return json.dumps(data, indent=2)


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Audit test files for excessive mocking")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="test_audit_report.md",
        help="Output file path (default: test_audit_report.md)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format instead of Markdown",
    )
    parser.add_argument(
        "--test-dir",
        "-d",
        type=str,
        default="tests",
        help="Test directory to scan (default: tests)",
    )

    args = parser.parse_args()

    # Find project root (where tests/ directory is)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    test_dir = project_root / args.test_dir

    if not test_dir.exists():
        print(f"Test directory not found: {test_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning test files in {test_dir}...")
    result = scan_test_directory(test_dir)

    if args.json:
        report = generate_json_report(result)
        output_file = args.output.replace(".md", ".json") if args.output.endswith(".md") else args.output
    else:
        report = generate_markdown_report(result)
        output_file = args.output

    output_path = project_root / output_file
    output_path.write_text(report)
    print(f"Report written to {output_path}")

    # Print summary
    print("\n=== Summary ===")
    print(f"Files analyzed: {result.files_analyzed}")
    print(f"Total tests: {result.summary['total_tests']}")
    print(f"HIGH severity: {result.summary['high']}")
    print(f"MEDIUM severity: {result.summary['medium']}")
    print(f"LOW severity: {result.summary['low']}")


if __name__ == "__main__":
    main()
