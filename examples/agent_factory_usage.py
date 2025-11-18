"""
Agent Factory Usage Examples

This file demonstrates how to use the new Agent Factory system
to create and manage agents in CodeFRAME.
"""

from codeframe.agents import AgentFactory
from codeframe.core.models import AgentMaturity


def example_basic_usage():
    """Basic agent factory usage."""
    print("=" * 60)
    print("Example 1: Basic Usage")
    print("=" * 60)

    # Initialize factory
    factory = AgentFactory()

    # List available agents
    agents = factory.list_available_agents()
    print(f"\nAvailable agents: {agents}")

    # Create a backend worker
    backend_worker = factory.create_agent(
        agent_type="backend-worker", agent_id="worker-001", provider="claude"
    )

    print(f"\nCreated agent: {backend_worker.agent_id}")
    print(f"Type: {backend_worker.agent_type}")
    print(f"Maturity: {backend_worker.maturity.value}")
    print(f"System prompt (first 100 chars): {backend_worker.system_prompt[:100]}...")


def example_specialized_agents():
    """Creating specialized agents."""
    print("\n" + "=" * 60)
    print("Example 2: Specialized Agents")
    print("=" * 60)

    factory = AgentFactory()

    # Create different types of agents
    agents = {
        "Backend Architect": factory.create_agent("backend-architect", "arch-001", "claude"),
        "Frontend Specialist": factory.create_agent(
            "frontend-specialist", "frontend-001", "claude"
        ),
        "Test Engineer": factory.create_agent("test-engineer", "test-001", "claude"),
        "Code Reviewer": factory.create_agent("code-reviewer", "review-001", "claude"),
    }

    for name, agent in agents.items():
        print(f"\n{name}:")
        print(f"  - ID: {agent.agent_id}")
        print(f"  - Type: {agent.agent_type}")
        print(f"  - Maturity: {agent.maturity.value}")
        print(f"  - Capabilities: {len(agent.capabilities)} defined")


def example_query_capabilities():
    """Querying agent capabilities."""
    print("\n" + "=" * 60)
    print("Example 3: Query Capabilities")
    print("=" * 60)

    factory = AgentFactory()

    # Get capabilities for specific agent type
    agent_type = "backend-architect"
    capabilities = factory.get_agent_capabilities(agent_type)

    print(f"\nCapabilities for {agent_type}:")
    for i, cap in enumerate(capabilities, 1):
        print(f"  {i}. {cap}")

    # Get full definition
    definition = factory.get_agent_definition(agent_type)
    print("\nDefinition details:")
    print(f"  - Name: {definition.name}")
    print(f"  - Type: {definition.type}")
    print(f"  - Maturity: {definition.maturity.value}")
    print(f"  - Description: {definition.description}")
    print(f"  - Tools: {', '.join(definition.tools)}")
    print(f"  - Constraints: {definition.constraints}")


def example_filter_by_type():
    """Filter agents by type category."""
    print("\n" + "=" * 60)
    print("Example 4: Filter by Type")
    print("=" * 60)

    factory = AgentFactory()

    # Get all backend agents
    backend_agents = factory.get_agents_by_type("backend")
    print(f"\nBackend agents: {backend_agents}")

    # Get all test agents
    test_agents = factory.get_agents_by_type("test")
    print(f"Test agents: {test_agents}")

    # Get all review agents
    review_agents = factory.get_agents_by_type("review")
    print(f"Review agents: {review_agents}")


def example_custom_maturity():
    """Override default maturity level."""
    print("\n" + "=" * 60)
    print("Example 5: Custom Maturity Override")
    print("=" * 60)

    factory = AgentFactory()

    # Create agent with default maturity (D1 for backend-worker)
    default_agent = factory.create_agent(
        agent_type="backend-worker", agent_id="worker-default", provider="claude"
    )
    print(f"\nDefault maturity: {default_agent.maturity.value}")

    # Override to D4
    advanced_agent = factory.create_agent(
        agent_type="backend-worker",
        agent_id="worker-advanced",
        provider="claude",
        maturity=AgentMaturity.D4,
    )
    print(f"Custom maturity: {advanced_agent.maturity.value}")


def example_agent_metadata():
    """Access agent metadata."""
    print("\n" + "=" * 60)
    print("Example 6: Agent Metadata")
    print("=" * 60)

    factory = AgentFactory()

    # Create agent and access metadata
    agent = factory.create_agent("code-reviewer", "review-001", "claude")

    print(f"\nAgent: {agent.agent_id}")
    print(f"Capabilities ({len(agent.capabilities)}):")
    for cap in agent.capabilities:
        print(f"  - {cap}")

    print(f"\nTools ({len(agent.tools)}):")
    for tool in agent.tools:
        print(f"  - {tool}")

    print("\nConstraints:")
    for key, value in agent.constraints.items():
        print(f"  - {key}: {value}")


def example_backward_compatibility():
    """Demonstrate backward compatibility."""
    print("\n" + "=" * 60)
    print("Example 7: Backward Compatibility")
    print("=" * 60)

    # Old way - still works
    from codeframe.agents import WorkerAgent

    old_style_agent = WorkerAgent(
        agent_id="old-001", agent_type="backend", provider="claude", maturity=AgentMaturity.D1
    )

    print("\nOld style agent created:")
    print(f"  - ID: {old_style_agent.agent_id}")
    print(f"  - Type: {old_style_agent.agent_type}")
    print(f"  - System prompt: {old_style_agent.system_prompt}")  # None

    # New way - with factory
    factory = AgentFactory()
    new_style_agent = factory.create_agent("backend-worker", "new-001", "claude")

    print("\nNew style agent created:")
    print(f"  - ID: {new_style_agent.agent_id}")
    print(f"  - Type: {new_style_agent.agent_type}")
    print(f"  - System prompt: {new_style_agent.system_prompt is not None}")  # True


def example_real_world_workflow():
    """Real-world workflow example."""
    print("\n" + "=" * 60)
    print("Example 8: Real-World Workflow")
    print("=" * 60)

    factory = AgentFactory()

    # Scenario: Create a team of agents for a project

    print("\nBuilding agent team...")

    # 1. Backend architect for API design
    architect = factory.create_agent("backend-architect", "arch-main", "claude")
    print(f"✓ Backend Architect: {architect.agent_id}")

    # 2. Backend worker for implementation
    worker = factory.create_agent("backend-worker", "worker-main", "claude")
    print(f"✓ Backend Worker: {worker.agent_id}")

    # 3. Test engineer for test coverage
    tester = factory.create_agent("test-engineer", "tester-main", "claude")
    print(f"✓ Test Engineer: {tester.agent_id}")

    # 4. Code reviewer for quality assurance
    reviewer = factory.create_agent("code-reviewer", "reviewer-main", "claude")
    print(f"✓ Code Reviewer: {reviewer.agent_id}")

    # 5. Frontend specialist for UI
    frontend = factory.create_agent("frontend-specialist", "frontend-main", "claude")
    print(f"✓ Frontend Specialist: {frontend.agent_id}")

    print("\n✓ Agent team assembled!")

    # Show team composition
    print("\nTeam Capabilities:")
    team = [architect, worker, tester, reviewer, frontend]
    for agent in team:
        print(f"  - {agent.agent_id}: {len(agent.capabilities)} capabilities")


if __name__ == "__main__":
    """Run all examples."""
    examples = [
        example_basic_usage,
        example_specialized_agents,
        example_query_capabilities,
        example_filter_by_type,
        example_custom_maturity,
        example_agent_metadata,
        example_backward_compatibility,
        example_real_world_workflow,
    ]

    print("\n" + "=" * 60)
    print("AGENT FACTORY USAGE EXAMPLES")
    print("=" * 60)

    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"\n❌ Example failed: {e}")

    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETE")
    print("=" * 60)
