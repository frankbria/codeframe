"""Lead Agent orchestrator for CodeFRAME."""

import logging
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from codeframe.providers.anthropic import AnthropicProvider
from codeframe.persistence.database import Database
from codeframe.discovery.questions import DiscoveryQuestionFramework
from codeframe.discovery.answers import AnswerCapture

if TYPE_CHECKING:
    from codeframe.core.project import Project


logger = logging.getLogger(__name__)


class LeadAgent:
    """
    Lead Agent - Central orchestrator responsible for:
    - Socratic requirements discovery
    - Task decomposition and assignment
    - Agent coordination
    - Blocker escalation
    - Natural language conversation with Claude integration
    """

    def __init__(
        self,
        project_id: int,
        db: Database,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        """Initialize Lead Agent with database and Anthropic provider.

        Args:
            project_id: Project ID for conversation context
            db: Database connection for conversation persistence
            api_key: Anthropic API key (required)
            model: Claude model to use (default: claude-sonnet-4-20250514)

        Raises:
            ValueError: If API key is missing
        """
        if not api_key:
            raise ValueError(
                "api_key is required for Lead Agent.\n"
                "Get your ANTHROPIC_API_KEY at: https://console.anthropic.com/"
            )

        self.project_id = project_id
        self.db = db
        self.provider = AnthropicProvider(api_key=api_key, model=model)

        # Discovery components
        self.discovery_framework = DiscoveryQuestionFramework()
        self.answer_capture = AnswerCapture()

        # Load discovery state from database
        self._load_discovery_state()

        logger.info(f"Initialized Lead Agent for project {project_id}")

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Load conversation history from database.

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        # Load conversation from database
        db_messages = self.db.get_conversation(self.project_id)

        # Convert database format to provider format
        conversation = []
        for msg in db_messages:
            conversation.append({
                "role": msg["key"],  # 'user' or 'assistant'
                "content": msg["value"],
            })

        logger.debug(f"Loaded {len(conversation)} messages from conversation history")
        return conversation

    def chat(self, message: str) -> str:
        """Handle natural language interaction with user.

        Args:
            message: User message

        Returns:
            Agent response text

        Raises:
            ValueError: If message is empty
            Exception: If API call fails or database error occurs
        """
        # Validate input
        if not message or not message.strip():
            raise ValueError("Message cannot be empty")

        try:
            # Load conversation history
            conversation = self.get_conversation_history()

            # Append user message to conversation
            conversation.append({
                "role": "user",
                "content": message,
            })

            # Save user message to database
            self.db.create_memory(
                project_id=self.project_id,
                category="conversation",
                key="user",
                value=message,
            )

            logger.info(f"User message: {message[:50]}...")

            # Send to Claude API
            response = self.provider.send_message(conversation)

            # Extract assistant response
            assistant_response = response["content"]

            # Save assistant response to database
            self.db.create_memory(
                project_id=self.project_id,
                category="conversation",
                key="assistant",
                value=assistant_response,
            )

            # Log token usage
            usage = response["usage"]
            logger.info(
                f"Token usage - Input: {usage['input_tokens']}, "
                f"Output: {usage['output_tokens']}"
            )

            logger.info(f"Assistant response: {assistant_response[:50]}...")

            return assistant_response

        except ValueError as e:
            logger.error(f"Validation error: {e}")
            raise

        except Exception as e:
            logger.error(f"Error during chat: {e}", exc_info=True)
            raise

    def _load_discovery_state(self) -> None:
        """Load discovery state from database."""
        try:
            # Load all memories and filter by category
            all_memories = self.db.get_project_memories(self.project_id)

            # Initialize default state
            self._discovery_state = "idle"
            self._current_question_id: Optional[str] = None
            self._discovery_answers: Dict[str, str] = {}

            # Filter and restore discovery state
            state_memories = [m for m in all_memories if m["category"] == "discovery_state"]
            for memory in state_memories:
                if memory["key"] == "state":
                    self._discovery_state = memory["value"]
                elif memory["key"] == "current_question_id":
                    self._current_question_id = memory["value"]

            # Filter and load discovery answers
            answer_memories = [m for m in all_memories if m["category"] == "discovery_answers"]
            for memory in answer_memories:
                question_id = memory["key"]
                answer_text = memory["value"]
                self._discovery_answers[question_id] = answer_text
                # Also capture in answer_capture for structured extraction
                self.answer_capture.capture_answer(question_id, answer_text)

            logger.debug(
                f"Loaded discovery state: {self._discovery_state}, "
                f"answers: {len(self._discovery_answers)}"
            )

        except Exception as e:
            logger.warning(f"Failed to load discovery state: {e}")
            # Initialize with defaults
            self._discovery_state = "idle"
            self._current_question_id = None
            self._discovery_answers = {}

    def _save_discovery_state(self) -> None:
        """Save discovery state to database."""
        try:
            # Save current state
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_state",
                key="state",
                value=self._discovery_state,
            )

            # Save current question ID if exists
            if self._current_question_id:
                self.db.create_memory(
                    project_id=self.project_id,
                    category="discovery_state",
                    key="current_question_id",
                    value=self._current_question_id,
                )

            logger.debug(f"Saved discovery state: {self._discovery_state}")

        except Exception as e:
            logger.error(f"Failed to save discovery state: {e}")

    def start_discovery(self) -> str:
        """
        Begin Socratic requirements discovery.

        Transitions state from 'idle' to 'discovering' and asks the first question.

        Returns:
            First discovery question
        """
        # Update state to discovering
        self._discovery_state = "discovering"
        self._save_discovery_state()

        # Get first question
        next_question = self.discovery_framework.get_next_question(self._discovery_answers)

        if next_question:
            self._current_question_id = next_question["id"]
            self._save_discovery_state()

            logger.info(f"Started discovery, first question: {next_question['id']}")
            return next_question["text"]
        else:
            # No questions available (shouldn't happen)
            logger.warning("No questions available to start discovery")
            return "Discovery framework initialized but no questions available."

    def process_discovery_answer(self, answer: str) -> str:
        """
        Process user answer during discovery phase.

        Saves the answer, advances to next question, and checks for completion.

        Args:
            answer: User's answer to current discovery question

        Returns:
            Next question or completion message
        """
        if self._discovery_state != "discovering":
            logger.warning(
                f"process_discovery_answer called in state: {self._discovery_state}"
            )
            return "Discovery is not active. Call start_discovery() first."

        # Save current answer
        if self._current_question_id:
            self._discovery_answers[self._current_question_id] = answer
            self.answer_capture.capture_answer(self._current_question_id, answer)

            # Persist to database
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_answers",
                key=self._current_question_id,
                value=answer,
            )

            logger.info(f"Captured answer for {self._current_question_id}")

        # Check if discovery is complete
        if self.discovery_framework.is_discovery_complete(self._discovery_answers):
            self._discovery_state = "completed"
            self._save_discovery_state()
            logger.info("Discovery completed!")
            return "Discovery complete! All required questions have been answered."

        # Get next question
        next_question = self.discovery_framework.get_next_question(self._discovery_answers)

        if next_question:
            self._current_question_id = next_question["id"]
            self._save_discovery_state()
            return next_question["text"]
        else:
            # All questions answered
            self._discovery_state = "completed"
            self._save_discovery_state()
            return "Discovery complete! All questions have been answered."

    def get_discovery_status(self) -> Dict[str, Any]:
        """
        Get current discovery status.

        Returns:
            Dictionary with state, current_question, answers, and structured_data
        """
        status = {
            "state": self._discovery_state,
            "answered_count": len(self._discovery_answers),
            "answers": self._discovery_answers.copy(),
        }

        # Add current question if in discovering state
        if self._discovery_state == "discovering" and self._current_question_id:
            # Find current question details
            questions = self.discovery_framework.generate_questions()
            current_q = next(
                (q for q in questions if q["id"] == self._current_question_id),
                None
            )
            if current_q:
                status["current_question"] = current_q

            # Add remaining count
            total_required = len([q for q in questions if q["importance"] == "required"])
            status["remaining_count"] = total_required - len(self._discovery_answers)

        # Add structured data if completed
        if self._discovery_state == "completed":
            status["structured_data"] = self.answer_capture.get_structured_data()

        return status

    def process_discovery_response(self, user_response: str) -> str:
        """
        Process user response during discovery phase.

        Args:
            user_response: User's answer to discovery questions

        Returns:
            Follow-up questions or next steps
        """
        # Use chat() for LLM-powered discovery
        return self.chat(user_response)

    def assign_task(self, task_id: int, agent_id: str) -> None:
        """Assign task to worker agent."""
        # TODO: Implement task assignment logic
        pass

    def detect_bottlenecks(self) -> list:
        """Detect workflow bottlenecks."""
        # TODO: Implement bottleneck detection
        return []
