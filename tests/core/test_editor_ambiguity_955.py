"""Fuzzy matching must report the real match count, not a hardcoded 1 (#955).

Match levels 1-3 all count their occurrences so ``apply_edits`` can reject an
ambiguous search (``editor.py``'s ``match_count > 1`` guard). Level 4 hardcoded
``match_count=1``, so when two blocks scored identically the editor silently
edited whichever came first — the wrong one half the time, with nothing in the
result to notice.
"""

from __future__ import annotations

import textwrap

import pytest

from codeframe.core.editor import EditOperation, SearchReplaceEditor

pytestmark = pytest.mark.v2


@pytest.fixture
def editor():
    return SearchReplaceEditor(preserve_indentation=True, fuzzy_threshold=0.85)


def _write(tmp_path, body: str):
    f = tmp_path / "sample.py"
    f.write_text(textwrap.dedent(body))
    return f


# A search that no exact / whitespace-normalized / indentation-agnostic level can
# match (`compute(0)` appears nowhere), so resolution necessarily falls to the
# fuzzy level under test.
_FUZZY_ONLY_SEARCH = "    value = compute(0)\n    return value"


class TestFuzzyAmbiguityRejected:
    def test_two_near_identical_blocks_are_rejected_as_ambiguous(
        self, editor, tmp_path
    ):
        """The acceptance criterion: two near-identical blocks must not silently edit."""
        f = _write(
            tmp_path,
            """\
            def alpha():
                value = compute(1)
                return value

            def beta():
                value = compute(2)
                return value
            """,
        )
        before = f.read_text()

        result = editor.apply_edits(
            str(f),
            [EditOperation(search=_FUZZY_ONLY_SEARCH, replace="    return 0")],
        )

        assert result.success is False
        assert "Multiple matches" in (result.error or "")
        assert result.match_results[-1].match_level_name == "fuzzy"
        assert result.match_results[-1].match_count == 2
        # And nothing was written — an ambiguous edit must not half-apply.
        assert f.read_text() == before

    def test_unambiguous_fuzzy_match_still_applies(self, editor, tmp_path):
        """The guard must not break the single-candidate case it sits in front of."""
        f = _write(
            tmp_path,
            """\
            def alpha():
                value = compute(1)
                return value

            def beta():
                other = something_else()
                return other
            """,
        )

        result = editor.apply_edits(
            str(f),
            [EditOperation(search=_FUZZY_ONLY_SEARCH, replace="    return 0")],
        )

        assert result.success is True, result.error
        assert result.match_results[-1].match_count == 1
        assert "return 0" in f.read_text()

    def test_two_non_overlapping_repeats_are_still_ambiguous(self, editor, tmp_path):
        """The overlap allowance must not swallow genuinely separate regions.

        Four repeated lines hold *two* non-overlapping 2-line regions, so unlike
        the overlapping case below, an edit here really is ambiguous.
        """
        f = _write(
            tmp_path,
            """\
            def alpha():
                acc += 1
                acc += 1
                acc += 1
                acc += 1
                return acc
            """,
        )

        result = editor.apply_edits(
            str(f),
            [EditOperation(search="    acc += 1\n    acc += 2", replace="    acc += 9")],
        )

        assert result.success is False
        assert result.match_results[-1].match_count == 2

    def test_overlapping_windows_in_repetitive_code_count_once(
        self, editor, tmp_path
    ):
        """Overlapping windows are one region seen at several offsets, not two matches.

        Three repeated lines give a 2-line search two *overlapping* top-scoring
        windows — offsets 1-2 and 2-3 — over a single region. Counting those
        separately would reject edits to any repetitive code, a different bug
        from the one being fixed. (Four repeated lines would be genuinely
        ambiguous: two non-overlapping regions, correctly rejected.)
        """
        f = _write(
            tmp_path,
            """\
            def alpha():
                acc += 1
                acc += 1
                acc += 1
                return acc
            """,
        )

        result = editor.apply_edits(
            str(f),
            [EditOperation(search="    acc += 1\n    acc += 2", replace="    acc += 9")],
        )

        assert result.success is True, result.error
        assert result.match_results[-1].match_count == 1
