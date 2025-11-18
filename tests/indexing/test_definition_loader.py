"""Tests for AgentDefinitionLoader."""

import pytest
import tempfile
from pathlib import Path

from codeframe.agents.definition_loader import AgentDefinition, AgentDefinitionLoader
from codeframe.core.models import AgentMaturity


class TestAgentDefinition:
    """Test AgentDefinition dataclass."""

    def test_valid_definition(self) -> None:
        """Test creating a valid agent definition."""
        definition = AgentDefinition(
            name="test-agent",
            type="test",
            system_prompt="You are a test agent",
            maturity=AgentMaturity.D1,
            description="Test description",
            capabilities=["testing", "validation"],
            tools=["test_tool"],
            constraints={"max_tokens": 1000},
            metadata={"version": "1.0.0"},
        )

        definition.validate()
        assert definition.name == "test-agent"
        assert definition.type == "test"
        assert definition.maturity == AgentMaturity.D1

    def test_missing_name(self) -> None:
        """Test validation fails with missing name."""
        definition = AgentDefinition(name="", type="test", system_prompt="Test prompt")

        with pytest.raises(ValueError, match="must have a 'name' field"):
            definition.validate()

    def test_missing_type(self) -> None:
        """Test validation fails with missing type."""
        definition = AgentDefinition(name="test", type="", system_prompt="Test prompt")

        with pytest.raises(ValueError, match="must have a 'type' field"):
            definition.validate()

    def test_missing_system_prompt(self) -> None:
        """Test validation fails with missing system_prompt."""
        definition = AgentDefinition(name="test", type="test", system_prompt="")

        with pytest.raises(ValueError, match="must have a 'system_prompt' field"):
            definition.validate()

    def test_invalid_capabilities_type(self) -> None:
        """Test validation fails with non-list capabilities."""
        definition = AgentDefinition(
            name="test",
            type="test",
            system_prompt="Test",
            capabilities="not a list",  # type: ignore
        )

        with pytest.raises(ValueError, match="'capabilities' must be a list"):
            definition.validate()


class TestAgentDefinitionLoader:
    """Test AgentDefinitionLoader class."""

    @pytest.fixture
    def temp_definitions_dir(self) -> Path:
        """Create a temporary directory for test definitions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_yaml_content(self) -> str:
        """Sample YAML content for testing."""
        return """
name: test-backend
type: backend
maturity: D2
description: "Test backend agent"

capabilities:
  - API design
  - Database optimization

system_prompt: |
  You are a test backend specialist.
  Focus on quality and performance.

tools:
  - database_query
  - api_test

constraints:
  max_tokens: 5000
  temperature: 0.7

metadata:
  version: "1.0.0"
  author: "Test Team"
"""

    def test_load_single_definition(
        self, temp_definitions_dir: Path, sample_yaml_content: str
    ) -> None:
        """Test loading a single YAML definition."""
        # Create YAML file
        yaml_file = temp_definitions_dir / "test-backend.yaml"
        yaml_file.write_text(sample_yaml_content)

        # Load definitions
        loader = AgentDefinitionLoader()
        definitions = loader.load_definitions(temp_definitions_dir)

        assert len(definitions) == 1
        assert "test-backend" in definitions

        definition = definitions["test-backend"]
        assert definition.name == "test-backend"
        assert definition.type == "backend"
        assert definition.maturity == AgentMaturity.D2
        assert "API design" in definition.capabilities
        assert "database_query" in definition.tools

    def test_load_multiple_definitions(self, temp_definitions_dir: Path) -> None:
        """Test loading multiple YAML definitions."""
        # Create multiple YAML files
        yaml1 = temp_definitions_dir / "backend.yaml"
        yaml1.write_text(
            """
name: backend-agent
type: backend
system_prompt: "Backend specialist"
"""
        )

        yaml2 = temp_definitions_dir / "frontend.yaml"
        yaml2.write_text(
            """
name: frontend-agent
type: frontend
system_prompt: "Frontend specialist"
"""
        )

        # Load definitions
        loader = AgentDefinitionLoader()
        definitions = loader.load_definitions(temp_definitions_dir)

        assert len(definitions) == 2
        assert "backend-agent" in definitions
        assert "frontend-agent" in definitions

    def test_load_from_custom_subdirectory(self, temp_definitions_dir: Path) -> None:
        """Test loading definitions from custom subdirectory."""
        # Create custom subdirectory
        custom_dir = temp_definitions_dir / "custom"
        custom_dir.mkdir()

        # Create YAML in custom directory
        yaml_file = custom_dir / "custom-agent.yaml"
        yaml_file.write_text(
            """
name: custom-agent
type: custom
system_prompt: "Custom agent"
"""
        )

        # Load definitions
        loader = AgentDefinitionLoader()
        definitions = loader.load_definitions(temp_definitions_dir)

        assert len(definitions) == 1
        assert "custom-agent" in definitions

    def test_get_definition(self, temp_definitions_dir: Path, sample_yaml_content: str) -> None:
        """Test retrieving a specific definition."""
        yaml_file = temp_definitions_dir / "test.yaml"
        yaml_file.write_text(sample_yaml_content)

        loader = AgentDefinitionLoader()
        loader.load_definitions(temp_definitions_dir)

        definition = loader.get_definition("test-backend")
        assert definition.name == "test-backend"

    def test_get_missing_definition(self, temp_definitions_dir: Path) -> None:
        """Test error when getting non-existent definition."""
        loader = AgentDefinitionLoader()
        loader.load_definitions(temp_definitions_dir)

        with pytest.raises(KeyError, match="not found"):
            loader.get_definition("nonexistent")

    def test_create_agent(self, temp_definitions_dir: Path, sample_yaml_content: str) -> None:
        """Test creating an agent from definition."""
        yaml_file = temp_definitions_dir / "test.yaml"
        yaml_file.write_text(sample_yaml_content)

        loader = AgentDefinitionLoader()
        loader.load_definitions(temp_definitions_dir)

        agent = loader.create_agent(
            agent_type="test-backend", agent_id="test-001", provider="anthropic"
        )

        assert agent.agent_id == "test-001"
        assert agent.agent_type == "backend"
        assert agent.maturity == AgentMaturity.D2
        assert hasattr(agent, "definition")
        assert agent.definition.name == "test-backend"

    def test_list_available_types(self, temp_definitions_dir: Path) -> None:
        """Test listing available agent types."""
        # Create multiple definitions
        for i, name in enumerate(["agent1", "agent2", "agent3"]):
            yaml_file = temp_definitions_dir / f"{name}.yaml"
            yaml_file.write_text(
                f"""
name: {name}
type: type{i}
system_prompt: "Test agent {i}"
"""
            )

        loader = AgentDefinitionLoader()
        loader.load_definitions(temp_definitions_dir)

        available = loader.list_available_types()
        assert len(available) == 3
        assert "agent1" in available
        assert "agent2" in available
        assert "agent3" in available

    def test_get_definitions_by_type(self, temp_definitions_dir: Path) -> None:
        """Test querying definitions by type category."""
        # Create definitions of different types
        yaml1 = temp_definitions_dir / "backend1.yaml"
        yaml1.write_text(
            """
name: backend1
type: backend
system_prompt: "Backend 1"
"""
        )

        yaml2 = temp_definitions_dir / "backend2.yaml"
        yaml2.write_text(
            """
name: backend2
type: backend
system_prompt: "Backend 2"
"""
        )

        yaml3 = temp_definitions_dir / "frontend1.yaml"
        yaml3.write_text(
            """
name: frontend1
type: frontend
system_prompt: "Frontend 1"
"""
        )

        loader = AgentDefinitionLoader()
        loader.load_definitions(temp_definitions_dir)

        backend_defs = loader.get_definitions_by_type("backend")
        frontend_defs = loader.get_definitions_by_type("frontend")

        assert len(backend_defs) == 2
        assert len(frontend_defs) == 1
        assert all(d.type == "backend" for d in backend_defs)
        assert all(d.type == "frontend" for d in frontend_defs)

    def test_reload_definitions(self, temp_definitions_dir: Path) -> None:
        """Test reloading definitions clears cache."""
        # Create initial definition
        yaml_file = temp_definitions_dir / "agent1.yaml"
        yaml_file.write_text(
            """
name: agent1
type: test
system_prompt: "Test"
"""
        )

        loader = AgentDefinitionLoader()
        definitions = loader.load_definitions(temp_definitions_dir)
        assert len(definitions) == 1

        # Add another definition
        yaml_file2 = temp_definitions_dir / "agent2.yaml"
        yaml_file2.write_text(
            """
name: agent2
type: test
system_prompt: "Test 2"
"""
        )

        # Reload
        definitions = loader.reload_definitions(temp_definitions_dir)
        assert len(definitions) == 2

    def test_invalid_maturity_level(self, temp_definitions_dir: Path) -> None:
        """Test error on invalid maturity level."""
        yaml_file = temp_definitions_dir / "bad.yaml"
        yaml_file.write_text(
            """
name: bad-agent
type: test
maturity: INVALID
system_prompt: "Test"
"""
        )

        loader = AgentDefinitionLoader()
        with pytest.raises(ValueError, match="Invalid maturity level"):
            loader.load_definitions(temp_definitions_dir)

    def test_empty_yaml_file(self, temp_definitions_dir: Path) -> None:
        """Test loading empty YAML file is skipped."""
        yaml_file = temp_definitions_dir / "empty.yaml"
        yaml_file.write_text("")

        loader = AgentDefinitionLoader()
        definitions = loader.load_definitions(temp_definitions_dir)
        assert len(definitions) == 0

    def test_nonexistent_directory(self) -> None:
        """Test error when loading from non-existent directory."""
        loader = AgentDefinitionLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_definitions(Path("/nonexistent/path"))

    def test_file_path_instead_of_directory(self, temp_definitions_dir: Path) -> None:
        """Test error when path is a file instead of directory."""
        file_path = temp_definitions_dir / "file.txt"
        file_path.write_text("test")

        loader = AgentDefinitionLoader()
        with pytest.raises(ValueError, match="must be a directory"):
            loader.load_definitions(file_path)
