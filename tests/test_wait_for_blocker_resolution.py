"""
Tests for wait_for_blocker_resolution() method (049-human-in-loop, Phase 5).

Test coverage for agent blocker resolution polling:
- Wait for blocker resolution with successful answer
- Timeout handling when blocker not resolved
- Polling interval behavior
- Answer retrieval and validation
- WebSocket broadcast on resume

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import time

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent
from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex


class TestBackendWorkerAgentBlockerResolution:
    """Test BackendWorkerAgent.wait_for_blocker_resolution()."""

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_returns_answer_when_resolved(self, tmp_path):
        """Test wait_for_blocker_resolution returns answer when blocker is resolved."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)
        agent.id = "backend-worker-001"

        # Mock blocker that transitions from PENDING to RESOLVED
        pending_blocker = {
            "id": 1,
            "agent_id": "backend-worker-001",
            "task_id": 1,
            "blocker_type": "SYNC",
            "question": "Should I use SQLite or PostgreSQL?",
            "answer": None,
            "status": "PENDING",
            "created_at": "2025-11-08T12:00:00Z",
            "resolved_at": None,
        }

        resolved_blocker = {
            **pending_blocker,
            "answer": "Use SQLite to match existing codebase",
            "status": "RESOLVED",
            "resolved_at": "2025-11-08T12:00:05Z",
        }

        # First call returns pending, second call returns resolved
        db.get_blocker.side_effect = [pending_blocker, resolved_blocker]

        # Wait for blocker resolution (should return answer)
        answer = await agent.wait_for_blocker_resolution(
            blocker_id=1, poll_interval=0.05, timeout=5.0
        )

        assert answer == "Use SQLite to match existing codebase"
        assert db.get_blocker.call_count == 2

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_raises_timeout_when_not_resolved(self, tmp_path):
        """Test wait_for_blocker_resolution raises TimeoutError when blocker not resolved."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)
        agent.id = "backend-worker-001"

        # Blocker remains pending
        pending_blocker = {
            "id": 1,
            "agent_id": "backend-worker-001",
            "task_id": 1,
            "blocker_type": "SYNC",
            "question": "Question?",
            "answer": None,
            "status": "PENDING",
            "created_at": "2025-11-08T12:00:00Z",
            "resolved_at": None,
        }

        db.get_blocker.return_value = pending_blocker

        # Wait for blocker resolution (should timeout)
        with pytest.raises(TimeoutError) as exc_info:
            await agent.wait_for_blocker_resolution(blocker_id=1, poll_interval=0.05, timeout=0.2)

        assert "Blocker 1 not resolved within" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_polls_at_specified_interval(self, tmp_path):
        """Test wait_for_blocker_resolution polls database at correct interval."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)
        agent.id = "backend-worker-001"

        # Track number of polls
        poll_count = 0

        def get_blocker_side_effect(blocker_id):
            nonlocal poll_count
            poll_count += 1

            # Resolve on 3rd poll
            if poll_count >= 3:
                return {
                    "id": blocker_id,
                    "agent_id": "backend-worker-001",
                    "task_id": 1,
                    "blocker_type": "ASYNC",
                    "question": "Question?",
                    "answer": "Answer",
                    "status": "RESOLVED",
                    "created_at": "2025-11-08T12:00:00Z",
                    "resolved_at": "2025-11-08T12:00:05Z",
                }
            else:
                return {
                    "id": blocker_id,
                    "agent_id": "backend-worker-001",
                    "task_id": 1,
                    "blocker_type": "ASYNC",
                    "question": "Question?",
                    "answer": None,
                    "status": "PENDING",
                    "created_at": "2025-11-08T12:00:00Z",
                    "resolved_at": None,
                }

        db.get_blocker.side_effect = get_blocker_side_effect

        answer = await agent.wait_for_blocker_resolution(
            blocker_id=1, poll_interval=0.05, timeout=5.0
        )

        assert answer == "Answer"
        assert poll_count == 3  # Should have polled 3 times

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_returns_immediately_if_already_resolved(
        self, tmp_path
    ):
        """Test wait_for_blocker_resolution returns immediately if blocker already resolved."""
        # Setup mocked database
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)
        agent.id = "backend-worker-001"

        # Blocker already resolved
        resolved_blocker = {
            "id": 1,
            "agent_id": "backend-worker-001",
            "task_id": 1,
            "blocker_type": "ASYNC",
            "question": "Question?",
            "answer": "Pre-resolved answer",
            "status": "RESOLVED",
            "created_at": "2025-11-08T12:00:00Z",
            "resolved_at": "2025-11-08T12:00:01Z",
        }

        db.get_blocker.return_value = resolved_blocker

        # Wait should return immediately
        start_time = time.time()
        answer = await agent.wait_for_blocker_resolution(
            blocker_id=1, poll_interval=0.1, timeout=5.0
        )
        elapsed = time.time() - start_time

        assert answer == "Pre-resolved answer"
        assert elapsed < 0.2  # Should return almost immediately (< 200ms)
        assert db.get_blocker.call_count == 1  # Only one call needed

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_broadcasts_agent_resumed_event(self, tmp_path):
        """Test wait_for_blocker_resolution broadcasts agent_resumed WebSocket event."""
        # Setup mocked database and WebSocket manager
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)
        ws_manager = AsyncMock()

        agent = BackendWorkerAgent(
            project_id=1, db=db, codebase_index=index, project_root=tmp_path, ws_manager=ws_manager
        )
        agent.id = "backend-worker-001"
        agent.current_task_id = 1

        # Blocker already resolved
        resolved_blocker = {
            "id": 1,
            "agent_id": "backend-worker-001",
            "task_id": 1,
            "blocker_type": "SYNC",
            "question": "Question?",
            "answer": "Answer",
            "status": "RESOLVED",
            "created_at": "2025-11-08T12:00:00Z",
            "resolved_at": "2025-11-08T12:00:05Z",
        }

        db.get_blocker.return_value = resolved_blocker

        # Wait for resolution
        with patch(
            "codeframe.ui.websocket_broadcasts.broadcast_agent_resumed", new_callable=AsyncMock
        ) as mock_broadcast:
            answer = await agent.wait_for_blocker_resolution(
                blocker_id=1, poll_interval=0.05, timeout=5.0
            )

            # Verify broadcast was called
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[1]["manager"] == ws_manager
            assert call_args[1]["project_id"] == 1
            assert call_args[1]["agent_id"] == "backend-worker-001"
            assert call_args[1]["task_id"] == 1
            assert call_args[1]["blocker_id"] == 1


class TestFrontendWorkerAgentBlockerResolution:
    """Test FrontendWorkerAgent.wait_for_blocker_resolution()."""

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_returns_answer_when_resolved(self, tmp_path):
        """Test wait_for_blocker_resolution returns answer when blocker is resolved."""
        # Setup mocked database
        db = Mock(spec=Database)

        agent = FrontendWorkerAgent(agent_id="frontend-worker-001")
        agent.db = db
        agent.project_id = 1
        agent.ws_manager = None

        # Mock blocker transition
        pending_blocker = {"id": 1, "answer": None, "status": "PENDING"}
        resolved_blocker = {
            "id": 1,
            "answer": "Use React to match existing stack",
            "status": "RESOLVED",
        }

        db.get_blocker.side_effect = [pending_blocker, resolved_blocker]

        answer = await agent.wait_for_blocker_resolution(
            blocker_id=1, poll_interval=0.05, timeout=5.0
        )

        assert answer == "Use React to match existing stack"


class TestTestWorkerAgentBlockerResolution:
    """Test TestWorkerAgent.wait_for_blocker_resolution()."""

    @pytest.mark.asyncio
    async def test_wait_for_blocker_resolution_returns_answer_when_resolved(self, tmp_path):
        """Test wait_for_blocker_resolution returns answer when blocker is resolved."""
        # Setup mocked database
        db = Mock(spec=Database)

        agent = TestWorkerAgent(agent_id="test-worker-001")
        agent.db = db
        agent.project_id = 1
        agent.ws_manager = None

        # Mock blocker transition
        pending_blocker = {"id": 1, "answer": None, "status": "PENDING"}
        resolved_blocker = {"id": 1, "answer": "Use pytest for consistency", "status": "RESOLVED"}

        db.get_blocker.side_effect = [pending_blocker, resolved_blocker]

        answer = await agent.wait_for_blocker_resolution(
            blocker_id=1, poll_interval=0.05, timeout=5.0
        )

        assert answer == "Use pytest for consistency"
