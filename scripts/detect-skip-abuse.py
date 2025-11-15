#!/usr/bin/env python3
"""
Skip Decorator Detection Tool

This tool uses Python's AST (Abstract Syntax Tree) module to detect skip
decorators in test files. It helps prevent AI agents from circumventing
failing tests by adding skip decorators.

Usage:
    python scripts/detect-skip-abuse.py [path]
    python scripts/detect-skip-abuse.py tests/
    python scripts/detect-skip-abuse.py tests/test_example.py

Exit Codes:
    0: No violations found
    1: Skip decorators detected

Based on patterns from scripts/verify_migration_001.py
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Dict, List, Optional


class SkipDetectorVisitor(ast.NodeVisitor):
    """
    AST visitor that detects skip decorators in test functions.

    Detects the following patterns:
    - @skip
    - @skipif
    - @pytest.mark.skip
    - @pytest.mark.skipif
    """

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: List[Dict[str, any]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition nodes and check for skip decorators."""
        # Only check functions that look like tests
        if not node.name.startswith("test_"):
            self.generic_visit(node)
            return

        for decorator in node.decorator_list:
            skip_info = self._check_decorator_for_skip(decorator)
            if skip_info:
                violation = {
                    "file": self.filename,
                    "line": node.lineno,
                    "function": node.name,
                    "decorator": skip_info["decorator"],
                    "reason": skip_info.get("reason"),
                }
                self.violations.append(violation)

        self.generic_visit(node)

    def _check_decorator_for_skip(
        self, decorator: ast.expr
    ) -> Optional[Dict[str, any]]:
        """
        Check if a decorator is a skip decorator.

        Returns:
            Dict with decorator info if it's a skip, None otherwise
        """
        # Case 1: @skip or @skipif (bare names)
        if isinstance(decorator, ast.Name):
            if decorator.id in ("skip", "skipif"):
                return {"decorator": f"@{decorator.id}", "reason": None}

        # Case 2: @skip(reason="...") or @skipif(condition, reason="...")
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                if decorator.func.id in ("skip", "skipif"):
                    reason = self._extract_reason(decorator)
                    return {"decorator": f"@{decorator.func.id}", "reason": reason}

            # Case 3: @pytest.mark.skip or @pytest.mark.skipif
            elif isinstance(decorator.func, ast.Attribute):
                if self._is_pytest_mark_skip(decorator.func):
                    reason = self._extract_reason(decorator)
                    decorator_name = f"@pytest.mark.{decorator.func.attr}"
                    return {"decorator": decorator_name, "reason": reason}

        # Case 4: @pytest.mark.skip (without call)
        elif isinstance(decorator, ast.Attribute):
            if self._is_pytest_mark_skip(decorator):
                decorator_name = f"@pytest.mark.{decorator.attr}"
                return {"decorator": decorator_name, "reason": None}

        return None

    def _is_pytest_mark_skip(self, attr: ast.Attribute) -> bool:
        """Check if an attribute is pytest.mark.skip or pytest.mark.skipif."""
        if attr.attr not in ("skip", "skipif"):
            return False

        # Check if it's pytest.mark.skip or pytest.mark.skipif
        if isinstance(attr.value, ast.Attribute):
            if attr.value.attr == "mark" and isinstance(attr.value.value, ast.Name):
                if attr.value.value.id == "pytest":
                    return True

        return False

    def _extract_reason(self, call: ast.Call) -> Optional[str]:
        """Extract the reason argument from a skip decorator call."""
        # Check keyword arguments
        for keyword in call.keywords:
            if keyword.arg == "reason":
                if isinstance(keyword.value, ast.Constant):
                    return keyword.value.value

        # Check positional arguments (for skipif, reason is usually second arg)
        if len(call.args) >= 2:
            if isinstance(call.args[1], ast.Constant):
                return call.args[1].value

        return None


def is_test_file(filepath: str) -> bool:
    """
    Check if a file is a test file.

    Test files are identified by:
    - Filename starts with 'test_'
    - File is in a 'tests/' directory
    """
    path = Path(filepath)
    return path.name.startswith("test_") or "tests" in path.parts


def check_file(filepath: str) -> List[Dict[str, any]]:
    """
    Check a single file for skip decorator abuse.

    Args:
        filepath: Path to the Python file to check

    Returns:
        List of violations found
    """
    if not is_test_file(filepath):
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename=filepath)
        visitor = SkipDetectorVisitor(filepath)
        visitor.visit(tree)
        return visitor.violations

    except SyntaxError as e:
        print(f"Warning: Syntax error in {filepath}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Warning: Error checking {filepath}: {e}", file=sys.stderr)
        return []


def format_violation(violation: Dict[str, any]) -> str:
    """
    Format a violation for display.

    Args:
        violation: Violation dictionary

    Returns:
        Formatted string
    """
    reason = violation.get("reason")
    reason_str = f' (reason: "{reason}")' if reason else " (no reason provided)"

    return (
        f"{violation['file']}:{violation['line']} - "
        f"{violation['function']} - "
        f"{violation['decorator']}{reason_str}"
    )


def print_summary(violations: List[Dict[str, any]]) -> None:
    """
    Print a summary of violations found.

    Args:
        violations: List of violations
    """
    if not violations:
        print("✅ No skip decorators found")
        return

    print(f"❌ Found {len(violations)} skip decorator(s):\n")
    for violation in violations:
        print(f"  {format_violation(violation)}")

    print(
        "\n⚠️  Skip decorators prevent tests from running and hide failures."
    )
    print("   Instead of skipping tests:")
    print("   1. Fix the failing test")
    print("   2. Remove the test if it's no longer needed")
    print(
        "   3. If blocked by external issue, document thoroughly with issue number"
    )


def main() -> int:
    """
    Main entry point for the skip detector.

    Returns:
        Exit code (0 = no violations, 1 = violations found)
    """
    parser = argparse.ArgumentParser(
        description="Detect skip decorator abuse in test files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Check all test files in tests/
  %(prog)s tests/             # Check all test files in tests/
  %(prog)s tests/test_api.py  # Check specific file

Exit codes:
  0 - No violations found
  1 - Skip decorators detected
""",
    )

    parser.add_argument(
        "path",
        nargs="?",
        default="tests",
        help="Path to check (file or directory, default: tests/)",
    )

    args = parser.parse_args()

    # Collect all violations
    all_violations: List[Dict[str, any]] = []

    path = Path(args.path)

    if path.is_file():
        violations = check_file(str(path))
        all_violations.extend(violations)
    elif path.is_dir():
        # Recursively check all .py files
        for py_file in path.rglob("*.py"):
            violations = check_file(str(py_file))
            all_violations.extend(violations)
    else:
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        return 1

    # Print summary
    print_summary(all_violations)

    # Return exit code
    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
