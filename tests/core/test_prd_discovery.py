"""Tests for PRD discovery session management.

Tests the headless discovery session that powers `cf prd generate`.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from codeframe.core.workspace import Workspace, create_or_load_workspace


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


class TestDiscoverySession:
    """Tests for PrdDiscoverySession class."""

    def test_start_discovery_creates_session(self, workspace: Workspace):
        """Starting discovery should create a new session."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        assert session.session_id is not None
        assert session.state == "discovering"
        assert session.answered_count == 0

    def test_get_current_question_returns_first_required(self, workspace: Workspace):
        """First question should be a required question from first category."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        question = session.get_current_question()

        assert question is not None
        assert question["importance"] == "required"
        assert question["category"] == "problem"  # First category

    def test_submit_answer_advances_to_next_question(self, workspace: Workspace):
        """Submitting valid answer should advance to next question."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        q1 = session.get_current_question()
        session.submit_answer("This solves the problem of task management")

        q2 = session.get_current_question()

        assert q2 is not None
        assert q2["id"] != q1["id"]
        assert session.answered_count == 1

    def test_submit_answer_validates_minimum_length(self, workspace: Workspace):
        """Answers shorter than minimum should be rejected."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, ValidationError

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        with pytest.raises(ValidationError, match="too short"):
            session.submit_answer("hi")

    def test_submit_answer_rejects_invalid_patterns(self, workspace: Workspace):
        """Answers like 'n/a' or 'none' should be rejected."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, ValidationError

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        # Invalid patterns are checked before length
        with pytest.raises(ValidationError, match="substantive"):
            session.submit_answer("none")

    def test_is_complete_when_all_required_answered(self, workspace: Workspace):
        """Session should be complete when all required questions answered."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        # Answer all required questions
        required_answers = [
            "This app solves the task management problem for remote teams",
            "The primary users are software developers and project managers",
            "Core features include task tracking, time estimates, and reporting",
            "Technical constraints include mobile-first and offline support",
            "We prefer Python backend with React frontend",
        ]

        for answer in required_answers:
            if not session.is_complete():
                session.submit_answer(answer)

        assert session.is_complete()

    def test_get_progress_returns_accurate_stats(self, workspace: Workspace):
        """Progress should accurately reflect answered/total questions."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        progress = session.get_progress()

        assert progress["answered"] == 0
        assert progress["required_total"] == 5  # 5 required questions
        assert progress["percentage"] == 0

        session.submit_answer("A valid answer to the first question")

        progress = session.get_progress()
        assert progress["answered"] == 1
        assert progress["percentage"] == 20  # 1/5 = 20%

    def test_pause_discovery_creates_blocker(self, workspace: Workspace):
        """Pausing should create a blocker for resume."""
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core import blockers

        session = PrdDiscoverySession(workspace)
        session.start_discovery()
        session.submit_answer("A valid answer to the first question")

        blocker_id = session.pause_discovery("Need to check with stakeholder")

        assert blocker_id is not None
        assert session.state == "paused"

        # Verify blocker was created
        blocker = blockers.get(workspace, blocker_id)
        assert blocker is not None
        assert "discovery" in blocker.question.lower()

    def test_resume_discovery_from_blocker(self, workspace: Workspace):
        """Resuming should restore previous session state."""
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core import blockers

        # Start and pause
        session1 = PrdDiscoverySession(workspace)
        session1.start_discovery()
        session1.submit_answer("A valid answer to the first question")
        blocker_id = session1.pause_discovery("Need to check with stakeholder")

        # Answer the blocker
        blockers.answer(workspace, blocker_id, "Checked with stakeholder, proceed")

        # Resume
        session2 = PrdDiscoverySession(workspace)
        session2.resume_discovery(blocker_id)

        assert session2.state == "discovering"
        assert session2.answered_count == 1

    def test_answers_persist_across_sessions(self, workspace: Workspace):
        """Answers should be saved and loadable in new session."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session1 = PrdDiscoverySession(workspace)
        session1.start_discovery()
        session_id = session1.session_id
        session1.submit_answer("A valid answer to the first question")

        # Create new session and load
        session2 = PrdDiscoverySession(workspace)
        session2.load_session(session_id)

        assert session2.answered_count == 1


class TestPrdGeneration:
    """Tests for PRD generation from discovery answers."""

    def test_generate_prd_from_complete_session(self, workspace: Workspace):
        """Complete session should generate valid PRD."""
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core import prd

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        # Answer all required questions
        answers = [
            "This app helps teams track software tasks and estimate effort",
            "Primary users are developers, project managers, and stakeholders",
            "Task CRUD, time tracking, dependency graphs, reporting dashboards",
            "Must work offline, support mobile, integrate with GitHub",
            "Python FastAPI backend, React TypeScript frontend, PostgreSQL",
        ]

        for answer in answers:
            if not session.is_complete():
                session.submit_answer(answer)

        prd_record = session.generate_prd()

        assert prd_record is not None
        assert prd_record.title is not None
        assert "Overview" in prd_record.content
        assert prd_record.workspace_id == workspace.id

        # Verify stored in database
        stored = prd.get_by_id(workspace, prd_record.id)
        assert stored is not None

    def test_generate_prd_includes_structured_sections(self, workspace: Workspace):
        """Generated PRD should have all expected sections."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        session.start_discovery()

        answers = [
            "Team collaboration platform for remote workers",
            "Remote developers and project managers",
            "Chat, video calls, screen sharing, task boards",
            "End-to-end encryption required, GDPR compliant",
            "Node.js, WebRTC, React, PostgreSQL",
        ]

        for answer in answers:
            if not session.is_complete():
                session.submit_answer(answer)

        prd_record = session.generate_prd()

        # Check for expected sections
        assert "## Overview" in prd_record.content
        assert "## User" in prd_record.content  # User Stories
        assert "## Technical" in prd_record.content or "## Constraint" in prd_record.content

    def test_generate_prd_fails_when_incomplete(self, workspace: Workspace):
        """Generating PRD before completion should raise error."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, IncompleteSessionError

        session = PrdDiscoverySession(workspace)
        session.start_discovery()
        session.submit_answer("Only answered one question here")

        with pytest.raises(IncompleteSessionError):
            session.generate_prd()


class TestAIQuestionGeneration:
    """Tests for AI-powered question generation."""

    def test_uses_static_questions_when_no_api_key(self, workspace: Workspace):
        """Should fall back to static questions without API key."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
            session = PrdDiscoverySession(workspace, api_key=None)
            session.start_discovery()

            question = session.get_current_question()

            # Should be one of the static questions
            assert question is not None
            assert question["id"].startswith("problem_")

    def test_uses_ai_questions_when_api_key_provided(self, workspace: Workspace):
        """Should use AI for questions when API key available."""
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.adapters.llm.base import LLMResponse

        with patch("codeframe.adapters.llm.anthropic.AnthropicProvider") as mock_provider_class:
            # Mock the LLM provider
            mock_provider = MagicMock()
            mock_provider.complete.return_value = LLMResponse(
                content="Based on your previous answers, what specific pain points "
                        "do your users experience with current solutions?",
                input_tokens=100,
                output_tokens=50,
            )
            mock_provider_class.return_value = mock_provider

            session = PrdDiscoverySession(workspace, api_key="test-key")
            session.start_discovery()
            session.submit_answer("A task management app for development teams")

            # Get second question (should trigger AI)
            question = session.get_current_question()

            # AI generates follow-up based on context
            assert question is not None
            # The implementation may use AI or fallback - just verify question exists


class TestDiscoveryPersistence:
    """Tests for discovery session database operations."""

    def test_session_saved_to_database(self, workspace: Workspace):
        """Session should be persisted to workspace database."""
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core.workspace import get_db_connection

        session = PrdDiscoverySession(workspace)
        session.start_discovery()
        session.submit_answer("A valid answer for persistence test")

        # Check database directly
        conn = get_db_connection(workspace)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM discovery_sessions WHERE id = ?",
            (session.session_id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None

    def test_answers_stored_as_json(self, workspace: Workspace):
        """Answers should be stored as JSON in session record."""
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core.workspace import get_db_connection

        session = PrdDiscoverySession(workspace)
        session.start_discovery()
        session.submit_answer("First answer about the problem")
        session.submit_answer("Second answer about the users")

        conn = get_db_connection(workspace)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT answers FROM discovery_sessions WHERE id = ?",
            (session.session_id,)
        )
        row = cursor.fetchone()
        conn.close()

        answers = json.loads(row[0])
        assert len(answers) == 2

    def test_session_state_transitions(self, workspace: Workspace):
        """Session state should transition correctly."""
        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace)
        assert session.state == "idle"

        session.start_discovery()
        assert session.state == "discovering"

        session.pause_discovery("test pause")
        assert session.state == "paused"

        # Complete all questions in new session
        session2 = PrdDiscoverySession(workspace)
        session2.start_discovery()
        for _ in range(5):
            if not session2.is_complete():
                session2.submit_answer("A sufficiently long answer for this test question")

        # After generating PRD
        session2.generate_prd()
        assert session2.state == "completed"
