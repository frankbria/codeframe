"""Read-only agent tools for codebase exploration.

Provides three tools for the ReAct agent loop:
- read_file: Read file contents with optional line range
- list_files: List directory contents with filtering
- search_codebase: Regex search across workspace files

All tools enforce workspace path safety and respect ignore patterns.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from codeframe.adapters.llm.base import Tool, ToolCall, ToolResult
from codeframe.core.context import DEFAULT_IGNORE_PATTERNS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_LINES = 500
MAX_SEARCH_FILE_SIZE = 1_000_000  # 1 MB — skip files larger than this in search
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_RESULTS = 20

# Lines shown at the top/bottom when truncating large files
_TRUNCATE_HEAD = 200
_TRUNCATE_TAIL = 50


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _is_path_safe(file_path: Path, workspace_path: Path) -> tuple[bool, str]:
    """Check if *file_path* is safely within *workspace_path*.

    Returns:
        ``(True, "")`` when safe, ``(False, reason)`` otherwise.
    """
    try:
        resolved_file = file_path.resolve()
        resolved_workspace = workspace_path.resolve()
        resolved_file.relative_to(resolved_workspace)
        return (True, "")
    except ValueError:
        return (False, f"Path escapes workspace: {file_path}")
    except Exception as e:
        return (False, f"Path resolution error: {e}")


# ---------------------------------------------------------------------------
# Ignore-pattern helper
# ---------------------------------------------------------------------------


def _should_ignore(rel_path: str) -> bool:
    """Return True if *rel_path* matches any default ignore pattern."""
    for pattern in DEFAULT_IGNORE_PATTERNS:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # Also check the basename for patterns like "*.pyc"
        if fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
    return False


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

_READ_FILE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path from workspace root",
        },
        "start_line": {
            "type": "integer",
            "description": "Optional starting line (1-indexed)",
            "minimum": 1,
        },
        "end_line": {
            "type": "integer",
            "description": "Optional ending line (1-indexed)",
            "minimum": 1,
        },
    },
    "required": ["path"],
}


def _execute_read_file(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    rel = input_data.get("path", "")
    file_path = workspace_path / rel

    safe, reason = _is_path_safe(file_path, workspace_path)
    if not safe:
        return ToolResult(tool_call_id=tool_call_id, content=reason, is_error=True)

    if not file_path.is_file():
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"File not found: {rel}",
            is_error=True,
        )

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Error reading file: {exc}",
            is_error=True,
        )

    lines = text.splitlines(keepends=True)
    total = len(lines)

    start = input_data.get("start_line")
    end = input_data.get("end_line")
    has_range = start is not None or end is not None

    if has_range:
        s = (start or 1) - 1  # 1-indexed → 0-indexed
        e = end if end is not None else total
        selected = lines[s:e]
        offset = s
    elif total > MAX_FILE_LINES:
        # Auto-truncate: first _TRUNCATE_HEAD + last _TRUNCATE_TAIL
        head = lines[:_TRUNCATE_HEAD]
        tail = lines[-_TRUNCATE_TAIL:]
        truncation_msg = (
            f"\n... [truncated: {total} total lines, "
            f"showing first {_TRUNCATE_HEAD} and last {_TRUNCATE_TAIL}] ...\n\n"
        )
        formatted_head = _format_lines(head, offset=0)
        formatted_tail = _format_lines(tail, offset=total - _TRUNCATE_TAIL)
        return ToolResult(
            tool_call_id=tool_call_id,
            content=formatted_head + truncation_msg + formatted_tail,
            is_error=False,
        )
    else:
        selected = lines
        offset = 0

    return ToolResult(
        tool_call_id=tool_call_id,
        content=_format_lines(selected, offset),
        is_error=False,
    )


def _format_lines(lines: list[str], offset: int) -> str:
    """Format lines with line numbers."""
    parts: list[str] = []
    for i, line in enumerate(lines):
        num = offset + i + 1  # 1-indexed
        parts.append(f"{num:4d} | {line.rstrip()}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

_LIST_FILES_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Directory path relative to workspace root (default: '.')",
            "default": ".",
        },
        "pattern": {
            "type": "string",
            "description": "Glob pattern to filter files (e.g., '*.py')",
        },
        "max_depth": {
            "type": "integer",
            "description": "Maximum directory depth to traverse (default: 3)",
            "default": 3,
            "minimum": 1,
        },
    },
}


def _execute_list_files(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    rel = input_data.get("path", ".")
    target = workspace_path / rel
    pattern = input_data.get("pattern")
    max_depth = input_data.get("max_depth", DEFAULT_MAX_DEPTH)

    safe, reason = _is_path_safe(target, workspace_path)
    if not safe:
        return ToolResult(tool_call_id=tool_call_id, content=reason, is_error=True)

    if not target.is_dir():
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Directory not found: {rel}",
            is_error=True,
        )

    files: list[tuple[str, int]] = []  # (relative_path, size_bytes)

    for dirpath, dirnames, filenames in os.walk(target):
        # Calculate depth relative to target
        depth = len(Path(dirpath).relative_to(target).parts)
        if depth >= max_depth:
            dirnames.clear()
            continue

        # Filter ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not _should_ignore(d) and not _should_ignore(d + "/")
        ]

        for fname in filenames:
            full = Path(dirpath) / fname

            # Guard against symlinks pointing outside workspace
            safe, _ = _is_path_safe(full, workspace_path)
            if not safe:
                continue

            rel_to_workspace = str(full.relative_to(workspace_path))

            if _should_ignore(rel_to_workspace) or _should_ignore(fname):
                continue

            if pattern and not fnmatch.fnmatch(fname, pattern):
                continue

            try:
                size = full.stat().st_size
            except OSError:
                size = 0

            files.append((rel_to_workspace, size))

    files.sort(key=lambda f: f[0])

    # Format output
    display_path = str(Path(rel)) if rel != "." else "workspace root"
    header = f"Files in {display_path}:\n\n"
    header += f"{'Size (bytes)':>12}  | Path\n"
    header += f"{'-' * 12}  | {'-' * 40}\n"

    rows = "\n".join(f"{size:>12}  | {path}" for path, size in files)

    footer = f"\n\nTotal: {len(files)} files"

    return ToolResult(
        tool_call_id=tool_call_id,
        content=header + rows + footer,
        is_error=False,
    )


# ---------------------------------------------------------------------------
# search_codebase
# ---------------------------------------------------------------------------

_SEARCH_CODEBASE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for",
        },
        "file_glob": {
            "type": "string",
            "description": "Glob pattern to filter files (e.g., '*.py')",
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of matching lines to return (default: 20)",
            "default": 20,
            "minimum": 1,
        },
    },
    "required": ["pattern"],
}


def _execute_search_codebase(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    raw_pattern = input_data.get("pattern", "")
    file_glob = input_data.get("file_glob")
    max_results = input_data.get("max_results", DEFAULT_MAX_RESULTS)

    try:
        compiled = re.compile(raw_pattern)
    except re.error as exc:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Invalid regex pattern: {exc}",
            is_error=True,
        )

    matches: list[str] = []
    truncated = False

    for dirpath, dirnames, filenames in os.walk(workspace_path):
        # Filter ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not _should_ignore(d) and not _should_ignore(d + "/")
        ]

        for fname in filenames:
            if len(matches) >= max_results:
                truncated = True
                break

            full = Path(dirpath) / fname

            # Guard against symlinks pointing outside workspace
            safe, _ = _is_path_safe(full, workspace_path)
            if not safe:
                continue

            rel = str(full.relative_to(workspace_path))

            if _should_ignore(rel) or _should_ignore(fname):
                continue

            if file_glob and not fnmatch.fnmatch(fname, file_glob):
                continue

            # Skip oversized files to prevent OOM
            try:
                if full.stat().st_size > MAX_SEARCH_FILE_SIZE:
                    continue
            except OSError:
                continue

            # Skip binary files by attempting UTF-8 decode
            try:
                text = full.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            for line_num, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append(f"{rel}:{line_num}: {line.rstrip()}")
                    if len(matches) >= max_results:
                        truncated = True
                        break

        if truncated:
            break

    count = len(matches)
    header = f'Found {count} matches for pattern "{raw_pattern}":\n\n'
    body = "\n".join(matches) if matches else "(no matches)"
    footer = ""
    if truncated:
        footer = f"\n\n[Results truncated to {max_results}]"

    return ToolResult(
        tool_call_id=tool_call_id,
        content=header + body + footer,
        is_error=False,
    )


# ---------------------------------------------------------------------------
# Tool registry & dispatcher
# ---------------------------------------------------------------------------

AGENT_TOOLS: list[Tool] = [
    Tool(
        name="read_file",
        description=(
            "Read the contents of a file from the workspace. "
            "Supports optional line range selection. "
            "Large files (>500 lines) are automatically truncated with a summary."
        ),
        input_schema=_READ_FILE_SCHEMA,
    ),
    Tool(
        name="list_files",
        description=(
            "List files in the workspace directory. "
            "Respects standard ignore rules (.git, node_modules, etc.). "
            "Returns file paths with sizes."
        ),
        input_schema=_LIST_FILES_SCHEMA,
    ),
    Tool(
        name="search_codebase",
        description=(
            "Search for a regex pattern across the codebase. "
            "Returns matching lines with file paths and line numbers. "
            "Results are limited to prevent overwhelming output."
        ),
        input_schema=_SEARCH_CODEBASE_SCHEMA,
    ),
]

_TOOL_HANDLERS = {
    "read_file": _execute_read_file,
    "list_files": _execute_list_files,
    "search_codebase": _execute_search_codebase,
}


def execute_tool(tool_call: ToolCall, workspace_path: Path) -> ToolResult:
    """Dispatch a tool call to the appropriate handler.

    Args:
        tool_call: The tool call from the LLM.
        workspace_path: Absolute path to the workspace root.

    Returns:
        ToolResult with the tool's output or an error message.
    """
    handler = _TOOL_HANDLERS.get(tool_call.name)
    if handler is None:
        return ToolResult(
            tool_call_id=tool_call.id,
            content=f"Unknown tool: {tool_call.name}",
            is_error=True,
        )

    try:
        return handler(tool_call.input, workspace_path, tool_call.id)
    except Exception as exc:
        return ToolResult(
            tool_call_id=tool_call.id,
            content=f"Tool execution error: {exc}",
            is_error=True,
        )
