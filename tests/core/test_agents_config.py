"""Tests for agent preferences loading from AGENTS.md and CLAUDE.md.

Tests the agents_config module which loads project-level preferences
for agent decision-making.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from codeframe.core.agents_config import (
    AgentPreferences,
    load_preferences,
    get_default_preferences,
    _parse_agents_md,
    _parse_list_items,
    _parse_key_value_items,
    _split_by_sections,
)


pytestmark = pytest.mark.v2


class TestAgentPreferences:
    """Tests for AgentPreferences dataclass."""

    def test_empty_preferences(self):
        """Empty preferences should report no preferences."""
        prefs = AgentPreferences()
        assert not prefs.has_preferences()

    def test_preferences_with_always_do(self):
        """Preferences with always_do should report has_preferences."""
        prefs = AgentPreferences(always_do=["test item"])
        assert prefs.has_preferences()

    def test_preferences_with_tooling(self):
        """Preferences with tooling should report has_preferences."""
        prefs = AgentPreferences(tooling={"package_manager": "uv"})
        assert prefs.has_preferences()

    def test_preferences_with_raw_content(self):
        """Preferences with raw_content should report has_preferences."""
        prefs = AgentPreferences(raw_content="some content")
        assert prefs.has_preferences()

    def test_to_prompt_section_empty(self):
        """Empty preferences should return empty prompt section."""
        prefs = AgentPreferences()
        assert prefs.to_prompt_section() == ""

    def test_to_prompt_section_with_tooling(self):
        """Preferences with tooling should generate proper prompt section."""
        prefs = AgentPreferences(tooling={"package_manager": "uv"})
        section = prefs.to_prompt_section()
        assert "## Project Preferences" in section
        assert "### Tooling" in section
        assert "package_manager" in section
        assert "uv" in section

    def test_to_prompt_section_with_always_do(self):
        """Preferences with always_do should generate proper prompt section."""
        prefs = AgentPreferences(always_do=["Run tests", "Fix linting"])
        section = prefs.to_prompt_section()
        assert "### Always Do" in section
        assert "Run tests" in section
        assert "Fix linting" in section

    def test_to_prompt_section_with_never_do(self):
        """Preferences with never_do should generate proper prompt section."""
        prefs = AgentPreferences(never_do=["Commit secrets"])
        section = prefs.to_prompt_section()
        assert "### Never Do" in section
        assert "Commit secrets" in section


class TestParseListItems:
    """Tests for _parse_list_items helper."""

    def test_parse_dash_list(self):
        """Parse dash-prefixed list items."""
        content = """- Item one
- Item two
- Item three"""
        items = _parse_list_items(content)
        assert items == ["Item one", "Item two", "Item three"]

    def test_parse_asterisk_list(self):
        """Parse asterisk-prefixed list items."""
        content = """* Item one
* Item two"""
        items = _parse_list_items(content)
        assert items == ["Item one", "Item two"]

    def test_parse_numbered_list(self):
        """Parse numbered list items."""
        content = """1. First item
2. Second item
3. Third item"""
        items = _parse_list_items(content)
        assert items == ["First item", "Second item", "Third item"]

    def test_parse_mixed_content(self):
        """Parse list items from mixed content."""
        content = """Some intro text

- Actual item
- Another item

More text"""
        items = _parse_list_items(content)
        assert items == ["Actual item", "Another item"]


class TestParseKeyValueItems:
    """Tests for _parse_key_value_items helper."""

    def test_parse_bold_key_value(self):
        """Parse **key**: value format."""
        content = """- **package_manager**: uv
- **test_runner**: pytest"""
        items = _parse_key_value_items(content)
        assert items["package_manager"] == "uv"
        assert items["test_runner"] == "pytest"

    def test_parse_backtick_key_value(self):
        """Parse `key`: value format."""
        content = """`build`: npm run build
`test`: npm test"""
        items = _parse_key_value_items(content)
        assert items["build"] == "npm run build"
        assert items["test"] == "npm test"

    def test_parse_simple_key_value(self):
        """Parse simple key: value format."""
        content = """package_manager: uv
test_runner: pytest"""
        items = _parse_key_value_items(content)
        assert items["package_manager"] == "uv"
        assert items["test_runner"] == "pytest"

    def test_key_normalization(self):
        """Keys should be normalized to lowercase with underscores."""
        content = """**Package Manager**: uv
**Test Runner**: pytest"""
        items = _parse_key_value_items(content)
        assert "package_manager" in items
        assert "test_runner" in items


class TestSplitBySections:
    """Tests for _split_by_sections helper."""

    def test_split_always_do_section(self):
        """Should identify Always Do section."""
        content = """# Always Do

- Item one
- Item two

# Never Do

- Item three"""
        sections = _split_by_sections(content)
        assert "always_do" in sections
        assert "Item one" in sections["always_do"]

    def test_split_never_do_section(self):
        """Should identify Never Do section."""
        content = """## Never Do

- Don't commit secrets"""
        sections = _split_by_sections(content)
        assert "never_do" in sections

    def test_split_tooling_section(self):
        """Should identify Tooling section."""
        content = """# Tooling

- **package_manager**: uv"""
        sections = _split_by_sections(content)
        assert "tooling" in sections


class TestParseAgentsMd:
    """Tests for _parse_agents_md function."""

    def test_parse_complete_agents_md(self):
        """Parse a complete AGENTS.md file."""
        content = """# Project Configuration

## Tooling

- **package_manager**: uv
- **test_runner**: pytest

## Always Do

- Run tests after changes
- Fix linting errors

## Never Do

- Commit secrets
- Delete .git directory

## Commands

- **test**: `uv run pytest`
- **lint**: `uv run ruff check .`
"""
        prefs = _parse_agents_md(content)

        assert prefs.tooling["package_manager"] == "uv"
        assert prefs.tooling["test_runner"] == "pytest"
        assert "Run tests after changes" in prefs.always_do
        assert "Commit secrets" in prefs.never_do
        assert "test" in prefs.commands
        assert content in prefs.raw_content

    def test_parse_minimal_agents_md(self):
        """Parse a minimal AGENTS.md file."""
        content = """# Always Do

- Be helpful"""
        prefs = _parse_agents_md(content)
        assert "Be helpful" in prefs.always_do

    def test_parse_empty_content(self):
        """Parse empty content."""
        prefs = _parse_agents_md("")
        assert not prefs.has_preferences()
        assert prefs.raw_content == ""


class TestLoadPreferences:
    """Tests for load_preferences function."""

    def test_load_from_workspace(self):
        """Load preferences from workspace AGENTS.md."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            agents_md = workspace / "AGENTS.md"
            agents_md.write_text("""# Tooling

- **package_manager**: npm

# Always Do

- Run lint
""")
            prefs = load_preferences(workspace)
            assert prefs.tooling.get("package_manager") == "npm"
            assert "Run lint" in prefs.always_do
            assert str(agents_md) in prefs.source_files

    def test_load_from_claude_md(self):
        """Load preferences from workspace CLAUDE.md."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            claude_md = workspace / "CLAUDE.md"
            claude_md.write_text("""# Always Do

- Use type hints
""")
            prefs = load_preferences(workspace)
            assert "Use type hints" in prefs.always_do
            assert str(claude_md) in prefs.source_files

    def test_agents_md_overrides_claude_md(self):
        """AGENTS.md should override CLAUDE.md at same level."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            claude_md = workspace / "CLAUDE.md"
            claude_md.write_text("""# Tooling

- **package_manager**: pip
""")

            agents_md = workspace / "AGENTS.md"
            agents_md.write_text("""# Tooling

- **package_manager**: uv
""")

            prefs = load_preferences(workspace)
            # AGENTS.md takes precedence
            assert prefs.tooling.get("package_manager") == "uv"

    def test_child_overrides_parent(self):
        """Child directory preferences override parent."""
        with TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            child = parent / "subproject"
            child.mkdir()

            parent_md = parent / "AGENTS.md"
            parent_md.write_text("""# Tooling

- **package_manager**: pip
""")

            child_md = child / "AGENTS.md"
            child_md.write_text("""# Tooling

- **package_manager**: uv
""")

            prefs = load_preferences(child)
            # Child takes precedence
            assert prefs.tooling.get("package_manager") == "uv"

    def test_no_preferences_file_returns_defaults(self):
        """Should return sensible defaults when no config files exist in workspace.

        Note: This may pick up global config from ~/.codeframe/AGENTS.md if it exists.
        If no config exists anywhere, returns get_default_preferences() instead of empty.
        """
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            prefs = load_preferences(workspace)
            # Should have preferences (either from global config or defaults)
            assert prefs.has_preferences()
            # Should have tooling/commands for autonomous operation
            assert prefs.tooling or prefs.commands


class TestGetDefaultPreferences:
    """Tests for get_default_preferences function."""

    def test_default_preferences_exist(self):
        """Default preferences should have content."""
        prefs = get_default_preferences()
        assert prefs.has_preferences()

    def test_default_always_do(self):
        """Default preferences should include always_do items."""
        prefs = get_default_preferences()
        assert len(prefs.always_do) > 0
        # Should include common autonomous actions
        assert any("approach" in item.lower() for item in prefs.always_do)

    def test_default_never_do(self):
        """Default preferences should include never_do items."""
        prefs = get_default_preferences()
        assert len(prefs.never_do) > 0
        # Should include security-related restrictions
        assert any("secret" in item.lower() for item in prefs.never_do)

    def test_default_source_files(self):
        """Default preferences should indicate source as defaults."""
        prefs = get_default_preferences()
        assert "<defaults>" in prefs.source_files
