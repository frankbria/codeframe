"""Example usage of AgentDefinitionLoader.

This file demonstrates how to:
1. Load agent definitions from YAML files
2. Access agent metadata and capabilities
3. Create agent instances from definitions
4. Query available agent types
"""

from pathlib import Path
from codeframe.agents.definition_loader import AgentDefinitionLoader


def main() -> None:
    """Demonstrate agent definition loader usage."""

    # Initialize the loader
    loader = AgentDefinitionLoader()

    # Load all definitions from the definitions directory
    definitions_path = Path("codeframe/agents/definitions")
    definitions = loader.load_definitions(definitions_path)

    print(f"Loaded {len(definitions)} agent definitions:\n")

    # List all available agent types
    available = loader.list_available_types()
    print(f"Available agent types: {available}\n")

    # Get a specific definition
    backend_def = loader.get_definition("backend-architect")
    print(f"Agent: {backend_def.name}")
    print(f"Type: {backend_def.type}")
    print(f"Maturity: {backend_def.maturity}")
    print(f"Description: {backend_def.description}")
    print(f"\nCapabilities:")
    for capability in backend_def.capabilities:
        print(f"  - {capability}")
    print(f"\nTools: {backend_def.tools}")
    print(f"Constraints: {backend_def.constraints}")
    print(f"Metadata: {backend_def.metadata}\n")

    # Create an agent from definition
    agent = loader.create_agent(
        agent_type="backend-architect",
        agent_id="backend-001",
        provider="anthropic"
    )

    print(f"Created agent: {agent.agent_id}")
    print(f"Agent type: {agent.agent_type}")
    print(f"Agent maturity: {agent.maturity}")
    print(f"Has definition: {hasattr(agent, 'definition')}")

    # Access definition through agent
    if hasattr(agent, 'definition'):
        print(f"\nSystem prompt (first 200 chars):")
        print(f"{agent.definition.system_prompt[:200]}...\n")

    # Query by type category
    backend_agents = loader.get_definitions_by_type("backend")
    frontend_agents = loader.get_definitions_by_type("frontend")

    print(f"Backend agents: {[a.name for a in backend_agents]}")
    print(f"Frontend agents: {[a.name for a in frontend_agents]}")

    # Example: Creating multiple agents
    print("\n--- Creating Multiple Agents ---")
    for agent_type in available:
        agent = loader.create_agent(
            agent_type=agent_type,
            agent_id=f"{agent_type}-instance-001"
        )
        print(f"Created {agent.agent_id} (type: {agent.agent_type})")


if __name__ == "__main__":
    main()
