"""Lead Agent orchestrator for CodeFRAME."""

import logging
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from codeframe.providers.anthropic import AnthropicProvider
from codeframe.persistence.database import Database

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

    def start_discovery(self) -> str:
        """
        Begin Socratic requirements discovery.

        Returns:
            Initial discovery prompt
        """
        return """Hi! I'm your Lead Agent. Let's figure out what we're building.
I'll ask some questions to understand the requirements. Ready?

1. What problem does this application solve?
2. Who are the primary users?
3. What are the core features (top 3)?
"""

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
