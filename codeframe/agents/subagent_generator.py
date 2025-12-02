"""Generate SDK subagent markdown from YAML definitions.

Preserves CodeFRAME's rich agent configurations while enabling
SDK subagent execution. Implements a hybrid approach where YAML
remains the source of truth for agent definitions.

SDK Subagent Markdown Format:
----------------------------
The generated markdown files follow the Claude Agent SDK format:

```markdown
---
name: Backend Developer
description: Python/FastAPI specialist
tools: [Read, Write, Bash, Grep, Glob]
---

You are a backend developer agent...

## Maturity Level: D2
...
```

Usage:
------
```python
from pathlib import Path
from codeframe.agents.subagent_generator import SubagentGenerator

# Initialize generator
generator = SubagentGenerator(
    definitions_dir=Path("codeframe/agents/definitions")
)

# Generate all agents at D2 maturity
generator.generate_all(maturity="D2")

# Generate specific agent
output_path = generator.generate_agent("backend", maturity="D3")
print(f"Generated: {output_path}")

# List available agent types
print(generator.list_available_types())
```
"""

import logging
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# Tool mapping from YAML abstract names to SDK concrete tools
YAML_TO_SDK_TOOL_MAPPING: Dict[str, List[str]] = {
    # Core file operations
    "file_operations": ["Read", "Write"],
    "codebase_index": ["Glob", "Grep"],
    "code_analyzer": ["Grep"],
    # Execution tools (all map to Bash)
    "test_runner": ["Bash"],
    "git_operations": ["Bash"],
    "api_test": ["Bash"],
    "database_query": ["Bash"],
    "performance_profile": ["Bash"],
    # Test frameworks (all executed via Bash)
    "pytest": ["Bash"],
    "jest": ["Bash"],
    "playwright": ["Bash"],
    "coverage_tools": ["Bash"],
    # Frontend tools (executed via Bash or internal)
    "component_preview": ["Bash"],
    "accessibility_check": ["Bash"],
    "performance_audit": ["Bash"],
    "browser_test": ["Bash"],
    "eslint": ["Bash"],
    # Code quality tools
    "static_analyzer": ["Bash", "Grep"],
    "security_scanner": ["Bash"],
    "security_scan": ["Bash"],
    "complexity_analyzer": ["Bash"],
    "dependency_checker": ["Bash"],
    "coverage_analyzer": ["Bash"],
    # Test utilities
    "fixture_generator": ["Write"],
    "mock_service": ["Bash"],
    # Tools that don't map to SDK tools (handled internally)
    "anthropic_api": [],
    "database": [],
    "websocket_manager": [],
    "self_correction": [],
}


@dataclass
class MaturityConfig:
    """Configuration for a specific maturity level."""

    level: str
    description: str
    capabilities: List[str]


class SubagentGenerator:
    """Generates SDK-compatible subagent markdown from YAML definitions.

    This class bridges CodeFRAME's YAML-based agent definitions with the
    Claude Agent SDK's subagent system. It preserves maturity levels,
    capabilities, and other CodeFRAME-specific features while generating
    valid SDK markdown.

    Attributes:
        definitions_dir: Path to YAML agent definitions
        output_dir: Path where generated markdown files are saved
        _raw_definitions: Cache of raw YAML data for each agent
    """

    def __init__(
        self,
        definitions_dir: Path,
        output_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the subagent generator.

        Args:
            definitions_dir: Directory containing YAML agent definitions
            output_dir: Directory for generated markdown (default: .claude/agents/)
        """
        self.definitions_dir = definitions_dir
        self.output_dir = output_dir or Path(".claude/agents")
        self._raw_definitions: Dict[str, Dict[str, Any]] = {}

        # Load definitions on init
        self._load_raw_definitions()

    def _load_raw_definitions(self) -> None:
        """Load raw YAML data from all definition files."""
        if not self.definitions_dir.exists():
            logger.warning(f"Definitions directory not found: {self.definitions_dir}")
            return

        # Load .yaml files
        for yaml_file in self.definitions_dir.glob("*.yaml"):
            self._load_single_file(yaml_file)

        # Load .yml files
        for yml_file in self.definitions_dir.glob("*.yml"):
            self._load_single_file(yml_file)

        # Load from custom subdirectory
        custom_dir = self.definitions_dir / "custom"
        if custom_dir.exists():
            for yaml_file in custom_dir.glob("*.yaml"):
                self._load_single_file(yaml_file)
            for yml_file in custom_dir.glob("*.yml"):
                self._load_single_file(yml_file)

        logger.info(f"Loaded {len(self._raw_definitions)} agent definitions")

    def _load_single_file(self, file_path: Path) -> None:
        """Load a single YAML definition file.

        Args:
            file_path: Path to YAML file
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data and "name" in data:
                # Store by name (key for lookup)
                self._raw_definitions[data["name"]] = data
                logger.debug(f"Loaded definition: {data['name']} from {file_path.name}")
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")

    def generate_all(self, maturity: str = "D2") -> List[Path]:
        """Generate markdown for all agent types at specified maturity.

        Args:
            maturity: Maturity level (D1, D2, D3, D4)

        Returns:
            List of paths to generated markdown files
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        generated_paths = []

        for agent_name in self._raw_definitions.keys():
            try:
                output_path = self.generate_agent(agent_name, maturity)
                generated_paths.append(output_path)
            except Exception as e:
                logger.error(f"Failed to generate {agent_name}: {e}")

        logger.info(f"Generated {len(generated_paths)} subagent markdown files")
        return generated_paths

    def generate_agent(self, agent_name: str, maturity: str = "D2") -> Path:
        """Generate markdown for a specific agent.

        Args:
            agent_name: Agent name from YAML definitions
            maturity: Maturity level (D1, D2, D3, D4)

        Returns:
            Path to generated markdown file

        Raises:
            KeyError: If agent_name not found in definitions
            ValueError: If maturity level is invalid
        """
        if agent_name not in self._raw_definitions:
            raise KeyError(
                f"Agent '{agent_name}' not found. "
                f"Available: {list(self._raw_definitions.keys())}"
            )

        if maturity not in ["D1", "D2", "D3", "D4"]:
            raise ValueError(f"Invalid maturity level: {maturity}. Must be D1, D2, D3, or D4")

        raw_def = self._raw_definitions[agent_name]

        # Generate SDK-compatible markdown
        content = self._build_markdown(raw_def, maturity)

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename (sanitize agent name)
        safe_name = agent_name.lower().replace(" ", "-").replace("_", "-")
        output_path = self.output_dir / f"{safe_name}.md"

        # Write file
        output_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated subagent: {output_path}")

        return output_path

    def _build_markdown(self, raw_def: Dict[str, Any], maturity: str) -> str:
        """Build SDK subagent markdown from raw definition.

        Args:
            raw_def: Raw YAML definition dictionary
            maturity: Target maturity level

        Returns:
            Complete markdown content string
        """
        name = raw_def.get("name", "Unknown Agent")
        description = raw_def.get("description", "").strip()
        system_prompt = raw_def.get("system_prompt", "").strip()
        yaml_tools = raw_def.get("tools", [])

        # Get first line of description for frontmatter
        short_description = description.split("\n")[0].strip() if description else name

        # Map tools to SDK format
        sdk_tools = self._map_tools_to_sdk(yaml_tools)

        # Get maturity-specific config
        maturity_config = self._get_maturity_config(raw_def, maturity)

        # Get error recovery settings (handles both dict and list formats)
        error_recovery = raw_def.get("error_recovery", {})
        max_attempts = 3  # Default
        if isinstance(error_recovery, dict):
            max_attempts = error_recovery.get("max_correction_attempts", 3)
        elif isinstance(error_recovery, list):
            # Handle list format: [{'max_correction_attempts': 3}, ...]
            for item in error_recovery:
                if isinstance(item, dict) and "max_correction_attempts" in item:
                    max_attempts = item["max_correction_attempts"]
                    break

        # Build markdown content
        markdown_parts = [
            "---",
            f"name: {name}",
            f"description: {short_description}",
            f"tools: {sdk_tools}",
            "---",
            "",
            system_prompt,
            "",
            f"## Maturity Level: {maturity}",
        ]

        # Add maturity description and capabilities
        if maturity_config:
            markdown_parts.append(maturity_config.description)
            markdown_parts.append("")
            markdown_parts.append("### Capabilities at this level:")
            markdown_parts.append(self._format_capabilities(maturity_config.capabilities))
        else:
            # Fallback: use general capabilities (always show section)
            capabilities = raw_def.get("capabilities", [])
            markdown_parts.append("")
            markdown_parts.append("### Capabilities:")
            markdown_parts.append(self._format_capabilities(capabilities))

        # Add error recovery section
        markdown_parts.extend(
            [
                "",
                "## Error Recovery",
                f"- Max correction attempts: {max_attempts}",
                "- Escalation: Create blocker for manual intervention",
            ]
        )

        # Add integration notes if present
        integration_points = raw_def.get("integration_points", [])
        if integration_points:
            markdown_parts.extend(
                [
                    "",
                    "## Integration Points",
                ]
            )
            if isinstance(integration_points, list):
                for point in integration_points:
                    # Handle list of dicts (YAML list with key-value pairs)
                    if isinstance(point, dict):
                        for key, value in point.items():
                            markdown_parts.append(f"- **{key}**: {value}")
                    else:
                        markdown_parts.append(f"- {point}")
            elif isinstance(integration_points, dict):
                for key, value in integration_points.items():
                    markdown_parts.append(f"- **{key}**: {value}")

        return "\n".join(markdown_parts)

    def _get_maturity_config(
        self, raw_def: Dict[str, Any], maturity: str
    ) -> Optional[MaturityConfig]:
        """Extract maturity-specific configuration.

        Args:
            raw_def: Raw YAML definition dictionary
            maturity: Target maturity level (D1-D4)

        Returns:
            MaturityConfig if found, None otherwise
        """
        maturity_progression = raw_def.get("maturity_progression", [])

        for level_config in maturity_progression:
            if level_config.get("level") == maturity:
                return MaturityConfig(
                    level=level_config.get("level", maturity),
                    description=level_config.get("description", ""),
                    capabilities=level_config.get("capabilities", []),
                )

        return None

    def _map_tools_to_sdk(self, yaml_tools: List[str]) -> List[str]:
        """Map YAML tool names to SDK tool names.

        Args:
            yaml_tools: List of tool names from YAML definition

        Returns:
            Sorted list of unique SDK tool names
        """
        sdk_tools: set[str] = set()

        for tool in yaml_tools:
            if tool in YAML_TO_SDK_TOOL_MAPPING:
                sdk_tools.update(YAML_TO_SDK_TOOL_MAPPING[tool])
            else:
                # Unknown tool - log warning but don't fail
                logger.warning(f"Unknown tool '{tool}' - not mapped to SDK")

        # Always include basic tools for agent functionality
        sdk_tools.add("Read")
        sdk_tools.add("Glob")

        return sorted(list(sdk_tools))

    def _format_capabilities(self, capabilities: List[str]) -> str:
        """Format capability list for markdown.

        Args:
            capabilities: List of capability strings

        Returns:
            Formatted markdown list
        """
        if not capabilities:
            return "- General task execution"

        return "\n".join(f"- {cap}" for cap in capabilities)

    def list_available_types(self) -> List[str]:
        """List all available agent type names.

        Returns:
            List of agent names from loaded definitions
        """
        return list(self._raw_definitions.keys())

    def get_raw_definition(self, agent_name: str) -> Dict[str, Any]:
        """Get raw YAML definition for an agent.

        Args:
            agent_name: Agent name to look up

        Returns:
            Raw YAML dictionary

        Raises:
            KeyError: If agent not found
        """
        if agent_name not in self._raw_definitions:
            raise KeyError(f"Agent '{agent_name}' not found")
        return self._raw_definitions[agent_name]

    def reload_definitions(self) -> None:
        """Clear cache and reload all definitions from disk."""
        self._raw_definitions.clear()
        self._load_raw_definitions()
