"""Integration tests for Discovery Question Framework with Lead Agent.

Following TDD: These tests are written FIRST before integration implementation.
Tests verify the complete discovery flow from start to completion.
Target: 10-12 tests, 100% pass rate after implementation.
"""

import pytest
from unittest.mock import Mock, patch
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.discovery.questions import DiscoveryQuestionFramework


@pytest.mark.integration
class TestDiscoveryFlowInitialization:
    """Test discovery flow initialization."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_start_discovery_initializes_discovery_state(self, mock_provider_class, temp_db_path):
        """Test that start_discovery() initializes discovery state to 'discovering'."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        agent.start_discovery()

        # ASSERT
        status = agent.get_discovery_status()
        assert status["state"] == "discovering"
        assert "current_question" in status
        assert status["current_question"] is not None

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_start_discovery_asks_first_question(self, mock_provider_class, temp_db_path):
        """Test that start_discovery() returns the first question."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        response = agent.start_discovery()

        # ASSERT
        assert "problem" in response.lower() or "what" in response.lower()
        # Verify it's the first required question
        status = agent.get_discovery_status()
        assert status["current_question"]["id"] == "problem_1"
        assert status["current_question"]["importance"] == "required"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_state_persists_in_database(self, mock_provider_class, temp_db_path):
        """Test that discovery state is saved to database."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        agent.start_discovery()

        # Verify persistence by checking database directly
        all_memories = db.get_project_memories(project_id)
        discovery_state = [m for m in all_memories if m["category"] == "discovery_state"]

        # ASSERT
        assert len(discovery_state) > 0
        state_entry = next((m for m in discovery_state if m["key"] == "state"), None)
        assert state_entry is not None
        assert state_entry["value"] == "discovering"


@pytest.mark.integration
class TestDiscoveryStateTransitions:
    """Test discovery state machine transitions."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_transitions_from_idle_to_discovering(
        self, mock_provider_class, temp_db_path
    ):
        """Test state transition from idle to discovering."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # Verify initial state is idle
        initial_status = agent.get_discovery_status()
        assert initial_status["state"] == "idle"

        # ACT
        agent.start_discovery()

        # ASSERT
        final_status = agent.get_discovery_status()
        assert final_status["state"] == "discovering"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_stays_in_discovering_while_questions_remain(
        self, mock_provider_class, temp_db_path
    ):
        """Test state stays in 'discovering' while questions remain."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # ACT - Answer first question
        agent.process_discovery_answer("This app helps developers track code quality")

        # ASSERT
        status = agent.get_discovery_status()
        assert status["state"] == "discovering"
        assert status["answered_count"] == 1
        assert status["remaining_count"] > 0

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_transitions_to_completed_when_all_required_answered(
        self, mock_provider_class, temp_db_path
    ):
        """Test state transitions to 'completed' when all required questions answered."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Get list of required questions
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()
        required_questions = [q for q in questions if q["importance"] == "required"]

        # ACT - Answer all required questions
        for i, question in enumerate(required_questions):
            agent.process_discovery_answer(f"Valid answer number {i + 1} with enough content")

        # ASSERT
        status = agent.get_discovery_status()
        assert status["state"] == "completed"
        assert status["answered_count"] >= len(required_questions)


@pytest.mark.integration
class TestDiscoveryAnswerProcessing:
    """Test discovery answer processing and progression."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_process_discovery_answer_saves_answer(self, mock_provider_class, temp_db_path):
        """Test that process_discovery_answer() saves the answer."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # ACT
        answer = "This application helps developers track code quality metrics"
        agent.process_discovery_answer(answer)

        # ASSERT
        status = agent.get_discovery_status()
        assert "problem_1" in status["answers"]
        assert status["answers"]["problem_1"] == answer

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_process_discovery_answer_asks_next_question(self, mock_provider_class, temp_db_path):
        """Test that processing an answer automatically asks the next question."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        first_question_id = agent.get_discovery_status()["current_question"]["id"]

        # ACT
        response = agent.process_discovery_answer("This app helps developers")

        # ASSERT
        status = agent.get_discovery_status()
        # Current question should have advanced
        assert status["current_question"]["id"] != first_question_id
        # Response should contain next question
        assert len(response) > 0

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_process_discovery_answer_updates_progress(self, mock_provider_class, temp_db_path):
        """Test that processing answers updates progress tracking."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        initial_status = agent.get_discovery_status()
        initial_answered = initial_status["answered_count"]

        # ACT
        agent.process_discovery_answer("Valid answer with enough content")

        # ASSERT
        final_status = agent.get_discovery_status()
        assert final_status["answered_count"] == initial_answered + 1


@pytest.mark.integration
class TestDiscoveryDatabasePersistence:
    """Test database persistence of discovery data."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_answers_persist_in_database(self, mock_provider_class, temp_db_path):
        """Test that answers are stored in database."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # ACT
        agent.process_discovery_answer("Answer to problem question")

        # Verify database persistence
        all_memories = db.get_project_memories(project_id)
        discovery_answers = [m for m in all_memories if m["category"] == "discovery_answers"]

        # ASSERT
        assert len(discovery_answers) > 0
        assert any("problem_1" in answer["key"] for answer in discovery_answers)

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_state_reloads_on_agent_restart(self, mock_provider_class, temp_db_path):
        """Test that discovery state persists across agent restarts."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        # First agent instance
        agent_1 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent_1.start_discovery()
        agent_1.process_discovery_answer("First answer with content")

        status_before = agent_1.get_discovery_status()

        # ACT - Create new agent instance (simulating restart)
        agent_2 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        status_after = agent_2.get_discovery_status()

        # ASSERT
        assert status_after["state"] == status_before["state"]
        assert status_after["answered_count"] == status_before["answered_count"]
        assert "problem_1" in status_after["answers"]


@pytest.mark.integration
class TestDiscoveryCompletionDetection:
    """Test discovery completion detection."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_returns_completion_state(self, mock_provider_class, temp_db_path):
        """Test that get_discovery_status() accurately reports completion."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # Before discovery
        status_idle = agent.get_discovery_status()
        assert status_idle["state"] == "idle"

        # During discovery
        agent.start_discovery()
        agent.process_discovery_answer("Valid answer")
        status_discovering = agent.get_discovery_status()
        assert status_discovering["state"] == "discovering"

        # After all required questions
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()
        required_questions = [q for q in questions if q["importance"] == "required"]

        # Answer remaining required questions
        for i in range(len(required_questions) - 1):
            agent.process_discovery_answer(f"Valid answer {i + 2}")

        # ACT
        status_complete = agent.get_discovery_status()

        # ASSERT
        assert status_complete["state"] == "completed"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_includes_structured_data(self, mock_provider_class, temp_db_path):
        """Test that completed discovery includes structured data."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Answer all required questions with realistic data
        agent.process_discovery_answer("Track code quality metrics for developers")
        agent.process_discovery_answer("Primary users are software developers and team leads")
        agent.process_discovery_answer("Login, dashboard, reporting")
        agent.process_discovery_answer("Must use PostgreSQL and Python")
        agent.process_discovery_answer("Python and React")

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert status["state"] == "completed"
        assert "structured_data" in status
        structured = status["structured_data"]
        assert "features" in structured
        assert "users" in structured
        assert "constraints" in structured


@pytest.mark.integration
class TestDiscoveryProgressIndicators:
    """Test discovery progress percentage and total_required fields (cf-17.2)."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_includes_progress_percentage_at_0_percent(
        self, mock_provider_class, temp_db_path
    ):
        """Test progress_percentage is 0% when discovery just started."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert "progress_percentage" in status
        assert status["progress_percentage"] == 0.0
        assert status["answered_count"] == 0

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_includes_progress_percentage_at_60_percent(
        self, mock_provider_class, temp_db_path
    ):
        """Test progress_percentage is 60% when 3 of 5 required questions answered."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Answer 3 questions
        agent.process_discovery_answer("Answer 1 with sufficient content")
        agent.process_discovery_answer("Answer 2 with sufficient content")
        agent.process_discovery_answer("Answer 3 with sufficient content")

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert "progress_percentage" in status
        assert status["progress_percentage"] == 60.0  # 3/5 * 100
        assert status["answered_count"] == 3

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_includes_progress_percentage_at_100_percent(
        self, mock_provider_class, temp_db_path
    ):
        """Test progress_percentage is 100% when all required questions answered."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Answer all 5 required questions
        for i in range(5):
            agent.process_discovery_answer(f"Answer {i + 1} with sufficient content")

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert "progress_percentage" in status
        assert status["progress_percentage"] == 100.0  # 5/5 * 100
        assert status["answered_count"] == 5
        assert status["state"] == "completed"

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_includes_total_required_count(
        self, mock_provider_class, temp_db_path
    ):
        """Test total_required field is included in status."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert "total_required" in status
        assert status["total_required"] == 5  # Framework has 5 required questions

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_handles_idle_state_progress(
        self, mock_provider_class, temp_db_path
    ):
        """Test progress indicators in idle state (before discovery started)."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert status["state"] == "idle"
        assert "progress_percentage" not in status  # No progress in idle state
        assert "total_required" not in status  # No total_required in idle state

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_get_discovery_status_handles_completed_state_progress(
        self, mock_provider_class, temp_db_path
    ):
        """Test progress indicators show 100% in completed state."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Complete discovery
        for i in range(5):
            agent.process_discovery_answer(f"Answer {i + 1} with sufficient content")

        # ACT
        status = agent.get_discovery_status()

        # ASSERT
        assert status["state"] == "completed"
        assert status["progress_percentage"] == 100.0
        assert status["total_required"] == 5


@pytest.mark.integration
class TestDiscoveryEndToEndFlow:
    """Test complete end-to-end discovery flow."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_complete_discovery_flow(self, mock_provider_class, temp_db_path):
        """Test complete discovery flow from start to completion."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "Next question...",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")

        # ACT - Complete discovery flow
        # 1. Start discovery
        agent.start_discovery()
        assert agent.get_discovery_status()["state"] == "discovering"

        # 2. Answer all required questions
        answers = [
            "Track code quality metrics and identify technical debt",
            "Software developers and engineering managers",
            "Login, code analysis dashboard, automated reporting",
            "Must be cloud-native and support PostgreSQL",
            "Python backend with React frontend",
        ]

        for answer in answers:
            agent.process_discovery_answer(answer)

        # 3. Verify completion
        final_status = agent.get_discovery_status()

        # ASSERT
        assert final_status["state"] == "completed"
        assert final_status["answered_count"] >= 5
        assert len(final_status["answers"]) >= 5
        assert "structured_data" in final_status

        # Verify structured data extraction
        structured = final_status["structured_data"]
        assert len(structured["features"]) > 0
        assert len(structured["users"]) > 0
        assert len(structured["constraints"]) > 0

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_discovery_flow_with_chat_integration(self, mock_provider_class, temp_db_path):
        """Test discovery flow integrates with regular chat after completion."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider.send_message.return_value = {
            "content": "I understand. Let me help you with that.",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 8},
        }
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Answer all required questions
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()
        required_questions = [q for q in questions if q["importance"] == "required"]

        for _ in required_questions:
            agent.process_discovery_answer("Valid answer with enough content")

        # ACT - Use regular chat after discovery
        chat_response = agent.chat("Can you summarize what we discussed?")

        # ASSERT
        assert chat_response is not None
        assert len(chat_response) > 0
        # Discovery should still be marked as completed
        assert agent.get_discovery_status()["state"] == "completed"


@pytest.mark.integration
class TestDiscoveryQuestionProgression:
    """Test that discovery questions progress correctly and don't repeat (Issue: fix-discovery-questions)."""

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_question_text_changes_after_each_answer(self, mock_provider_class, temp_db_path):
        """Test that the question TEXT changes after each answer (not just the ID).

        This was the root cause of the bug where the same question was displayed 5 times.
        The fix ensures _current_question_text is updated when moving to the next question.
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Collect all question texts shown to user
        shown_questions = []

        # ACT - Answer 5 questions and collect question texts
        for i in range(5):
            status = agent.get_discovery_status()
            current_question = status.get("current_question", {})
            question_text = current_question.get("text", "")
            shown_questions.append(question_text)

            agent.process_discovery_answer(f"Valid answer {i+1} with enough content")

        # ASSERT - All 5 questions should be different
        assert len(shown_questions) == 5
        assert len(set(shown_questions)) == 5, (
            f"Expected 5 unique questions but got {len(set(shown_questions))}. "
            f"Questions shown: {shown_questions}"
        )

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_question_id_and_text_match_after_answer(self, mock_provider_class, temp_db_path):
        """Test that question ID and text are consistent after processing an answer.

        Verifies that _current_question_text is updated to match the framework question
        when transitioning from AI-generated question to framework questions.
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # ACT - Answer first question
        agent.process_discovery_answer("This is my problem description with sufficient detail")
        status = agent.get_discovery_status()

        # ASSERT - After first answer, should be on "users_1" question
        current_question = status.get("current_question", {})
        question_id = current_question.get("id", "")
        question_text = current_question.get("text", "")

        # The text should match the framework question for "users_1"
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()
        users_1 = next(q for q in questions if q["id"] == "users_1")

        assert question_id == "users_1", f"Expected users_1 but got {question_id}"
        assert question_text == users_1["text"], (
            f"Question text mismatch. Expected '{users_1['text']}' but got '{question_text}'"
        )

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_all_framework_questions_shown_in_order(self, mock_provider_class, temp_db_path):
        """Test that all 5 required framework questions are shown in correct order."""
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Get expected framework question IDs in order
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()
        required_ids = [q["id"] for q in questions if q["importance"] == "required"]

        # Collect actual question IDs shown
        shown_ids = []

        # ACT - Answer 5 questions
        for i in range(5):
            status = agent.get_discovery_status()
            current_question = status.get("current_question", {})
            shown_ids.append(current_question.get("id", ""))

            agent.process_discovery_answer(f"Valid answer {i+1} for question")

        # ASSERT - Should see all 5 required questions in order
        assert shown_ids == required_ids, (
            f"Question order mismatch. Expected {required_ids} but got {shown_ids}"
        )

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_question_text_persists_across_agent_restart(self, mock_provider_class, temp_db_path):
        """Test that question text is correctly restored when LeadAgent is recreated.

        This tests the full flow: answering a question, then creating a new LeadAgent
        instance (simulating a server restart) and verifying the next question is correct.
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test Project project")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        # First agent instance - start discovery and answer first question
        agent1 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent1.start_discovery()
        agent1.process_discovery_answer("First answer with sufficient detail")

        # Get the expected next question from framework
        framework = DiscoveryQuestionFramework()
        questions = framework.generate_questions()
        users_1 = next(q for q in questions if q["id"] == "users_1")

        # ACT - Create new agent instance (simulating server restart)
        agent2 = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        status = agent2.get_discovery_status()

        # ASSERT - New agent should show the correct next question
        current_question = status.get("current_question", {})
        assert current_question.get("id") == "users_1", (
            f"Expected users_1 but got {current_question.get('id')}"
        )
        assert current_question.get("text") == users_1["text"], (
            f"Question text mismatch after restart. "
            f"Expected '{users_1['text']}' but got '{current_question.get('text')}'"
        )

    @patch("codeframe.agents.lead_agent.AnthropicProvider")
    def test_no_duplicate_questions_full_discovery_flow(self, mock_provider_class, temp_db_path):
        """Test that no duplicate questions are shown during complete discovery flow.

        This is a comprehensive test that simulates the exact user experience:
        going through all 5 questions and verifying no duplicates.
        """
        # ARRANGE
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test description")

        mock_provider = Mock()
        mock_provider_class.return_value = mock_provider

        agent = LeadAgent(project_id=project_id, db=db, api_key="sk-ant-test-key")
        agent.start_discovery()

        # Collect all questions seen
        all_questions = []

        # ACT - Go through entire discovery flow
        while True:
            status = agent.get_discovery_status()

            if status["state"] == "completed":
                break

            current_question = status.get("current_question", {})
            question_text = current_question.get("text", "")
            question_id = current_question.get("id", "")

            # Check for duplicate
            for prev_q in all_questions:
                if prev_q["text"] == question_text:
                    pytest.fail(
                        f"Duplicate question detected! "
                        f"Question '{question_text}' (ID: {question_id}) was already shown "
                        f"(previous ID: {prev_q['id']})"
                    )

            all_questions.append({"id": question_id, "text": question_text})
            agent.process_discovery_answer(f"Answer for {question_id} with detail")

        # ASSERT - Should have asked 5 unique questions
        assert len(all_questions) == 5, f"Expected 5 questions but got {len(all_questions)}"

        # Double-check uniqueness of both IDs and texts
        unique_ids = set(q["id"] for q in all_questions)
        unique_texts = set(q["text"] for q in all_questions)

        assert len(unique_ids) == 5, f"Expected 5 unique IDs but got {len(unique_ids)}"
        assert len(unique_texts) == 5, f"Expected 5 unique texts but got {len(unique_texts)}"
