"""Agent Factory - Create agents from YAML definitions."""

from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from codeframe.core.models import AgentMaturity
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.agents.definition_loader import AgentDefinitionLoader, AgentDefinition

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Factory for creating agents from YAML definitions.

    This factory uses AgentDefinitionLoader to load agent configurations
    from YAML files and creates WorkerAgent instances with the appropriate
    system prompts and capabilities.

    Example usage:
        factory = AgentFactory()
        agent = factory.create_agent("backend-worker", "agent-001", "claude")
        capabilities = factory.get_agent_capabilities("backend-worker")
        available = factory.list_available_agents()
    """

    def __init__(self, definitions_dir: Optional[Path] = None):
        """
        Initialize the agent factory.

        Args:
            definitions_dir: Optional custom definitions directory.
                           Defaults to codeframe/agents/definitions/
        """
        self.loader = AgentDefinitionLoader()

        # Determine definitions directory
        if definitions_dir is None:
            # Default to definitions directory relative to this file
            self.definitions_dir = Path(__file__).parent / "definitions"
        else:
            self.definitions_dir = Path(definitions_dir)

        # Load all definitions on initialization
        try:
            self.loader.load_definitions(self.definitions_dir)
            loaded = len(self.loader.list_available_types())
            logger.info(f"AgentFactory initialized with {loaded} agent definitions")
        except FileNotFoundError:
            logger.warning(
                f"Definitions directory not found: {self.definitions_dir}. "
                "No agents loaded."
            )
        except Exception as e:
            logger.error(f"Failed to load agent definitions: {e}")
            raise

    def create_agent(
        self,
        agent_type: str,
        agent_id: str,
        provider: str = "claude",
        **kwargs: Any
    ) -> WorkerAgent:
        """
        Create a WorkerAgent instance from a definition.

        Args:
            agent_type: Agent type name (e.g., "backend-worker", "frontend-specialist")
            agent_id: Unique identifier for this agent instance
            provider: LLM provider (default: "claude")
            **kwargs: Additional arguments passed to WorkerAgent constructor

        Returns:
            Configured WorkerAgent instance

        Raises:
            KeyError: If agent_type not found in definitions
            ValueError: If agent configuration is invalid

        Example:
            agent = factory.create_agent(
                agent_type="backend-architect",
                agent_id="backend-001",
                provider="claude"
            )
        """
        try:
            definition = self.loader.get_definition(agent_type)
        except KeyError as e:
            available = self.list_available_agents()
            raise KeyError(
                f"Agent type '{agent_type}' not found. "
                f"Available agents: {available}"
            ) from e

        # Extract maturity if not provided in kwargs
        maturity = kwargs.pop('maturity', definition.maturity)

        # Create WorkerAgent with system_prompt
        agent = WorkerAgent(
            agent_id=agent_id,
            agent_type=definition.type,
            provider=provider,
            maturity=maturity,
            system_prompt=definition.system_prompt,
            **kwargs
        )

        # Store additional definition metadata on agent for reference
        agent.definition = definition  # type: ignore
        agent.capabilities = definition.capabilities  # type: ignore
        agent.tools = definition.tools  # type: ignore
        agent.constraints = definition.constraints  # type: ignore

        logger.debug(
            f"Created agent: {agent_id} (type={agent_type}, provider={provider})"
        )

        return agent

    def list_available_agents(self) -> List[str]:
        """
        List all available agent type names.

        Returns:
            List of agent type strings that can be used with create_agent()

        Example:
            >>> factory.list_available_agents()
            ['backend-worker', 'backend-architect', 'frontend-specialist', ...]
        """
        return self.loader.list_available_types()

    def get_agent_capabilities(self, agent_type: str) -> List[str]:
        """
        Get capabilities for a specific agent type.

        Args:
            agent_type: Agent type name

        Returns:
            List of capability strings

        Raises:
            KeyError: If agent_type not found

        Example:
            >>> factory.get_agent_capabilities("backend-architect")
            ['RESTful and GraphQL API design', 'Database schema design', ...]
        """
        try:
            definition = self.loader.get_definition(agent_type)
            return definition.capabilities
        except KeyError as e:
            available = self.list_available_agents()
            raise KeyError(
                f"Agent type '{agent_type}' not found. "
                f"Available agents: {available}"
            ) from e

    def get_agent_definition(self, agent_type: str) -> AgentDefinition:
        """
        Get the full definition for an agent type.

        Args:
            agent_type: Agent type name

        Returns:
            AgentDefinition object

        Raises:
            KeyError: If agent_type not found

        Example:
            >>> definition = factory.get_agent_definition("backend-architect")
            >>> print(definition.system_prompt)
        """
        return self.loader.get_definition(agent_type)

    def reload_definitions(self) -> None:
        """
        Reload all agent definitions from disk.

        Useful for picking up changes to YAML files without restarting.
        """
        self.loader.reload_definitions(self.definitions_dir)
        loaded = len(self.loader.list_available_types())
        logger.info(f"Reloaded {loaded} agent definitions")

    def get_agents_by_type(self, type_category: str) -> List[str]:
        """
        Get all agent names matching a type category.

        Args:
            type_category: Type category (e.g., "backend", "frontend", "test")

        Returns:
            List of agent names with matching type

        Example:
            >>> factory.get_agents_by_type("backend")
            ['backend-worker', 'backend-architect']
        """
        definitions = self.loader.get_definitions_by_type(type_category)
        return [d.name for d in definitions]
