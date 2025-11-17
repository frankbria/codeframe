"""
Tests for blocker type validation (049-human-in-loop, T035).

Test coverage for blocker type classification logic:
- Validate SYNC blocker type accepted
- Validate ASYNC blocker type accepted
- Reject invalid blocker types
- Default to ASYNC when not specified
- All three worker agent types validate blocker type

Following strict TDD methodology (RED-GREEN-REFACTOR).
"""

import pytest
from unittest.mock import Mock

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent
from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex


class TestBackendWorkerAgentBlockerTypeValidation:
    """Test BackendWorkerAgent blocker type validation."""

    @pytest.mark.asyncio
    async def test_create_blocker_accepts_sync_type(self, tmp_path):
        """Test create_blocker accepts SYNC blocker type."""
        db = Mock(spec=Database)
        db.create_blocker.return_value = 1
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Create SYNC blocker should succeed
        blocker_id = await agent.create_blocker(question="Critical issue?", blocker_type="SYNC")

        assert blocker_id == 1
        db.create_blocker.assert_called_once()
        call_args = db.create_blocker.call_args[1]
        assert call_args["blocker_type"] == "SYNC"

    @pytest.mark.asyncio
    async def test_create_blocker_accepts_async_type(self, tmp_path):
        """Test create_blocker accepts ASYNC blocker type."""
        db = Mock(spec=Database)
        db.create_blocker.return_value = 2
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Create ASYNC blocker should succeed
        blocker_id = await agent.create_blocker(question="Style preference?", blocker_type="ASYNC")

        assert blocker_id == 2
        db.create_blocker.assert_called_once()
        call_args = db.create_blocker.call_args[1]
        assert call_args["blocker_type"] == "ASYNC"

    @pytest.mark.asyncio
    async def test_create_blocker_defaults_to_async(self, tmp_path):
        """Test create_blocker defaults to ASYNC when type not specified."""
        db = Mock(spec=Database)
        db.create_blocker.return_value = 3
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Create blocker without specifying type
        blocker_id = await agent.create_blocker(question="Optional question?")

        assert blocker_id == 3
        db.create_blocker.assert_called_once()
        call_args = db.create_blocker.call_args[1]
        assert call_args["blocker_type"] == "ASYNC"

    @pytest.mark.asyncio
    async def test_create_blocker_rejects_invalid_type(self, tmp_path):
        """Test create_blocker rejects invalid blocker type."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Create blocker with invalid type should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await agent.create_blocker(question="Question?", blocker_type="INVALID")

        assert "Invalid blocker_type" in str(exc_info.value)
        assert "SYNC" in str(exc_info.value)
        assert "ASYNC" in str(exc_info.value)
        db.create_blocker.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_blocker_rejects_lowercase_type(self, tmp_path):
        """Test create_blocker rejects lowercase blocker type."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(project_id=1, db=db, codebase_index=index, project_root=tmp_path)

        # Lowercase "sync" should be rejected
        with pytest.raises(ValueError) as exc_info:
            await agent.create_blocker(question="Question?", blocker_type="sync")

        assert "Invalid blocker_type" in str(exc_info.value)
        db.create_blocker.assert_not_called()


class TestFrontendWorkerAgentBlockerTypeValidation:
    """Test FrontendWorkerAgent blocker type validation."""

    @pytest.mark.asyncio
    async def test_create_blocker_accepts_sync_type(self):
        """Test create_blocker accepts SYNC blocker type."""
        agent = FrontendWorkerAgent(agent_id="frontend-001")
        agent.db = Mock(spec=Database)
        agent.db.create_blocker.return_value = 1
        agent.project_id = 1
        agent.ws_manager = None  # No WebSocket manager in test

        blocker_id = await agent.create_blocker(
            question="Critical frontend issue?", blocker_type="SYNC"
        )

        assert blocker_id == 1
        agent.db.create_blocker.assert_called_once()
        call_args = agent.db.create_blocker.call_args[1]
        assert call_args["blocker_type"] == "SYNC"

    @pytest.mark.asyncio
    async def test_create_blocker_rejects_invalid_type(self):
        """Test create_blocker rejects invalid blocker type."""
        agent = FrontendWorkerAgent(agent_id="frontend-001")
        agent.db = Mock(spec=Database)
        agent.project_id = 1
        agent.ws_manager = None

        with pytest.raises(ValueError) as exc_info:
            await agent.create_blocker(question="Question?", blocker_type="MEDIUM")

        assert "Invalid blocker_type" in str(exc_info.value)
        agent.db.create_blocker.assert_not_called()


class TestTestWorkerAgentBlockerTypeValidation:
    """Test TestWorkerAgent blocker type validation."""

    @pytest.mark.asyncio
    async def test_create_blocker_accepts_sync_type(self):
        """Test create_blocker accepts SYNC blocker type."""
        agent = TestWorkerAgent(agent_id="test-001")
        agent.database = Mock(spec=Database)
        agent.database.create_blocker.return_value = 1
        agent.project_id = 1

        blocker_id = await agent.create_blocker(
            question="Critical test issue?", blocker_type="SYNC"
        )

        assert blocker_id == 1
        agent.database.create_blocker.assert_called_once()
        call_args = agent.database.create_blocker.call_args[1]
        assert call_args["blocker_type"] == "SYNC"

    @pytest.mark.asyncio
    async def test_create_blocker_rejects_invalid_type(self):
        """Test create_blocker rejects invalid blocker type."""
        agent = TestWorkerAgent(agent_id="test-001")
        agent.database = Mock(spec=Database)
        agent.project_id = 1

        with pytest.raises(ValueError) as exc_info:
            await agent.create_blocker(question="Question?", blocker_type="HIGH")

        assert "Invalid blocker_type" in str(exc_info.value)
        agent.database.create_blocker.assert_not_called()
