"""
Tests for create_blocker_and_wait() answer injection method (049-human-in-loop, T031).

Test coverage for blocker answer injection into agent execution context:
- Create blocker and wait for resolution with context enrichment
- Answer injected into context with correct keys
- Question preserved in enriched context
- Blocker ID included in enriched context
- Original context fields preserved in enriched context
- Method works for all three worker agent types

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent
from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex


class TestBackendWorkerAgentAnswerInjection:
    """Test BackendWorkerAgent.create_blocker_and_wait()."""

    @pytest.mark.asyncio
    async def test_create_blocker_and_wait_enriches_context_with_answer(self, tmp_path):
        """Test create_blocker_and_wait enriches context with blocker answer."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)
        agent.id = "backend-worker-001"

        # Mock create_blocker to return blocker ID
        with patch.object(agent, "create_blocker", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 123

            # Mock wait_for_blocker_resolution to return answer
            with patch.object(
                agent, "wait_for_blocker_resolution", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = "Use SQLite to match existing codebase"

                # Original context
                original_context = {
                    "task": {"id": 1, "title": "Implement feature"},
                    "related_files": ["file1.py", "file2.py"],
                    "issue_context": {"id": 10, "title": "Epic feature"},
                }

                # Call create_blocker_and_wait
                enriched_context = await agent.create_blocker_and_wait(
                    question="Should I use SQLite or PostgreSQL?",
                    context=original_context,
                    blocker_type="SYNC",
                )

                # Verify blocker was created
                mock_create.assert_called_once_with(
                    question="Should I use SQLite or PostgreSQL?", blocker_type="SYNC", task_id=1
                )

                # Verify agent waited for resolution
                mock_wait.assert_called_once_with(blocker_id=123, poll_interval=5.0, timeout=600.0)

                # Verify context was enriched with answer
                assert enriched_context["blocker_answer"] == "Use SQLite to match existing codebase"
                assert enriched_context["blocker_question"] == "Should I use SQLite or PostgreSQL?"
                assert enriched_context["blocker_id"] == 123

                # Verify original context fields preserved
                assert enriched_context["task"] == {"id": 1, "title": "Implement feature"}
                assert enriched_context["related_files"] == ["file1.py", "file2.py"]
                assert enriched_context["issue_context"] == {"id": 10, "title": "Epic feature"}

    @pytest.mark.asyncio
    async def test_create_blocker_and_wait_extracts_task_id_from_context(self, tmp_path):
        """Test create_blocker_and_wait extracts task_id from context when not provided."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Mock methods
        with patch.object(agent, "create_blocker", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 456
            with patch.object(
                agent, "wait_for_blocker_resolution", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = "Answer"

                # Context with nested task ID
                context = {"task": {"id": 42, "title": "Test task"}}

                # Call without explicit task_id
                enriched_context = await agent.create_blocker_and_wait(
                    question="Test question?", context=context
                )

                # Verify task_id was extracted from context
                mock_create.assert_called_once_with(
                    question="Test question?", blocker_type="ASYNC", task_id=42
                )

    @pytest.mark.asyncio
    async def test_create_blocker_and_wait_uses_custom_timeouts(self, tmp_path):
        """Test create_blocker_and_wait respects custom poll_interval and timeout."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Mock methods
        with patch.object(agent, "create_blocker", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 789
            with patch.object(
                agent, "wait_for_blocker_resolution", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = "Custom answer"

                context = {"task": {"id": 1}}

                # Call with custom timeouts
                enriched_context = await agent.create_blocker_and_wait(
                    question="Question?", context=context, poll_interval=2.0, timeout=120.0
                )

                # Verify custom timeouts were passed to wait_for_blocker_resolution
                mock_wait.assert_called_once_with(blocker_id=789, poll_interval=2.0, timeout=120.0)


class TestFrontendWorkerAgentAnswerInjection:
    """Test FrontendWorkerAgent.create_blocker_and_wait()."""

    @pytest.mark.asyncio
    async def test_create_blocker_and_wait_enriches_context_with_answer(self):
        """Test create_blocker_and_wait enriches context with blocker answer."""
        # Setup agent
        agent = FrontendWorkerAgent(agent_id="frontend-worker-001")
        agent.db = Mock(spec=Database)
        agent.project_id = 1

        # Mock methods
        with patch.object(agent, "create_blocker", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 123
            with patch.object(
                agent, "wait_for_blocker_resolution", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = "Use React to match existing stack"

                # Original context
                original_context = {
                    "task": {"id": 5, "title": "Build UI component"},
                    "requirements": ["responsive", "accessible"],
                }

                # Call create_blocker_and_wait
                enriched_context = await agent.create_blocker_and_wait(
                    question="Should I use React or Vue?",
                    context=original_context,
                    blocker_type="SYNC",
                )

                # Verify context enriched
                assert enriched_context["blocker_answer"] == "Use React to match existing stack"
                assert enriched_context["blocker_question"] == "Should I use React or Vue?"
                assert enriched_context["blocker_id"] == 123
                assert enriched_context["task"] == {"id": 5, "title": "Build UI component"}
                assert enriched_context["requirements"] == ["responsive", "accessible"]


class TestTestWorkerAgentAnswerInjection:
    """Test TestWorkerAgent.create_blocker_and_wait()."""

    @pytest.mark.asyncio
    async def test_create_blocker_and_wait_enriches_context_with_answer(self):
        """Test create_blocker_and_wait enriches context with blocker answer."""
        # Setup agent
        agent = TestWorkerAgent(agent_id="test-worker-001")
        agent.db = Mock(spec=Database)
        agent.project_id = 1

        # Mock methods
        with patch.object(agent, "create_blocker", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 456
            with patch.object(
                agent, "wait_for_blocker_resolution", new_callable=AsyncMock
            ) as mock_wait:
                mock_wait.return_value = "Use pytest for consistency"

                # Original context
                original_context = {
                    "task": {"id": 8, "title": "Write test suite"},
                    "test_requirements": ["unit", "integration"],
                }

                # Call create_blocker_and_wait
                enriched_context = await agent.create_blocker_and_wait(
                    question="Should I use pytest or unittest?",
                    context=original_context,
                    blocker_type="ASYNC",
                )

                # Verify context enriched
                assert enriched_context["blocker_answer"] == "Use pytest for consistency"
                assert enriched_context["blocker_question"] == "Should I use pytest or unittest?"
                assert enriched_context["blocker_id"] == 456
                assert enriched_context["task"] == {"id": 8, "title": "Write test suite"}
                assert enriched_context["test_requirements"] == ["unit", "integration"]
