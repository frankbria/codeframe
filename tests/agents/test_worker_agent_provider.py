"""Tests for WorkerAgent with LLMProvider abstraction."""
import pytest
from codeframe.adapters.llm import MockProvider
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import Task

pytestmark = pytest.mark.v2


@pytest.fixture
def mock_task():
    return Task(
        id=1,
        project_id=1,
        issue_id="issue-1",
        task_number="T-001",
        parent_issue_number="P-001",
        title="Test task",
        description="A simple test task",
        assigned_to="test-agent",
    )


class TestWorkerAgentWithProvider:
    """WorkerAgent should accept llm_provider constructor param."""

    def test_accepts_llm_provider(self):
        """WorkerAgent can be created with a custom llm_provider."""
        provider = MockProvider(default_response="task done")
        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="mock",
            llm_provider=provider,
        )
        assert agent.llm_provider is provider

    def test_no_anthropic_import_in_init(self):
        """WorkerAgent init should not require ANTHROPIC_API_KEY when llm_provider supplied."""
        provider = MockProvider(default_response="task done")
        # Should not raise even without ANTHROPIC_API_KEY in env
        agent = WorkerAgent(
            agent_id="test-001",
            agent_type="backend",
            provider="mock",
            llm_provider=provider,
        )
        assert agent is not None
