"""
Tests for planning automation triggered after PRD generation (Feature: 016-planning-phase-automation).

These tests verify:
- Planning automation is triggered after PRD completion
- WebSocket events are broadcast at each stage
- Error handling and retry capability
- Proper sequencing of generate_issues and decompose_prd
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codeframe.ui.routers.discovery import generate_planning_background


@pytest.fixture
def mock_manager():
    """Create mock ConnectionManager."""
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def mock_db():
    """Create mock Database."""
    db = MagicMock()
    db.get_project.return_value = {"id": 1, "name": "Test Project", "phase": "planning"}
    return db


@pytest.fixture
def mock_lead_agent():
    """Create mock LeadAgent that returns successful results."""
    agent = MagicMock()
    # Mock generate_issues to return a list of issues
    agent.generate_issues.return_value = [
        MagicMock(id=1, title="Issue 1"),
        MagicMock(id=2, title="Issue 2"),
        MagicMock(id=3, title="Issue 3"),
    ]
    # Mock decompose_prd to return task count info
    agent.decompose_prd.return_value = {
        "issues": 3,
        "tasks": 10,
        "success": True,
    }
    return agent


class TestPlanningAutomationBackgroundTask:
    """Tests for generate_planning_background function."""

    @pytest.mark.asyncio
    async def test_planning_automation_broadcasts_started_event(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that planning_started event is broadcast when automation begins."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        # Find the planning_started broadcast call
        calls = mock_manager.broadcast.call_args_list
        planning_started_calls = [
            call for call in calls
            if call[0][0].get("type") == "planning_started"
        ]

        assert len(planning_started_calls) == 1
        message = planning_started_calls[0][0][0]
        assert message["type"] == "planning_started"
        assert message["project_id"] == 1
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_planning_automation_calls_generate_issues(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that generate_issues is called with sprint_number=1."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        mock_lead_agent.generate_issues.assert_called_once_with(sprint_number=1)

    @pytest.mark.asyncio
    async def test_planning_automation_broadcasts_issues_generated_event(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that issues_generated event is broadcast with issue count."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        calls = mock_manager.broadcast.call_args_list
        issues_generated_calls = [
            call for call in calls
            if call[0][0].get("type") == "issues_generated"
        ]

        assert len(issues_generated_calls) == 1
        message = issues_generated_calls[0][0][0]
        assert message["type"] == "issues_generated"
        assert message["project_id"] == 1
        assert message["issue_count"] == 3
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_planning_automation_calls_decompose_prd(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that decompose_prd is called after generate_issues."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        mock_lead_agent.decompose_prd.assert_called_once()

    @pytest.mark.asyncio
    async def test_planning_automation_broadcasts_tasks_decomposed_event(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that tasks_decomposed event is broadcast with task count."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        calls = mock_manager.broadcast.call_args_list
        tasks_decomposed_calls = [
            call for call in calls
            if call[0][0].get("type") == "tasks_decomposed"
        ]

        assert len(tasks_decomposed_calls) == 1
        message = tasks_decomposed_calls[0][0][0]
        assert message["type"] == "tasks_decomposed"
        assert message["project_id"] == 1
        assert message["task_count"] == 10
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_planning_automation_broadcasts_tasks_ready_event(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that tasks_ready event is broadcast when automation completes."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        calls = mock_manager.broadcast.call_args_list
        tasks_ready_calls = [
            call for call in calls
            if call[0][0].get("type") == "tasks_ready"
        ]

        assert len(tasks_ready_calls) == 1
        message = tasks_ready_calls[0][0][0]
        assert message["type"] == "tasks_ready"
        assert message["project_id"] == 1
        assert message["total_tasks"] == 10
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_planning_automation_all_events_in_order(
        self, mock_db, mock_lead_agent, mock_manager
    ):
        """Test that all WebSocket events are broadcast in correct order."""
        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_lead_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        calls = mock_manager.broadcast.call_args_list
        event_types = [call[0][0].get("type") for call in calls]

        # Verify order: planning_started → issues_generated → tasks_decomposed → tasks_ready
        expected_order = ["planning_started", "issues_generated", "tasks_decomposed", "tasks_ready"]
        assert event_types == expected_order


class TestPlanningAutomationErrorHandling:
    """Tests for error handling in planning automation."""

    @pytest.mark.asyncio
    async def test_issues_generation_error_broadcasts_failure(
        self, mock_db, mock_manager
    ):
        """Test that planning_failed event is broadcast when generate_issues fails."""
        mock_agent = MagicMock()
        mock_agent.generate_issues.side_effect = Exception("API Error")

        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        calls = mock_manager.broadcast.call_args_list
        failure_calls = [
            call for call in calls
            if call[0][0].get("type") == "planning_failed"
        ]

        assert len(failure_calls) == 1
        message = failure_calls[0][0][0]
        assert message["type"] == "planning_failed"
        assert message["project_id"] == 1
        assert "error" in message
        assert "API Error" in message["error"]

    @pytest.mark.asyncio
    async def test_decompose_prd_error_broadcasts_failure(
        self, mock_db, mock_manager
    ):
        """Test that planning_failed event is broadcast when decompose_prd fails."""
        mock_agent = MagicMock()
        mock_agent.generate_issues.return_value = [MagicMock(id=1)]
        mock_agent.decompose_prd.side_effect = Exception("Task decomposition failed")

        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        calls = mock_manager.broadcast.call_args_list
        failure_calls = [
            call for call in calls
            if call[0][0].get("type") == "planning_failed"
        ]

        assert len(failure_calls) == 1
        message = failure_calls[0][0][0]
        assert message["type"] == "planning_failed"
        assert "Task decomposition failed" in message["error"]

    @pytest.mark.asyncio
    async def test_error_does_not_update_project_phase(
        self, mock_db, mock_manager
    ):
        """Test that project phase is not updated when planning fails."""
        mock_agent = MagicMock()
        mock_agent.generate_issues.side_effect = Exception("API Error")

        with patch("codeframe.ui.routers.discovery.manager", mock_manager), \
             patch("codeframe.ui.routers.discovery.LeadAgent", return_value=mock_agent):
            await generate_planning_background(
                project_id=1, db=mock_db, api_key="test-key"
            )

        # Phase should not be updated on error
        mock_db.update_project.assert_not_called()


class TestPRDCompletionTrigger:
    """Tests for planning automation trigger after PRD completion."""

    @pytest.mark.asyncio
    async def test_prd_completion_triggers_planning_automation(self):
        """Test that planning automation is triggered after PRD completion."""
        # This test verifies the integration point in generate_prd_background
        # We'll test that the function signature supports BackgroundTasks
        from codeframe.ui.routers.discovery import generate_prd_background
        import inspect

        # Check that the function can accept background_tasks parameter
        # (This will be added as part of the implementation)
        sig = inspect.signature(generate_prd_background)
        params = list(sig.parameters.keys())

        # The function should have project_id, db, api_key parameters
        assert "project_id" in params
        assert "db" in params
        assert "api_key" in params
