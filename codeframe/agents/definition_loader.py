"""Agent Definition Loader for YAML/Markdown-based agent configuration.

This module provides the infrastructure for loading agent definitions from
YAML configuration files, enabling dynamic agent creation with declarative
specifications.

Schema Documentation:
--------------------

YAML Agent Definition Format:
```yaml
name: backend-architect
type: backend
maturity: D2
description: "Specialized in backend architecture and API design"

capabilities:
  - API design and implementation
  - Database schema design
  - Performance optimization
  - Security best practices

system_prompt: |
  You are a backend architecture specialist with expertise in:
  - RESTful and GraphQL API design
  - Database optimization and schema design
  - Authentication and authorization patterns
  - Microservices architecture

  Your focus is on scalable, maintainable backend systems.

tools:
  - database_query
  - api_test
  - performance_profile

constraints:
  max_tokens: 8000
  temperature: 0.7
  timeout_seconds: 300

metadata:
  version: "1.0.0"
  author: "CodeFRAME Team"
  tags:
    - backend
    - architecture
    - api
```

Required Fields:
- name: Unique agent identifier (str)
- type: Agent category (str)
- system_prompt: Agent behavioral instructions (str)

Optional Fields:
- maturity: Agent maturity level (D1-D4, default: D1)
- description: Human-readable description (str)
- capabilities: List of agent capabilities (list[str])
- tools: Available tool names (list[str])
- constraints: Execution constraints (dict)
- metadata: Additional metadata (dict)

Example Usage:
-------------
```python
from pathlib import Path
from codeframe.agents.definition_loader import AgentDefinitionLoader

# Initialize loader
loader = AgentDefinitionLoader()

# Load all definitions from a directory
definitions = loader.load_definitions(Path("codeframe/agents/definitions"))

# Get specific definition
backend_def = loader.get_definition("backend-architect")

# Create agent from definition
agent = loader.create_agent("backend-architect", agent_id="agent-001")

# List all available agent types
available = loader.list_available_types()
print(f"Available agents: {available}")
```

Error Handling:
--------------
- ValidationError: Missing required fields or invalid values
- FileNotFoundError: Definition file not found
- yaml.YAMLError: Invalid YAML syntax
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any

from codeframe.core.models import AgentMaturity
from codeframe.agents.worker_agent import WorkerAgent


@dataclass
class AgentDefinition:
    """
    Agent definition data structure.

    Attributes:
        name: Unique agent identifier
        type: Agent category (backend, frontend, test, review, etc.)
        system_prompt: Behavioral instructions for the agent
        maturity: Agent maturity level (D1-D4)
        description: Human-readable description
        capabilities: List of agent capabilities
        tools: Available tool names
        constraints: Execution constraints (tokens, temperature, timeout)
        metadata: Additional metadata (version, author, tags)
    """

    name: str
    type: str
    system_prompt: str
    maturity: AgentMaturity = AgentMaturity.D1
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """
        Validate agent definition for required fields and valid values.

        Raises:
            ValueError: If validation fails
        """
        if not self.name:
            raise ValueError("Agent definition must have a 'name' field")

        if not self.type:
            raise ValueError("Agent definition must have a 'type' field")

        if not self.system_prompt:
            raise ValueError("Agent definition must have a 'system_prompt' field")

        # Validate maturity level
        if not isinstance(self.maturity, AgentMaturity):
            raise ValueError(
                f"Invalid maturity level: {self.maturity}. "
                f"Must be one of: {[m.value for m in AgentMaturity]}"
            )

        # Validate capabilities is a list
        if not isinstance(self.capabilities, list):
            raise ValueError("'capabilities' must be a list")

        # Validate tools is a list
        if not isinstance(self.tools, list):
            raise ValueError("'tools' must be a list")

        # Validate constraints is a dict
        if not isinstance(self.constraints, dict):
            raise ValueError("'constraints' must be a dictionary")

        # Validate metadata is a dict
        if not isinstance(self.metadata, dict):
            raise ValueError("'metadata' must be a dictionary")


class AgentDefinitionLoader:
    """
    Loader for YAML-based agent definitions.

    Manages loading, validation, and caching of agent definitions from
    YAML files. Supports both built-in and custom agent definitions.
    """

    def __init__(self) -> None:
        """Initialize the agent definition loader."""
        self._definitions: Dict[str, AgentDefinition] = {}

    def load_definitions(self, path: Path) -> Dict[str, AgentDefinition]:
        """
        Load all agent definitions from a directory.

        Scans the directory for YAML files (.yaml, .yml) and loads each
        as an agent definition. Validates all definitions after loading.

        Args:
            path: Directory path containing agent definition files

        Returns:
            Dictionary mapping agent names to AgentDefinition objects

        Raises:
            FileNotFoundError: If path does not exist
            yaml.YAMLError: If YAML parsing fails
            ValueError: If validation fails
        """
        if not path.exists():
            raise FileNotFoundError(f"Definition path does not exist: {path}")

        if not path.is_dir():
            raise ValueError(f"Path must be a directory: {path}")

        loaded_count = 0

        # Load YAML files
        for yaml_file in path.glob("*.yaml"):
            self._load_definition_file(yaml_file)
            loaded_count += 1

        for yml_file in path.glob("*.yml"):
            self._load_definition_file(yml_file)
            loaded_count += 1

        # Also check custom subdirectory if it exists
        custom_path = path / "custom"
        if custom_path.exists() and custom_path.is_dir():
            for yaml_file in custom_path.glob("*.yaml"):
                self._load_definition_file(yaml_file)
                loaded_count += 1

            for yml_file in custom_path.glob("*.yml"):
                self._load_definition_file(yml_file)
                loaded_count += 1

        return self._definitions

    def _load_definition_file(self, file_path: Path) -> None:
        """
        Load a single agent definition file.

        Args:
            file_path: Path to YAML definition file

        Raises:
            yaml.YAMLError: If YAML parsing fails
            ValueError: If validation fails
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            return  # Skip empty files

        # Parse maturity level if provided
        maturity = AgentMaturity.D1
        if "maturity" in data:
            maturity_str = data["maturity"]
            try:
                maturity = AgentMaturity[maturity_str]
            except KeyError:
                raise ValueError(
                    f"Invalid maturity level '{maturity_str}' in {file_path}. "
                    f"Must be one of: {[m.name for m in AgentMaturity]}"
                )

        # Create definition
        definition = AgentDefinition(
            name=data.get("name", ""),
            type=data.get("type", ""),
            system_prompt=data.get("system_prompt", ""),
            maturity=maturity,
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            tools=data.get("tools", []),
            constraints=data.get("constraints", {}),
            metadata=data.get("metadata", {}),
        )

        # Validate definition
        definition.validate()

        # Store definition
        self._definitions[definition.name] = definition

    def get_definition(self, agent_type: str) -> AgentDefinition:
        """
        Get a specific agent definition by name/type.

        Args:
            agent_type: Agent name or type identifier

        Returns:
            AgentDefinition object

        Raises:
            KeyError: If agent_type not found in loaded definitions
        """
        if agent_type not in self._definitions:
            raise KeyError(
                f"Agent definition '{agent_type}' not found. "
                f"Available: {list(self._definitions.keys())}"
            )

        return self._definitions[agent_type]

    def create_agent(
        self, agent_type: str, agent_id: str, provider: str = "anthropic", **kwargs: Any
    ) -> WorkerAgent:
        """
        Create a WorkerAgent instance from a definition.

        Args:
            agent_type: Agent name/type from loaded definitions
            agent_id: Unique identifier for the agent instance
            provider: LLM provider name (default: "anthropic")
            **kwargs: Additional arguments to pass to WorkerAgent

        Returns:
            Configured WorkerAgent instance

        Raises:
            KeyError: If agent_type not found
        """
        definition = self.get_definition(agent_type)

        # Create agent with definition parameters
        agent = WorkerAgent(
            agent_id=agent_id,
            agent_type=definition.type,
            provider=provider,
            maturity=definition.maturity,
            **kwargs,
        )

        # Store definition reference on agent for access to system_prompt, tools, etc.
        agent.definition = definition  # type: ignore

        return agent

    def list_available_types(self) -> List[str]:
        """
        List all available agent type names.

        Returns:
            List of agent names that can be used with get_definition() or create_agent()
        """
        return list(self._definitions.keys())

    def get_definitions_by_type(self, agent_type: str) -> List[AgentDefinition]:
        """
        Get all definitions matching a specific type category.

        Args:
            agent_type: Agent type category (e.g., "backend", "frontend")

        Returns:
            List of matching AgentDefinition objects
        """
        return [
            definition for definition in self._definitions.values() if definition.type == agent_type
        ]

    def reload_definitions(self, path: Path) -> Dict[str, AgentDefinition]:
        """
        Clear cache and reload all definitions.

        Args:
            path: Directory path containing agent definition files

        Returns:
            Dictionary mapping agent names to AgentDefinition objects
        """
        self._definitions.clear()
        return self.load_definitions(path)
