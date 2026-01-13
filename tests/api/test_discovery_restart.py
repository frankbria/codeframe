"""API tests for full discovery restart endpoint (Issue #247).

Following TDD: These tests are written FIRST before implementation.
Tests verify POST /api/projects/{id}/discovery/restart supports restart from any phase.
"""

from unittest.mock import Mock, patch


def get_db_from_client(api_client):
    """Get database instance from test client's app."""
    from codeframe.ui import server

    return server.app.state.db


class TestDiscoveryRestartFromAnyPhase:
    """Test POST /api/projects/{id}/discovery/restart from any phase (Issue #247)."""

    def test_restart_from_planning_phase_requires_confirmation(self, api_client):
        """Test restart from planning phase returns confirmation request without confirmed=true."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})

        # Add some PRD content to verify it would be deleted
        db.upsert_memory(
            project_id=project_id,
            category="prd",
            key="content",
            value="# Test PRD\n\nThis is a test PRD."
        )

        # ACT - Call without confirmed parameter
        response = api_client.post(f"/api/projects/{project_id}/discovery/restart")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["requires_confirmation"] is True
        assert "data_to_be_deleted" in data
        assert "message" in data
        # Should NOT have reset the project yet
        project = db.get_project(project_id)
        assert project["phase"] == "planning"

    def test_restart_from_planning_phase_with_confirmation_succeeds(self, api_client):
        """Test restart from planning phase works when confirmed=true."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})

        # Add PRD content
        db.upsert_memory(
            project_id=project_id,
            category="prd",
            key="content",
            value="# Test PRD\n\nThis is a test PRD."
        )
        db.upsert_memory(
            project_id=project_id,
            category="prd",
            key="generated_at",
            value="2025-01-01T00:00:00Z"
        )

        # Add discovery answers
        db.upsert_memory(
            project_id=project_id,
            category="discovery_answers",
            key="answer_1",
            value="Test answer 1"
        )

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/restart",
            params={"confirmed": True}
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "idle"

        # Verify project phase reset to discovery
        project = db.get_project(project_id)
        assert project["phase"] == "discovery"

        # Verify PRD was deleted
        prd = db.get_prd(project_id)
        assert prd is None

        # Verify discovery answers were cleared
        memories = db.get_memories_by_category(project_id, "discovery_answers")
        assert len(memories) == 0

    def test_restart_from_active_phase_clears_tasks_and_issues(self, api_client):
        """Test restart from active phase clears all tasks and issues."""
        from codeframe.core.models import Task, TaskStatus

        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "active"})

        # Add an issue
        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": 1,
            "title": "Test Issue",
            "description": "Test issue description"
        })

        # Add a task
        task_id = db.create_task(Task(
            project_id=project_id,
            title="Test Task",
            description="Test task description",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step="planning"
        ))

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/restart",
            params={"confirmed": True}
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify tasks were deleted
        tasks = db.get_project_tasks(project_id)
        assert len(tasks) == 0

        # Verify issues were deleted
        issues = db.get_project_issues(project_id)
        assert len(issues) == 0

        # Verify project phase reset to discovery
        project = db.get_project(project_id)
        assert project["phase"] == "discovery"

    def test_restart_from_review_phase_succeeds(self, api_client):
        """Test restart from review phase works correctly."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "review"})

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/restart",
            params={"confirmed": True}
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        project = db.get_project(project_id)
        assert project["phase"] == "discovery"

    def test_restart_from_discovery_phase_no_confirmation_needed(self, api_client):
        """Test restart from discovery phase doesn't require confirmation."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "discovery"})

        # ACT - No confirmation parameter needed
        response = api_client.post(f"/api/projects/{project_id}/discovery/restart")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "idle"

    def test_restart_nonexistent_project_returns_404(self, api_client):
        """Test restart for non-existent project returns 404."""
        # ACT
        response = api_client.post(
            "/api/projects/99999/discovery/restart",
            params={"confirmed": True}
        )

        # ASSERT
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_restart_clears_discovery_state_completely(self, api_client):
        """Test restart clears all discovery state including conversation history."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})

        # Add discovery state
        db.upsert_memory(
            project_id=project_id,
            category="discovery_state",
            key="state",
            value="completed"
        )
        db.upsert_memory(
            project_id=project_id,
            category="discovery_state",
            key="conversation_turn_0",
            value='{"question": "Q1", "answer": "A1"}'
        )
        db.upsert_memory(
            project_id=project_id,
            category="discovery_state",
            key="conversation_turn_1",
            value='{"question": "Q2", "answer": "A2"}'
        )

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/restart",
            params={"confirmed": True}
        )

        # ASSERT
        assert response.status_code == 200

        # Verify discovery state was reset to idle
        state_memories = db.get_memories_by_category(project_id, "discovery_state")
        state_value = next(
            (m["value"] for m in state_memories if m["key"] == "state"),
            None
        )
        assert state_value == "idle"

    def test_restart_returns_cleared_items_count(self, api_client):
        """Test restart returns count of items that were cleared."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")
        db.update_project(project_id, {"phase": "planning"})

        # Add PRD
        db.upsert_memory(
            project_id=project_id,
            category="prd",
            key="content",
            value="# PRD Content"
        )

        # Add discovery answers
        db.upsert_memory(
            project_id=project_id,
            category="discovery_answers",
            key="answer_1",
            value="Answer 1"
        )
        db.upsert_memory(
            project_id=project_id,
            category="discovery_answers",
            key="answer_2",
            value="Answer 2"
        )

        # ACT
        response = api_client.post(
            f"/api/projects/{project_id}/discovery/restart",
            params={"confirmed": True}
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert "cleared_items" in data
        assert data["cleared_items"]["prd_existed"] is True


class TestDiscoveryRestartDatabaseMethods:
    """Test new database methods for discovery restart."""

    def test_delete_prd_removes_all_prd_entries(self, api_client):
        """Test delete_prd removes all PRD-related memory entries."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        # Add PRD content
        db.upsert_memory(
            project_id=project_id,
            category="prd",
            key="content",
            value="# Test PRD"
        )
        db.upsert_memory(
            project_id=project_id,
            category="prd",
            key="generated_at",
            value="2025-01-01T00:00:00Z"
        )

        # Verify PRD exists
        prd = db.get_prd(project_id)
        assert prd is not None

        # ACT
        result = db.delete_prd(project_id)

        # ASSERT
        assert result is True
        prd = db.get_prd(project_id)
        assert prd is None

    def test_delete_discovery_answers_removes_all_answers(self, api_client):
        """Test delete_discovery_answers removes all answer entries."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        # Add discovery answers
        db.upsert_memory(
            project_id=project_id,
            category="discovery_answers",
            key="q1",
            value="Answer 1"
        )
        db.upsert_memory(
            project_id=project_id,
            category="discovery_answers",
            key="q2",
            value="Answer 2"
        )

        # Verify answers exist
        answers = db.get_memories_by_category(project_id, "discovery_answers")
        assert len(answers) == 2

        # ACT
        count = db.delete_discovery_answers(project_id)

        # ASSERT
        assert count == 2
        answers = db.get_memories_by_category(project_id, "discovery_answers")
        assert len(answers) == 0

    def test_delete_project_tasks_and_issues(self, api_client):
        """Test delete_project_tasks_and_issues removes all tasks and issues."""
        from codeframe.core.models import Task, TaskStatus

        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        # Add an issue
        issue_id = db.create_issue({
            "project_id": project_id,
            "issue_number": 1,
            "title": "Test Issue",
            "description": "Description"
        })

        # Add tasks
        db.create_task(Task(
            project_id=project_id,
            title="Task 1",
            description="Desc 1",
            status=TaskStatus.PENDING,
            priority=1,
            workflow_step="planning"
        ))
        db.create_task(Task(
            project_id=project_id,
            title="Task 2",
            description="Desc 2",
            status=TaskStatus.PENDING,
            priority=2,
            workflow_step="planning"
        ))

        # Verify data exists
        tasks = db.get_project_tasks(project_id)
        assert len(tasks) == 2
        issues = db.get_project_issues(project_id)
        assert len(issues) == 1

        # ACT
        deleted = db.delete_project_tasks_and_issues(project_id)

        # ASSERT
        assert deleted["tasks"] == 2
        assert deleted["issues"] == 1

        tasks = db.get_project_tasks(project_id)
        assert len(tasks) == 0
        issues = db.get_project_issues(project_id)
        assert len(issues) == 0


class TestLeadAgentFullReset:
    """Test LeadAgent.full_reset_discovery() method."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_full_reset_clears_all_discovery_data(self, mock_provider_class, api_client):
        """Test full_reset_discovery clears answers, state, and conversation history."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Test question?",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        from codeframe.agents.lead_agent import LeadAgent

        # Start discovery and add some answers
        agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")
        agent.start_discovery()
        agent.process_discovery_answer("Test answer")

        # Verify there's data to clear
        status = agent.get_discovery_status()
        assert status["answered_count"] >= 1

        # ACT
        agent.full_reset_discovery()

        # ASSERT
        new_agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")
        status = new_agent.get_discovery_status()
        assert status["state"] == "idle"
        assert status["answered_count"] == 0

        # Verify discovery answers were cleared
        answers = db.get_memories_by_category(project_id, "discovery_answers")
        assert len(answers) == 0

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_full_reset_resets_answer_capture_state(self, mock_provider_class, api_client):
        """Test full_reset_discovery resets DiscoveryAnswerCapture state."""
        # ARRANGE
        db = get_db_from_client(api_client)
        project_id = db.create_project("test-project", "Test Project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        from codeframe.agents.lead_agent import LeadAgent

        agent = LeadAgent(project_id=project_id, db=db, api_key="test-key")

        # ACT
        agent.full_reset_discovery()

        # ASSERT
        # Agent should be in idle state
        status = agent.get_discovery_status()
        assert status["state"] == "idle"


class TestPhaseManagerTransitions:
    """Test phase manager allows transitions back to discovery from any phase."""

    def test_active_to_discovery_transition_allowed(self):
        """Test transition from active to discovery is allowed."""
        from codeframe.core.phase_manager import PhaseManager

        assert PhaseManager.can_transition("active", "discovery") is True

    def test_review_to_discovery_transition_allowed(self):
        """Test transition from review to discovery is allowed."""
        from codeframe.core.phase_manager import PhaseManager

        assert PhaseManager.can_transition("review", "discovery") is True

    def test_planning_to_discovery_transition_already_allowed(self):
        """Test transition from planning to discovery is already allowed."""
        from codeframe.core.phase_manager import PhaseManager

        # This should already be allowed per existing VALID_TRANSITIONS
        assert PhaseManager.can_transition("planning", "discovery") is True
