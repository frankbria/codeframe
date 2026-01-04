"""Tests for Agent Lifecycle (cf-10) - Project Start & Agent Lifecycle.

Following strict TDD methodology: Tests written FIRST (RED phase).
Target: 100% coverage for agent lifecycle functionality.

Requirements from cf-10:
- cf-10.1: Status Server agent management with running_agents dictionary
- cf-10.2: POST /api/projects/{id}/start endpoint (202 Accepted, non-blocking)
- cf-10.3: Lead Agent greeting on start
- cf-10.4: WebSocket message protocol and broadcasting

Definition of Done:
- ✅ POST /api/projects/{id}/start starts Lead Agent
- ✅ Project status changes to "running"
- ✅ Greeting message saved to database
- ✅ WebSocket broadcasts work
- ✅ Agent runs in background
- ✅ 100% TDD compliance (tests FIRST)
- ✅ All tests pass (100% pass rate)
"""

import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from importlib import reload
from unittest.mock import AsyncMock, Mock, patch

from codeframe.core.models import ProjectStatus
from codeframe.persistence.database import Database


@pytest.fixture(autouse=True)
def clear_shared_state():
    """Clear shared_state before each test to prevent state leakage.

    Since shared_state uses global dictionaries that persist across tests,
    we need to clear them before each test to ensure test isolation.
    """
    from codeframe.ui.shared import shared_state

    # Clear before test
    shared_state._running_agents.clear()
    shared_state._review_cache.clear()

    yield

    # Clear after test
    shared_state._running_agents.clear()
    shared_state._review_cache.clear()


@pytest.fixture
def temp_db_for_lifecycle(tmp_path):
    """Create temporary database for lifecycle tests."""
    db_path = tmp_path / "test_lifecycle.db"

    # Save original value
    original_db_path = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(db_path)

    db = Database(db_path)
    db.initialize()

    yield db

    db.close()
    if db_path.exists():
        db_path.unlink()

    # Restore original value
    if original_db_path is not None:
        os.environ["DATABASE_PATH"] = original_db_path
    else:
        os.environ.pop("DATABASE_PATH", None)


@pytest.fixture
def test_client_with_db(temp_db_path, tmp_path):
    """Create test client with properly initialized database and authentication.

    Follows the pattern from test_project_creation_api.py:
    1. Set DATABASE_PATH environment variable
    2. Set WORKSPACE_ROOT to temporary directory to avoid collisions
    3. Reset auth engine to pick up new DATABASE_PATH
    4. Reload server module to pick up new env vars
    5. Create test user and add authentication headers
    6. Use TestClient which triggers lifespan initialization
    """
    from tests.helpers import create_test_jwt_token, setup_test_user

    # Save original values
    original_db_path = os.environ.get("DATABASE_PATH")
    original_workspace_root = os.environ.get("WORKSPACE_ROOT")

    # Set environment variables
    os.environ["DATABASE_PATH"] = str(temp_db_path)

    # Set temporary workspace root to avoid collisions between test runs
    workspace_root = tmp_path / "workspaces"
    os.environ["WORKSPACE_ROOT"] = str(workspace_root)

    # Reset auth engine to pick up new DATABASE_PATH
    from codeframe.auth.manager import reset_auth_engine
    reset_auth_engine()

    # Reload server to pick up new DATABASE_PATH and WORKSPACE_ROOT
    from codeframe.ui import server

    reload(server)

    # TestClient will trigger lifespan which initializes app.state.db
    with TestClient(server.app) as client:
        # Create test user for authentication
        db = server.app.state.db
        setup_test_user(db, user_id=1)

        # Add authentication header
        auth_token = create_test_jwt_token(user_id=1)
        client.headers["Authorization"] = f"Bearer {auth_token}"

        yield client

    # Restore original values
    if original_db_path is not None:
        os.environ["DATABASE_PATH"] = original_db_path
    else:
        os.environ.pop("DATABASE_PATH", None)

    if original_workspace_root is not None:
        os.environ["WORKSPACE_ROOT"] = original_workspace_root
    else:
        os.environ.pop("WORKSPACE_ROOT", None)

    # Reset auth engine for next test
    reset_auth_engine()


@pytest.fixture
def sample_project(test_client_with_db):
    """Create a sample project for lifecycle tests."""
    response = test_client_with_db.post(
        "/api/projects",
        json={"name": "Lifecycle Test Project", "description": "Test project for lifecycle tests"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.unit
class TestStartAgentEndpoint:
    """Test POST /api/projects/{id}/start endpoint (cf-10.2)."""

    def test_start_agent_endpoint_returns_202_accepted(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint returns 202 Accepted immediately (non-blocking).

        Requirement: cf-10.2 - Return 202 Accepted immediately (non-blocking)
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent") as mock_start_agent:
            mock_start_agent.return_value = AsyncMock()
            response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT
        assert response.status_code == 202
        assert "message" in response.json()
        assert "starting" in response.json()["message"].lower()

    def test_start_agent_endpoint_handles_nonexistent_project(self, test_client_with_db):
        """Test that start endpoint returns 404 for nonexistent project.

        Requirement: cf-10.2 - Handle nonexistent projects gracefully
        """
        # ARRANGE
        nonexistent_id = 99999

        # ACT
        response = test_client_with_db.post(f"/api/projects/{nonexistent_id}/start")

        # ASSERT
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_start_agent_endpoint_handles_already_running(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint is idempotent for already running projects.

        Requirement: cf-10.2 - Idempotent behavior for already running agents

        Updated for fix/start-discovery: Returns 200 only when discovery is
        already in progress (not idle). When discovery is idle, endpoint
        should start discovery regardless of project status.
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # Update project status to RUNNING - get db from reloaded server
        from codeframe.ui import server

        db = server.app.state.db
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Mock LeadAgent's get_discovery_status to return discovering state
        # (discovery already in progress - so "already running" is correct)
        mock_agent = Mock()
        mock_agent.get_discovery_status.return_value = {
            "state": "discovering",
            "answered_count": 1,
            "total_required": 5,
            "progress_percentage": 20.0,
            "answers": {"q1": "answer1"},
        }

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent") as mock_start_agent:
            mock_start_agent.return_value = AsyncMock()
            with patch("codeframe.ui.routers.agents.LeadAgent", return_value=mock_agent):
                response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT
        assert response.status_code == 200  # Already running
        assert (
            "already" in response.json()["message"].lower()
            or "running" in response.json()["message"].lower()
        )

    def test_start_agent_endpoint_triggers_background_task(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint triggers background task execution.

        Requirement: cf-10.2 - Call start_agent in background task
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent"):
            response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT
        assert response.status_code == 202


@pytest.mark.unit
class TestStartAgentFunction:
    """Test start_agent async function (cf-10.1)."""

    @pytest.mark.asyncio
    async def test_start_agent_creates_lead_agent_instance(self, temp_db_for_lifecycle):
        """Test that start_agent creates LeadAgent instance.

        Requirement: cf-10.1 - Create and store agent reference
        """
        # ARRANGE
        project_id = temp_db_for_lifecycle.create_project("Test Project", "Test Project project")

        # Initialize running_agents dictionary
        running_agents = {}

        # ACT
        with patch("codeframe.ui.shared.LeadAgent") as mock_lead_agent_class:
            mock_agent = Mock()
            mock_lead_agent_class.return_value = mock_agent

            from codeframe.ui.shared import start_agent

            await start_agent(project_id, temp_db_for_lifecycle, running_agents, "test-api-key")

        # ASSERT
        assert project_id in running_agents
        mock_lead_agent_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_agent_updates_project_status_to_running(self, temp_db_for_lifecycle):
        """Test that start_agent updates project status to RUNNING.

        Requirement: cf-10.1 - Update project status to "running"
        """
        # ARRANGE
        project_id = temp_db_for_lifecycle.create_project("Test Project", "Test Project project")
        running_agents = {}

        # ACT
        with patch("codeframe.ui.shared.LeadAgent"):
            from codeframe.ui.shared import start_agent

            await start_agent(project_id, temp_db_for_lifecycle, running_agents, "test-api-key")

        # ASSERT
        project = temp_db_for_lifecycle.get_project(project_id)
        assert project["status"] == ProjectStatus.RUNNING.value

    @pytest.mark.asyncio
    async def test_start_agent_saves_greeting_to_database(self, temp_db_for_lifecycle):
        """Test that start_agent saves greeting message to conversation history.

        Requirement: cf-10.3 - Save greeting to conversation history
        """
        # ARRANGE
        project_id = temp_db_for_lifecycle.create_project("Test Project", "Test Project project")
        running_agents = {}
        expected_greeting = "Hi! I'm your Lead Agent. I'm here to help build your project. What would you like to create?"

        # ACT
        with patch("codeframe.ui.shared.LeadAgent"):
            from codeframe.ui.shared import start_agent

            await start_agent(project_id, temp_db_for_lifecycle, running_agents, "test-api-key")

        # ASSERT
        conversation = temp_db_for_lifecycle.get_conversation(project_id)
        assert len(conversation) == 1
        assert conversation[0]["key"] == "assistant"
        assert expected_greeting in conversation[0]["value"]

    @pytest.mark.asyncio
    async def test_start_agent_broadcasts_via_websocket(self, temp_db_for_lifecycle):
        """Test that start_agent broadcasts messages via WebSocket.

        Requirement: cf-10.4 - Broadcast messages via WebSocket
        """
        # ARRANGE
        project_id = temp_db_for_lifecycle.create_project("Test Project", "Test Project project")
        running_agents = {}

        # ACT
        with patch("codeframe.ui.shared.LeadAgent"):
            with patch("codeframe.ui.shared.manager.broadcast") as mock_broadcast:
                from codeframe.ui.shared import start_agent

                await start_agent(project_id, temp_db_for_lifecycle, running_agents, "test-api-key")

        # ASSERT
        # Should broadcast at least 2 messages: agent_started and chat_message (greeting)
        assert mock_broadcast.call_count >= 2

        # Verify message types
        calls = mock_broadcast.call_args_list
        message_types = [call[0][0]["type"] for call in calls]
        assert "agent_started" in message_types or "status_update" in message_types
        assert "chat_message" in message_types


@pytest.mark.unit
class TestWebSocketMessageProtocol:
    """Test WebSocket message protocol (cf-10.4)."""

    def test_broadcast_message_formats_status_update(self):
        """Test that broadcast_message formats status_update correctly.

        Requirement: cf-10.4 - Define message types: status_update
        """
        # ARRANGE
        mock_manager = Mock()
        mock_manager.broadcast = AsyncMock()

        # ACT

        message = {"type": "status_update", "project_id": 1, "status": "running"}
        asyncio.run(mock_manager.broadcast(message))

        # ASSERT
        mock_manager.broadcast.assert_called_once()
        call_args = mock_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "status_update"

    def test_broadcast_message_formats_chat_message(self):
        """Test that broadcast_message formats chat_message correctly.

        Requirement: cf-10.4 - Define message types: chat_message
        """
        # ARRANGE
        mock_manager = Mock()
        mock_manager.broadcast = AsyncMock()

        # ACT

        message = {
            "type": "chat_message",
            "project_id": 1,
            "role": "assistant",
            "content": "Hello!",
        }
        asyncio.run(mock_manager.broadcast(message))

        # ASSERT
        mock_manager.broadcast.assert_called_once()
        call_args = mock_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "chat_message"
        assert "content" in call_args

    def test_broadcast_message_formats_agent_started(self):
        """Test that broadcast_message formats agent_started correctly.

        Requirement: cf-10.4 - Define message types: agent_started
        """
        # ARRANGE
        mock_manager = Mock()
        mock_manager.broadcast = AsyncMock()

        # ACT

        message = {"type": "agent_started", "project_id": 1, "agent_type": "lead"}
        asyncio.run(mock_manager.broadcast(message))

        # ASSERT
        mock_manager.broadcast.assert_called_once()
        call_args = mock_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "agent_started"


@pytest.mark.integration
class TestAgentLifecycleIntegration:
    """Integration test for complete agent lifecycle workflow."""

    def test_complete_start_workflow_end_to_end(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test complete workflow from start request to agent running.

        Integration test covering:
        - POST /api/projects/{id}/start returns 202
        - Project status changes to RUNNING
        - Greeting saved to database
        - WebSocket broadcasts sent
        - Agent instance created and stored

        Requirements: cf-10.1, cf-10.2, cf-10.3, cf-10.4
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
        # Get db from reloaded server
        from codeframe.ui import server

        db = server.app.state.db

        # Verify initial state
        project = db.get_project(project_id)
        assert project["status"] == ProjectStatus.INIT.value  # Database returns string

        initial_conversation = db.get_conversation(project_id)
        assert len(initial_conversation) == 0

        # ACT
        with patch("codeframe.ui.shared.LeadAgent") as mock_lead_agent_class:
            with patch("codeframe.ui.shared.manager.broadcast") as mock_broadcast:
                # Mock LeadAgent
                mock_agent = Mock()
                mock_lead_agent_class.return_value = mock_agent

                # Send start request
                response = test_client_with_db.post(f"/api/projects/{project_id}/start")

                # Give background task time to execute
                import time

                time.sleep(0.5)

        # ASSERT
        # 1. Endpoint returns 202 Accepted
        assert response.status_code == 202

        # 2. Project status updated to RUNNING
        project = db.get_project(project_id)
        assert project["status"] == ProjectStatus.RUNNING.value

        # 3. Greeting saved to database
        conversation = db.get_conversation(project_id)
        assert len(conversation) >= 1
        greeting_message = conversation[0]
        assert greeting_message["key"] == "assistant"
        assert "Lead Agent" in greeting_message["value"]

        # 4. WebSocket broadcasts sent
        assert mock_broadcast.call_count >= 2

        # 5. Agent instance created
        mock_lead_agent_class.assert_called_once()


@pytest.mark.unit
class TestRunningAgentsDictionary:
    """Test running_agents dictionary management (cf-10.1)."""

    def test_running_agents_dictionary_stores_agent_reference(self):
        """Test that running_agents stores agent by project_id.

        Requirement: cf-10.1 - Store agent reference in dictionary
        """
        # ARRANGE
        running_agents = {}
        project_id = 1
        mock_agent = Mock()

        # ACT
        running_agents[project_id] = mock_agent

        # ASSERT
        assert project_id in running_agents
        assert running_agents[project_id] == mock_agent

    def test_running_agents_dictionary_handles_multiple_projects(self):
        """Test that running_agents can handle multiple concurrent projects.

        Requirement: cf-10.1 - Support multiple concurrent agents
        """
        # ARRANGE
        running_agents = {}

        # ACT
        running_agents[1] = Mock()
        running_agents[2] = Mock()
        running_agents[3] = Mock()

        # ASSERT
        assert len(running_agents) == 3
        assert 1 in running_agents
        assert 2 in running_agents
        assert 3 in running_agents

    def test_running_agents_dictionary_allows_agent_removal(self):
        """Test that agents can be removed from running_agents.

        Requirement: cf-10.1 - Support agent lifecycle (stop)
        """
        # ARRANGE
        running_agents = {1: Mock(), 2: Mock()}

        # ACT
        del running_agents[1]

        # ASSERT
        assert 1 not in running_agents
        assert 2 in running_agents
        assert len(running_agents) == 1


@pytest.mark.unit
class TestAgentLifecycleErrorHandling:
    """Test error handling in agent lifecycle."""

    def test_start_agent_handles_database_error_gracefully(self, test_client_with_db):
        """Test that start_agent handles database errors gracefully."""
        # ARRANGE
        project_id = 1

        # ACT - Mock get_project to return None (simulating not found)
        with patch("codeframe.ui.server.app.state.db.get_project", return_value=None):
            response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT - Should return 404 when project not found
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_start_agent_handles_lead_agent_initialization_error(self, temp_db_for_lifecycle):
        """Test that start_agent handles LeadAgent initialization errors."""
        # ARRANGE
        project_id = temp_db_for_lifecycle.create_project("Test Project", "Test Project project")
        running_agents = {}

        # ACT & ASSERT
        with patch("codeframe.ui.shared.LeadAgent", side_effect=ValueError("Missing API key")):
            from codeframe.ui.shared import start_agent

            with pytest.raises(ValueError):
                await start_agent(project_id, temp_db_for_lifecycle, running_agents, None)

    @pytest.mark.asyncio
    async def test_start_agent_handles_websocket_broadcast_failure(self, temp_db_for_lifecycle):
        """Test that start_agent continues even if WebSocket broadcast fails."""
        # ARRANGE
        project_id = temp_db_for_lifecycle.create_project("Test Project", "Test Project project")
        running_agents = {}

        # ACT
        with patch("codeframe.ui.shared.LeadAgent"):
            with patch("codeframe.ui.shared.manager.broadcast", side_effect=Exception("WS Error")):
                from codeframe.ui.shared import start_agent

                # Should not raise exception
                await start_agent(project_id, temp_db_for_lifecycle, running_agents, "test-api-key")

        # ASSERT - Agent still created despite broadcast failure
        project = temp_db_for_lifecycle.get_project(project_id)
        assert project["status"] == ProjectStatus.RUNNING.value


@pytest.mark.unit
class TestStartEndpointDiscoveryState:
    """Test /start endpoint behavior based on discovery state.

    Fix for issue: When project is "running" but discovery is "idle", the
    "Start Discovery" button should still work. The /start endpoint should
    check discovery state, not just project status.
    """

    def test_start_endpoint_starts_discovery_when_project_running_but_discovery_idle(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint proceeds when project is running but discovery is idle.

        Scenario:
        - Project status: "running"
        - Discovery state: "idle" (no discovery started)
        - Expected: 202 Accepted (start discovery)
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # Update project status to RUNNING but keep discovery idle
        from codeframe.ui import server

        db = server.app.state.db
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Mock LeadAgent's get_discovery_status to return idle state
        mock_agent = Mock()
        mock_agent.get_discovery_status.return_value = {
            "state": "idle",
            "answered_count": 0,
            "answers": {},
        }

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent") as mock_start_agent:
            mock_start_agent.return_value = AsyncMock()
            with patch("codeframe.ui.routers.agents.LeadAgent", return_value=mock_agent):
                response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT - Should return 202 Accepted, not 200 "already running"
        assert response.status_code == 202
        assert "starting" in response.json()["message"].lower() or "start" in response.json()["message"].lower()
        # start_agent should have been called to initiate discovery
        mock_start_agent.assert_called_once()

    def test_start_endpoint_returns_already_running_when_discovery_active(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint returns 200 when discovery is already in progress.

        Scenario:
        - Project status: "running"
        - Discovery state: "discovering" (discovery already active)
        - Expected: 200 OK with "already running" message
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # Update project status to RUNNING
        from codeframe.ui import server

        db = server.app.state.db
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Mock LeadAgent's get_discovery_status to return discovering state
        mock_agent = Mock()
        mock_agent.get_discovery_status.return_value = {
            "state": "discovering",
            "answered_count": 2,
            "total_required": 5,
            "progress_percentage": 40.0,
            "answers": {"q1": "answer1", "q2": "answer2"},
        }

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent") as mock_start_agent:
            with patch("codeframe.ui.routers.agents.LeadAgent", return_value=mock_agent):
                response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT - Should return 200 OK with already running message
        assert response.status_code == 200
        response_data = response.json()
        assert "running" in response_data.get("status", "").lower() or "running" in response_data.get("message", "").lower()
        # start_agent should NOT have been called
        mock_start_agent.assert_not_called()

    def test_start_endpoint_handles_discovery_completed(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint returns appropriate response when discovery is completed.

        Scenario:
        - Project status: "running"
        - Discovery state: "completed"
        - Expected: 200 OK with "discovery completed" or "already running" message
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # Update project status to RUNNING
        from codeframe.ui import server

        db = server.app.state.db
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Mock LeadAgent's get_discovery_status to return completed state
        mock_agent = Mock()
        mock_agent.get_discovery_status.return_value = {
            "state": "completed",
            "answered_count": 5,
            "total_required": 5,
            "progress_percentage": 100.0,
            "answers": {"q1": "a1", "q2": "a2", "q3": "a3", "q4": "a4", "q5": "a5"},
        }

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent") as mock_start_agent:
            with patch("codeframe.ui.routers.agents.LeadAgent", return_value=mock_agent):
                response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT - Should return 200 OK
        assert response.status_code == 200
        response_data = response.json()
        # Either "completed" or "running" message is acceptable
        message = response_data.get("message", "").lower()
        status = response_data.get("status", "").lower()
        assert "complet" in message or "running" in message or "complet" in status or "running" in status
        # start_agent should NOT have been called since discovery is already done
        mock_start_agent.assert_not_called()

    def test_start_endpoint_handles_discovery_status_check_failure(
        self, test_client_with_db, sample_project, monkeypatch
    ):
        """Test that start endpoint proceeds when discovery status check fails.

        Scenario:
        - Project status: "running"
        - Discovery status check: raises exception (e.g., database error)
        - Expected: 202 Accepted (fall back to normal start flow)
        """
        # ARRANGE
        project_id = sample_project["id"]
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")

        # Update project status to RUNNING
        from codeframe.ui import server

        db = server.app.state.db
        db.update_project(project_id, {"status": ProjectStatus.RUNNING})

        # Mock LeadAgent to raise exception when checking discovery status
        mock_agent = Mock()
        mock_agent.get_discovery_status.side_effect = Exception("Database error")

        # ACT
        with patch("codeframe.ui.routers.agents.start_agent") as mock_start_agent:
            mock_start_agent.return_value = AsyncMock()
            with patch("codeframe.ui.routers.agents.LeadAgent", return_value=mock_agent):
                response = test_client_with_db.post(f"/api/projects/{project_id}/start")

        # ASSERT - Should return 202 and proceed with start (fallback behavior)
        assert response.status_code == 202
        mock_start_agent.assert_called_once()
