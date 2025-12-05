"""Tests for SubagentGenerator - SDK subagent markdown generation.

Tests cover:
- YAML definition loading
- Markdown generation for all agent types
- Tool mapping (YAML → SDK)
- Maturity level injection
- Error handling and edge cases
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from codeframe.agents.subagent_generator import (
    SubagentGenerator,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_definitions_dir():
    """Create a temporary directory with test YAML definitions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        definitions_dir = Path(tmpdir)

        # Create a minimal backend agent definition
        backend_yaml = definitions_dir / "backend.yaml"
        backend_yaml.write_text(
            """
name: "Backend Worker"
type: "backend"
description: |
  Backend development agent for Python tasks.
  Handles API design, database modeling, and testing.

capabilities:
  - python_development
  - api_design
  - database_modeling
  - tdd

system_prompt: |
  You are a Backend Worker Agent.
  Write clean, well-tested Python code.

tools:
  - anthropic_api
  - codebase_index
  - file_operations
  - test_runner
  - git_operations

maturity_progression:
  - level: D1
    description: "Basic task execution with supervision"
    capabilities: ["simple_functions", "basic_tests"]
  - level: D2
    description: "Independent feature implementation"
    capabilities: ["complex_logic", "integration_tests", "error_handling"]
  - level: D3
    description: "Architecture decisions and optimization"
    capabilities: ["design_patterns", "performance_tuning"]
  - level: D4
    description: "System-level thinking and mentorship"
    capabilities: ["architectural_design", "code_review"]

error_recovery:
  max_correction_attempts: 3
  escalation_policy: "Create blocker for manual intervention"

integration_points:
  - database: "Task queue and status updates"
  - codebase_index: "Symbol search and file discovery"
"""
        )

        # Create a frontend agent definition
        frontend_yaml = definitions_dir / "frontend.yaml"
        frontend_yaml.write_text(
            """
name: "Frontend Specialist"
type: "frontend"
description: "React/TypeScript frontend development"

capabilities:
  - react_development
  - typescript
  - tailwind_css

system_prompt: |
  You are a Frontend Specialist Agent.
  Build React components with TypeScript.

tools:
  - file_operations
  - codebase_index
"""
        )

        yield definitions_dir


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def generator(temp_definitions_dir, temp_output_dir):
    """Create a SubagentGenerator with test definitions."""
    return SubagentGenerator(
        definitions_dir=temp_definitions_dir,
        output_dir=temp_output_dir,
    )


# ============================================================================
# Definition Loading Tests
# ============================================================================


class TestDefinitionLoading:
    """Tests for YAML definition loading."""

    def test_loads_yaml_files_on_init(self, generator):
        """Should load all YAML definitions on initialization."""
        available = generator.list_available_types()
        assert "Backend Worker" in available
        assert "Frontend Specialist" in available
        assert len(available) == 2

    def test_loads_raw_definitions(self, generator):
        """Should store raw YAML data for each agent."""
        raw_def = generator.get_raw_definition("Backend Worker")
        assert raw_def["name"] == "Backend Worker"
        assert raw_def["type"] == "backend"
        assert "system_prompt" in raw_def
        assert "tools" in raw_def
        assert "maturity_progression" in raw_def

    def test_handles_missing_definitions_dir(self, temp_output_dir):
        """Should handle non-existent definitions directory gracefully."""
        generator = SubagentGenerator(
            definitions_dir=Path("/nonexistent/path"),
            output_dir=temp_output_dir,
        )
        assert generator.list_available_types() == []

    def test_reload_definitions(self, generator, temp_definitions_dir):
        """Should reload definitions from disk."""
        # Add a new definition
        new_yaml = temp_definitions_dir / "test.yaml"
        new_yaml.write_text(
            """
name: "Test Agent"
type: "test"
system_prompt: "You are a test agent."
"""
        )

        # Reload
        generator.reload_definitions()
        assert "Test Agent" in generator.list_available_types()

    def test_invalid_agent_name_raises_keyerror(self, generator):
        """Should raise KeyError for unknown agent names."""
        with pytest.raises(KeyError, match="not found"):
            generator.get_raw_definition("NonExistent Agent")


# ============================================================================
# Markdown Generation Tests
# ============================================================================


class TestMarkdownGeneration:
    """Tests for markdown file generation."""

    def test_generate_single_agent(self, generator, temp_output_dir):
        """Should generate markdown for a single agent."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")

        assert output_path.exists()
        assert output_path.suffix == ".md"

        content = output_path.read_text()
        assert "---" in content  # Has frontmatter
        assert "name: Backend Worker" in content
        assert "tools:" in content

    def test_generate_all_agents(self, generator, temp_output_dir):
        """Should generate markdown for all agents."""
        paths = generator.generate_all(maturity="D2")

        assert len(paths) == 2
        assert all(p.exists() for p in paths)
        assert all(p.suffix == ".md" for p in paths)

    def test_output_directory_created(self, temp_definitions_dir):
        """Should create output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "subdir" / "agents"
            generator = SubagentGenerator(
                definitions_dir=temp_definitions_dir,
                output_dir=output_dir,
            )
            generator.generate_agent("Backend Worker", maturity="D1")
            assert output_dir.exists()

    def test_filename_sanitization(self, generator, temp_output_dir):
        """Should sanitize agent names for filenames."""
        output_path = generator.generate_agent("Backend Worker", maturity="D1")
        assert output_path.name == "backend-worker.md"

    def test_invalid_maturity_raises_error(self, generator):
        """Should raise ValueError for invalid maturity levels."""
        with pytest.raises(ValueError, match="Invalid maturity level"):
            generator.generate_agent("Backend Worker", maturity="D5")

    def test_unknown_agent_raises_error(self, generator):
        """Should raise KeyError for unknown agent names."""
        with pytest.raises(KeyError, match="not found"):
            generator.generate_agent("Unknown Agent", maturity="D2")


# ============================================================================
# Markdown Content Tests
# ============================================================================


class TestMarkdownContent:
    """Tests for markdown content structure and accuracy."""

    def test_frontmatter_format(self, generator, temp_output_dir):
        """Should generate valid YAML frontmatter."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        # Check frontmatter delimiters
        assert content.startswith("---")
        lines = content.split("\n")
        frontmatter_end = lines[1:].index("---") + 1

        # Check required frontmatter fields
        frontmatter_section = "\n".join(lines[: frontmatter_end + 1])
        assert "name:" in frontmatter_section
        assert "description:" in frontmatter_section
        assert "tools:" in frontmatter_section

    def test_system_prompt_included(self, generator, temp_output_dir):
        """Should include the system prompt in markdown body."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        assert "You are a Backend Worker Agent" in content
        assert "Write clean, well-tested Python code" in content

    def test_maturity_section_included(self, generator, temp_output_dir):
        """Should include maturity level section."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        assert "## Maturity Level: D2" in content
        assert "Independent feature implementation" in content

    def test_maturity_capabilities_included(self, generator, temp_output_dir):
        """Should include maturity-specific capabilities."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        assert "### Capabilities at this level:" in content
        assert "complex_logic" in content
        assert "integration_tests" in content

    def test_different_maturity_levels(self, generator, temp_output_dir):
        """Should generate different content for each maturity level."""
        d1_path = generator.generate_agent("Backend Worker", maturity="D1")
        d1_content = d1_path.read_text()  # Read before overwriting

        d3_path = generator.generate_agent("Backend Worker", maturity="D3")
        d3_content = d3_path.read_text()

        # D1 should have basic capabilities
        assert "## Maturity Level: D1" in d1_content
        assert "simple_functions" in d1_content

        # D3 should have advanced capabilities
        assert "## Maturity Level: D3" in d3_content
        assert "design_patterns" in d3_content

    def test_error_recovery_section(self, generator, temp_output_dir):
        """Should include error recovery section."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        assert "## Error Recovery" in content
        assert "Max correction attempts: 3" in content
        assert "Escalation:" in content

    def test_integration_points_section(self, generator, temp_output_dir):
        """Should include integration points if present."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        assert "## Integration Points" in content
        assert "database" in content.lower()


# ============================================================================
# Tool Mapping Tests
# ============================================================================


class TestToolMapping:
    """Tests for YAML tool to SDK tool mapping."""

    def test_file_operations_maps_to_read_write(self, generator):
        """file_operations should map to Read and Write."""
        sdk_tools = generator._map_tools_to_sdk(["file_operations"])
        assert "Read" in sdk_tools
        assert "Write" in sdk_tools

    def test_codebase_index_maps_to_glob_grep(self, generator):
        """codebase_index should map to Glob and Grep."""
        sdk_tools = generator._map_tools_to_sdk(["codebase_index"])
        assert "Glob" in sdk_tools
        assert "Grep" in sdk_tools

    def test_test_runner_maps_to_bash(self, generator):
        """test_runner should map to Bash."""
        sdk_tools = generator._map_tools_to_sdk(["test_runner"])
        assert "Bash" in sdk_tools

    def test_git_operations_maps_to_bash(self, generator):
        """git_operations should map to Bash."""
        sdk_tools = generator._map_tools_to_sdk(["git_operations"])
        assert "Bash" in sdk_tools

    def test_anthropic_api_maps_to_empty(self, generator):
        """anthropic_api should not add SDK tools (handled internally)."""
        sdk_tools = generator._map_tools_to_sdk(["anthropic_api"])
        # Should only have default tools (Read, Glob)
        assert "Read" in sdk_tools
        assert "Glob" in sdk_tools

    def test_multiple_tools_combined(self, generator):
        """Multiple YAML tools should be combined and deduplicated."""
        sdk_tools = generator._map_tools_to_sdk(
            ["file_operations", "test_runner", "git_operations"]
        )
        assert "Read" in sdk_tools
        assert "Write" in sdk_tools
        assert "Bash" in sdk_tools
        # Bash should only appear once
        assert sdk_tools.count("Bash") == 1

    def test_tools_sorted_alphabetically(self, generator):
        """SDK tools should be sorted alphabetically."""
        sdk_tools = generator._map_tools_to_sdk(
            ["file_operations", "codebase_index", "test_runner"]
        )
        assert sdk_tools == sorted(sdk_tools)

    def test_unknown_tool_logged_as_warning(self, generator):
        """Unknown tools should be logged but not cause failure."""
        with patch("codeframe.agents.subagent_generator.logger") as mock_logger:
            sdk_tools = generator._map_tools_to_sdk(["unknown_tool"])
            mock_logger.warning.assert_called()
            # Should still have default tools
            assert "Read" in sdk_tools
            assert "Glob" in sdk_tools

    def test_generated_markdown_has_correct_tools(self, generator, temp_output_dir):
        """Generated markdown should have correctly mapped tools."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        # Backend Worker has: anthropic_api, codebase_index, file_operations,
        # test_runner, git_operations
        # Expected SDK tools: Bash, Glob, Grep, Read, Write
        assert "Bash" in content
        assert "Glob" in content
        assert "Grep" in content
        assert "Read" in content
        assert "Write" in content


# ============================================================================
# Maturity Config Tests
# ============================================================================


class TestMaturityConfig:
    """Tests for maturity configuration extraction."""

    def test_get_maturity_config_d1(self, generator):
        """Should extract D1 maturity config."""
        raw_def = generator.get_raw_definition("Backend Worker")
        config = generator._get_maturity_config(raw_def, "D1")

        assert config is not None
        assert config.level == "D1"
        assert "Basic task execution" in config.description
        assert "simple_functions" in config.capabilities

    def test_get_maturity_config_d4(self, generator):
        """Should extract D4 maturity config."""
        raw_def = generator.get_raw_definition("Backend Worker")
        config = generator._get_maturity_config(raw_def, "D4")

        assert config is not None
        assert config.level == "D4"
        assert "System-level" in config.description
        assert "architectural_design" in config.capabilities

    def test_missing_maturity_returns_none(self, generator):
        """Should return None if maturity level not defined."""
        raw_def = generator.get_raw_definition("Frontend Specialist")
        config = generator._get_maturity_config(raw_def, "D3")

        assert config is None

    def test_fallback_to_general_capabilities(self, generator, temp_output_dir):
        """Should use general capabilities if maturity-specific not available."""
        output_path = generator.generate_agent("Frontend Specialist", maturity="D2")
        content = output_path.read_text()

        # Should fall back to general capabilities
        assert "react_development" in content or "Capabilities" in content


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_capabilities_list(self, temp_output_dir):
        """Should handle agents with no capabilities."""
        with tempfile.TemporaryDirectory() as tmpdir:
            definitions_dir = Path(tmpdir)
            yaml_file = definitions_dir / "minimal.yaml"
            yaml_file.write_text(
                """
name: "Minimal Agent"
type: "test"
system_prompt: "Minimal system prompt."
tools: []
capabilities: []
"""
            )

            generator = SubagentGenerator(
                definitions_dir=definitions_dir,
                output_dir=temp_output_dir,
            )
            output_path = generator.generate_agent("Minimal Agent", maturity="D1")

            content = output_path.read_text()
            assert "General task execution" in content

    def test_empty_tools_list(self, temp_output_dir):
        """Should handle agents with no tools (uses defaults)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            definitions_dir = Path(tmpdir)
            yaml_file = definitions_dir / "notool.yaml"
            yaml_file.write_text(
                """
name: "No Tool Agent"
type: "test"
system_prompt: "Agent without tools."
tools: []
"""
            )

            generator = SubagentGenerator(
                definitions_dir=definitions_dir,
                output_dir=temp_output_dir,
            )
            output_path = generator.generate_agent("No Tool Agent", maturity="D1")

            content = output_path.read_text()
            # Should have default tools
            assert "Read" in content
            assert "Glob" in content

    def test_multiline_description(self, generator, temp_output_dir):
        """Should handle multiline descriptions, using first line in frontmatter."""
        output_path = generator.generate_agent("Backend Worker", maturity="D2")
        content = output_path.read_text()

        # Frontmatter should have single-line description
        lines = content.split("\n")
        for line in lines[:10]:  # Check frontmatter area
            if line.startswith("description:"):
                # Should be the first line of the description
                assert "Backend development agent" in line
                break

    def test_special_characters_in_name(self, temp_output_dir):
        """Should handle special characters in agent names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            definitions_dir = Path(tmpdir)
            yaml_file = definitions_dir / "special.yaml"
            yaml_file.write_text(
                """
name: "Test & Debug Agent (v2.0)"
type: "test"
system_prompt: "Special name agent."
"""
            )

            generator = SubagentGenerator(
                definitions_dir=definitions_dir,
                output_dir=temp_output_dir,
            )
            output_path = generator.generate_agent("Test & Debug Agent (v2.0)", maturity="D1")

            # Filename should be sanitized
            assert "test" in output_path.name.lower()


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests using real definition files."""

    def test_with_real_definitions_dir(self, temp_output_dir):
        """Test with actual CodeFRAME definitions directory."""
        real_definitions = Path("codeframe/agents/definitions")

        generator = SubagentGenerator(
            definitions_dir=real_definitions,
            output_dir=temp_output_dir,
        )

        # Should have loaded some definitions
        available = generator.list_available_types()
        assert len(available) > 0

        # Generate all agents
        paths = generator.generate_all(maturity="D2")
        assert len(paths) > 0

        # All generated files should be valid markdown
        for path in paths:
            content = path.read_text()
            assert content.startswith("---")
            assert "name:" in content
            assert "tools:" in content

    def test_roundtrip_consistency(self, generator, temp_output_dir):
        """Generated markdown should be consistent across runs."""
        path1 = generator.generate_agent("Backend Worker", maturity="D2")
        content1 = path1.read_text()

        # Generate again
        path2 = generator.generate_agent("Backend Worker", maturity="D2")
        content2 = path2.read_text()

        assert content1 == content2
