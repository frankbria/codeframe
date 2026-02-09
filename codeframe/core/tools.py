"""Agent tools for codebase exploration and modification.

Provides seven tools for the ReAct agent loop:
- read_file: Read file contents with optional line range
- list_files: List directory contents with filtering
- search_codebase: Regex search across workspace files
- edit_file: Search-and-replace editing via SearchReplaceEditor
- create_file: Create new files (fails if file already exists)
- run_command: Execute shell commands with safety checks
- run_tests: Run project test suite and return focused results

All tools enforce workspace path safety and respect ignore patterns.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path

from codeframe.adapters.llm.base import Tool, ToolCall, ToolResult
from codeframe.core.context import DEFAULT_IGNORE_PATTERNS
from codeframe.core.editor import EditOperation, SearchReplaceEditor
from codeframe.core.executor import is_dangerous_command
from codeframe.core.gates import _detect_available_gates

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
        if start is not None and start < 1:
            return ToolResult(
                tool_call_id=tool_call_id,
                content="Invalid start_line: must be >= 1.",
                is_error=True,
            )
        if end is not None and end < 1:
            return ToolResult(
                tool_call_id=tool_call_id,
                content="Invalid end_line: must be >= 1.",
                is_error=True,
            )
        if start is not None and end is not None and start > end:
            return ToolResult(
                tool_call_id=tool_call_id,
                content="Invalid line range: start_line > end_line.",
                is_error=True,
            )
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

            if _should_ignore(rel_to_workspace):
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

            if _should_ignore(rel):
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
# edit_file
# ---------------------------------------------------------------------------

_EDIT_FILE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path from workspace root to the file to edit",
        },
        "edits": {
            "type": "array",
            "description": "List of search-and-replace operations to apply sequentially",
            "items": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Text to search for (must match uniquely)",
                    },
                    "replace": {
                        "type": "string",
                        "description": "Text to replace the matched search block with",
                    },
                },
                "required": ["search", "replace"],
            },
        },
    },
    "required": ["path", "edits"],
}


def _execute_edit_file(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    rel = input_data.get("path")
    edits_raw = input_data.get("edits")

    if not rel:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Missing required parameter: path",
            is_error=True,
        )
    if edits_raw is None:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Missing required parameter: edits",
            is_error=True,
        )
    if not isinstance(edits_raw, list):
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Invalid parameter: edits must be a list of objects.",
            is_error=True,
        )
    for idx, entry in enumerate(edits_raw):
        if not isinstance(entry, dict):
            return ToolResult(
                tool_call_id=tool_call_id,
                content=f"Invalid edit at index {idx}: expected an object.",
                is_error=True,
            )

    file_path = workspace_path / rel

    safe, reason = _is_path_safe(file_path, workspace_path)
    if not safe:
        return ToolResult(tool_call_id=tool_call_id, content=reason, is_error=True)

    # Convert raw dicts to EditOperation objects
    edit_ops = [
        EditOperation(
            search=e.get("search", ""),
            replace=e.get("replace", ""),
            description=e.get("description"),
        )
        for e in edits_raw
    ]

    editor = SearchReplaceEditor()
    result = editor.apply_edits(str(file_path), edit_ops)

    if result.success:
        content = result.diff or "Edit applied (no textual changes)."
        return ToolResult(
            tool_call_id=tool_call_id, content=content, is_error=False
        )
    else:
        # Combine error and context for LLM-friendly feedback
        parts = []
        if result.error:
            parts.append(result.error)
        if result.context:
            parts.append(result.context)
        return ToolResult(
            tool_call_id=tool_call_id,
            content="\n".join(parts) if parts else "Edit failed.",
            is_error=True,
        )


# ---------------------------------------------------------------------------
# create_file
# ---------------------------------------------------------------------------

_CREATE_FILE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path from workspace root for the new file",
        },
        "content": {
            "type": "string",
            "description": "Complete file content to write",
        },
    },
    "required": ["path", "content"],
}


def _execute_create_file(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    rel = input_data.get("path")
    content = input_data.get("content")

    if not rel:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Missing required parameter: path",
            is_error=True,
        )
    if content is None:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Missing required parameter: content",
            is_error=True,
        )

    file_path = workspace_path / rel

    safe, reason = _is_path_safe(file_path, workspace_path)
    if not safe:
        return ToolResult(tool_call_id=tool_call_id, content=reason, is_error=True)

    if file_path.exists():
        return ToolResult(
            tool_call_id=tool_call_id,
            content=(
                f"File already exists: {rel}. "
                "Use edit_file to modify existing files."
            ),
            is_error=True,
        )

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Error creating file: {exc}",
            is_error=True,
        )

    return ToolResult(
        tool_call_id=tool_call_id,
        content=f"Created file: {rel}",
        is_error=False,
    )


# ---------------------------------------------------------------------------
# run_tests
# ---------------------------------------------------------------------------

_RUN_TESTS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "test_path": {
            "type": "string",
            "description": (
                "Optional path to specific test file or directory "
                "(relative to workspace)"
            ),
        },
        "verbose": {
            "type": "boolean",
            "description": (
                "If true, include full test output instead of summary only"
            ),
            "default": False,
        },
    },
}


def _execute_run_tests(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    test_path = input_data.get("test_path")
    verbose = input_data.get("verbose", False)

    # Validate test_path stays inside workspace
    if test_path:
        candidate = workspace_path / test_path
        safe, reason = _is_path_safe(candidate, workspace_path)
        if not safe:
            return ToolResult(
                tool_call_id=tool_call_id, content=reason, is_error=True
            )

    gates = _detect_available_gates(workspace_path)

    if "pytest" in gates:
        # Build pytest command, preferring uv if available
        if shutil.which("uv"):
            cmd = ["uv", "run", "pytest"]
        else:
            cmd = ["pytest"]
        if test_path:
            cmd.append(test_path)
        cmd.extend(["-v", "--tb=short"])
    elif "npm-test" in gates:
        cmd = ["npm", "test"]
        if test_path:
            cmd.extend(["--", test_path])
    else:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=(
                "No test runner detected. "
                "Ensure pytest, pyproject.toml, or package.json "
                "with a test script exists."
            ),
            is_error=True,
        )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(workspace_path),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Test execution timed out after 300 seconds.",
            is_error=True,
        )
    except OSError as exc:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Failed to run tests: {exc}",
            is_error=True,
        )

    output = proc.stdout + proc.stderr

    if proc.returncode == 0:
        # Extract last summary line from pytest output (e.g., "5 passed in 0.12s")
        summary_matches = re.findall(
            r"=+ (.+?) =+\s*$", output, re.MULTILINE
        )
        summary = summary_matches[-1] if summary_matches else "Tests passed."
        content = f"PASSED: {summary}"
    else:
        # Extract first failing test and its traceback
        lines = output.splitlines()
        failed_lines = [
            line for line in lines if line.startswith("FAILED ")
        ]
        first_failure = failed_lines[0] if failed_lines else None

        # Find the FAILURES section and extract first traceback
        traceback_lines: list[str] = []
        in_failures = False
        in_first_tb = False
        tb_header_count = 0
        for line in lines:
            if "= FAILURES =" in line:
                in_failures = True
                continue
            if in_failures:
                # Traceback sections start with "_ test_name _" headers
                if re.match(r"^_+ .+ _+$", line):
                    tb_header_count += 1
                    if tb_header_count == 1:
                        in_first_tb = True
                        traceback_lines.append(line)
                        continue
                    else:
                        break
                if re.match(r"^=+ short test summary info =+$", line):
                    break
                if in_first_tb:
                    traceback_lines.append(line)

        traceback_text = (
            "\n".join(traceback_lines[:50]) if traceback_lines else ""
        )

        parts = ["FAILED"]
        if first_failure:
            parts.append(first_failure)
        if traceback_text:
            parts.append(f"\nTraceback:\n{traceback_text}")

        content = "\n".join(parts)

    if verbose:
        truncated = output[:5000]
        if len(output) > 5000:
            truncated += "\n... [output truncated at 5000 chars]"
        content += f"\n\nFull output:\n{truncated}"

    return ToolResult(
        tool_call_id=tool_call_id,
        content=content,
        is_error=proc.returncode != 0,
    )


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------

_RUN_COMMAND_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "Shell command to execute in the workspace",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds (default: 60, max: 300)",
            "default": 60,
            "minimum": 1,
            "maximum": 300,
        },
    },
    "required": ["command"],
}

_RUN_COMMAND_MAX_OUTPUT = 4000
_RUN_COMMAND_MAX_TIMEOUT = 300


def _execute_run_command(
    input_data: dict, workspace_path: Path, tool_call_id: str
) -> ToolResult:
    command = input_data.get("command", "")
    if not command.strip():
        return ToolResult(
            tool_call_id=tool_call_id,
            content="Missing required parameter: command",
            is_error=True,
        )

    timeout = input_data.get("timeout", 60)
    timeout = min(max(int(timeout), 1), _RUN_COMMAND_MAX_TIMEOUT)

    # Safety: reject dangerous commands
    is_dangerous, description = is_dangerous_command(command)
    if is_dangerous:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Blocked dangerous command: {description}",
            is_error=True,
        )

    # Build env with venv activation if present
    env = os.environ.copy()
    for venv_dir in (".venv", "venv"):
        venv_bin = workspace_path / venv_dir / "bin"
        if venv_bin.is_dir():
            env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = str(workspace_path / venv_dir)
            break

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_call_id=tool_call_id,
            content=f"Command timed out after {timeout} seconds: {command}",
            is_error=True,
        )

    # Build output
    parts = [f"Exit code: {proc.returncode}"]
    if proc.stdout:
        parts.append(f"stdout:\n{proc.stdout}")
    if proc.stderr:
        parts.append(f"stderr:\n{proc.stderr}")
    output = "\n".join(parts)

    # Truncate if too long
    if len(output) > _RUN_COMMAND_MAX_OUTPUT:
        half = _RUN_COMMAND_MAX_OUTPUT // 2
        output = output[:half] + "\n...[truncated]...\n" + output[-half:]

    return ToolResult(
        tool_call_id=tool_call_id,
        content=output,
        is_error=proc.returncode != 0,
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
    Tool(
        name="edit_file",
        description=(
            "Edit an existing file using search-and-replace operations. "
            "Each edit must match uniquely in the file. "
            "Returns a unified diff on success, or file context on failure "
            "to help retry with corrected search blocks."
        ),
        input_schema=_EDIT_FILE_SCHEMA,
    ),
    Tool(
        name="create_file",
        description=(
            "Create a new file in the workspace. "
            "Fails if the file already exists — use edit_file to modify "
            "existing files. Parent directories are created automatically."
        ),
        input_schema=_CREATE_FILE_SCHEMA,
    ),
    Tool(
        name="run_tests",
        description=(
            "Run the project's test suite and return focused results. "
            "Detects pytest or npm test automatically. "
            "On failure, shows only the first failing test with traceback "
            "to keep context clean."
        ),
        input_schema=_RUN_TESTS_SCHEMA,
    ),
    Tool(
        name="run_command",
        description=(
            "Execute a shell command in the workspace directory. "
            "Dangerous commands (rm -rf /, dd, mkfs, etc.) are blocked. "
            "Virtual environments are auto-detected and activated. "
            "Output is truncated if it exceeds 4000 characters."
        ),
        input_schema=_RUN_COMMAND_SCHEMA,
    ),
]

_TOOL_HANDLERS = {
    "read_file": _execute_read_file,
    "list_files": _execute_list_files,
    "search_codebase": _execute_search_codebase,
    "edit_file": _execute_edit_file,
    "create_file": _execute_create_file,
    "run_tests": _execute_run_tests,
    "run_command": _execute_run_command,
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
