"""Tests for agent tools (read-only + write).

Tests cover five tools: read_file, list_files, search_codebase,
edit_file, create_file, plus the execute_tool dispatcher and AGENT_TOOLS
registry.
"""

import os

import pytest
from pathlib import Path

from codeframe.adapters.llm.base import ToolCall, ToolResult
from codeframe.core.tools import AGENT_TOOLS, execute_tool

pytestmark = pytest.mark.v2


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with sample files."""
    # src/main.py
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    return 'Hello, world!'\n\ndef add(a, b):\n    return a + b\n"
    )

    # src/utils.py
    (src / "utils.py").write_text(
        "import os\n\ndef get_home():\n    return os.path.expanduser('~')\n"
    )

    # tests/test_main.py
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text(
        "from src.main import hello\n\ndef test_hello():\n    assert hello() == 'Hello, world!'\n"
    )

    # README.md
    (tmp_path / "README.md").write_text("# Sample Project\n\nA test project.\n")

    # Dockerfile (no extension - should still be listed)
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n")

    # Directories that should be ignored
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n")

    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "something.js").write_text("module.exports = {}")

    return tmp_path


def _call(name: str, input_data: dict, workspace: Path) -> ToolResult:
    """Helper to execute a tool call."""
    tc = ToolCall(id="test-call-1", name=name, input=input_data)
    return execute_tool(tc, workspace)


def _safe_symlink(src: Path, dest: Path) -> None:
    """Create a symlink, skipping the test on platforms that don't support it."""
    try:
        os.symlink(src, dest)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")


# ---------------------------------------------------------------------------
# read_file tests
# ---------------------------------------------------------------------------


class TestReadFile:
    def test_basic(self, workspace: Path):
        """Read entire small file."""
        result = _call("read_file", {"path": "src/main.py"}, workspace)
        assert not result.is_error
        assert "def hello():" in result.content
        assert "def add(a, b):" in result.content
        assert result.tool_call_id == "test-call-1"

    def test_with_line_numbers(self, workspace: Path):
        """Output includes line numbers."""
        result = _call("read_file", {"path": "src/main.py"}, workspace)
        assert not result.is_error
        # Line 1 should contain "def hello"
        assert "1" in result.content
        assert "|" in result.content

    def test_with_line_range(self, workspace: Path):
        """Read specific line range."""
        result = _call(
            "read_file",
            {"path": "src/main.py", "start_line": 1, "end_line": 2},
            workspace,
        )
        assert not result.is_error
        assert "def hello():" in result.content
        assert "def add(a, b):" not in result.content

    def test_large_file_truncation(self, workspace: Path):
        """Auto-truncate files exceeding 500 lines."""
        # Create a file with 600 lines
        large = workspace / "large.py"
        lines = [f"line_{i} = {i}" for i in range(1, 601)]
        large.write_text("\n".join(lines) + "\n")

        result = _call("read_file", {"path": "large.py"}, workspace)
        assert not result.is_error
        assert "truncated" in result.content.lower()
        # Should include first 200 lines
        assert "line_1 = 1" in result.content
        assert "line_200 = 200" in result.content
        # Should include last 50 lines
        assert "line_600 = 600" in result.content
        # Should NOT include a middle line
        assert "line_300 = 300" not in result.content

    def test_nonexistent_file(self, workspace: Path):
        """Error for missing file."""
        result = _call("read_file", {"path": "does_not_exist.py"}, workspace)
        assert result.is_error
        assert "not found" in result.content.lower() or "does not exist" in result.content.lower()

    def test_path_traversal(self, workspace: Path):
        """Error for ../ escape attempts."""
        result = _call("read_file", {"path": "../../../etc/passwd"}, workspace)
        assert result.is_error
        assert "escape" in result.content.lower() or "unsafe" in result.content.lower() or "outside" in result.content.lower()

    def test_binary_file(self, workspace: Path):
        """Handle binary files gracefully."""
        binary_file = workspace / "image.bin"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256)))

        result = _call("read_file", {"path": "image.bin"}, workspace)
        # Should not crash - either shows replaced content or reports binary
        assert result.tool_call_id == "test-call-1"

    def test_empty_file(self, workspace: Path):
        """Handle empty files."""
        (workspace / "empty.py").write_text("")
        result = _call("read_file", {"path": "empty.py"}, workspace)
        assert not result.is_error

    def test_start_line_only(self, workspace: Path):
        """Read from start_line to end of file."""
        result = _call(
            "read_file",
            {"path": "src/main.py", "start_line": 4},
            workspace,
        )
        assert not result.is_error
        assert "def add(a, b):" in result.content
        # Should not include line 1
        assert "def hello():" not in result.content

    def test_end_line_only(self, workspace: Path):
        """Read from beginning to end_line."""
        result = _call(
            "read_file",
            {"path": "src/main.py", "end_line": 2},
            workspace,
        )
        assert not result.is_error
        assert "def hello():" in result.content
        assert "def add(a, b):" not in result.content

    def test_start_line_greater_than_end_line(self, workspace: Path):
        """Error when start_line > end_line."""
        result = _call(
            "read_file",
            {"path": "src/main.py", "start_line": 5, "end_line": 2},
            workspace,
        )
        assert result.is_error
        assert "start_line" in result.content.lower() or "range" in result.content.lower()

    def test_invalid_start_line_zero(self, workspace: Path):
        """Error when start_line is 0 (must be >= 1)."""
        result = _call(
            "read_file",
            {"path": "src/main.py", "start_line": 0},
            workspace,
        )
        assert result.is_error
        assert "start_line" in result.content.lower()

    def test_invalid_end_line_zero(self, workspace: Path):
        """Error when end_line is 0 (must be >= 1)."""
        result = _call(
            "read_file",
            {"path": "src/main.py", "end_line": 0},
            workspace,
        )
        assert result.is_error
        assert "end_line" in result.content.lower()

    def test_absolute_path_rejected(self, workspace: Path):
        """Absolute paths must not bypass workspace containment."""
        result = _call("read_file", {"path": "/etc/passwd"}, workspace)
        assert result.is_error

    def test_symlink_outside_workspace(self, workspace: Path):
        """Symlinks pointing outside workspace must not leak content."""
        external = workspace.parent / "external_secret.txt"
        external.write_text("TOP_SECRET=abc123")
        _safe_symlink(external, workspace / "evil_link.txt")

        result = _call("read_file", {"path": "evil_link.txt"}, workspace)
        assert result.is_error
        assert "TOP_SECRET" not in result.content


# ---------------------------------------------------------------------------
# list_files tests
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_root(self, workspace: Path):
        """List workspace root."""
        result = _call("list_files", {}, workspace)
        assert not result.is_error
        assert "src/main.py" in result.content
        assert "README.md" in result.content
        assert "Dockerfile" in result.content

    def test_subdirectory(self, workspace: Path):
        """List specific subdirectory."""
        result = _call("list_files", {"path": "src"}, workspace)
        assert not result.is_error
        assert "main.py" in result.content
        assert "utils.py" in result.content

    def test_with_pattern(self, workspace: Path):
        """Filter by glob pattern."""
        result = _call("list_files", {"path": ".", "pattern": "*.py"}, workspace)
        assert not result.is_error
        assert "main.py" in result.content
        assert "README.md" not in result.content

    def test_max_depth(self, workspace: Path):
        """Respect depth limit."""
        # Create a deeply nested file
        deep = workspace / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("# deep")

        result = _call("list_files", {"path": ".", "max_depth": 2}, workspace)
        assert not result.is_error
        # depth 2 should reach a/b/ but not a/b/c/d/
        assert "deep.py" not in result.content

    def test_max_depth_includes_boundary_files(self, workspace: Path):
        """Files at exactly max_depth boundary are listed."""
        nested = workspace / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "boundary.py").write_text("# at depth 2")

        result = _call("list_files", {"path": ".", "max_depth": 3}, workspace)
        assert not result.is_error
        assert "boundary.py" in result.content

    def test_respects_ignore_patterns(self, workspace: Path):
        """Verify .git, node_modules are ignored."""
        result = _call("list_files", {}, workspace)
        assert not result.is_error
        assert ".git" not in result.content
        assert "node_modules" not in result.content

    def test_nonexistent_directory(self, workspace: Path):
        """Error for missing directory."""
        result = _call("list_files", {"path": "no_such_dir"}, workspace)
        assert result.is_error

    def test_path_traversal(self, workspace: Path):
        """Error for unsafe paths."""
        result = _call("list_files", {"path": "../../"}, workspace)
        assert result.is_error

    def test_shows_file_count(self, workspace: Path):
        """Output includes total file count."""
        result = _call("list_files", {}, workspace)
        assert not result.is_error
        assert "total" in result.content.lower() or "file" in result.content.lower()

    def test_symlink_outside_workspace(self, workspace: Path):
        """Symlinks pointing outside workspace must not appear in listing."""
        external = workspace.parent / "external_file.txt"
        external.write_text("external content")
        _safe_symlink(external, workspace / "sneaky_link.txt")

        result = _call("list_files", {}, workspace)
        assert not result.is_error
        assert "sneaky_link" not in result.content


# ---------------------------------------------------------------------------
# search_codebase tests
# ---------------------------------------------------------------------------


class TestSearchCodebase:
    def test_basic(self, workspace: Path):
        """Find simple string pattern."""
        result = _call("search_codebase", {"pattern": "hello"}, workspace)
        assert not result.is_error
        assert "src/main.py" in result.content
        assert "hello" in result.content.lower()

    def test_regex(self, workspace: Path):
        r"""Use regex pattern (def \w+\()."""
        result = _call("search_codebase", {"pattern": r"def \w+\("}, workspace)
        assert not result.is_error
        assert "def hello(" in result.content
        assert "def add(" in result.content

    def test_with_file_glob(self, workspace: Path):
        """Filter search to specific file types."""
        result = _call(
            "search_codebase",
            {"pattern": "hello", "file_glob": "*.py"},
            workspace,
        )
        assert not result.is_error
        assert "main.py" in result.content

    def test_max_results(self, workspace: Path):
        """Verify result truncation."""
        # Create many files with matches
        for i in range(30):
            (workspace / f"file_{i}.py").write_text(f"match_{i} = True\n")

        result = _call(
            "search_codebase",
            {"pattern": "match_", "max_results": 5},
            workspace,
        )
        assert not result.is_error
        # Should have at most 5 result lines
        assert "truncated" in result.content.lower() or "5" in result.content

    def test_no_matches(self, workspace: Path):
        """Handle no results gracefully."""
        result = _call(
            "search_codebase",
            {"pattern": "this_string_does_not_exist_anywhere"},
            workspace,
        )
        assert not result.is_error
        assert "0" in result.content or "no match" in result.content.lower()

    def test_invalid_regex(self, workspace: Path):
        """Error for invalid regex pattern."""
        result = _call("search_codebase", {"pattern": "[invalid"}, workspace)
        assert result.is_error
        assert "regex" in result.content.lower() or "pattern" in result.content.lower()

    def test_respects_ignore_patterns(self, workspace: Path):
        """Skip ignored directories."""
        result = _call("search_codebase", {"pattern": "module.exports"}, workspace)
        assert not result.is_error
        # node_modules should be ignored, so this shouldn't match
        assert "node_modules" not in result.content

    def test_symlink_outside_workspace(self, workspace: Path):
        """Symlinks pointing outside workspace must not leak content."""
        external = workspace.parent / "external_secret.txt"
        external.write_text("TOP_SECRET=abc123")
        _safe_symlink(external, workspace / "evil_link.txt")

        result = _call("search_codebase", {"pattern": "TOP_SECRET"}, workspace)
        assert not result.is_error
        # The pattern appears in the header, but the actual secret content must not
        assert "abc123" not in result.content
        assert "evil_link" not in result.content

    def test_large_file_skipped(self, workspace: Path):
        """Files over 1MB are skipped in search."""
        large = workspace / "huge.txt"
        large.write_text("FINDME\n" + "x" * 1_100_000)

        result = _call("search_codebase", {"pattern": "FINDME"}, workspace)
        assert not result.is_error
        assert "huge.txt" not in result.content


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


class TestDispatcher:
    def test_unknown_tool(self, workspace: Path):
        """Error for unrecognized tool name."""
        result = _call("nonexistent_tool", {}, workspace)
        assert result.is_error
        assert "unknown" in result.content.lower()

    def test_tool_registry_completeness(self):
        """Verify all 5 tools are in AGENT_TOOLS."""
        names = {t.name for t in AGENT_TOOLS}
        assert "read_file" in names
        assert "list_files" in names
        assert "search_codebase" in names
        assert "edit_file" in names
        assert "create_file" in names
        assert len(AGENT_TOOLS) == 5

    def test_tool_schemas_valid(self):
        """Verify JSON schema structure for each tool."""
        for tool in AGENT_TOOLS:
            assert isinstance(tool.name, str)
            assert isinstance(tool.description, str)
            assert isinstance(tool.input_schema, dict)
            assert tool.input_schema.get("type") == "object"
            assert "properties" in tool.input_schema

    def test_tool_call_id_propagated(self, workspace: Path):
        """ToolResult.tool_call_id matches ToolCall.id."""
        tc = ToolCall(id="custom-id-42", name="read_file", input={"path": "README.md"})
        result = execute_tool(tc, workspace)
        assert result.tool_call_id == "custom-id-42"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_list_then_read(self, workspace: Path):
        """List files, then read one of them."""
        list_result = _call("list_files", {"path": "src"}, workspace)
        assert not list_result.is_error
        assert "main.py" in list_result.content

        read_result = _call("read_file", {"path": "src/main.py"}, workspace)
        assert not read_result.is_error
        assert "def hello():" in read_result.content

    def test_search_then_read(self, workspace: Path):
        """Search for a pattern, then read the file containing it."""
        search_result = _call("search_codebase", {"pattern": "get_home"}, workspace)
        assert not search_result.is_error
        assert "src/utils.py" in search_result.content

        read_result = _call("read_file", {"path": "src/utils.py"}, workspace)
        assert not read_result.is_error
        assert "def get_home():" in read_result.content


# ---------------------------------------------------------------------------
# edit_file tests
# ---------------------------------------------------------------------------


class TestEditFile:
    def test_successful_edit_with_diff(self, workspace: Path):
        """Successful search-replace returns unified diff."""
        result = _call(
            "edit_file",
            {
                "path": "src/main.py",
                "edits": [{"search": "return 'Hello, world!'", "replace": "return 'Hi!'"}],
            },
            workspace,
        )
        assert not result.is_error
        assert "---" in result.content  # unified diff header
        assert "+++" in result.content
        assert "@@" in result.content
        # Verify file actually changed
        assert (workspace / "src/main.py").read_text().count("return 'Hi!'") == 1

    def test_multiple_edits(self, workspace: Path):
        """Multiple sequential edits in one call."""
        result = _call(
            "edit_file",
            {
                "path": "src/main.py",
                "edits": [
                    {"search": "def hello():", "replace": "def greet():"},
                    {"search": "return a + b", "replace": "return a + b  # sum"},
                ],
            },
            workspace,
        )
        assert not result.is_error
        content = (workspace / "src/main.py").read_text()
        assert "def greet():" in content
        assert "return a + b  # sum" in content

    def test_edit_failure_returns_context(self, workspace: Path):
        """When search string not found, return file context for LLM retry."""
        result = _call(
            "edit_file",
            {
                "path": "src/main.py",
                "edits": [{"search": "this_does_not_exist_anywhere", "replace": "x"}],
            },
            workspace,
        )
        assert result.is_error
        # Should contain helpful context from the file
        assert "EDIT FAILED" in result.content or "no match" in result.content.lower()
        # File should be unchanged
        assert "def hello():" in (workspace / "src/main.py").read_text()

    def test_edit_nonexistent_file(self, workspace: Path):
        """Error when target file doesn't exist."""
        result = _call(
            "edit_file",
            {
                "path": "no_such_file.py",
                "edits": [{"search": "x", "replace": "y"}],
            },
            workspace,
        )
        assert result.is_error
        assert "not found" in result.content.lower()

    def test_edit_path_traversal(self, workspace: Path):
        """Path traversal attempts are blocked."""
        result = _call(
            "edit_file",
            {
                "path": "../../../etc/passwd",
                "edits": [{"search": "root", "replace": "hacked"}],
            },
            workspace,
        )
        assert result.is_error
        assert "escape" in result.content.lower() or "path" in result.content.lower()

    def test_edit_missing_params(self, workspace: Path):
        """Error when required parameters are missing."""
        result = _call("edit_file", {}, workspace)
        assert result.is_error

        result2 = _call("edit_file", {"path": "src/main.py"}, workspace)
        assert result2.is_error

    def test_edit_invalid_edits_type(self, workspace: Path):
        """Error when edits is not a list."""
        result = _call(
            "edit_file",
            {"path": "src/main.py", "edits": "not a list"},
            workspace,
        )
        assert result.is_error
        assert "list" in result.content.lower()

    def test_edit_invalid_edit_entry(self, workspace: Path):
        """Error when an edit entry is not a dict."""
        result = _call(
            "edit_file",
            {"path": "src/main.py", "edits": [42]},
            workspace,
        )
        assert result.is_error
        assert "index 0" in result.content

    def test_edit_empty_search_string(self, workspace: Path):
        """Error when search string is empty."""
        result = _call(
            "edit_file",
            {
                "path": "src/main.py",
                "edits": [{"search": "", "replace": "x"}],
            },
            workspace,
        )
        assert result.is_error

    def test_edit_absolute_path_rejected(self, workspace: Path):
        """Absolute paths must not bypass workspace containment."""
        result = _call(
            "edit_file",
            {
                "path": "/etc/passwd",
                "edits": [{"search": "x", "replace": "y"}],
            },
            workspace,
        )
        assert result.is_error

    def test_edit_symlink_outside_workspace(self, workspace: Path):
        """Symlinks pointing outside workspace must not allow edits."""
        external = workspace.parent / "external_file.txt"
        external.write_text("original content")
        _safe_symlink(external, workspace / "evil_link.txt")

        result = _call(
            "edit_file",
            {
                "path": "evil_link.txt",
                "edits": [{"search": "original", "replace": "hacked"}],
            },
            workspace,
        )
        assert result.is_error
        assert external.read_text() == "original content"


# ---------------------------------------------------------------------------
# create_file tests
# ---------------------------------------------------------------------------


class TestCreateFile:
    def test_create_new_file(self, workspace: Path):
        """Create a brand-new file successfully."""
        result = _call(
            "create_file",
            {"path": "src/new_module.py", "content": "# New module\n"},
            workspace,
        )
        assert not result.is_error
        assert (workspace / "src/new_module.py").exists()
        assert (workspace / "src/new_module.py").read_text() == "# New module\n"

    def test_create_with_nested_dirs(self, workspace: Path):
        """Auto-create parent directories."""
        result = _call(
            "create_file",
            {"path": "a/b/c/deep.py", "content": "deep = True\n"},
            workspace,
        )
        assert not result.is_error
        assert (workspace / "a/b/c/deep.py").exists()
        assert (workspace / "a/b/c/deep.py").read_text() == "deep = True\n"

    def test_create_existing_file_fails(self, workspace: Path):
        """CRITICAL: create_file must fail if file already exists."""
        result = _call(
            "create_file",
            {"path": "src/main.py", "content": "overwrite attempt"},
            workspace,
        )
        assert result.is_error
        assert "already exists" in result.content.lower()
        assert "edit_file" in result.content.lower()
        # File must NOT be overwritten
        assert "def hello():" in (workspace / "src/main.py").read_text()

    def test_create_path_traversal(self, workspace: Path):
        """Path traversal attempts are blocked."""
        result = _call(
            "create_file",
            {"path": "../../../tmp/evil.py", "content": "evil"},
            workspace,
        )
        assert result.is_error
        assert "escape" in result.content.lower() or "path" in result.content.lower()

    def test_create_missing_params(self, workspace: Path):
        """Error when required parameters are missing."""
        result = _call("create_file", {}, workspace)
        assert result.is_error

        result2 = _call("create_file", {"path": "new.py"}, workspace)
        assert result2.is_error

    def test_create_absolute_path_rejected(self, workspace: Path):
        """Absolute paths must not bypass workspace containment."""
        result = _call(
            "create_file",
            {"path": "/tmp/outside.py", "content": "outside"},
            workspace,
        )
        assert result.is_error

    def test_create_empty_content(self, workspace: Path):
        """Creating a file with empty content should succeed."""
        result = _call(
            "create_file",
            {"path": "empty_file.txt", "content": ""},
            workspace,
        )
        assert not result.is_error
        assert (workspace / "empty_file.txt").exists()
        assert (workspace / "empty_file.txt").read_text() == ""

    def test_create_symlink_dir_outside_workspace(self, workspace: Path):
        """Symlinked parent directory outside workspace must not allow creation."""
        external_dir = workspace.parent / "external_dir"
        external_dir.mkdir()
        _safe_symlink(external_dir, workspace / "linked_dir")

        result = _call(
            "create_file",
            {"path": "linked_dir/evil.py", "content": "evil"},
            workspace,
        )
        assert result.is_error
        assert not (external_dir / "evil.py").exists()
