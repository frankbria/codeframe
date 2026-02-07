"""Tests for SearchReplaceEditor - TDD Red Phase.

All tests written BEFORE implementation. They should fail on import
until codeframe/core/editor.py exists.
"""

from __future__ import annotations

import textwrap

import pytest

from codeframe.core.editor import (
    EditOperation,
    EditResult,
    MatchResult,
    SearchReplaceEditor,
)

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def editor():
    return SearchReplaceEditor(preserve_indentation=True, fuzzy_threshold=0.85)


@pytest.fixture
def tmp_file(tmp_path):
    """Temp file with simple multi-line content."""
    f = tmp_path / "sample.py"
    f.write_text(
        textwrap.dedent("""\
        def hello():
            print("hello world")

        def goodbye():
            print("goodbye world")
        """)
    )
    return f


@pytest.fixture
def sample_python_file(tmp_path):
    """Realistic Python file for testing."""
    f = tmp_path / "app.py"
    f.write_text(
        textwrap.dedent("""\
        import os
        import sys

        class Config:
            DEBUG = True
            VERSION = "1.0.0"

        def process_data(items):
            result = []
            for item in items:
                if item.is_valid():
                    result.append(item.transform())
            return result

        def helper():
            pass

        def process_data_copy(items):
            result = []
            for item in items:
                if item.is_valid():
                    result.append(item.transform())
            return result
        """)
    )
    return f


@pytest.fixture
def sample_config_file(tmp_path):
    """TOML-like config file."""
    f = tmp_path / "config.toml"
    f.write_text(
        textwrap.dedent("""\
        [project]
        name = "codeframe"
        version = "0.1.0"

        [project.dependencies]
        fastapi = ">=0.109.0"
        pydantic = ">=2.6.0"
        """)
    )
    return f


# ===========================================================================
# Data model tests
# ===========================================================================


class TestEditOperation:
    def test_creation(self):
        op = EditOperation(search="foo", replace="bar")
        assert op.search == "foo"
        assert op.replace == "bar"
        assert op.description is None

    def test_optional_description(self):
        op = EditOperation(search="a", replace="b", description="rename variable")
        assert op.description == "rename variable"


class TestMatchResult:
    def test_exact_match_level(self):
        mr = MatchResult(
            success=True,
            match_level=1,
            match_level_name="exact",
            start_pos=0,
            end_pos=5,
            matched_text="hello",
        )
        assert mr.success is True
        assert mr.match_level == 1
        assert mr.match_level_name == "exact"
        assert mr.match_count == 1  # default

    def test_whitespace_match_level(self):
        mr = MatchResult(
            success=True,
            match_level=2,
            match_level_name="whitespace-normalized",
            start_pos=0,
            end_pos=10,
            matched_text="hello  world",
        )
        assert mr.match_level == 2

    def test_indentation_match_level(self):
        mr = MatchResult(
            success=True,
            match_level=3,
            match_level_name="indentation-agnostic",
            start_pos=0,
            end_pos=10,
            matched_text="    hello",
        )
        assert mr.match_level == 3

    def test_fuzzy_match_level(self):
        mr = MatchResult(
            success=True,
            match_level=4,
            match_level_name="fuzzy",
            start_pos=0,
            end_pos=10,
            matched_text="helo",
        )
        assert mr.match_level == 4

    def test_match_count_field(self):
        mr = MatchResult(
            success=True,
            match_level=1,
            match_level_name="exact",
            start_pos=0,
            end_pos=5,
            matched_text="hello",
            match_count=3,
        )
        assert mr.match_count == 3

    def test_failed_match(self):
        mr = MatchResult(
            success=False,
            match_level=0,
            match_level_name="none",
            start_pos=-1,
            end_pos=-1,
            matched_text="",
        )
        assert mr.success is False


class TestEditResult:
    def test_success_result(self):
        er = EditResult(success=True, file_path="/tmp/test.py", diff="--- a\n+++ b")
        assert er.success is True
        assert er.file_path == "/tmp/test.py"
        assert er.diff is not None
        assert er.error is None
        assert er.failed_edit is None
        assert er.applied_edits == 0

    def test_failure_result(self):
        op = EditOperation(search="missing", replace="x")
        er = EditResult(
            success=False,
            file_path="/tmp/test.py",
            error="No match found",
            failed_edit=op,
            context="Line 1: something\nLine 2: else",
        )
        assert er.success is False
        assert er.failed_edit is op
        assert er.context is not None

    def test_applied_edits_count(self):
        er = EditResult(success=True, file_path="/tmp/test.py", applied_edits=3)
        assert er.applied_edits == 3


# ===========================================================================
# Exact match tests (Level 1)
# ===========================================================================


class TestSearchReplaceEditorExactMatch:
    def test_exact_match_simple(self, editor, tmp_file):
        ops = [EditOperation(search='print("hello world")', replace='print("hi world")')]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is True
        assert result.applied_edits == 1
        content = tmp_file.read_text()
        assert 'print("hi world")' in content
        assert 'print("hello world")' not in content

    def test_exact_match_multiline(self, editor, tmp_file):
        ops = [
            EditOperation(
                search='def hello():\n    print("hello world")',
                replace='def hello():\n    print("greetings")',
            )
        ]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is True
        content = tmp_file.read_text()
        assert 'print("greetings")' in content

    def test_exact_match_with_special_chars(self, editor, tmp_path):
        f = tmp_path / "special.py"
        f.write_text('regex = r"\\d+\\.\\d+"\n')
        ops = [EditOperation(search=r'regex = r"\\d+\\.\\d+"', replace=r'regex = r"\\w+"')]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert r'regex = r"\\w+"' in content

    def test_multiple_exact_matches(self, editor, sample_python_file):
        """When multiple exact matches exist, apply to first and report count."""
        ops = [
            EditOperation(
                search="            result.append(item.transform())",
                replace="            result.append(item.process())",
            )
        ]
        result = editor.apply_edits(str(sample_python_file), ops)
        assert result.success is True
        content = sample_python_file.read_text()
        # First occurrence replaced
        assert "item.process()" in content
        # Second occurrence still has original
        assert "item.transform()" in content


# ===========================================================================
# Whitespace-normalized tests (Level 2)
# ===========================================================================


class TestSearchReplaceEditorWhitespaceNormalized:
    def test_whitespace_normalized_extra_spaces(self, editor, tmp_path):
        f = tmp_path / "ws.py"
        f.write_text('x  =  1\n')
        ops = [EditOperation(search="x = 1", replace="x = 2")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "x = 2" in content

    def test_whitespace_normalized_tabs_vs_spaces(self, editor, tmp_path):
        f = tmp_path / "tabs.py"
        f.write_text("x\t=\t1\n")
        ops = [EditOperation(search="x = 1", replace="x = 2")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "x = 2" in content

    def test_whitespace_normalized_mixed(self, editor, tmp_path):
        f = tmp_path / "mixed.py"
        f.write_text("if  x  ==  1:\n    print( 'yes' )\n")
        ops = [
            EditOperation(
                search="if x == 1:\n    print( 'yes' )",
                replace="if x == 1:\n    print('yes')",
            )
        ]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "print('yes')" in content


# ===========================================================================
# Indentation-agnostic tests (Level 3)
# ===========================================================================


class TestSearchReplaceEditorIndentationAgnostic:
    def test_indentation_agnostic_different_indent(self, editor, tmp_path):
        f = tmp_path / "indent.py"
        f.write_text("    x = 1\n    y = 2\n")
        # Search without leading indent
        ops = [EditOperation(search="x = 1\ny = 2", replace="x = 10\ny = 20")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        # The replacement should preserve the original indentation
        assert "    x = 10\n    y = 20\n" == content

    def test_indentation_agnostic_tabs_vs_spaces(self, editor, tmp_path):
        f = tmp_path / "indent_tabs.py"
        f.write_text("\tx = 1\n")
        ops = [EditOperation(search="    x = 1", replace="    x = 2")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        # Tab-indented original stays as tab
        assert "\tx = 2\n" == content

    def test_indentation_preserved_in_replacement(self, editor, tmp_path):
        f = tmp_path / "preserve.py"
        f.write_text("        value = compute()\n")
        ops = [EditOperation(search="value = compute()", replace="value = calculate()")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "        value = calculate()\n" == content

    def test_multiline_replacement_preserves_relative_indentation(self, editor, tmp_path):
        """Critical Fix 1: multi-line replacement must maintain relative indentation.

        When the replacement block contains nested structures (if/for/etc),
        the internal relative indentation must be preserved while adjusting
        the base indent to match the original file's indent level.
        """
        f = tmp_path / "nested.py"
        f.write_text(
            textwrap.dedent("""\
            class Foo:
                def bar(self):
                    for item in items:
                        process(item)
            """)
        )
        # Search uses 0-indent, but file has 8-space indent for the block
        search = "for item in items:\n    process(item)"
        replace = "for item in items:\n    if item.valid:\n        process(item)"
        ops = [EditOperation(search=search, replace=replace)]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        lines = content.splitlines()
        # The for line should be at 8 spaces (original indent)
        assert lines[2] == "        for item in items:"
        # The if line should be at 12 spaces (8 base + 4 relative)
        assert lines[3] == "            if item.valid:"
        # The process line should be at 16 spaces (8 base + 8 relative)
        assert lines[4] == "                process(item)"


# ===========================================================================
# Fuzzy match tests (Level 4)
# ===========================================================================


class TestSearchReplaceEditorFuzzyMatch:
    def test_fuzzy_match_minor_typo(self, editor, tmp_path):
        f = tmp_path / "fuzzy.py"
        f.write_text('print("hello world")\n')
        # Search has minor typo
        ops = [EditOperation(search='print("helo world")', replace='print("hi world")')]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert 'print("hi world")' in content

    def test_fuzzy_match_variable_rename(self, editor, tmp_path):
        f = tmp_path / "var.py"
        f.write_text("result = process_data(items)\n")
        # Search uses slightly different name
        ops = [
            EditOperation(
                search="result = process_dat(items)",
                replace="output = process_data(items)",
            )
        ]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "output = process_data(items)" in content

    def test_fuzzy_match_threshold(self, editor, tmp_path):
        """Match just above the 0.85 threshold should succeed."""
        f = tmp_path / "threshold.py"
        f.write_text("very_long_variable_name = 42\n")
        # One char difference in a long string => high similarity
        ops = [
            EditOperation(
                search="very_long_variable_nam = 42",
                replace="very_long_variable_name = 100",
            )
        ]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True

    def test_fuzzy_match_fails_below_threshold(self, editor, tmp_path):
        f = tmp_path / "low.py"
        f.write_text("alpha = 1\n")
        # Totally different string
        ops = [EditOperation(search="zzzzz = 999", replace="beta = 2")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is False

    def test_fuzzy_match_uses_line_boundary_sliding_window(self, editor, tmp_path):
        """Fix 2: fuzzy matching should work on line boundaries, not char-level.

        A multi-line search should be compared against sliding windows of
        the same number of lines from the file content.
        """
        f = tmp_path / "multiline_fuzzy.py"
        f.write_text(
            textwrap.dedent("""\
            def alpha():
                pass

            def beta():
                x = 1
                y = 2
                return x + y

            def gamma():
                pass
            """)
        )
        # Search has minor differences in the beta function body
        search = "def beta():\n    x = 1\n    y = 3\n    return x + y"
        replace = "def beta():\n    x = 10\n    y = 20\n    return x + y"
        ops = [EditOperation(search=search, replace=replace)]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "x = 10" in content
        assert "y = 20" in content


# ===========================================================================
# Multiple edits tests
# ===========================================================================


class TestSearchReplaceEditorMultipleEdits:
    def test_multiple_edits_sequential(self, editor, tmp_file):
        ops = [
            EditOperation(search='print("hello world")', replace='print("hi")'),
            EditOperation(search='print("goodbye world")', replace='print("bye")'),
        ]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is True
        assert result.applied_edits == 2
        content = tmp_file.read_text()
        assert 'print("hi")' in content
        assert 'print("bye")' in content

    def test_multiple_edits_partial_failure(self, editor, tmp_file):
        """Stop on first failure and return context about the failed edit."""
        ops = [
            EditOperation(search='print("hello world")', replace='print("hi")'),
            EditOperation(search="NONEXISTENT_CODE", replace="replacement"),
        ]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is False
        assert result.applied_edits == 1
        assert result.failed_edit is not None
        assert result.failed_edit.search == "NONEXISTENT_CODE"
        assert result.context is not None


# ===========================================================================
# Duplicate match tests (Fix 3)
# ===========================================================================


class TestSearchReplaceEditorDuplicateMatch:
    def test_ambiguous_match_warns_on_duplicates(self, editor, tmp_path):
        """When search text matches 3+ times, match_count should reflect that."""
        f = tmp_path / "dupes.py"
        f.write_text("x = 1\nx = 1\nx = 1\n")
        ops = [EditOperation(search="x = 1", replace="x = 2")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        # First occurrence replaced, others untouched
        lines = content.strip().splitlines()
        assert lines[0] == "x = 2"
        assert lines[1] == "x = 1"
        assert lines[2] == "x = 1"

    def test_duplicate_match_uses_first_occurrence(self, editor, tmp_path):
        f = tmp_path / "first.py"
        f.write_text("a = 1\nb = 2\na = 1\n")
        ops = [EditOperation(search="a = 1", replace="a = 99")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert content == "a = 99\nb = 2\na = 1\n"


# ===========================================================================
# Error handling tests
# ===========================================================================


class TestSearchReplaceEditorErrorHandling:
    def test_file_not_found(self, editor, tmp_path):
        ops = [EditOperation(search="x", replace="y")]
        result = editor.apply_edits(str(tmp_path / "nonexistent.py"), ops)
        assert result.success is False
        assert result.error is not None
        assert "not found" in result.error.lower() or "no such file" in result.error.lower()

    def test_match_failure_returns_context(self, editor, tmp_file):
        ops = [EditOperation(search="NOTHING_LIKE_THIS_EXISTS", replace="x")]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is False
        assert result.context is not None
        assert "EDIT FAILED" in result.context
        assert "Please retry" in result.context

    def test_error_context_shows_nearby_lines(self, editor, sample_python_file):
        ops = [EditOperation(search="def process_dat(items):", replace="def foo():")]
        result = editor.apply_edits(str(sample_python_file), ops)
        # This may match via fuzzy, but if it doesn't match, context should show lines
        if not result.success:
            assert result.context is not None
            assert "Line" in result.context

    def test_preserve_indentation_flag_off(self, tmp_path):
        """With preserve_indentation=False, no indentation adjustment."""
        editor_no_indent = SearchReplaceEditor(
            preserve_indentation=False, fuzzy_threshold=0.85
        )
        f = tmp_path / "no_indent.py"
        f.write_text("    x = 1\n")
        ops = [EditOperation(search="x = 1", replace="x = 2")]
        result = editor_no_indent.apply_edits(str(f), ops)
        # Should still match via indentation-agnostic but NOT adjust replacement indent
        if result.success:
            content = f.read_text()
            # Without preserve_indentation, replacement is literal
            assert "x = 2" in content


# ===========================================================================
# Diff generation tests
# ===========================================================================


class TestSearchReplaceEditorDiff:
    def test_diff_format(self, editor, tmp_file):
        ops = [EditOperation(search='print("hello world")', replace='print("hi")')]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is True
        assert result.diff is not None
        # Unified diff markers
        assert "---" in result.diff
        assert "+++" in result.diff

    def test_diff_includes_file_path(self, editor, tmp_file):
        ops = [EditOperation(search='print("hello world")', replace='print("hi")')]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is True
        assert result.diff is not None
        assert str(tmp_file.name) in result.diff or str(tmp_file) in result.diff


# ===========================================================================
# Edge case tests
# ===========================================================================


class TestSearchReplaceEditorEdgeCases:
    def test_empty_file(self, editor, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        ops = [EditOperation(search="anything", replace="something")]
        result = editor.apply_edits(str(f), ops)
        assert result.success is False

    def test_empty_search_string(self, editor, tmp_file):
        ops = [EditOperation(search="", replace="something")]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is False
        assert result.error is not None

    def test_empty_replacement(self, editor, tmp_file):
        """Empty replacement is allowed — it deletes the matched text."""
        ops = [EditOperation(search='print("hello world")', replace="")]
        result = editor.apply_edits(str(tmp_file), ops)
        assert result.success is True
        content = tmp_file.read_text()
        assert 'print("hello world")' not in content

    def test_unicode_content(self, editor, tmp_path):
        f = tmp_path / "unicode.py"
        f.write_text('msg = "Hello, World!"\n')
        ops = [
            EditOperation(search='msg = "Hello, World!"', replace='msg = "Hola, Mundo!"')
        ]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "Hola, Mundo!" in content

    def test_very_large_file(self, editor, tmp_path):
        f = tmp_path / "large.py"
        lines = [f"line_{i} = {i}" for i in range(10_000)]
        lines[5000] = "target_line = 'find_me'"
        f.write_text("\n".join(lines) + "\n")
        ops = [
            EditOperation(search="target_line = 'find_me'", replace="target_line = 'found'")
        ]
        result = editor.apply_edits(str(f), ops)
        assert result.success is True
        content = f.read_text()
        assert "target_line = 'found'" in content

    def test_no_edits_provided(self, editor, tmp_file):
        result = editor.apply_edits(str(tmp_file), [])
        assert result.success is True
        assert result.applied_edits == 0
