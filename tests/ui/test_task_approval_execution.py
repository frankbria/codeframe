"""
Tests for multi-agent execution trigger after task approval.

This module tests the P0 blocker fix: connecting task approval to the
multi-agent execution engine. After tasks are approved, the system should:
1. Schedule a background task to start multi-agent execution
2. Create LeadAgent and call start_multi_agent_execution()
3. Broadcast agent_created and task_assigned events
4. Handle errors gracefully

Feature: Connect Task Approval to Multi-Agent Execution
Related: codeframe/ui/routers/tasks.py, codeframe/agents/lead_agent.py
"""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks, Request

from codeframe.core.models import Task, TaskStatus


@pytest.fixture
def mock_request():
    """Create mock starlette Request for rate limiter."""
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    request.state = MagicMock()
    request.state.user = None
    return request


# ============================================================================
# Unit Tests for start_development_execution Background Task
# ============================================================================


class TestStartDevelopmentExecution:
    """Tests for the start_development_execution background task function."""

    @pytest.fixture
    def mock_db(self):
        """Create mock Database."""
        db = MagicMock()
        db.get_project.return_value = {
            "id": 1,
            "name": "Test Project",
            "phase": "active"
        }
        return db

    @pytest.fixture
    def mock_ws_manager(self):
        """Create mock WebSocket manager."""
        manager = MagicMock()
        manager.broadcast = AsyncMock()
        return manager

    @pytest.fixture
    def mock_lead_agent(self):
        """Create mock LeadAgent with start_multi_agent_execution."""
        agent = MagicMock()
        agent.start_multi_agent_execution = AsyncMock(return_value={
            "total_tasks": 5,
            "completed": 5,
            "failed": 0,
            "retries": 0,
            "execution_time": 10.5
        })
        return agent

    @pytest.mark.asyncio
    async def test_start_development_execution_calls_lead_agent(
        self, mock_db, mock_ws_manager, mock_lead_agent
    ):
        """Test that start_development_execution creates LeadAgent and starts execution."""
        from codeframe.ui.routers.tasks import start_development_execution

        with patch("codeframe.ui.routers.tasks.LeadAgent", return_value=mock_lead_agent):
            await start_development_execution(
                project_id=1,
                db=mock_db,
                ws_manager=mock_ws_manager,
                api_key="test-api-key"
            )

        # Verify LeadAgent.start_multi_agent_execution was called
        mock_lead_agent.start_multi_agent_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_development_execution_passes_correct_parameters(
        self, mock_db, mock_ws_manager, mock_lead_agent
    ):
        """Test that start_development_execution passes correct parameters to LeadAgent."""
        from codeframe.ui.routers.tasks import start_development_execution

        with patch("codeframe.ui.routers.tasks.LeadAgent") as MockLeadAgent:
            MockLeadAgent.return_value = mock_lead_agent

            await start_development_execution(
                project_id=42,
                db=mock_db,
                ws_manager=mock_ws_manager,
                api_key="sk-ant-test"
            )

            # Verify LeadAgent was instantiated with correct args
            MockLeadAgent.assert_called_once_with(
                project_id=42,
                db=mock_db,
                api_key="sk-ant-test",
                ws_manager=mock_ws_manager
            )

    @pytest.mark.asyncio
    async def test_start_development_execution_handles_timeout_error(
        self, mock_db, mock_ws_manager
    ):
        """Test that timeout errors are caught and broadcast to WebSocket."""
        from codeframe.ui.routers.tasks import start_development_execution

        mock_agent = MagicMock()
        mock_agent.start_multi_agent_execution = AsyncMock(
            side_effect=asyncio.TimeoutError("Execution timed out")
        )

        with patch("codeframe.ui.routers.tasks.LeadAgent", return_value=mock_agent):
            # Should not raise - error is caught internally
            await start_development_execution(
                project_id=1,
                db=mock_db,
                ws_manager=mock_ws_manager,
                api_key="test-key"
            )

        # Verify error was broadcast
        broadcast_calls = mock_ws_manager.broadcast.call_args_list
        error_broadcasts = [
            c for c in broadcast_calls
            if c[0][0].get("type") == "development_failed"
        ]
        assert len(error_broadcasts) == 1
        assert "timed out" in error_broadcasts[0][0][0]["error"].lower()

    @pytest.mark.asyncio
    async def test_start_development_execution_handles_general_exception(
        self, mock_db, mock_ws_manager
    ):
        """Test that general exceptions are caught and broadcast."""
        from codeframe.ui.routers.tasks import start_development_execution

        mock_agent = MagicMock()
        mock_agent.start_multi_agent_execution = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        with patch("codeframe.ui.routers.tasks.LeadAgent", return_value=mock_agent):
            await start_development_execution(
                project_id=1,
                db=mock_db,
                ws_manager=mock_ws_manager,
                api_key="test-key"
            )

        # Verify error was broadcast
        broadcast_calls = mock_ws_manager.broadcast.call_args_list
        error_broadcasts = [
            c for c in broadcast_calls
            if c[0][0].get("type") == "development_failed"
        ]
        assert len(error_broadcasts) == 1
        assert "Database connection failed" in error_broadcasts[0][0][0]["error"]

    @pytest.mark.asyncio
    async def test_start_development_execution_logs_success_summary(
        self, mock_db, mock_ws_manager, mock_lead_agent, caplog
    ):
        """Test that successful execution logs summary."""
        from codeframe.ui.routers.tasks import start_development_execution
        import logging

        with caplog.at_level(logging.INFO):
            with patch("codeframe.ui.routers.tasks.LeadAgent", return_value=mock_lead_agent):
                await start_development_execution(
                    project_id=1,
                    db=mock_db,
                    ws_manager=mock_ws_manager,
                    api_key="test-key"
                )

        # Verify success log message
        assert any("completed" in record.message.lower() for record in caplog.records)


# ============================================================================
# Integration Tests for Task Approval → Execution Flow
# ============================================================================


class TestTaskApprovalTriggersExecution:
    """Tests for approve_tasks endpoint triggering multi-agent execution."""

    @pytest.fixture
    def mock_db(self):
        """Create mock Database with project and tasks."""
        db = MagicMock()
        db.get_project.return_value = {
            "id": 1,
            "name": "Test Project",
            "phase": "planning"
        }
        db.user_has_project_access.return_value = True
        db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
            Task(id=2, project_id=1, title="Task 2", status=TaskStatus.PENDING),
        ]
        db.update_task.return_value = None
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock authenticated user."""
        user = MagicMock()
        user.id = 1
        user.email = "test@example.com"
        return user

    @pytest.fixture
    def mock_ws_manager(self):
        """Create mock WebSocket manager."""
        manager = MagicMock()
        manager.broadcast = AsyncMock()
        return manager

    @pytest.fixture
    def mock_background_tasks(self):
        """Create mock BackgroundTasks."""
        bg = MagicMock(spec=BackgroundTasks)
        bg.add_task = MagicMock()
        return bg

    @pytest.mark.asyncio
    async def test_approve_tasks_schedules_background_execution(
        self, mock_db, mock_user, mock_ws_manager, mock_background_tasks, mock_request
    ):
        """Test that approving tasks schedules multi-agent execution as background task."""
        from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest

        body = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_ws_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            await approve_tasks(
                request=mock_request,
                project_id=1,
                body=body,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Verify background task was scheduled
        mock_background_tasks.add_task.assert_called_once()

        # Verify correct function and arguments
        call_args = mock_background_tasks.add_task.call_args
        assert call_args[0][0].__name__ == "start_development_execution"
        assert call_args[0][1] == 1  # project_id
        assert call_args[0][2] == mock_db
        assert call_args[0][3] == mock_ws_manager
        assert call_args[0][4] == "test-key"  # api_key

    @pytest.mark.asyncio
    async def test_approve_tasks_skips_execution_without_api_key(
        self, mock_db, mock_user, mock_ws_manager, mock_background_tasks, mock_request, caplog
    ):
        """Test that execution is skipped when ANTHROPIC_API_KEY is not set."""
        from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest
        import logging

        body = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        # Remove API key from environment
        env_without_key = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

        with caplog.at_level(logging.WARNING):
            with patch("codeframe.ui.routers.tasks.manager", mock_ws_manager), \
                 patch("codeframe.ui.routers.tasks.PhaseManager"), \
                 patch.dict(os.environ, env_without_key, clear=True):
                response = await approve_tasks(
                    request=mock_request,
                    project_id=1,
                    body=body,
                    background_tasks=mock_background_tasks,
                    db=mock_db,
                    current_user=mock_user
                )

        # Approval should still succeed
        assert response.success is True

        # But background task should NOT be scheduled
        mock_background_tasks.add_task.assert_not_called()

        # Should log warning
        assert any("ANTHROPIC_API_KEY" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_approve_tasks_rejection_does_not_trigger_execution(
        self, mock_db, mock_user, mock_ws_manager, mock_background_tasks, mock_request
    ):
        """Test that rejecting tasks does not trigger execution."""
        from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest

        body = TaskApprovalRequest(approved=False, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_ws_manager), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await approve_tasks(
                request=mock_request,
                project_id=1,
                body=body,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Rejection response
        assert response.success is False

        # Background task should NOT be scheduled for rejection
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_tasks_returns_immediately(
        self, mock_db, mock_user, mock_ws_manager, mock_background_tasks, mock_request
    ):
        """Test that approve_tasks returns immediately (doesn't wait for execution)."""
        from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest
        import time

        body = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        start_time = time.time()

        with patch("codeframe.ui.routers.tasks.manager", mock_ws_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            response = await approve_tasks(
                request=mock_request,
                project_id=1,
                body=body,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        elapsed = time.time() - start_time

        # Should return quickly (< 1 second) - execution happens in background
        assert elapsed < 1.0
        assert response.success is True


# ============================================================================
# WebSocket Event Tests
# ============================================================================


class TestDevelopmentFailedBroadcast:
    """Tests for development_failed WebSocket event broadcast."""

    @pytest.fixture
    def mock_ws_manager(self):
        """Create mock WebSocket manager."""
        manager = MagicMock()
        manager.broadcast = AsyncMock()
        return manager

    @pytest.mark.asyncio
    async def test_development_failed_message_format(self, mock_ws_manager):
        """Test that development_failed message has correct format."""
        from codeframe.ui.routers.tasks import start_development_execution

        mock_agent = MagicMock()
        mock_agent.start_multi_agent_execution = AsyncMock(
            side_effect=Exception("Test error")
        )

        with patch("codeframe.ui.routers.tasks.LeadAgent", return_value=mock_agent):
            await start_development_execution(
                project_id=42,
                db=MagicMock(),
                ws_manager=mock_ws_manager,
                api_key="test-key"
            )

        # Find development_failed broadcast
        broadcast_calls = mock_ws_manager.broadcast.call_args_list
        error_broadcasts = [
            c for c in broadcast_calls
            if c[0][0].get("type") == "development_failed"
        ]

        assert len(error_broadcasts) == 1
        message = error_broadcasts[0][0][0]

        # Verify message format
        assert message["type"] == "development_failed"
        assert message["project_id"] == 42
        assert "error" in message
        assert "timestamp" in message
        assert message["timestamp"].endswith("Z")  # ISO format with Z suffix

    @pytest.mark.asyncio
    async def test_development_failed_includes_error_details(self, mock_ws_manager):
        """Test that error message is included in broadcast."""
        from codeframe.ui.routers.tasks import start_development_execution

        mock_agent = MagicMock()
        mock_agent.start_multi_agent_execution = AsyncMock(
            side_effect=ValueError("Invalid task dependency graph")
        )

        with patch("codeframe.ui.routers.tasks.LeadAgent", return_value=mock_agent):
            await start_development_execution(
                project_id=1,
                db=MagicMock(),
                ws_manager=mock_ws_manager,
                api_key="test-key"
            )

        # Find error broadcast
        error_broadcasts = [
            c for c in mock_ws_manager.broadcast.call_args_list
            if c[0][0].get("type") == "development_failed"
        ]

        assert "Invalid task dependency graph" in error_broadcasts[0][0][0]["error"]


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestExecutionEdgeCases:
    """Tests for edge cases in multi-agent execution trigger."""

    @pytest.fixture
    def mock_db(self):
        """Create mock Database."""
        db = MagicMock()
        db.get_project.return_value = {"id": 1, "name": "Test", "phase": "planning"}
        db.user_has_project_access.return_value = True
        db.get_project_tasks.return_value = [
            Task(id=1, project_id=1, title="Task 1", status=TaskStatus.PENDING),
        ]
        db.update_task.return_value = None
        return db

    @pytest.fixture
    def mock_user(self):
        """Create mock user."""
        user = MagicMock()
        user.id = 1
        return user

    @pytest.fixture
    def mock_ws_manager(self):
        """Create mock WebSocket manager."""
        manager = MagicMock()
        manager.broadcast = AsyncMock()
        return manager

    @pytest.fixture
    def mock_background_tasks(self):
        """Create mock BackgroundTasks."""
        bg = MagicMock(spec=BackgroundTasks)
        bg.add_task = MagicMock()
        return bg

    @pytest.mark.asyncio
    async def test_lead_agent_instantiation_error_is_handled(self, mock_ws_manager):
        """Test that LeadAgent instantiation errors are handled gracefully."""
        from codeframe.ui.routers.tasks import start_development_execution

        with patch("codeframe.ui.routers.tasks.LeadAgent") as MockLeadAgent:
            MockLeadAgent.side_effect = RuntimeError("Failed to initialize agent pool")

            # Should not raise
            await start_development_execution(
                project_id=1,
                db=MagicMock(),
                ws_manager=mock_ws_manager,
                api_key="test-key"
            )

        # Error should be broadcast
        error_broadcasts = [
            c for c in mock_ws_manager.broadcast.call_args_list
            if c[0][0].get("type") == "development_failed"
        ]
        assert len(error_broadcasts) == 1

    @pytest.mark.asyncio
    async def test_empty_api_key_treated_as_missing(
        self, mock_db, mock_user, mock_ws_manager, mock_background_tasks, mock_request
    ):
        """Test that empty string API key is treated same as missing."""
        from codeframe.ui.routers.tasks import approve_tasks, TaskApprovalRequest

        body = TaskApprovalRequest(approved=True, excluded_task_ids=[])

        with patch("codeframe.ui.routers.tasks.manager", mock_ws_manager), \
             patch("codeframe.ui.routers.tasks.PhaseManager"), \
             patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            await approve_tasks(
                request=mock_request,
                project_id=1,
                body=body,
                background_tasks=mock_background_tasks,
                db=mock_db,
                current_user=mock_user
            )

        # Empty key should not trigger execution
        mock_background_tasks.add_task.assert_not_called()


# ============================================================================
# Signature Compatibility Tests
# ============================================================================


class TestApproveTasksSignature:
    """Tests to ensure approve_tasks signature is correct after modification."""

    def test_approve_tasks_accepts_background_tasks_parameter(self):
        """Test that approve_tasks function accepts BackgroundTasks parameter."""
        from codeframe.ui.routers.tasks import approve_tasks
        import inspect

        sig = inspect.signature(approve_tasks)
        params = list(sig.parameters.keys())

        # Must have background_tasks parameter
        assert "background_tasks" in params

    def test_approve_tasks_background_tasks_has_correct_type(self):
        """Test that background_tasks parameter has correct type annotation."""
        from codeframe.ui.routers.tasks import approve_tasks
        import inspect

        sig = inspect.signature(approve_tasks)
        bg_param = sig.parameters.get("background_tasks")

        # Should be annotated as BackgroundTasks
        assert bg_param is not None
        assert bg_param.annotation == BackgroundTasks
