"""Test if mock is being applied correctly."""

from unittest.mock import patch, Mock

# Test 1: Can we patch TestWorkerAgent at all?
print("Test 1: Basic patch test")
with patch('codeframe.agents.test_worker_agent.TestWorkerAgent') as MockCls:
    mock_instance = Mock()
    MockCls.return_value = mock_instance

    from codeframe.agents.test_worker_agent import TestWorkerAgent
    agent = TestWorkerAgent(agent_id="test-001")

    print(f"agent type: {type(agent)}")
    print(f"agent is mock_instance: {agent is mock_instance}")
    print(f"MockCls called: {MockCls.called}")
    print(f"MockCls call count: {MockCls.call_count}")

print("\n" + "="*80)

# Test 2: Patch at import location
print("\nTest 2: Patch at import location (agent_pool_manager)")
with patch('codeframe.agents.agent_pool_manager.TestWorkerAgent') as MockCls:
    mock_instance = Mock()
    MockCls.return_value = mock_instance

    # Import AFTER patching
    from codeframe.agents.agent_pool_manager import AgentPoolManager
    from codeframe.persistence.database import Database
    from codeframe.core.models import ProjectStatus

    db = Database(":memory:")
    db.initialize()
    project_id = db.create_project("test", ProjectStatus.ACTIVE)

    pool = AgentPoolManager(
        project_id=project_id,
        db=db,
        ws_manager=None,
        max_agents=5,
        api_key="test-key"
    )

    print("Creating agent...")
    agent_id = pool.create_agent("test-engineer")

    print(f"agent_id: {agent_id}")
    print(f"MockCls called: {MockCls.called}")
    print(f"MockCls call count: {MockCls.call_count}")

    agent_instance = pool.get_agent_instance(agent_id)
    print(f"agent_instance type: {type(agent_instance)}")
    print(f"agent_instance is mock_instance: {agent_instance is mock_instance}")

    db.close()

print("\n✅ All tests passed!")
