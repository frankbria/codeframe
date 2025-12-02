"""Unit tests for Lead Agent session lifecycle functionality."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from codeframe.agents.lead_agent import LeadAgent
from codeframe.core.session_manager import SessionManager
from codeframe.persistence.database import Database


class TestSessionManager:
    """Tests for SessionManager class."""

    def test_save_session_creates_file(self, tmp_path):
        """Test save_session() creates JSON file."""
        mgr = SessionManager(str(tmp_path))

        state = {
            "summary": "Test summary",
            "completed_tasks": [1, 2, 3],
            "next_actions": ["Action 1"],
            "current_plan": "Test plan",
            "active_blockers": [],
            "progress_pct": 25.0,
        }

        mgr.save_session(state)

        # Verify file exists

        assert Path(mgr.state_file).exists()

        # Verify file permissions
        file_stat = os.stat(mgr.state_file)
        assert oct(file_stat.st_mode)[-3:] == "600"

    def test_load_session_returns_dict(self, tmp_path):
        """Test load_session() returns state dict."""
        mgr = SessionManager(str(tmp_path))

        # Save then load
        state = {
            "summary": "Test",
            "completed_tasks": [1],
            "next_actions": ["Action 1"],
            "current_plan": None,
            "active_blockers": [],
            "progress_pct": 25.0,
        }
        mgr.save_session(state)

        loaded = mgr.load_session()

        assert loaded is not None
        assert loaded["progress_pct"] == 25.0
        assert loaded["last_session"]["summary"] == "Test"

    def test_load_session_returns_none_missing_file(self, tmp_path):
        """Test load_session() returns None when file missing."""
        mgr = SessionManager(str(tmp_path))

        result = mgr.load_session()

        assert result is None

    def test_load_session_handles_corrupted_json(self, tmp_path):
        """Test load_session() handles corrupted JSON gracefully."""
        mgr = SessionManager(str(tmp_path))

        # Create .codeframe directory
        os.makedirs(os.path.dirname(mgr.state_file), exist_ok=True)

        # Write corrupted JSON
        with open(mgr.state_file, "w") as f:
            f.write('{"invalid": json')

        result = mgr.load_session()

        assert result is None

    def test_clear_session_removes_file(self, tmp_path):
        """Test clear_session() deletes state file."""
        mgr = SessionManager(str(tmp_path))

        # Create session
        state = {
            "summary": "Test",
            "completed_tasks": [],
            "next_actions": [],
            "current_plan": None,
            "active_blockers": [],
            "progress_pct": 0,
        }
        mgr.save_session(state)

        assert Path(mgr.state_file).exists()

        # Clear
        mgr.clear_session()

        assert not Path(mgr.state_file).exists()

    def test_clear_session_no_error_when_file_missing(self, tmp_path):
        """Test clear_session() succeeds when file doesn't exist."""
        mgr = SessionManager(str(tmp_path))

        # Should not raise exception
        mgr.clear_session()


class TestLeadAgentSessionHelpers:
    """Tests for Lead Agent session helper methods."""

    @pytest.fixture
    def mock_db(self):
        """Mock database with test data."""
        db = Mock(spec=Database)

        # Mock completed tasks
        db.get_recently_completed_tasks.return_value = [
            {
                "id": 27,
                "title": "JWT refresh tokens",
                "status": "completed",
                "updated_at": "2025-11-20T10:00:00",
            },
            {
                "id": 28,
                "title": "Add token validation",
                "status": "completed",
                "updated_at": "2025-11-20T09:00:00",
            },
        ]

        # Mock pending tasks
        db.get_pending_tasks.return_value = [
            {
                "id": 29,
                "title": "Fix JWT validation",
                "priority": "high",
                "created_at": "2025-11-20T08:00:00",
            },
            {
                "id": 30,
                "title": "Add refresh token tests",
                "priority": "medium",
                "created_at": "2025-11-20T08:00:00",
            },
        ]

        # Mock project stats
        db.get_project_stats.return_value = {"total_tasks": 40, "completed_tasks": 27}

        # Mock blockers
        db.list_blockers.return_value = {
            "blockers": [
                {
                    "id": 5,
                    "question": "Which OAuth provider?",
                    "priority": "high",
                    "resolved": False,
                }
            ],
            "total": 1,
        }

        # Mock project
        db.get_project.return_value = {"workspace_path": "/tmp/test-project"}

        return db

    @pytest.fixture
    def lead_agent(self, mock_db):
        """Create Lead Agent with mocked dependencies."""
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            agent = LeadAgent(project_id=1, db=mock_db, api_key="test-key")
            return agent

    def test_get_session_summary(self, lead_agent):
        """Test _get_session_summary() generates correct summary."""
        summary = lead_agent._get_session_summary()

        assert "Task #27" in summary
        assert "JWT refresh tokens" in summary
        assert "Task #28" in summary

    def test_get_session_summary_no_tasks(self, lead_agent, mock_db):
        """Test _get_session_summary() with no completed tasks."""
        mock_db.get_recently_completed_tasks.return_value = []

        summary = lead_agent._get_session_summary()

        assert summary == "No tasks completed"

    def test_get_completed_task_ids(self, lead_agent):
        """Test _get_completed_task_ids() returns task IDs."""
        ids = lead_agent._get_completed_task_ids()

        assert ids == [27, 28]

    def test_format_time_ago_minutes(self, lead_agent):
        """Test _format_time_ago() for minutes."""
        timestamp = (datetime.now() - timedelta(minutes=5)).isoformat()

        result = lead_agent._format_time_ago(timestamp)

        assert "minute" in result
        assert "5" in result

    def test_format_time_ago_hours(self, lead_agent):
        """Test _format_time_ago() for hours."""
        timestamp = (datetime.now() - timedelta(hours=2)).isoformat()

        result = lead_agent._format_time_ago(timestamp)

        assert "hour" in result
        assert "2" in result

    def test_format_time_ago_days(self, lead_agent):
        """Test _format_time_ago() for days."""
        timestamp = (datetime.now() - timedelta(days=3)).isoformat()

        result = lead_agent._format_time_ago(timestamp)

        assert "day" in result
        assert "3" in result

    def test_format_time_ago_invalid(self, lead_agent):
        """Test _format_time_ago() with invalid timestamp."""
        result = lead_agent._format_time_ago("invalid")

        assert result == "unknown time"

    def test_get_pending_actions(self, lead_agent):
        """Test _get_pending_actions() returns action list."""
        actions = lead_agent._get_pending_actions()

        assert len(actions) == 2
        assert "Fix JWT validation (Task #29)" in actions
        assert "Add refresh token tests (Task #30)" in actions

    def test_get_blocker_summaries(self, lead_agent):
        """Test _get_blocker_summaries() returns blocker info."""
        blockers = lead_agent._get_blocker_summaries()

        assert len(blockers) == 1
        assert blockers[0]["id"] == 5
        assert blockers[0]["question"] == "Which OAuth provider?"
        assert blockers[0]["priority"] == "high"

    def test_get_progress_percentage(self, lead_agent):
        """Test _get_progress_percentage() calculates correctly."""
        progress = lead_agent._get_progress_percentage()

        # 27 / 40 = 67.5%
        assert progress == 67.5

    def test_get_progress_percentage_zero_tasks(self, lead_agent, mock_db):
        """Test _get_progress_percentage() with zero tasks."""
        mock_db.get_project_stats.return_value = {"total_tasks": 0, "completed_tasks": 0}

        progress = lead_agent._get_progress_percentage()

        assert progress == 0.0


class TestLeadAgentSessionLifecycle:
    """Tests for Lead Agent session lifecycle methods."""

    @pytest.fixture
    def mock_db(self):
        """Mock database."""
        db = Mock(spec=Database)
        db.get_project.return_value = {"workspace_path": "/tmp/test-project"}
        db.get_recently_completed_tasks.return_value = []
        db.get_pending_tasks.return_value = []
        db.get_project_stats.return_value = {"total_tasks": 0, "completed_tasks": 0}
        db.list_blockers.return_value = {"blockers": [], "total": 0}
        return db

    @pytest.fixture
    def lead_agent_with_session(self, mock_db, tmp_path):
        """Create Lead Agent with SessionManager."""
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            # Patch the workspace path to use tmp_path
            mock_db.get_project.return_value = {"workspace_path": str(tmp_path)}

            agent = LeadAgent(project_id=1, db=mock_db, api_key="test-key")
            return agent

    def test_on_session_start_no_state(self, lead_agent_with_session, capsys):
        """Test on_session_start() with no state file."""
        lead_agent_with_session.on_session_start()

        captured = capsys.readouterr()
        assert "Starting new session" in captured.out

    def test_on_session_end_saves_state(self, lead_agent_with_session):
        """Test on_session_end() saves all state fields."""
        lead_agent_with_session.on_session_end()

        # Verify state file created

        assert Path(lead_agent_with_session.session_manager.state_file).exists()

        # Load and verify structure
        state = lead_agent_with_session.session_manager.load_session()
        assert "last_session" in state
        assert "next_actions" in state
        assert "progress_pct" in state
        assert "active_blockers" in state

    def test_session_lifecycle_integration(self, lead_agent_with_session, tmp_path):
        """Test full session lifecycle: save → load → display."""
        # Save session
        lead_agent_with_session.on_session_end()

        # Create new agent instance (simulating CLI restart)
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            mock_db = Mock(spec=Database)
            mock_db.get_project.return_value = {"workspace_path": str(tmp_path)}
            mock_db.get_project_stats.return_value = {"total_tasks": 10, "completed_tasks": 5}

            new_agent = LeadAgent(project_id=1, db=mock_db, api_key="test-key")

            # Session should be restored
            session = new_agent.session_manager.load_session()
            assert session is not None


class TestLeadAgentSDKCoordination:
    """Tests for Lead Agent SDK coordination features (Phase 3)."""

    @pytest.fixture
    def mock_db(self):
        """Mock database with test data."""
        db = Mock(spec=Database)
        db.get_project.return_value = {"workspace_path": "/tmp/test-project"}
        db.get_recently_completed_tasks.return_value = []
        db.get_pending_tasks.return_value = []
        db.get_project_stats.return_value = {"total_tasks": 0, "completed_tasks": 0}
        db.list_blockers.return_value = {"blockers": [], "total": 0}
        return db

    @pytest.fixture
    def lead_agent(self, mock_db):
        """Create Lead Agent with mocked dependencies."""
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            agent = LeadAgent(project_id=1, db=mock_db, api_key="test-key")
            return agent

    def test_init_with_use_sdk_parameter(self, mock_db):
        """Test LeadAgent initializes with use_sdk parameter."""
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            agent = LeadAgent(project_id=1, db=mock_db, api_key="test-key", use_sdk=True)

            assert agent.use_sdk is True

    def test_init_with_project_root_parameter(self, mock_db, tmp_path):
        """Test LeadAgent initializes with project_root parameter."""
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            agent = LeadAgent(
                project_id=1,
                db=mock_db,
                api_key="test-key",
                project_root=str(tmp_path),
            )

            assert agent._project_root_override == str(tmp_path)

    def test_sdk_sessions_initialized_empty(self, lead_agent):
        """Test _sdk_sessions dict is initialized empty."""
        assert hasattr(lead_agent, "_sdk_sessions")
        assert lead_agent._sdk_sessions == {}

    def test_get_sdk_sessions_returns_empty_dict(self, lead_agent):
        """Test _get_sdk_sessions() returns empty dict when no hybrid agents."""
        result = lead_agent._get_sdk_sessions()

        assert result == {}

    def test_get_sdk_sessions_with_hybrid_agents(self, lead_agent):
        """Test _get_sdk_sessions() returns session IDs from hybrid agents."""
        # Mock agent pool manager to return hybrid agent status
        lead_agent.agent_pool_manager.get_agent_status = Mock(
            return_value={
                "backend-worker-001": {
                    "agent_type": "backend",
                    "status": "idle",
                    "is_hybrid": True,
                    "session_id": "sess-123-abc",
                },
                "frontend-worker-001": {
                    "agent_type": "frontend",
                    "status": "busy",
                    "is_hybrid": True,
                    "session_id": "sess-456-def",
                },
            }
        )

        result = lead_agent._get_sdk_sessions()

        assert len(result) == 2
        assert result["backend-worker-001"] == "sess-123-abc"
        assert result["frontend-worker-001"] == "sess-456-def"

    def test_get_sdk_sessions_excludes_non_hybrid_agents(self, lead_agent):
        """Test _get_sdk_sessions() excludes traditional (non-hybrid) agents."""
        # Mock mix of hybrid and traditional agents
        lead_agent.agent_pool_manager.get_agent_status = Mock(
            return_value={
                "backend-worker-001": {
                    "agent_type": "backend",
                    "status": "idle",
                    "is_hybrid": True,
                    "session_id": "sess-123",
                },
                "frontend-worker-001": {
                    "agent_type": "frontend",
                    "status": "idle",
                    "is_hybrid": False,
                    "session_id": None,
                },
            }
        )

        result = lead_agent._get_sdk_sessions()

        assert len(result) == 1
        assert "backend-worker-001" in result
        assert "frontend-worker-001" not in result

    def test_get_sdk_sessions_excludes_agents_without_session_id(self, lead_agent):
        """Test _get_sdk_sessions() excludes hybrid agents without session_id."""
        # Mock hybrid agent that hasn't started a session yet
        lead_agent.agent_pool_manager.get_agent_status = Mock(
            return_value={
                "backend-worker-001": {
                    "agent_type": "backend",
                    "status": "idle",
                    "is_hybrid": True,
                    "session_id": None,  # No session yet
                },
            }
        )

        result = lead_agent._get_sdk_sessions()

        assert result == {}

    def test_get_sdk_sessions_handles_error(self, lead_agent):
        """Test _get_sdk_sessions() handles errors gracefully."""
        # Mock exception from agent pool manager
        lead_agent.agent_pool_manager.get_agent_status = Mock(side_effect=Exception("Pool error"))

        result = lead_agent._get_sdk_sessions()

        # Should return empty dict, not raise exception
        assert result == {}

    def test_on_session_end_includes_sdk_sessions(self, lead_agent, tmp_path):
        """Test on_session_end() includes sdk_sessions in saved state."""
        # Set up mock session manager with tmp_path
        from codeframe.core.session_manager import SessionManager

        lead_agent.session_manager = SessionManager(str(tmp_path))

        # Mock SDK sessions
        lead_agent.agent_pool_manager.get_agent_status = Mock(
            return_value={
                "backend-worker-001": {
                    "is_hybrid": True,
                    "session_id": "sess-test-123",
                }
            }
        )

        # Save session
        lead_agent.on_session_end()

        # Load and verify SDK sessions saved
        session = lead_agent.session_manager.load_session()
        assert "sdk_sessions" in session
        assert session["sdk_sessions"]["backend-worker-001"] == "sess-test-123"

    def test_agent_pool_manager_created_with_use_sdk(self, mock_db):
        """Test AgentPoolManager is created with use_sdk parameter."""
        with patch("codeframe.agents.lead_agent.AnthropicProvider"):
            with patch("codeframe.agents.lead_agent.AgentPoolManager") as mock_pool_class:
                mock_pool_class.return_value = Mock()

                LeadAgent(
                    project_id=1,
                    db=mock_db,
                    api_key="test-key",
                    use_sdk=True,
                    project_root="/test/path",
                )

                # Verify AgentPoolManager was called with SDK parameters
                mock_pool_class.assert_called_once()
                call_kwargs = mock_pool_class.call_args[1]
                assert call_kwargs["use_sdk"] is True
                assert call_kwargs["cwd"] == "/test/path"
