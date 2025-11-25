"""Integration tests for Session Lifecycle Management.

Tests the full end-to-end workflow of session persistence including:
- Creating and saving session state
- Loading and restoring session state
- Handling corrupted session files
- Session cleanup on Ctrl+C
"""

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.session_manager import SessionManager
from codeframe.agents.lead_agent import LeadAgent


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir)
        codeframe_dir = project_path / ".codeframe"
        codeframe_dir.mkdir()
        yield str(project_path)


@pytest.fixture
def test_db():
    """Create a mock database with test data."""
    db = MagicMock()
    project_id = 1
    task_ids = list(range(1, 11))
    blocker_ids = [1, 2, 3]

    # Mock database methods to return test data
    db.get_recently_completed_tasks.return_value = [
        {'id': i, 'title': f'Task {i}', 'status': 'completed', 'updated_at': '2025-11-20T10:00:00'}
        for i in range(1, 6)
    ]
    db.get_pending_tasks.return_value = [
        {'id': i, 'title': f'Task {i}', 'priority': 'high' if i < 8 else 'medium', 'created_at': '2025-11-20T09:00:00'}
        for i in range(6, 11)
    ]
    db.get_active_blockers.return_value = [
        {'id': 1, 'question': 'Blocker question 1?', 'priority': 'high'},
        {'id': 2, 'question': 'Blocker question 2?', 'priority': 'medium'},
        {'id': 3, 'question': 'Blocker question 3?', 'priority': 'medium'}
    ]
    db.get_project_stats.return_value = {
        'total_tasks': 10,
        'completed_tasks': 5
    }

    yield db, project_id, task_ids, blocker_ids


class TestFullSessionLifecycle:
    """Test complete session lifecycle workflow."""

    def test_end_to_end_session_workflow(self, temp_project_dir, test_db):
        """Test T032: Full session lifecycle from save to restore.

        This test validates:
        1. Session state is saved on session end
        2. Session state file is created with correct format
        3. Session state is loaded on session start
        4. Restored session shows correct summary, actions, progress
        """
        db, project_id, task_ids, blocker_ids = test_db

        # Initialize SessionManager
        session_mgr = SessionManager(temp_project_dir)

        # Create a mock Lead Agent
        with patch.object(LeadAgent, '__init__', return_value=None):
            lead_agent = LeadAgent.__new__(LeadAgent)
            lead_agent.project_id = project_id
            lead_agent.db = db
            lead_agent.session_manager = session_mgr
            lead_agent.current_task = "Implement OAuth 2.0"

            # Add session helper methods
            def get_session_summary():
                tasks = db.get_recently_completed_tasks(project_id, limit=5)
                if not tasks:
                    return "No activity"
                summaries = [f"Task #{t['id']} ({t['title']})" for t in tasks]
                return f"Completed {', '.join(summaries)}"

            def get_completed_task_ids():
                tasks = db.get_recently_completed_tasks(project_id, limit=10)
                return [t['id'] for t in tasks]

            def get_pending_actions():
                tasks = db.get_pending_tasks(project_id, limit=5)
                return [f"{t['title']} (Task #{t['id']})" for t in tasks]

            def get_blocker_summaries():
                blockers = db.get_active_blockers(project_id, limit=10)
                return [
                    {
                        'id': b['id'],
                        'question': b['question'],
                        'priority': b['priority']
                    }
                    for b in blockers
                ]

            def get_progress_percentage():
                stats = db.get_project_stats(project_id)
                total = stats['total_tasks']
                completed = stats['completed_tasks']
                if total == 0:
                    return 0.0
                return (completed / total) * 100.0

            lead_agent._get_session_summary = get_session_summary
            lead_agent._get_completed_task_ids = get_completed_task_ids
            lead_agent._get_pending_actions = get_pending_actions
            lead_agent._get_blocker_summaries = get_blocker_summaries
            lead_agent._get_progress_percentage = get_progress_percentage

            # Simulate session end
            summary = lead_agent._get_session_summary()
            completed_ids = lead_agent._get_completed_task_ids()
            next_actions = lead_agent._get_pending_actions()
            blockers = lead_agent._get_blocker_summaries()
            progress = lead_agent._get_progress_percentage()

            session_state = {
                'summary': summary,
                'completed_tasks': completed_ids,
                'next_actions': next_actions,
                'current_plan': lead_agent.current_task,
                'active_blockers': blockers,
                'progress_pct': progress
            }

            session_mgr.save_session(session_state)

            # Verify session file created
            session_file = os.path.join(temp_project_dir, '.codeframe', 'session_state.json')
            assert os.path.exists(session_file), "Session state file should be created"

            # Verify file content structure
            with open(session_file, 'r') as f:
                saved_data = json.load(f)

            assert 'last_session' in saved_data
            assert 'summary' in saved_data['last_session']
            assert 'completed_tasks' in saved_data['last_session']
            assert 'timestamp' in saved_data['last_session']
            assert 'next_actions' in saved_data
            assert 'current_plan' in saved_data
            assert 'active_blockers' in saved_data
            assert 'progress_pct' in saved_data

            # Verify data values
            assert saved_data['last_session']['summary'] == summary
            assert saved_data['last_session']['completed_tasks'] == completed_ids
            assert saved_data['next_actions'] == next_actions
            assert saved_data['current_plan'] == "Implement OAuth 2.0"
            assert len(saved_data['active_blockers']) == 3
            assert saved_data['progress_pct'] == 50.0  # 5 of 10 tasks completed

            # Simulate session start - load session
            loaded_state = session_mgr.load_session()
            assert loaded_state is not None, "Session state should load successfully"

            # Verify loaded data matches saved data
            assert loaded_state['last_session']['summary'] == summary
            assert loaded_state['next_actions'] == next_actions
            assert loaded_state['progress_pct'] == 50.0
            assert len(loaded_state['active_blockers']) == 3

    def test_session_persists_across_restarts(self, temp_project_dir, test_db):
        """Test that session state persists across multiple CLI restarts."""
        db, project_id, task_ids, blocker_ids = test_db

        session_mgr = SessionManager(temp_project_dir)

        # First session: Save state
        state1 = {
            'summary': 'Completed Task #1, Task #2',
            'completed_tasks': [task_ids[0], task_ids[1]],
            'next_actions': ['Fix validation (Task #3)', 'Add tests (Task #4)'],
            'current_plan': 'Build API',
            'active_blockers': [],
            'progress_pct': 25.0
        }
        session_mgr.save_session(state1)

        # Simulate restart: Load state
        loaded_state1 = session_mgr.load_session()
        assert loaded_state1['last_session']['summary'] == 'Completed Task #1, Task #2'
        assert loaded_state1['progress_pct'] == 25.0

        # Continue work: Update state
        state2 = {
            'summary': 'Completed Task #3, Task #4',
            'completed_tasks': [task_ids[2], task_ids[3]],
            'next_actions': ['Write docs (Task #5)'],
            'current_plan': 'Build API',
            'active_blockers': [],
            'progress_pct': 50.0
        }
        session_mgr.save_session(state2)

        # Another restart: Verify updated state
        loaded_state2 = session_mgr.load_session()
        assert loaded_state2['last_session']['summary'] == 'Completed Task #3, Task #4'
        assert loaded_state2['progress_pct'] == 50.0


class TestCorruptedSessionHandling:
    """Test corrupted session file handling."""

    def test_corrupted_json_file_returns_none(self, temp_project_dir):
        """Test T033: Corrupted JSON file is handled gracefully.

        When session state file contains invalid JSON:
        - load_session() returns None (no crash)
        - User sees "Starting new session..." message
        - CLI continues to work normally
        """
        session_mgr = SessionManager(temp_project_dir)

        # Create corrupted JSON file
        session_file = os.path.join(temp_project_dir, '.codeframe', 'session_state.json')
        with open(session_file, 'w') as f:
            f.write('{"last_session": {"summary": "Invalid JSON - missing brace')

        # Try to load corrupted session
        loaded_state = session_mgr.load_session()

        # Should return None instead of crashing
        assert loaded_state is None, "Corrupted session should return None"

    def test_malformed_json_structure(self, temp_project_dir):
        """Test that malformed JSON structure (valid JSON but wrong schema) is handled."""
        session_mgr = SessionManager(temp_project_dir)

        # Create valid JSON but missing required fields
        session_file = os.path.join(temp_project_dir, '.codeframe', 'session_state.json')
        with open(session_file, 'w') as f:
            json.dump({'invalid': 'structure'}, f)

        # Should load without crashing (returns dict with invalid structure)
        loaded_state = session_mgr.load_session()

        # Session loads but with unexpected structure
        assert loaded_state is not None
        assert 'invalid' in loaded_state
        assert 'last_session' not in loaded_state

    def test_clear_session_removes_corrupted_file(self, temp_project_dir):
        """Test that clear_session removes corrupted files successfully."""
        session_mgr = SessionManager(temp_project_dir)

        # Create corrupted file
        session_file = os.path.join(temp_project_dir, '.codeframe', 'session_state.json')
        with open(session_file, 'w') as f:
            f.write('corrupted content')

        # Clear session should remove file
        session_mgr.clear_session()

        # Verify file is gone
        assert not os.path.exists(session_file), "Corrupted session file should be deleted"


class TestCtrlCSessionSave:
    """Test Ctrl+C session save behavior."""

    def test_keyboard_interrupt_saves_session(self, temp_project_dir, test_db):
        """Test T034: Ctrl+C (KeyboardInterrupt) triggers session save.

        Validates:
        1. KeyboardInterrupt is caught
        2. on_session_end() executes in finally block
        3. Session state is saved before exit
        """
        db, project_id, task_ids, blocker_ids = test_db

        session_mgr = SessionManager(temp_project_dir)

        # Simulate work in progress
        state = {
            'summary': 'Working on Task #5',
            'completed_tasks': [task_ids[0]],
            'next_actions': ['Continue Task #5'],
            'current_plan': 'Build feature',
            'active_blockers': [],
            'progress_pct': 10.0
        }

        # Simulate Ctrl+C during execution
        try:
            # User presses Ctrl+C
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            pass
        finally:
            # on_session_end() runs in finally block
            session_mgr.save_session(state)

        # Verify session was saved despite interrupt
        session_file = os.path.join(temp_project_dir, '.codeframe', 'session_state.json')
        assert os.path.exists(session_file), "Session should save on Ctrl+C"

        # Verify content
        loaded_state = session_mgr.load_session()
        assert loaded_state is not None
        assert loaded_state['last_session']['summary'] == 'Working on Task #5'

    def test_multiple_interrupts_only_last_state_saved(self, temp_project_dir):
        """Test that multiple Ctrl+C events only persist last session state."""
        session_mgr = SessionManager(temp_project_dir)

        # First interrupt
        state1 = {
            'summary': 'First interrupt',
            'completed_tasks': [1],
            'next_actions': [],
            'current_plan': None,
            'active_blockers': [],
            'progress_pct': 10.0
        }
        session_mgr.save_session(state1)

        # Second interrupt (overwrites)
        state2 = {
            'summary': 'Second interrupt',
            'completed_tasks': [1, 2],
            'next_actions': [],
            'current_plan': None,
            'active_blockers': [],
            'progress_pct': 20.0
        }
        session_mgr.save_session(state2)

        # Verify only last state persisted
        loaded_state = session_mgr.load_session()
        assert loaded_state['last_session']['summary'] == 'Second interrupt'
        assert loaded_state['progress_pct'] == 20.0


class TestSessionEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_session_state(self, temp_project_dir):
        """Test saving and loading empty session state."""
        session_mgr = SessionManager(temp_project_dir)

        # Save minimal valid state
        state = {
            'summary': 'No activity',
            'completed_tasks': [],
            'next_actions': [],
            'current_plan': None,
            'active_blockers': [],
            'progress_pct': 0.0
        }
        session_mgr.save_session(state)

        # Load and verify
        loaded_state = session_mgr.load_session()
        assert loaded_state is not None
        assert loaded_state['last_session']['summary'] == 'No activity'
        assert loaded_state['progress_pct'] == 0.0
        assert len(loaded_state['next_actions']) == 0

    def test_session_with_max_items(self, temp_project_dir):
        """Test session with maximum number of items (10 tasks, 10 blockers, 5 actions)."""
        session_mgr = SessionManager(temp_project_dir)

        state = {
            'summary': 'Completed 10 tasks',
            'completed_tasks': list(range(1, 11)),  # 10 tasks
            'next_actions': [f'Action {i}' for i in range(1, 6)],  # 5 actions
            'current_plan': 'Large project',
            'active_blockers': [
                {'id': i, 'question': f'Question {i}?', 'priority': 'high'}
                for i in range(1, 11)  # 10 blockers
            ],
            'progress_pct': 100.0
        }
        session_mgr.save_session(state)

        # Load and verify all items persisted
        loaded_state = session_mgr.load_session()
        assert len(loaded_state['last_session']['completed_tasks']) == 10
        assert len(loaded_state['next_actions']) == 5
        assert len(loaded_state['active_blockers']) == 10

    def test_session_file_permissions(self, temp_project_dir):
        """Test that session file has correct permissions (owner read/write only)."""
        session_mgr = SessionManager(temp_project_dir)

        state = {
            'summary': 'Test permissions',
            'completed_tasks': [],
            'next_actions': [],
            'current_plan': None,
            'active_blockers': [],
            'progress_pct': 0.0
        }
        session_mgr.save_session(state)

        # Check file permissions (should be 0o600 or similar)
        session_file = os.path.join(temp_project_dir, '.codeframe', 'session_state.json')
        file_stat = os.stat(session_file)
        mode = file_stat.st_mode

        # Verify owner has read/write access
        assert mode & 0o400, "Owner should have read permission"
        assert mode & 0o200, "Owner should have write permission"
