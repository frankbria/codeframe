"""Search-and-replace editor with 4-level fuzzy matching.

Levels:
  1. Exact match
  2. Whitespace-normalized (collapse spaces/tabs)
  3. Indentation-agnostic (strip leading whitespace per line)
  4. Fuzzy (rapidfuzz line-boundary sliding window, threshold configurable)
"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class EditOperation:
    search: str
    replace: str
    description: str | None = None


@dataclass
class MatchResult:
    success: bool
    match_level: int
    match_level_name: str
    start_pos: int
    end_pos: int
    matched_text: str
    match_count: int = 1


@dataclass
class EditResult:
    success: bool
    file_path: str
    diff: str | None = None
    error: str | None = None
    failed_edit: EditOperation | None = None
    context: str | None = None
    applied_edits: int = 0
    match_results: list[MatchResult] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEVEL_NAMES = {0: "none", 1: "exact", 2: "whitespace-normalized",
                3: "indentation-agnostic", 4: "fuzzy"}


def _normalize_whitespace(text: str) -> tuple[str, list[int]]:
    """Collapse runs of horizontal whitespace to single space.

    Returns (normalized_text, position_map) where ``position_map[i]`` is the
    index in *text* that produced ``normalized_text[i]``.
    """
    result: list[str] = []
    pos_map: list[int] = []
    in_run = False
    for i, ch in enumerate(text):
        if ch in (" ", "\t"):
            if not in_run:
                result.append(" ")
                pos_map.append(i)
                in_run = True
        else:
            result.append(ch)
            pos_map.append(i)
            in_run = False
    return "".join(result), pos_map


def _strip_leading_per_line(text: str) -> str:
    """Strip leading whitespace from every line."""
    return "\n".join(line.lstrip() for line in text.splitlines())


def _leading_ws(line: str) -> str:
    """Return the leading whitespace of *line*."""
    return line[: len(line) - len(line.lstrip())]


def _count_occurrences(content: str, search: str) -> int:
    """Count non-overlapping exact occurrences of *search* in *content*."""
    count = 0
    start = 0
    while True:
        idx = content.find(search, start)
        if idx == -1:
            break
        count += 1
        start = idx + len(search)
    return count


# ---------------------------------------------------------------------------
# SearchReplaceEditor
# ---------------------------------------------------------------------------


class SearchReplaceEditor:
    """Apply search-and-replace edits with 4-level fuzzy matching."""

    def __init__(
        self,
        preserve_indentation: bool = True,
        fuzzy_threshold: float = 0.85,
    ) -> None:
        self.preserve_indentation = preserve_indentation
        self.fuzzy_threshold = fuzzy_threshold

    # -- public API --------------------------------------------------------

    def apply_edits(
        self, file_path: str, edits: list[EditOperation]
    ) -> EditResult:
        fp = Path(file_path)

        # Validate inputs
        if not fp.exists():
            return EditResult(
                success=False,
                file_path=file_path,
                error=f"File not found: {file_path}",
            )

        for op in edits:
            if not op.search:
                return EditResult(
                    success=False,
                    file_path=file_path,
                    error="Empty search string is not allowed",
                    failed_edit=op,
                )

        # No edits is a no-op success
        if not edits:
            return EditResult(success=True, file_path=file_path, applied_edits=0)

        encoding = "utf-8"
        try:
            original_content = fp.read_text(encoding=encoding)
        except UnicodeDecodeError:
            encoding = "latin-1"
            original_content = fp.read_text(encoding=encoding)

        content = original_content
        applied = 0
        matches: list[MatchResult] = []

        for op in edits:
            match = self._find_match(content, op.search)
            matches.append(match)
            if not match.success:
                ctx = self._generate_error_context(
                    content, op.search, os.path.basename(file_path)
                )
                return EditResult(
                    success=False,
                    file_path=file_path,
                    error="No match found",
                    failed_edit=op,
                    context=ctx,
                    applied_edits=applied,
                    match_results=matches,
                )

            replacement = op.replace
            if self.preserve_indentation and match.match_level >= 2:
                replacement = self._apply_indentation(
                    match.matched_text, replacement, content, match.start_pos
                )

            content = (
                content[: match.start_pos]
                + replacement
                + content[match.end_pos :]
            )
            applied += 1

        # Generate diff
        diff = "".join(
            difflib.unified_diff(
                original_content.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{os.path.basename(file_path)}",
                tofile=f"b/{os.path.basename(file_path)}",
            )
        )

        fp.write_text(content, encoding=encoding)

        return EditResult(
            success=True,
            file_path=file_path,
            diff=diff if diff else None,
            applied_edits=applied,
            match_results=matches,
        )

    # -- matching ----------------------------------------------------------

    def _find_match(self, content: str, search: str) -> MatchResult:
        """Try 4 match levels in order, returning the first success."""

        # Level 1: exact
        result = self._match_exact(content, search)
        if result.success:
            return result

        # Level 2: whitespace-normalized
        result = self._match_whitespace(content, search)
        if result.success:
            return result

        # Level 3: indentation-agnostic
        result = self._match_indentation(content, search)
        if result.success:
            return result

        # Level 4: fuzzy (line-boundary sliding window)
        result = self._match_fuzzy(content, search)
        if result.success:
            return result

        return MatchResult(
            success=False,
            match_level=0,
            match_level_name="none",
            start_pos=-1,
            end_pos=-1,
            matched_text="",
        )

    def _match_exact(self, content: str, search: str) -> MatchResult:
        idx = content.find(search)
        if idx == -1:
            return self._fail()
        count = _count_occurrences(content, search)
        return MatchResult(
            success=True,
            match_level=1,
            match_level_name="exact",
            start_pos=idx,
            end_pos=idx + len(search),
            matched_text=content[idx : idx + len(search)],
            match_count=count,
        )

    def _match_whitespace(self, content: str, search: str) -> MatchResult:
        norm_search, _ = _normalize_whitespace(search)
        norm_content, pos_map = _normalize_whitespace(content)

        idx = norm_content.find(norm_search)
        if idx == -1:
            return self._fail()

        orig_start = pos_map[idx]
        end_idx = idx + len(norm_search)
        if end_idx < len(pos_map):
            orig_end = pos_map[end_idx]
        else:
            orig_end = len(content)

        matched = content[orig_start:orig_end]

        # Count occurrences in normalized space
        count = 0
        start = 0
        while True:
            i = norm_content.find(norm_search, start)
            if i == -1:
                break
            count += 1
            start = i + len(norm_search)

        return MatchResult(
            success=True,
            match_level=2,
            match_level_name="whitespace-normalized",
            start_pos=orig_start,
            end_pos=orig_end,
            matched_text=matched,
            match_count=count,
        )

    def _match_indentation(self, content: str, search: str) -> MatchResult:
        """Level 3: strip leading whitespace per line and compare."""
        search_lines = search.splitlines()
        content_lines = content.splitlines()
        n = len(search_lines)

        if n == 0:
            return self._fail()

        stripped_search = [line.lstrip() for line in search_lines]

        for i in range(len(content_lines) - n + 1):
            window = content_lines[i : i + n]
            stripped_window = [line.lstrip() for line in window]
            if stripped_window == stripped_search:
                # Compute positions in original content
                start_pos = self._line_offset(content, i)
                end_pos = self._line_offset(content, i + n)
                # Trim trailing newline from end_pos if at file end
                if end_pos > len(content):
                    end_pos = len(content)
                matched = content[start_pos:end_pos]
                # Remove trailing newline from matched text for clean replacement
                # (the newline after the last line is not part of the match)
                if matched.endswith("\n") and not search.endswith("\n"):
                    end_pos -= 1
                    matched = content[start_pos:end_pos]

                count = self._count_indentation_matches(
                    content_lines, stripped_search
                )
                return MatchResult(
                    success=True,
                    match_level=3,
                    match_level_name="indentation-agnostic",
                    start_pos=start_pos,
                    end_pos=end_pos,
                    matched_text=content[start_pos:end_pos],
                    match_count=count,
                )

        return self._fail()

    def _match_fuzzy(self, content: str, search: str) -> MatchResult:
        """Level 4: line-boundary sliding window with rapidfuzz."""
        search_lines = search.splitlines()
        content_lines = content.splitlines()
        n = len(search_lines)

        if n == 0 or n > len(content_lines):
            return self._fail()

        best_ratio = 0.0
        best_i = -1

        for i in range(len(content_lines) - n + 1):
            window = "\n".join(content_lines[i : i + n])
            ratio = fuzz.ratio(search, window) / 100.0
            if ratio > best_ratio:
                best_ratio = ratio
                best_i = i

        if best_ratio < self.fuzzy_threshold:
            return self._fail()

        start_pos = self._line_offset(content, best_i)
        end_pos = self._line_offset(content, best_i + n)
        if end_pos > len(content):
            end_pos = len(content)
        matched = content[start_pos:end_pos]
        if matched.endswith("\n") and not search.endswith("\n"):
            end_pos -= 1
            matched = content[start_pos:end_pos]

        return MatchResult(
            success=True,
            match_level=4,
            match_level_name="fuzzy",
            start_pos=start_pos,
            end_pos=end_pos,
            matched_text=content[start_pos:end_pos],
            match_count=1,
        )

    # -- indentation -------------------------------------------------------

    def _apply_indentation(
        self,
        matched_text: str,
        replacement: str,
        content: str = "",
        start_pos: int = 0,
    ) -> str:
        """Adjust replacement indentation to match original context.

        Detects the actual line indentation in the file by looking back from
        *start_pos* to the beginning of the line.  For the first replacement
        line no indent is prepended (the file already has the leading
        whitespace before *start_pos*).  For subsequent lines the indent
        delta between original and replacement base indentation is applied.
        """
        matched_lines = matched_text.splitlines()
        replace_lines = replacement.splitlines()

        if not matched_lines or not replace_lines:
            return replacement

        # Determine the indentation of the line in the file where the match
        # starts.  This is the whitespace between the last newline before
        # start_pos and start_pos itself.
        file_indent = ""
        if content:
            line_start = content.rfind("\n", 0, start_pos)
            line_start = 0 if line_start == -1 else line_start + 1
            file_indent = content[line_start:start_pos]
            # file_indent is only valid if it is purely whitespace
            if file_indent and not file_indent.isspace():
                file_indent = ""

        # The matched text's first line indent (from the matched span itself)
        matched_first_indent = _leading_ws(matched_lines[0])
        replace_first_indent = _leading_ws(replace_lines[0])

        # The "original base" is the full indent that the first line has
        # in the actual file.  It combines the whitespace before start_pos
        # (file_indent) with any leading whitespace in the matched text.
        original_base = file_indent + matched_first_indent
        replace_base = replace_first_indent

        # The first line of the replacement is inserted at start_pos.
        # If file_indent is non-empty, the file already has indentation
        # BEFORE start_pos, so we must NOT duplicate it on the first line.
        # However, if the match itself included leading whitespace
        # (matched_first_indent is non-empty), we DO need to handle that.
        #
        # For subsequent lines, the full original_base indent is applied.

        # Single-line case
        if len(replace_lines) == 1:
            stripped = replace_lines[0]
            if stripped.startswith(replace_base):
                stripped = stripped[len(replace_base):]
            else:
                stripped = stripped.lstrip()
            if file_indent:
                # File already has indent before start_pos
                return matched_first_indent + stripped
            return original_base + stripped

        # Multi-line case
        result_lines: list[str] = []
        for i, line in enumerate(replace_lines):
            if line.startswith(replace_base):
                relative = line[len(replace_base):]
            else:
                relative = line.lstrip()
            if i == 0 and file_indent:
                # First line: file already has indent before start_pos
                result_lines.append(matched_first_indent + relative)
            else:
                result_lines.append(original_base + relative)

        result = "\n".join(result_lines)
        # Preserve trailing newline if the original replacement had one
        if replacement.endswith("\n") and not result.endswith("\n"):
            result += "\n"
        return result

    # -- error context -----------------------------------------------------

    def _generate_error_context(
        self, content: str, search: str, filename: str
    ) -> str:
        """Generate helpful error context when a match fails."""
        lines = content.splitlines()
        if not lines:
            return (
                f"EDIT FAILED: No match found for search block in {filename}.\n"
                "The file is empty.\n"
                "Please retry with the actual content from the file."
            )

        # Try to find the most similar region using fuzzy matching
        search_lines = search.splitlines()
        n = max(len(search_lines), 1)
        best_ratio = 0.0
        best_i = 0

        for i in range(max(len(lines) - n + 1, 1)):
            window = "\n".join(lines[i : i + n])
            ratio = fuzz.ratio(search, window) / 100.0
            if ratio > best_ratio:
                best_ratio = ratio
                best_i = i

        # Show ~5 lines around the best match
        start = max(0, best_i - 1)
        end = min(len(lines), best_i + n + 2)
        nearby = []
        for j in range(start, end):
            nearby.append(f"  Line {j + 1}: {lines[j]}")

        return (
            f"EDIT FAILED: No match found for search block in {filename}.\n"
            "The file contains these similar lines near the expected location:\n"
            + "\n".join(nearby)
            + "\nPlease retry with the actual content from the file."
        )

    # -- utilities ---------------------------------------------------------

    @staticmethod
    def _line_offset(content: str, line_index: int) -> int:
        """Return the character offset of *line_index* in *content*."""
        offset = 0
        for i, line in enumerate(content.splitlines(keepends=True)):
            if i == line_index:
                return offset
            offset += len(line)
        return offset

    @staticmethod
    def _count_indentation_matches(
        content_lines: list[str], stripped_search: list[str]
    ) -> int:
        n = len(stripped_search)
        count = 0
        for i in range(len(content_lines) - n + 1):
            window = [line.lstrip() for line in content_lines[i : i + n]]
            if window == stripped_search:
                count += 1
        return count

    @staticmethod
    def _fail() -> MatchResult:
        return MatchResult(
            success=False,
            match_level=0,
            match_level_name="none",
            start_pos=-1,
            end_pos=-1,
            matched_text="",
        )
