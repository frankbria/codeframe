"""
Unit tests for skip decorator detection tool.

These tests verify that the skip detector correctly identifies and reports
skip decorators in test files.

Test Coverage:
- T012: @skip detection
- T013: @skipif detection
- T014: @pytest.mark.skip detection
- T015: Skip with no reason (violation)
- T016: Skip with strong justification (allowed if policy changes)
- T017: Nested decorators handling
- T018: Non-test file handling (no false positives)
- T019: Performance <100ms on large files
"""

import ast
import tempfile
import time
from pathlib import Path

import pytest

# Import the skip detector module using importlib (due to hyphen in filename)
import importlib.util

scripts_dir = Path(__file__).parent.parent.parent / "scripts"
script_path = scripts_dir / "detect-skip-abuse.py"

spec = importlib.util.spec_from_file_location("detect_skip_abuse", script_path)
detect_skip_abuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(detect_skip_abuse)

SkipDetectorVisitor = detect_skip_abuse.SkipDetectorVisitor
check_file = detect_skip_abuse.check_file
is_test_file = detect_skip_abuse.is_test_file
format_violation = detect_skip_abuse.format_violation


class TestSkipDetection:
    """Test basic skip decorator detection."""

    def test_detects_simple_skip_decorator(self):
        """T012: Test @skip detection"""
        code = """
import pytest

@skip
def test_example():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.violations) == 1
        assert "@skip" in visitor.violations[0]["decorator"]

    def test_detects_skipif_decorator(self):
        """T013: Test @skipif detection"""
        code = """
import pytest

@skipif(sys.version_info < (3, 10))
def test_example():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.violations) == 1
        assert "@skipif" in visitor.violations[0]["decorator"]

    def test_detects_pytest_mark_skip(self):
        """T014: Test @pytest.mark.skip detection"""
        code = """
import pytest

@pytest.mark.skip
def test_example():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.violations) == 1
        assert "pytest.mark.skip" in visitor.violations[0]["decorator"]

    def test_detects_skip_with_no_reason(self):
        """T015: Test skip with no reason (violation)"""
        code = """
import pytest

@pytest.mark.skip
def test_example():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.violations) == 1
        violation = visitor.violations[0]
        assert violation["reason"] is None or violation["reason"] == ""

    def test_allows_skip_with_strong_justification(self):
        """T016: Test skip with strong justification (allowed if policy changes)"""
        code = """
import pytest

@pytest.mark.skip(reason="Blocked by external API downtime - Issue #123")
def test_example():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)

        # Currently all skips are detected - policy can be changed later
        assert len(visitor.violations) == 1
        violation = visitor.violations[0]
        assert "Blocked by external API downtime" in violation["reason"]

    def test_detects_nested_decorators(self):
        """T017: Test nested decorators handling"""
        code = """
import pytest

@pytest.mark.asyncio
@pytest.mark.skip(reason="TODO")
def test_example():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)

        assert len(visitor.violations) == 1
        assert "pytest.mark.skip" in visitor.violations[0]["decorator"]

    def test_handles_non_test_files(self):
        """T018: Test non-test file handling (no false positives)"""
        # Even though this contains "skip", it's not a test file
        # and shouldn't trigger violations
        assert not is_test_file("utils/helper.py")
        assert not is_test_file("src/processor.py")
        assert is_test_file("tests/test_example.py")
        assert is_test_file("test_foo.py")

    def test_performance_on_large_files(self):
        """T019: Test performance <100ms on large files"""
        # Create a large test file with 500 test functions
        code_parts = ["import pytest\n\n"]
        for i in range(500):
            code_parts.append(
                f"""
def test_example_{i}():
    assert True
"""
            )

        code = "".join(code_parts)

        start = time.time()
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("large_test.py")
        visitor.visit(tree)
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert elapsed < 100, f"Performance too slow: {elapsed}ms (threshold: 100ms)"


class TestSkipDetectorHelpers:
    """Test helper functions for skip detection."""

    def test_is_test_file_recognizes_test_patterns(self):
        """Test that is_test_file correctly identifies test files."""
        assert is_test_file("tests/test_foo.py")
        assert is_test_file("test_bar.py")
        assert is_test_file("tests/integration/test_api.py")
        assert not is_test_file("src/main.py")
        assert not is_test_file("utils/helper.py")

    def test_check_file_returns_violations(self):
        """Test that check_file returns violations for test files with skips."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", prefix="test_", delete=False) as f:
            f.write(
                """
import pytest

@pytest.mark.skip
def test_example():
    pass
"""
            )
            f.flush()
            temp_path = f.name

        try:
            violations = check_file(temp_path)
            assert len(violations) > 0
        finally:
            Path(temp_path).unlink()

    def test_format_violation_produces_readable_output(self):
        """Test that format_violation produces human-readable output."""
        violation = {
            "file": "tests/test_example.py",
            "line": 10,
            "function": "test_authentication",
            "decorator": "@pytest.mark.skip",
            "reason": "TODO",
        }

        formatted = format_violation(violation)
        assert "tests/test_example.py" in formatted
        assert "10" in formatted
        assert "test_authentication" in formatted
        assert "@pytest.mark.skip" in formatted


class TestSkipDetectorEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_empty_file(self):
        """Test that empty files are handled gracefully."""
        code = ""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("empty.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 0

    def test_handles_file_with_only_comments(self):
        """Test files with only comments."""
        code = """
# This is a comment
# Another comment
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("comments.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 0

    def test_detects_multiple_skips_in_one_file(self):
        """Test detection of multiple skip decorators in a single file."""
        code = """
import pytest

@pytest.mark.skip
def test_one():
    pass

@pytest.mark.skip(reason="TODO")
def test_two():
    pass

@skip
def test_three():
    pass
"""
        tree = ast.parse(code)
        visitor = SkipDetectorVisitor("test.py")
        visitor.visit(tree)
        assert len(visitor.violations) == 3
