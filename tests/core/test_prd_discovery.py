"""Tests for AI-native PRD discovery session management.

Tests the headless discovery session that powers `cf prd generate`.
All tests use mocked LLM responses to avoid actual API calls.
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


@pytest.fixture
def mock_llm_provider():
    """Create a mock LLM provider that returns predictable responses."""
    mock = MagicMock()

    # Default responses for different prompt patterns
    def complete_side_effect(messages, purpose=None, system=None, max_tokens=None, temperature=None):
        content = messages[0]["content"] if messages else ""
        response = MagicMock()

        # Opening question
        if "opening question" in content.lower():
            response.content = "What problem are you trying to solve with this project?"
        # Coverage assessment
        elif "assess the current coverage" in content.lower():
            response.content = json.dumps({
                "scores": {
                    "problem": 70,
                    "users": 60,
                    "features": 50,
                    "constraints": 40,
                    "tech_stack": 30
                },
                "average": 50,
                "weakest_category": "tech_stack",
                "ready_for_prd": False,
                "reasoning": "Need more details on tech stack"
            })
        # Answer validation
        elif "evaluate whether this answer" in content.lower():
            response.content = json.dumps({
                "adequate": True,
                "reason": "Answer provides useful information"
            })
        # Next question generation
        elif "generate the next discovery question" in content.lower():
            response.content = "What technologies are you planning to use?"
        # PRD generation
        elif "generate a product requirements document" in content.lower():
            response.content = """# Test Project

## Overview
A test project for unit testing.

## Target Users
Developers and testers.

## Core Features
1. Feature one
2. Feature two

## Technical Requirements
Python, pytest

## Constraints & Considerations
Must be testable.

## Success Criteria
All tests pass.

## Out of Scope (MVP)
Advanced features."""
        else:
            response.content = "Default response"

        response.input_tokens = 100
        response.output_tokens = 50
        return response

    mock.complete.side_effect = complete_side_effect
    return mock


class TestDiscoverySession:
    """Tests for PrdDiscoverySession class."""

    def test_requires_api_key(self, workspace: Workspace):
        """Session should require API key."""
        from codeframe.core.prd_discovery import PrdDiscoverySession, NoApiKeyError

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=True):
            with pytest.raises(NoApiKeyError):
                PrdDiscoverySession(workspace, api_key=None)

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_start_discovery_creates_session(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Starting discovery should create a new session and generate first question."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        assert session.session_id is not None
        assert session.state.value == "discovering"
        assert session.answered_count == 0

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_get_current_question_returns_ai_question(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Current question should be AI-generated."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        question = session.get_current_question()

        assert question is not None
        assert "text" in question
        assert "question_number" in question
        assert question["question_number"] == 1

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_submit_answer_validates_with_ai(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Answer submission should use AI for validation."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        result = session.submit_answer("This solves the problem of task management for teams")

        assert result["accepted"] is True
        assert session.answered_count == 1

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_submit_answer_rejects_inadequate_with_feedback(
        self, mock_provider_class, workspace: Workspace
    ):
        """AI should reject inadequate answers with feedback."""
        mock = MagicMock()

        def complete_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()

            if "opening question" in content.lower():
                response.content = "What problem are you solving?"
            elif "evaluate whether this answer" in content.lower():
                response.content = json.dumps({
                    "adequate": False,
                    "reason": "Answer is too vague",
                    "follow_up": "Can you be more specific about the problem?"
                })
            else:
                response.content = "Default"
            return response

        mock.complete.side_effect = complete_side_effect
        mock_provider_class.return_value = mock

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        result = session.submit_answer("stuff")

        assert result["accepted"] is False
        assert "vague" in result["feedback"].lower()
        assert "follow_up" in result

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_submit_answer_empty_raises_error(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Empty answers should raise ValidationError."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession, ValidationError

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        with pytest.raises(ValidationError):
            session.submit_answer("")

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_is_complete_based_on_ai_assessment(
        self, mock_provider_class, workspace: Workspace
    ):
        """Completion should be determined by AI coverage assessment."""
        mock = MagicMock()
        call_count = [0]

        def complete_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()

            if "opening question" in content.lower():
                response.content = "What problem are you solving?"
            elif "assess the current coverage" in content.lower():
                call_count[0] += 1
                # After 3 answers, mark ready
                if call_count[0] >= 3:
                    response.content = json.dumps({
                        "scores": {"problem": 80, "users": 75, "features": 70, "constraints": 65, "tech_stack": 60},
                        "average": 70,
                        "weakest_category": "tech_stack",
                        "ready_for_prd": True,
                        "reasoning": "Sufficient information gathered"
                    })
                else:
                    response.content = json.dumps({
                        "scores": {"problem": 50, "users": 40, "features": 30, "constraints": 20, "tech_stack": 10},
                        "average": 30,
                        "weakest_category": "tech_stack",
                        "ready_for_prd": False,
                        "reasoning": "Need more information"
                    })
            elif "evaluate whether this answer" in content.lower():
                response.content = json.dumps({"adequate": True, "reason": "Good"})
            elif "generate the next discovery question" in content.lower():
                if call_count[0] >= 3:
                    response.content = "DISCOVERY_COMPLETE"
                else:
                    response.content = "Tell me more about X?"
            else:
                response.content = "Default"
            return response

        mock.complete.side_effect = complete_side_effect
        mock_provider_class.return_value = mock

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()

        # Submit answers until complete
        answers = [
            "This app solves task management for teams",
            "Primary users are project managers",
            "Core features include boards and cards",
        ]

        for answer in answers:
            if not session.is_complete():
                session.submit_answer(answer)

        assert session.is_complete()

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_get_progress_returns_coverage(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Progress should include coverage scores."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()
        session.submit_answer("A valid answer about the project")

        progress = session.get_progress()

        assert "answered" in progress
        assert "coverage" in progress
        assert "percentage" in progress

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_pause_discovery_creates_blocker(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Pausing should create a blocker for resume."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core import blockers

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()
        session.submit_answer("A valid answer")

        blocker_id = session.pause_discovery("Need to check with team")

        assert blocker_id is not None
        assert session.state.value == "paused"

        # Verify blocker was created
        blocker = blockers.get(workspace, blocker_id)
        assert blocker is not None
        assert "discovery" in blocker.question.lower()

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_resume_discovery_from_blocker(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Resuming should restore previous session state."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core import blockers

        # Start and pause
        session1 = PrdDiscoverySession(workspace, api_key="test-key")
        session1.start_discovery()
        session1.submit_answer("A valid answer")
        blocker_id = session1.pause_discovery("Need to check")

        # Answer the blocker
        blockers.answer(workspace, blocker_id, "Checked, proceed")

        # Resume
        session2 = PrdDiscoverySession(workspace, api_key="test-key")
        session2.resume_discovery(blocker_id)

        assert session2.state.value == "discovering"
        assert session2.answered_count == 1


class TestPrdGeneration:
    """Tests for PRD generation from discovery."""

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_generate_prd_from_complete_session(
        self, mock_provider_class, workspace: Workspace
    ):
        """Complete session should generate valid PRD."""
        mock = MagicMock()
        call_count = [0]

        def complete_side_effect(messages, **kwargs):
            content = messages[0]["content"] if messages else ""
            response = MagicMock()

            if "opening question" in content.lower():
                response.content = "What problem are you solving?"
            elif "assess the current coverage" in content.lower():
                call_count[0] += 1
                response.content = json.dumps({
                    "scores": {"problem": 80, "users": 75, "features": 70, "constraints": 65, "tech_stack": 60},
                    "average": 70,
                    "ready_for_prd": True,
                    "weakest_category": "tech_stack",
                    "reasoning": "Ready"
                })
            elif "evaluate whether this answer" in content.lower():
                response.content = json.dumps({"adequate": True, "reason": "Good"})
            elif "generate the next discovery question" in content.lower():
                response.content = "DISCOVERY_COMPLETE"
            elif "generate a product requirements document" in content.lower():
                response.content = """# Task Management App

## Overview
A task management app for development teams.

## Target Users
Developers and project managers.

## Core Features
1. Task boards
2. Time tracking

## Technical Requirements
Python FastAPI, React

## Constraints & Considerations
Must be self-hosted.

## Success Criteria
Users can manage tasks effectively.

## Out of Scope (MVP)
Mobile app."""
            else:
                response.content = "Default"
            return response

        mock.complete.side_effect = complete_side_effect
        mock_provider_class.return_value = mock

        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core import prd

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()
        session.submit_answer("A task management app for teams")

        prd_record = session.generate_prd()

        assert prd_record is not None
        assert prd_record.title is not None
        assert "Overview" in prd_record.content
        assert prd_record.workspace_id == workspace.id

        # Verify stored in database
        stored = prd.get_by_id(workspace, prd_record.id)
        assert stored is not None

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_generate_prd_fails_when_incomplete(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Generating PRD before completion should raise error."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession, IncompleteSessionError

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()
        session.submit_answer("Only one answer")

        with pytest.raises(IncompleteSessionError):
            session.generate_prd()


class TestDiscoveryPersistence:
    """Tests for discovery session database operations."""

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_session_saved_to_database(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Session should be persisted to workspace database."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core.workspace import get_db_connection

        session = PrdDiscoverySession(workspace, api_key="test-key")
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

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_qa_history_stored_as_json(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Q&A history should be stored as JSON in session record."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core.workspace import get_db_connection

        session = PrdDiscoverySession(workspace, api_key="test-key")
        session.start_discovery()
        session.submit_answer("First answer about the problem")
        session.submit_answer("Second answer about the users")

        conn = get_db_connection(workspace)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT qa_history FROM discovery_sessions WHERE id = ?",
            (session.session_id,)
        )
        row = cursor.fetchone()
        conn.close()

        qa_history = json.loads(row[0])
        assert len(qa_history) == 2

    @patch("codeframe.core.prd_discovery.AnthropicProvider")
    def test_session_state_transitions(
        self, mock_provider_class, workspace: Workspace, mock_llm_provider
    ):
        """Session state should transition correctly."""
        mock_provider_class.return_value = mock_llm_provider

        from codeframe.core.prd_discovery import PrdDiscoverySession

        session = PrdDiscoverySession(workspace, api_key="test-key")

        session.start_discovery()
        assert session.state.value == "discovering"

        session.pause_discovery("test pause")
        assert session.state.value == "paused"
