"""Tests for CODEFRAME.md unified workflow configuration.

Tests the parse_codeframe_md() parser, integration into load_preferences(),
and the get_codeframe_config() accessor.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from codeframe.core.agents_config import (
    load_preferences,
    parse_codeframe_md,
    get_codeframe_config,
)


pytestmark = pytest.mark.v2


class TestParseCodeframeMdFull:
    """Tests for parse_codeframe_md with full YAML front matter + markdown body."""

    def test_parse_codeframe_md_full(self):
        """YAML front matter + markdown body returns both config and preferences."""
        content = """\
---
engine: react
tech_stack: "Python with uv"
batch:
  max_parallel: 4
  default_strategy: parallel
gates:
  - ruff
  - pytest
hooks:
  before_task: "git checkout -b cf/{{task_id}}"
  after_task: "git add -A"
agent:
  max_iterations: 30
  verbose: true
---

# Project Instructions

## Always Do

- Run tests after changes
- Fix linting errors

## Never Do

- Commit secrets
"""
        config, prefs = parse_codeframe_md(content)

        # CodeframeConfig fields
        assert config.engine == "react"
        assert config.tech_stack == "Python with uv"
        assert config.batch == {"max_parallel": 4, "default_strategy": "parallel"}
        assert config.gates == ["ruff", "pytest"]
        assert config.hooks["before_task"] == "git checkout -b cf/{{task_id}}"
        assert config.agent == {"max_iterations": 30, "verbose": True}
        assert config.raw["engine"] == "react"

        # AgentPreferences from markdown body
        assert "Run tests after changes" in prefs.always_do
        assert "Commit secrets" in prefs.never_do
        assert "CODEFRAME.md" in prefs.source_files[0]

    def test_parse_codeframe_md_yaml_only(self):
        """YAML front matter with no body returns config and minimal prefs."""
        content = """\
---
engine: plan
gates:
  - ruff
---
"""
        config, prefs = parse_codeframe_md(content)

        assert config.engine == "plan"
        assert config.gates == ["ruff"]
        # Preferences should still be valid but empty lists
        assert prefs.always_do == []
        assert prefs.never_do == []

    def test_parse_codeframe_md_body_only(self):
        """No YAML front matter - just markdown - backward compat."""
        content = """\
# Project Instructions

## Always Do

- Use type hints
- Write docstrings
"""
        config, prefs = parse_codeframe_md(content)

        # Config should be empty defaults
        assert config.engine is None
        assert config.gates == []
        assert config.batch == {}
        assert config.raw == {}

        # Preferences should be parsed from the body
        assert "Use type hints" in prefs.always_do
        assert "Write docstrings" in prefs.always_do

    def test_parse_codeframe_md_invalid_yaml(self):
        """Invalid YAML should be handled gracefully."""
        content = """\
---
engine: react
bad_yaml: [unclosed
  - broken
---

# Instructions

## Always Do

- Be helpful
"""
        config, prefs = parse_codeframe_md(content)

        # Config should be empty due to parse failure
        assert config.engine is None
        assert config.raw == {}

        # Body should still be parsed
        assert "Be helpful" in prefs.always_do

    def test_parse_codeframe_md_empty(self):
        """Empty content should return empty config and prefs."""
        config, prefs = parse_codeframe_md("")

        assert config.engine is None
        assert config.gates == []
        assert config.raw == {}
        assert prefs.always_do == []
        assert prefs.raw_content == ""


class TestParseCodeframeMdFields:
    """Tests for individual field extraction."""

    def test_parse_codeframe_md_extracts_engine(self):
        """engine field should be populated from YAML."""
        content = """\
---
engine: react
---
"""
        config, _ = parse_codeframe_md(content)
        assert config.engine == "react"

    def test_parse_codeframe_md_extracts_gates(self):
        """gates list should be populated from YAML."""
        content = """\
---
gates:
  - ruff
  - pytest
  - mypy
---
"""
        config, _ = parse_codeframe_md(content)
        assert config.gates == ["ruff", "pytest", "mypy"]

    def test_parse_codeframe_md_extracts_hooks(self):
        """hooks dict should be populated from YAML."""
        content = """\
---
hooks:
  before_task: "echo starting"
  after_task: "echo done"
  on_failure: "notify-send 'Task failed'"
---
"""
        config, _ = parse_codeframe_md(content)
        assert config.hooks["before_task"] == "echo starting"
        assert config.hooks["after_task"] == "echo done"
        assert config.hooks["on_failure"] == "notify-send 'Task failed'"

    def test_parse_codeframe_md_extracts_batch(self):
        """batch settings should be populated from YAML."""
        content = """\
---
batch:
  max_parallel: 8
  default_strategy: auto
---
"""
        config, _ = parse_codeframe_md(content)
        assert config.batch["max_parallel"] == 8
        assert config.batch["default_strategy"] == "auto"

    def test_parse_codeframe_md_tech_stack_in_preferences(self):
        """tech_stack from YAML should also appear in preferences tooling."""
        content = """\
---
tech_stack: "TypeScript with npm, Next.js, jest"
---
"""
        config, prefs = parse_codeframe_md(content)
        assert config.tech_stack == "TypeScript with npm, Next.js, jest"
        assert prefs.tooling.get("tech_stack") == "TypeScript with npm, Next.js, jest"


class TestLoadPreferencesWithCodeframeMd:
    """Tests for load_preferences() integration with CODEFRAME.md."""

    def test_load_preferences_codeframe_highest_priority(self):
        """CODEFRAME.md should override AGENTS.md at the same level."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            agents_md = workspace / "AGENTS.md"
            agents_md.write_text("""\
# Tooling

- **package_manager**: pip
""")

            codeframe_md = workspace / "CODEFRAME.md"
            codeframe_md.write_text("""\
---
tech_stack: "Python with uv"
---

# Tooling

- **package_manager**: uv
""")

            prefs = load_preferences(workspace)
            assert prefs.tooling.get("package_manager") == "uv"
            assert any("CODEFRAME.md" in f for f in prefs.source_files)

    def test_load_preferences_fallback_agents_md(self):
        """Falls back to AGENTS.md when no CODEFRAME.md exists."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            agents_md = workspace / "AGENTS.md"
            agents_md.write_text("""\
# Tooling

- **package_manager**: yarn
""")

            prefs = load_preferences(workspace)
            assert prefs.tooling.get("package_manager") == "yarn"
            assert any("AGENTS.md" in f for f in prefs.source_files)

    def test_load_preferences_fallback_claude_md(self):
        """Falls back to CLAUDE.md when no CODEFRAME.md or AGENTS.md exists."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            claude_md = workspace / "CLAUDE.md"
            claude_md.write_text("""\
# Always Do

- Write tests first
""")

            prefs = load_preferences(workspace)
            assert "Write tests first" in prefs.always_do
            assert any("CLAUDE.md" in f for f in prefs.source_files)


class TestGetCodeframeConfig:
    """Tests for get_codeframe_config() accessor."""

    def test_get_codeframe_config_found(self):
        """Returns config when CODEFRAME.md exists."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            codeframe_md = workspace / "CODEFRAME.md"
            codeframe_md.write_text("""\
---
engine: react
gates:
  - ruff
  - pytest
batch:
  max_parallel: 4
---

# Instructions
""")

            config = get_codeframe_config(workspace)
            assert config is not None
            assert config.engine == "react"
            assert config.gates == ["ruff", "pytest"]
            assert config.batch["max_parallel"] == 4

    def test_get_codeframe_config_not_found(self):
        """Returns None when no CODEFRAME.md exists."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            config = get_codeframe_config(workspace)
            assert config is None
