"""Lead Agent orchestrator for CodeFRAME."""

import json
import logging
import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from codeframe.providers.anthropic import AnthropicProvider
from codeframe.persistence.database import Database
from codeframe.discovery.questions import DiscoveryQuestionFramework
from codeframe.discovery.answers import AnswerCapture
from codeframe.planning.issue_generator import IssueGenerator
from codeframe.planning.task_decomposer import TaskDecomposer
from codeframe.core.models import Issue, Task, TaskStatus
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.agents.simple_assignment import SimpleAgentAssigner

if TYPE_CHECKING:
    pass


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

    # Configuration constants for bottleneck detection
    DEPENDENCY_WAIT_THRESHOLD_MINUTES = 60
    AGENT_OVERLOAD_THRESHOLD = 5
    CRITICAL_PATH_THRESHOLD = 3
    CRITICAL_SEVERITY_WAIT_MINUTES = 120
    HIGH_SEVERITY_WAIT_MINUTES = 60

    def __init__(
        self,
        project_id: int,
        db: Database,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        ws_manager=None,
        max_agents: int = 10,
        use_sdk: bool = False,
        project_root: Optional[str] = None,
    ):
        """Initialize Lead Agent with database and Anthropic provider.

        Args:
            project_id: Project ID for conversation context
            db: Database connection for conversation persistence
            api_key: Anthropic API key (required)
            model: Claude model to use (default: claude-sonnet-4-20250514)
            ws_manager: WebSocket manager for broadcasts (optional)
            max_agents: Maximum number of concurrent agents (default: 10)
            use_sdk: Use SDK execution mode for worker agents (default: False)
            project_root: Project root directory for SDK agents (optional, overrides workspace_path)

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
        self.ws_manager = ws_manager  # Store ws_manager for WebSocket broadcasts

        # Discovery components
        self.discovery_framework = DiscoveryQuestionFramework()
        self.answer_capture = AnswerCapture()

        # Codebase indexing
        self.codebase_index: Optional[CodebaseIndex] = None

        # Store SDK mode flag
        self.use_sdk = use_sdk
        self._project_root_override = project_root

        # Multi-agent coordination (Sprint 4) with SDK support (Phase 3)
        self.agent_pool_manager = AgentPoolManager(
            project_id=project_id,
            db=db,
            ws_manager=ws_manager,
            max_agents=max_agents,
            api_key=api_key,
            use_sdk=use_sdk,
            model=model,
            cwd=project_root,  # Set after workspace_path resolution below
        )
        self.dependency_resolver = DependencyResolver()
        self.agent_assigner = SimpleAgentAssigner()

        # SDK session tracking (Phase 3)
        self._sdk_sessions: Dict[str, str] = {}

        # Git workflow manager (cf-33)
        from codeframe.git.workflow_manager import GitWorkflowManager
        from pathlib import Path
        import git

        project = self.db.get_project(project_id)
        project_root_str = project.get(
            "workspace_path"
        )  # Fixed: use workspace_path per migration 002

        # Only initialize GitWorkflowManager if workspace_path is set and is a valid git repo
        self.git_workflow = None
        if project_root_str:
            try:
                project_root = Path(project_root_str)
                self.git_workflow = GitWorkflowManager(project_root, db)
            except (git.InvalidGitRepositoryError, git.NoSuchPathError) as e:
                logger.warning(
                    f"Could not initialize GitWorkflowManager: {e}. Git features will be disabled."
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error initializing GitWorkflowManager: {e}. Git features will be disabled."
                )

        # Session lifecycle manager (014-session-lifecycle)
        from codeframe.core.session_manager import SessionManager

        self.session_manager = None
        if project_root_str:
            try:
                self.session_manager = SessionManager(project_root_str)
                logger.debug(f"Initialized SessionManager for project at {project_root_str}")
            except Exception as e:
                logger.warning(
                    f"Could not initialize SessionManager: {e}. Session features will be disabled."
                )

        # Track current task/plan for session state
        self.current_task: Optional[str] = None

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
            conversation.append(
                {
                    "role": msg["key"],  # 'user' or 'assistant'
                    "content": msg["value"],
                }
            )

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
            conversation.append(
                {
                    "role": "user",
                    "content": message,
                }
            )

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
            self._current_question_text: Optional[str] = None
            self._discovery_answers: Dict[str, str] = {}

            # Filter and restore discovery state
            state_memories = [m for m in all_memories if m["category"] == "discovery_state"]
            for memory in state_memories:
                if memory["key"] == "state":
                    self._discovery_state = memory["value"]
                elif memory["key"] == "current_question_id":
                    self._current_question_id = memory["value"]
                elif memory["key"] == "current_question_text":
                    self._current_question_text = memory["value"]

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

            # Save current question text if exists (needed for fallback path)
            if self._current_question_text:
                self.db.create_memory(
                    project_id=self.project_id,
                    category="discovery_state",
                    key="current_question_text",
                    value=self._current_question_text,
                )

            logger.debug(f"Saved discovery state: {self._discovery_state}")

        except Exception as e:
            logger.error(f"Failed to save discovery state: {e}")

    def reset_discovery(self) -> None:
        """Reset discovery state to idle, clearing any stuck state.

        This method should be called when discovery is in a stuck state
        (e.g., state is 'discovering' but no question is available).
        It clears all discovery state from memory and resets to idle,
        allowing the user to start fresh.

        Note: This does NOT clear previously answered questions - those are
        preserved in case the user wants to continue with existing answers.
        """
        logger.info(f"Resetting discovery state for project {self.project_id}")

        # Reset in-memory state
        self._discovery_state = "idle"
        self._current_question_id = None
        self._current_question_text = None

        # Update state in database
        try:
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_state",
                key="state",
                value="idle",
            )
            # Clear current question from database
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_state",
                key="current_question_id",
                value="",
            )
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_state",
                key="current_question_text",
                value="",
            )
            logger.info(f"Discovery reset to idle for project {self.project_id}")
        except Exception as e:
            logger.error(f"Failed to reset discovery state: {e}")
            raise

    def start_discovery(self, project_description: Optional[str] = None) -> str:
        """
        Begin Socratic requirements discovery.

        Transitions state from 'idle' to 'discovering' and generates an intelligent
        first question based on the project context.

        Args:
            project_description: Optional project description from project creation.
                Provided as context to help the AI ask relevant questions.

        Returns:
            First discovery question (AI-generated based on context)
        """
        # Update state to discovering
        self._discovery_state = "discovering"
        self._save_discovery_state()

        # Store project description as context for discovery
        # Note: Use 'discovery_state' category (allowed by schema CHECK constraint)
        # instead of 'discovery_context' which is not in the allowed list
        if project_description and project_description.strip():
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_state",
                key="context_project_description",
                value=project_description.strip(),
            )
            logger.info(f"Stored project description as discovery context ({len(project_description)} chars)")

        # Get all discovery questions to show what we need to cover
        all_questions = self.discovery_framework.generate_questions()
        required_topics = [q["category"] for q in all_questions if q["importance"] == "required"]

        # Build discovery prompt with context
        discovery_prompt = self._build_discovery_start_prompt(
            project_description, required_topics
        )

        # Use Claude to generate an intelligent first question
        # Note: Use provider directly to avoid persisting prompt/response to conversation history
        try:
            conversation = [
                {
                    "role": "user",
                    "content": discovery_prompt,
                }
            ]

            response = self.provider.send_message(conversation)
            question_text = response["content"]

            # Log token usage
            usage = response["usage"]
            logger.info(
                f"Discovery question generation - Input: {usage['input_tokens']}, "
                f"Output: {usage['output_tokens']} tokens"
            )

            # Use distinct ID for AI-generated questions (not a framework ID)
            # The answer will be mapped to the appropriate framework question in process_discovery_answer()
            self._current_question_id = "ai_generated"
            self._current_question_text = question_text  # Store the actual question text
            self._save_discovery_state()  # Persists state, question_id, and question_text

            logger.info("Started discovery with AI-generated question")
            return question_text

        except Exception as e:
            logger.error(f"Failed to generate AI question, falling back to default: {e}")
            # Fallback to first question from framework
            next_question = self.discovery_framework.get_next_question(self._discovery_answers)
            if next_question:
                self._current_question_id = next_question["id"]
                self._current_question_text = next_question["text"]
                self._save_discovery_state()
                return next_question["text"]

            # Final fallback: use a default question with proper state tracking
            # Use distinct ID - answer will be mapped to framework question in process_discovery_answer()
            default_question = "What would you like to build? Please describe the main problem you're trying to solve."
            self._current_question_id = "default_generated"
            self._current_question_text = default_question
            self._save_discovery_state()  # Persists state, question_id, and question_text

            logger.info("Using default discovery question as final fallback")
            return default_question

    def _build_discovery_start_prompt(
        self, project_description: Optional[str], required_topics: list
    ) -> str:
        """Build the prompt for starting discovery with context.

        Args:
            project_description: User-provided project description
            required_topics: List of topic categories we need to cover

        Returns:
            Prompt string for Claude
        """
        prompt = """You are a helpful AI assistant gathering requirements for a software project.

Your goal is to understand:
- The problem being solved
- Who the users are
- Core features needed
- Technical constraints
- Preferred tech stack

"""
        if project_description:
            prompt += f"""The user has provided this initial description:
---
{project_description}
---

Based on this description, ask ONE focused follow-up question to clarify the most important missing detail. Don't ask about something already explained in the description.
"""
        else:
            prompt += """The user hasn't provided a project description yet.

Ask ONE clear question to understand what they want to build and what problem it solves.
"""

        prompt += """
Keep your question concise and conversational. Don't number it or add preamble - just ask the question directly."""

        return prompt

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
            logger.warning(f"process_discovery_answer called in state: {self._discovery_state}")
            return "Discovery is not active. Call start_discovery() first."

        # Determine the target question ID for storing this answer
        # AI-generated and default questions map to the first unanswered framework question
        target_question_id = self._current_question_id
        if self._current_question_id in ("ai_generated", "default_generated"):
            # Map to the first unanswered framework question
            next_framework_question = self.discovery_framework.get_next_question(self._discovery_answers)
            if next_framework_question:
                target_question_id = next_framework_question["id"]
                logger.info(f"Mapping {self._current_question_id} answer to framework question {target_question_id}")
            else:
                # Edge case: no framework questions available (shouldn't happen normally)
                target_question_id = "problem_1"
                logger.warning(f"No framework question available, defaulting to {target_question_id}")

        # Save answer under the target framework question ID
        if target_question_id:
            self._discovery_answers[target_question_id] = answer
            self.answer_capture.capture_answer(target_question_id, answer)

            # Persist to database
            self.db.create_memory(
                project_id=self.project_id,
                category="discovery_answers",
                key=target_question_id,
                value=answer,
            )

            logger.info(f"Captured answer for {target_question_id}")

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
            # CRITICAL: Update the question text to the next question's text
            # Without this, the old AI-generated question text would be displayed
            self._current_question_text = next_question["text"]
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
            Dictionary with state, current_question, answers, progress indicators, and structured_data

            Fields include:
            - state: Current discovery state (idle, discovering, completed)
            - answered_count: Number of questions answered
            - answers: Dict of question_id -> answer text
            - progress_percentage: Float 0-100 (only in discovering/completed states)
            - total_required: Total number of required questions (only in discovering/completed states)
            - remaining_count: Number of unanswered required questions (only in discovering state)
            - current_question: Current question details (only in discovering state)
            - structured_data: Extracted structured data (only in completed state)
        """
        status = {
            "state": self._discovery_state,
            "answered_count": len(self._discovery_answers),
            "answers": self._discovery_answers.copy(),
        }

        # Add progress indicators if in discovering state
        # Note: We calculate progress even if current_question_id is None to handle edge cases
        if self._discovery_state == "discovering":
            # Get all questions to calculate progress
            questions = self.discovery_framework.generate_questions()
            total_required = len([q for q in questions if q["importance"] == "required"])

            # Calculate progress percentage: (answered / total_required) * 100
            # Handle edge case: if total_required is 0, progress is 0%
            if total_required > 0:
                progress_percentage = (len(self._discovery_answers) / total_required) * 100
            else:
                progress_percentage = 0.0

            status["progress_percentage"] = progress_percentage
            status["total_required"] = total_required
            status["remaining_count"] = total_required - len(self._discovery_answers)

            # Add current question if available
            if self._current_question_id:
                # Handle AI-generated or default questions (distinct from framework IDs)
                if self._current_question_id in ("ai_generated", "default_generated"):
                    # These questions have custom text stored separately
                    # They map to framework questions when answered, but display their custom text
                    status["current_question"] = {
                        "id": self._current_question_id,
                        "category": "problem",  # AI questions typically start with problem domain
                        "text": self._current_question_text or "What would you like to build?",
                        "importance": "required",
                    }
                else:
                    # Look up from framework
                    current_q = next((q for q in questions if q["id"] == self._current_question_id), None)
                    if current_q:
                        status["current_question"] = current_q.copy()
                        # Override text if we have stored custom text
                        if self._current_question_text:
                            status["current_question"]["text"] = self._current_question_text
                    elif self._current_question_text:
                        # Fallback for unknown question IDs with stored text
                        status["current_question"] = {
                            "id": self._current_question_id,
                            "category": "discovery",
                            "text": self._current_question_text,
                            "importance": "required",
                        }

            # Detect stuck state: discovering but no current question
            # This can happen if start_discovery() failed partially
            if not self._current_question_id or "current_question" not in status:
                status["needs_recovery"] = True
                status["recovery_reason"] = "Discovery started but no question available"
                logger.warning(f"Project {self.project_id}: Discovery in stuck state - no current question")

        # Add progress indicators if completed (100% progress)
        if self._discovery_state == "completed":
            questions = self.discovery_framework.generate_questions()
            total_required = len([q for q in questions if q["importance"] == "required"])

            status["progress_percentage"] = 100.0
            status["total_required"] = total_required
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

    def generate_prd(self) -> str:
        """
        Generate a Product Requirements Document from discovery answers.

        Returns:
            PRD content as markdown string

        Raises:
            ValueError: If discovery is not complete
            Exception: If PRD generation fails
        """
        # Check if discovery is complete
        if self._discovery_state != "completed":
            raise ValueError(
                f"Discovery must be completed before generating PRD. "
                f"Current state: {self._discovery_state}"
            )

        # Get structured discovery data
        structured_data = self.answer_capture.get_structured_data()

        # Build PRD generation prompt
        prd_prompt = self._build_prd_prompt(structured_data)

        try:
            # Send to Claude for PRD generation
            conversation = [
                {
                    "role": "user",
                    "content": prd_prompt,
                }
            ]

            response = self.provider.send_message(conversation)
            prd_content = response["content"]

            # Log token usage
            usage = response["usage"]
            logger.info(
                f"PRD generation - Input: {usage['input_tokens']}, "
                f"Output: {usage['output_tokens']} tokens"
            )

            # Save PRD to database
            self.db.create_memory(
                project_id=self.project_id,
                category="prd",
                key="content",
                value=prd_content,
            )

            # Save PRD to file
            self._save_prd_to_file(prd_content)

            logger.info("PRD generated successfully")
            return prd_content

        except Exception as e:
            logger.error(f"Failed to generate PRD: {e}", exc_info=True)
            raise

    def _build_prd_prompt(self, structured_data: Dict[str, Any]) -> str:
        """Build PRD generation prompt from structured discovery data."""
        prompt = """Generate a comprehensive Product Requirements Document (PRD) based on the following discovery information:

**Problem:**
{problem}

**Users:**
{users}

**Features:**
{features}

**Technical Requirements:**
{tech_stack}

**Constraints:**
{constraints}

Please create a well-structured PRD with the following sections:

# Product Requirements Document (PRD)

## Executive Summary
Brief overview of the project and its goals.

## Problem Statement
Detailed description of the problem being solved.

## User Personas
Description of primary users and their needs.

## Features & Requirements
Comprehensive list of features and functional requirements.

## Technical Architecture
High-level technical approach and stack.

## Success Metrics
Key performance indicators and success criteria.

## Timeline & Milestones
Project phases and major milestones.

Generate the PRD in markdown format with clear sections and professional language."""

        # Format with discovery data
        return prompt.format(
            problem=structured_data.get("problem", "Not specified"),
            users=", ".join(structured_data.get("users", ["Not specified"])),
            features=", ".join(structured_data.get("features", ["Not specified"])),
            tech_stack=", ".join(structured_data.get("tech_stack", ["Not specified"])),
            constraints=", ".join(structured_data.get("constraints", ["Not specified"])),
        )

    def _save_prd_to_file(self, prd_content: str) -> None:
        """Save PRD content to file system."""
        from pathlib import Path

        try:
            # Create .codeframe/memory directory
            memory_dir = Path(".codeframe/memory")
            memory_dir.mkdir(parents=True, exist_ok=True)

            # Write PRD to file
            prd_file = memory_dir / "prd.md"
            prd_file.write_text(prd_content, encoding="utf-8")

            logger.debug(f"PRD saved to {prd_file}")

        except Exception as e:
            logger.warning(f"Failed to save PRD to file: {e}")
            # Don't fail the entire operation if file save fails

    def assign_task(self, task_id: int, agent_id: str) -> None:
        """
        Assign a task to a specific agent.

        Args:
            task_id: ID of the task to assign
            agent_id: ID of the agent to assign the task to

        Raises:
            ValueError: If task not found, agent not found, agent is blocked,
                       task is completed, or task doesn't belong to this project
        """
        from codeframe.ui.websocket_broadcasts import broadcast_task_assigned

        # Input Validation (6 checks)

        # 1. Check task exists
        task = self.db.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        # 2. Verify task belongs to this project
        if task.project_id != self.project_id:
            raise ValueError(
                f"Task {task_id} does not belong to project {self.project_id}"
            )

        # 3. Check agent exists in pool
        agent_status_map = self.agent_pool_manager.get_agent_status()
        if agent_id not in agent_status_map:
            raise ValueError(f"Agent {agent_id} not found in agent pool")

        # 4. Check agent is not blocked
        agent_status = agent_status_map[agent_id]
        if agent_status.get("status") == "blocked":
            raise ValueError(
                f"Agent {agent_id} is blocked and cannot accept new tasks"
            )

        # 5. Check task is not completed
        if task.status == TaskStatus.COMPLETED:
            raise ValueError(f"Cannot assign completed task {task_id}")

        # 6. Check for reassignment
        old_agent = task.assigned_to
        if old_agent and old_agent != agent_id:
            logger.warning(
                f"⚠️  Task {task_id} reassigned from {old_agent} to {agent_id}"
            )

        # Database Update
        try:
            self.db.update_task(
                task_id,
                {
                    "assigned_to": agent_id,
                    "status": TaskStatus.ASSIGNED.value
                }
            )
        except Exception as e:
            logger.error(f"Failed to update task assignment in database: {e}")
            raise

        # WebSocket Broadcast (async, non-blocking)
        if self.ws_manager:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    broadcast_task_assigned(
                        self.ws_manager,
                        self.project_id,
                        task_id,
                        agent_id,
                        task_title=task.title
                    )
                )
            except RuntimeError:
                logger.warning(
                    f"Failed to broadcast task {task_id} assignment: no event loop running"
                )

        # Logging
        task_title = task.title or "Untitled"
        logger.info(
            f"✅ Task {task_id} ({task_title}) assigned to agent {agent_id}"
        )

    def _calculate_wait_time(self, task: Task) -> int:
        """
        Calculate minutes elapsed since task creation.

        Args:
            task: Task object with created_at datetime

        Returns:
            Wait time in minutes as int
        """
        try:
            created_at = task.created_at
            if not created_at:
                return 0

            # Normalize both datetimes to same timezone to avoid TypeError
            if created_at.tzinfo is not None:
                # created_at is timezone-aware, use matching timezone for now
                now = datetime.now(tz=created_at.tzinfo)
            else:
                # created_at is naive, use naive now (consistent with database storage)
                now = datetime.now()

            wait_minutes = int((now - created_at).total_seconds() / 60)
            return max(0, wait_minutes)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to calculate wait time for task {task.id}: {e}")
            return 0

    def _get_agent_workload(self) -> dict:
        """
        Get assigned task count per agent.

        Returns:
            Dictionary mapping agent_id to task count
        """
        try:
            agent_status = self.agent_pool_manager.get_agent_status()
            workload = {}

            for agent_id, info in agent_status.items():
                # Count 1 if busy (has current_task), 0 if idle
                # Note: Agents process one task at a time, not queued tasks
                if info.get("status") == "busy":
                    workload[agent_id] = 1  # One task at a time
                else:
                    workload[agent_id] = 0

            return workload
        except Exception as e:
            logger.warning(f"Failed to get agent workload: {e}")
            return {}

    def _get_blocking_relationships(self) -> dict:
        """
        Get mapping of blocked tasks to their blockers.

        Returns:
            Dictionary mapping task_id to list of blocking task_ids
        """
        try:
            return self.dependency_resolver.get_blocked_tasks()
        except Exception as e:
            logger.warning(f"Failed to get blocking relationships: {e}")
            return {}

    def _determine_severity(self, bottleneck_type: str, metrics: dict) -> str:
        """
        Determine severity level based on bottleneck type and metrics.

        Args:
            bottleneck_type: Type of bottleneck ('dependency_wait', 'agent_overload', etc.)
            metrics: Dictionary with relevant metrics

        Returns:
            Severity level: 'critical', 'high', 'medium', or 'low'
        """
        if bottleneck_type == "dependency_wait":
            wait_time = metrics.get("wait_time_minutes", 0)
            if wait_time >= self.CRITICAL_SEVERITY_WAIT_MINUTES:
                return "critical"
            elif wait_time >= self.HIGH_SEVERITY_WAIT_MINUTES:
                return "high"
            else:
                return "medium"

        elif bottleneck_type == "agent_overload":
            assigned_tasks = metrics.get("assigned_tasks", 0)
            if assigned_tasks > 8:
                return "high"
            elif assigned_tasks > self.AGENT_OVERLOAD_THRESHOLD:
                return "medium"
            else:
                return "low"

        elif bottleneck_type == "agent_idle":
            return "medium"

        elif bottleneck_type == "critical_path":
            blocked_dependents = metrics.get("blocked_dependents", 0)
            if blocked_dependents >= 5:
                return "critical"
            elif blocked_dependents >= self.CRITICAL_PATH_THRESHOLD:
                return "high"
            else:
                return "medium"

        return "low"

    def _generate_recommendation(self, bottleneck: dict) -> str:
        """
        Generate recommendation for resolving bottleneck.

        Args:
            bottleneck: Bottleneck descriptor dictionary

        Returns:
            Recommendation string
        """
        bottleneck_type = bottleneck.get("type")

        if bottleneck_type == "dependency_wait":
            task_id = bottleneck.get("task_id")
            blocking_task_id = bottleneck.get("blocking_task_id")
            wait_time = bottleneck.get("wait_time_minutes", 0)
            return (
                f"Task {task_id} has been waiting {wait_time}min on task {blocking_task_id}. "
                f"Investigate or manually unblock dependency."
            )

        elif bottleneck_type == "agent_overload":
            agent_id = bottleneck.get("agent_id")
            assigned_tasks = bottleneck.get("assigned_tasks", 0)
            return (
                f"Agent {agent_id} is overloaded with {assigned_tasks} tasks. "
                f"Consider scaling up agents or re-distributing tasks."
            )

        elif bottleneck_type == "agent_idle":
            idle_agents = bottleneck.get("idle_agents", [])
            return (
                f"Agents idle ({', '.join(idle_agents)}) while pending tasks exist. "
                f"Check task assignment logic or dependencies."
            )

        elif bottleneck_type == "critical_path":
            task_id = bottleneck.get("task_id")
            blocked_dependents = bottleneck.get("blocked_dependents", 0)
            return (
                f"Task {task_id} blocks {blocked_dependents} dependent tasks. "
                f"Prioritize this task or parallelize blocking dependencies."
            )

        return "Unknown bottleneck type"

    def detect_bottlenecks(self) -> list:
        """
        Detect workflow bottlenecks.

        Identifies four types of bottlenecks:
        1. Dependency wait: Tasks blocked on dependencies for >60min
        2. Agent overload: Agents with >5 assigned tasks
        3. Agent idle: Idle agents while pending tasks exist
        4. Critical path: Tasks blocking >3 dependent tasks

        Returns:
            List of bottleneck descriptors, each with:
                - type: Bottleneck type
                - severity: 'critical', 'high', 'medium', or 'low'
                - recommendation: Human-readable recommendation
                - Additional type-specific fields
        """
        bottlenecks = []

        try:
            # Query data sources
            tasks = self.db.get_project_tasks(self.project_id)
            agent_status = self.agent_pool_manager.get_agent_status()
            blocked_tasks = self._get_blocking_relationships()

            if not tasks:
                logger.debug("No tasks found for bottleneck detection")
                return []

            # 1. Dependency Wait Bottlenecks
            for task in tasks:
                if task.status == TaskStatus.BLOCKED or task.id in blocked_tasks:
                    wait_minutes = self._calculate_wait_time(task)
                    if wait_minutes >= self.DEPENDENCY_WAIT_THRESHOLD_MINUTES:
                        blocking_task_ids = blocked_tasks.get(task.id, [])
                        bottleneck = {
                            "type": "dependency_wait",
                            "task_id": task.id,
                            "wait_time_minutes": wait_minutes,
                            "blocking_task_id": blocking_task_ids[0] if blocking_task_ids else None,
                            "severity": self._determine_severity(
                                "dependency_wait", {"wait_time_minutes": wait_minutes}
                            ),
                        }
                        bottleneck["recommendation"] = self._generate_recommendation(bottleneck)
                        bottlenecks.append(bottleneck)

            # 2. Agent Overload Bottlenecks
            workload = self._get_agent_workload()
            for agent_id, task_count in workload.items():
                if task_count > self.AGENT_OVERLOAD_THRESHOLD:
                    bottleneck = {
                        "type": "agent_overload",
                        "agent_id": agent_id,
                        "assigned_tasks": task_count,
                        "severity": self._determine_severity(
                            "agent_overload", {"assigned_tasks": task_count}
                        ),
                    }
                    bottleneck["recommendation"] = self._generate_recommendation(bottleneck)
                    bottlenecks.append(bottleneck)

            # 3. Agent Idle Bottlenecks
            idle_agents = [
                aid for aid, info in agent_status.items() if info.get("status") == "idle"
            ]
            pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

            if idle_agents and pending_tasks:
                bottleneck = {
                    "type": "agent_idle",
                    "idle_agents": idle_agents,
                    "severity": "medium",
                }
                bottleneck["recommendation"] = self._generate_recommendation(bottleneck)
                bottlenecks.append(bottleneck)

            # 4. Critical Path Bottlenecks
            for task in tasks:
                if task.status in [TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED]:
                    # Get all dependent task IDs
                    dependent_ids = self.dependency_resolver.dependents.get(task.id, set())

                    # Filter to only count active (non-completed) dependents
                    active_dependents = [
                        dep_id
                        for dep_id in dependent_ids
                        if any(t.id == dep_id and t.status != TaskStatus.COMPLETED for t in tasks)
                    ]
                    dependent_count = len(active_dependents)

                    if dependent_count >= self.CRITICAL_PATH_THRESHOLD:
                        bottleneck = {
                            "type": "critical_path",
                            "task_id": task.id,
                            "blocked_dependents": dependent_count,
                            "severity": self._determine_severity(
                                "critical_path", {"blocked_dependents": dependent_count}
                            ),
                        }
                        bottleneck["recommendation"] = self._generate_recommendation(bottleneck)
                        bottlenecks.append(bottleneck)

            # Log summary
            if bottlenecks:
                logger.warning(f"Detected {len(bottlenecks)} workflow bottlenecks")
                for bn in bottlenecks:
                    if bn["severity"] in ["critical", "high"]:
                        logger.warning(
                            f"  {bn['severity'].upper()}: {bn['type']} - {bn['recommendation']}"
                        )
            else:
                logger.info("No workflow bottlenecks detected")

            return bottlenecks

        except Exception as e:
            logger.error(f"Failed to detect bottlenecks: {e}", exc_info=True)
            return []

    def generate_issues(self, sprint_number: int) -> List[Issue]:
        """Generate issues from PRD for given sprint number.

        This method implements the first step of hierarchical work breakdown:
        PRD → Issues → Tasks

        Workflow:
        1. Load PRD from database
        2. Use IssueGenerator to extract features → Issues
        3. Save issues to database
        4. Return list of created issues

        Args:
            sprint_number: Sprint number for issue numbering (e.g., 2 for Sprint 2)

        Returns:
            List of Issue objects created from PRD

        Raises:
            ValueError: If PRD not found or sprint_number invalid
            Exception: If issue generation or database save fails
        """
        # Validate sprint number
        if sprint_number < 1:
            raise ValueError(f"Sprint number must be >= 1, got {sprint_number}")

        try:
            # Load PRD from database
            prd_content = self._load_prd_from_database()

            if not prd_content:
                raise ValueError(
                    "No PRD found in database. Generate PRD first using generate_prd()"
                )

            # Initialize issue generator
            generator = IssueGenerator()

            # Generate issues from PRD
            logger.info(f"Generating issues from PRD for sprint {sprint_number}")
            issues = generator.generate_issues_from_prd(prd_content, sprint_number)

            if not issues:
                logger.warning("No issues generated from PRD")
                return []

            # Save issues to database
            saved_issues = []
            for issue in issues:
                # Set project_id
                issue.project_id = self.project_id

                # Save to database
                issue_id = self.db.create_issue(issue)
                issue.id = issue_id
                saved_issues.append(issue)

                logger.debug(f"Saved issue {issue.issue_number}: {issue.title} (id={issue_id})")

            logger.info(f"Successfully generated and saved {len(saved_issues)} issues")
            return saved_issues

        except ValueError as e:
            logger.error(f"Validation error during issue generation: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to generate issues: {e}", exc_info=True)
            raise

    def has_existing_prd(self) -> bool:
        """Check if project has an existing PRD.

        Returns:
            True if PRD exists, False otherwise
        """
        try:
            prd_content = self._load_prd_from_database()
            return prd_content is not None
        except ValueError:
            return False

    def _load_prd_from_database(self) -> str:
        """Load PRD content from database.

        Returns:
            PRD content as markdown string

        Raises:
            ValueError: If PRD not found
        """
        # Load PRD from memory table
        memories = self.db.get_project_memories(self.project_id)
        prd_memories = [m for m in memories if m["category"] == "prd" and m["key"] == "content"]

        if not prd_memories:
            raise ValueError("PRD not found in database")

        # Get most recent PRD (in case multiple exist)
        prd_content = prd_memories[-1]["value"]

        logger.debug(f"Loaded PRD from database ({len(prd_content)} chars)")
        return prd_content

    def decompose_prd(self, sprint_number: Optional[int] = None) -> Dict[str, Any]:
        """Decompose PRD into issues and tasks (complete hierarchical breakdown).

        This method implements the full hierarchical work breakdown:
        PRD → Issues → Tasks

        Workflow:
        1. Load all issues for project (or generate if sprint_number provided)
        2. For each issue, decompose into tasks using TaskDecomposer
        3. Save tasks to database
        4. Return summary statistics

        Args:
            sprint_number: Optional sprint number for issue generation first.
                          If None, decomposes existing issues.

        Returns:
            Dictionary with:
                - total_issues: Number of issues processed
                - total_tasks: Number of tasks created
                - issues_decomposed: List of issue numbers decomposed
                - tasks_by_issue: Dict mapping issue_number to task count

        Raises:
            ValueError: If no issues found or decomposition fails
            Exception: If database operations fail
        """
        try:
            # Step 1: Get or generate issues
            if sprint_number is not None:
                logger.info(f"Generating issues for sprint {sprint_number} first")
                issues = self.generate_issues(sprint_number)
            else:
                logger.info("Loading existing issues from database")
                issues = self.db.get_project_issues(self.project_id)

                if not issues:
                    raise ValueError(
                        "No issues found in database. "
                        "Generate issues first using generate_issues(sprint_number) "
                        "or provide sprint_number parameter."
                    )

            if not issues:
                raise ValueError("No issues available for decomposition")

            # Step 2: Initialize TaskDecomposer
            decomposer = TaskDecomposer()

            # Step 3: Decompose each issue into tasks
            total_tasks = 0
            issues_decomposed = []
            tasks_by_issue = {}

            for issue in issues:
                logger.info(f"Decomposing issue {issue.issue_number}: {issue.title}")

                try:
                    # Decompose issue into tasks
                    tasks = decomposer.decompose_issue(issue, self.provider)

                    # Save tasks to database
                    saved_task_count = 0
                    for task in tasks:
                        task_id = self.db.create_task_with_issue(
                            project_id=task.project_id,
                            issue_id=task.issue_id,
                            task_number=task.task_number,
                            parent_issue_number=task.parent_issue_number,
                            title=task.title,
                            description=task.description,
                            status=task.status,
                            priority=task.priority,
                            workflow_step=task.workflow_step,
                            can_parallelize=task.can_parallelize,
                            requires_mcp=task.requires_mcp,
                        )

                        logger.debug(f"Saved task {task.task_number}: {task.title} (id={task_id})")
                        saved_task_count += 1

                    # Update statistics
                    total_tasks += saved_task_count
                    issues_decomposed.append(issue.issue_number)
                    tasks_by_issue[issue.issue_number] = saved_task_count

                    logger.info(
                        f"Successfully decomposed issue {issue.issue_number} "
                        f"into {saved_task_count} tasks"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to decompose issue {issue.issue_number}: {e}", exc_info=True
                    )
                    # Continue with next issue instead of failing completely
                    continue

            # Step 4: Return summary
            summary = {
                "total_issues": len(issues_decomposed),
                "total_tasks": total_tasks,
                "issues_decomposed": issues_decomposed,
                "tasks_by_issue": tasks_by_issue,
            }

            logger.info(
                f"PRD decomposition complete: {len(issues_decomposed)} issues "
                f"decomposed into {total_tasks} tasks"
            )

            return summary

        except ValueError as e:
            logger.error(f"Validation error during PRD decomposition: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to decompose PRD: {e}", exc_info=True)
            raise

    def build_codebase_index(self) -> Dict[str, Any]:
        """Build index of project codebase structure.

        Returns:
            Dictionary with index stats (files indexed, symbols found, etc.)

        Raises:
            ValueError: If project root path is invalid
            Exception: If indexing fails
        """
        try:
            # Get project root from database
            project = self.db.get_project(self.project_id)
            project_root = project.get("root_path", ".")

            logger.info(f"Building codebase index for project at: {project_root}")

            # Create and build index
            self.codebase_index = CodebaseIndex(project_root)
            self.codebase_index.build()

            # Get statistics
            file_paths = set(s.file_path for s in self.codebase_index.symbols)
            languages = set(s.language for s in self.codebase_index.symbols)

            stats = {
                "files_indexed": len(file_paths),
                "symbols_found": len(self.codebase_index.symbols),
                "languages": list(languages),
            }

            logger.info(
                f"Codebase indexed successfully: {stats['files_indexed']} files, "
                f"{stats['symbols_found']} symbols"
            )

            return stats

        except Exception as e:
            logger.error(f"Failed to build codebase index: {e}", exc_info=True)
            raise

    def query_codebase(self, query: str, query_type: str = "name") -> List[Dict[str, Any]]:
        """Query codebase structure.

        Args:
            query: Search query (symbol name or pattern)
            query_type: 'name' or 'pattern'

        Returns:
            List of symbols matching query

        Raises:
            ValueError: If unknown query_type or codebase not indexed
            Exception: If query fails
        """
        if not self.codebase_index:
            self.build_codebase_index()

        try:
            if query_type == "name":
                symbols = self.codebase_index.find_symbols(query)
            elif query_type == "pattern":
                symbols = self.codebase_index.search_pattern(query)
            else:
                raise ValueError(f"Unknown query_type: {query_type}")

            logger.debug(f"Query '{query}' ({query_type}) found {len(symbols)} results")

            return [s.to_dict() for s in symbols]

        except ValueError as e:
            logger.error(f"Validation error during codebase query: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to query codebase: {e}", exc_info=True)
            raise

    def start_issue_work(self, issue_id: int) -> Dict[str, Any]:
        """
        Start work on an issue by creating feature branch.

        Creates git branch using GitWorkflowManager and tracks in database.

        Args:
            issue_id: Database ID of the issue

        Returns:
            dict with:
                - branch_name: Created branch name
                - issue_number: Issue number
                - status: 'created'

        Raises:
            ValueError: If issue doesn't exist or already has active branch
            RuntimeError: If git workflow is not available
        """
        # Check if git workflow is available
        if not self.git_workflow:
            raise RuntimeError(
                "Git workflow is not available. Please ensure project has a valid git repository."
            )

        # 1. Get issue from database
        issue = self.db.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue {issue_id} not found")

        # 2. Check if issue already has active branch
        existing_branch = self.db.get_branch_for_issue(issue_id)
        if existing_branch:
            raise ValueError(
                f"Issue {issue.issue_number} already has an active branch: "
                f"{existing_branch['branch_name']}"
            )

        # 3. Create feature branch via GitWorkflowManager
        branch_name = self.git_workflow.create_feature_branch(issue.issue_number, issue.title)

        # 4. Record in git_branches table (already done by GitWorkflowManager)
        # GitWorkflowManager.create_feature_branch() already stores in database

        # 5. Return branch info
        logger.info(f"Started work on issue {issue.issue_number}: created branch {branch_name}")

        return {
            "branch_name": branch_name,
            "issue_number": issue.issue_number,
            "status": "created",
        }

    async def complete_issue(self, issue_id: int) -> Dict[str, Any]:
        """
        Complete an issue by merging feature branch to main.

        Validates all tasks complete, merges branch, updates database, and triggers deployment.

        Args:
            issue_id: Database ID of the issue

        Returns:
            dict with:
                - merge_commit: Git commit hash
                - branch_name: Merged branch name
                - tasks_completed: Number of tasks in issue
                - status: 'merged'
                - deployment: Deployment result dict (if triggered)

        Raises:
            ValueError: If tasks not all complete or no active branch
            RuntimeError: If git workflow is not available
        """
        # Check if git workflow is available
        if not self.git_workflow:
            raise RuntimeError(
                "Git workflow is not available. Please ensure project has a valid git repository."
            )

        # 1. Get issue from database
        issue = self.db.get_issue(issue_id)
        if not issue:
            raise ValueError(f"Issue {issue_id} not found")

        # 2. Validate all tasks completed using GitWorkflowManager (async)
        if not await self.git_workflow.is_issue_complete(issue_id):
            raise ValueError(
                f"Cannot complete issue {issue.issue_number}: incomplete tasks remain"
            )

        # 3. Get active branch for issue
        branch_record = self.db.get_branch_for_issue(issue_id)
        if not branch_record:
            raise ValueError(f"No active branch found for issue {issue.issue_number}")

        # 4. Merge to main via GitWorkflowManager (async)
        merge_result = await self.git_workflow.merge_to_main(issue.issue_number)

        # 5. Update issue status to 'completed'
        self.db.update_issue(issue_id, {"status": "completed"})

        # 6. Count tasks (async)
        tasks = await self.db.get_tasks_by_issue(issue_id)
        tasks_completed = len(tasks)

        # 7. Trigger deployment after successful merge
        from codeframe.deployment.deployer import Deployer

        deployer = Deployer(self.git_workflow.project_root, self.db)
        deployment_result = deployer.trigger_deployment(
            commit_hash=merge_result["merge_commit"], environment="staging"
        )

        logger.info(
            f"Completed issue {issue.issue_number}: merged {merge_result['branch_name']} "
            f"with {tasks_completed} tasks, deployment {deployment_result['status']}"
        )

        return {
            "merge_commit": merge_result["merge_commit"],
            "branch_name": merge_result["branch_name"],
            "tasks_completed": tasks_completed,
            "status": "merged",
            "deployment": deployment_result,
        }

    async def start_multi_agent_execution(
        self, max_retries: int = 3, max_concurrent: int = 5, timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Start multi-agent parallel task execution with timeout protection.

        Main coordination loop that:
        1. Loads all project tasks and builds dependency graph
        2. Continuously assigns ready tasks to agents
        3. Executes tasks in parallel (up to max_concurrent)
        4. Handles task completion and dependency unblocking
        5. Retries failed tasks (up to max_retries)
        6. Continues until all tasks complete or fail

        Args:
            max_retries: Maximum retry attempts per task (default: 3)
            max_concurrent: Maximum concurrent task executions (default: 5)
            timeout: Maximum execution time in seconds (default: 300)

        Returns:
            Dict with execution summary:
                - total_tasks: Total number of tasks
                - completed: Number of successfully completed tasks
                - failed: Number of failed tasks
                - retries: Total number of retry attempts
                - execution_time: Total execution time in seconds

        Raises:
            ValueError: If no tasks found for project
            asyncio.TimeoutError: If execution exceeds timeout
            Exception: If critical execution error occurs
        """
        try:
            async with asyncio.timeout(timeout):
                return await self._execute_coordination_loop(max_retries, max_concurrent)
        except asyncio.TimeoutError:
            logger.error(f"❌ Multi-agent execution timed out after {timeout}s")
            await self._emergency_shutdown()
            raise

    async def _execute_coordination_loop(
        self, max_retries: int = 3, max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """Internal coordination loop extracted for timeout wrapping."""
        import time

        start_time = time.time()

        # Load all tasks for project
        tasks = self.db.get_project_tasks(self.project_id)
        if not tasks:
            raise ValueError(f"No tasks found for project {self.project_id}")

        logger.info(f"🚀 Multi-agent execution started: {len(tasks)} tasks")

        # Build dependency graph
        self.dependency_resolver.build_dependency_graph(tasks)

        # Track execution state
        retry_counts = {}  # task_id -> retry_count
        running_tasks = {}  # task_id -> asyncio.Task
        total_retries = 0
        iteration_count = 0
        max_iterations = 1000  # Safety watchdog

        try:
            # Main execution loop
            while not self._all_tasks_complete():
                iteration_count += 1
                if iteration_count > max_iterations:
                    logger.error(f"❌ WATCHDOG: Hit max iterations {max_iterations}")
                    logger.error(f"Running tasks: {len(running_tasks)}")
                    logger.error(f"Retry counts: {retry_counts}")
                    await self._emergency_shutdown()
                    break

                # Get ready tasks (dependencies satisfied, not completed/running)
                ready_task_ids = self.dependency_resolver.get_ready_tasks(exclude_completed=True)

                # Filter out already running tasks
                ready_task_ids = [tid for tid in ready_task_ids if tid not in running_tasks]

                # Log loop state
                completed_count = len(
                    [t for t in tasks if t.id in self.dependency_resolver.completed_tasks]
                )
                logger.debug(
                    f"🔄 Loop {iteration_count}: {len(ready_task_ids)} ready, "
                    f"{len(running_tasks)} running, {completed_count}/{len(tasks)} complete"
                )

                # Assign and execute ready tasks (up to max_concurrent)
                for task_id in ready_task_ids[: max_concurrent - len(running_tasks)]:
                    task = next((t for t in tasks if t.id == task_id), None)
                    if not task:
                        continue

                    # Check retry limit
                    if retry_counts.get(task_id, 0) >= max_retries:
                        logger.warning(
                            f"Task {task_id} exceeded max retries ({max_retries}), marking as failed"
                        )
                        self.db.update_task(task_id, {"status": "failed"})
                        self.dependency_resolver.completed_tasks.add(task_id)
                        continue

                    # T036/T037: Check for SYNC blocker before assigning
                    can_assign = await self.can_assign_task(task_id)
                    if not can_assign:
                        logger.info(f"Task {task_id} skipped: blocked by pending SYNC blocker")
                        continue

                    # Assign and execute task
                    task_future = asyncio.create_task(
                        self._assign_and_execute_task(task, retry_counts)
                    )
                    running_tasks[task_id] = task_future

                # Wait for at least one task to complete
                if running_tasks:
                    done, _ = await asyncio.wait(
                        running_tasks.values(), return_when=asyncio.FIRST_COMPLETED
                    )

                    # Process completed tasks
                    for completed_future in done:
                        # Find which task this was
                        task_id = next(
                            (tid for tid, fut in running_tasks.items() if fut == completed_future),
                            None,
                        )

                        if task_id:
                            # Remove from running tasks
                            running_tasks.pop(task_id, None)

                            # Check if task succeeded or failed
                            try:
                                success = await completed_future
                                if success:
                                    # Unblock dependent tasks
                                    self.dependency_resolver.unblock_dependent_tasks(task_id)
                                else:
                                    # Task failed - increment retry count
                                    retry_counts[task_id] = retry_counts.get(task_id, 0) + 1
                                    total_retries += 1
                                    # Check if task has pending SYNC blocker before resetting to pending
                                    can_assign = await self.can_assign_task(task_id)
                                    if can_assign:
                                        # No blocker - reset to pending for retry
                                        self.db.update_task(task_id, {"status": "pending"})
                                    else:
                                        # Has SYNC blocker - keep as blocked
                                        self.db.update_task(task_id, {"status": "blocked"})
                                        logger.info(
                                            f"Task {task_id} kept as blocked due to pending SYNC blocker"
                                        )
                            except Exception:
                                logger.exception(f"Error processing task {task_id}")
                                retry_counts[task_id] = retry_counts.get(task_id, 0) + 1
                                total_retries += 1
                                # Check if task has pending SYNC blocker before resetting to pending
                                can_assign = await self.can_assign_task(task_id)
                                if can_assign:
                                    # No blocker - reset to pending for retry
                                    self.db.update_task(task_id, {"status": "pending"})
                                else:
                                    # Has SYNC blocker - keep as blocked
                                    self.db.update_task(task_id, {"status": "blocked"})
                                    logger.info(
                                        f"Task {task_id} kept as blocked due to pending SYNC blocker"
                                    )
                else:
                    # No tasks running and none ready - check if we're stuck
                    if not self._all_tasks_complete():
                        logger.warning("⚠️  No tasks running or ready, but not all tasks complete")
                        blocked = self.dependency_resolver.get_blocked_tasks()
                        if blocked:
                            logger.error(f"❌ DEADLOCK: Blocked tasks: {blocked}")
                            break
                        else:
                            # Small delay before checking again
                            await asyncio.sleep(0.1)

        except Exception:
            logger.exception("Critical error in multi-agent execution")
            raise

        # Calculate summary statistics
        execution_time = time.time() - start_time

        # Re-fetch task states from database to get accurate final statuses.
        # The original `tasks` list was loaded at the start of execution and may be stale
        # after concurrent task updates during multi-agent execution. A single bulk fetch
        # here avoids N individual get_task() calls and ensures consistent status snapshot.
        current_tasks = self.db.get_project_tasks(self.project_id)
        task_status_map = {t.id: t.status for t in current_tasks}

        failed_count = sum(
            1 for t in tasks
            if task_status_map.get(t.id) == TaskStatus.FAILED
        )
        # Completed count = tasks in completed_tasks that are not failed
        completed_count = sum(
            1 for t in tasks
            if t.id in self.dependency_resolver.completed_tasks
            and task_status_map.get(t.id) != TaskStatus.FAILED
        )

        summary = {
            "total_tasks": len(tasks),
            "completed": completed_count,
            "failed": failed_count,
            "retries": total_retries,
            "execution_time": execution_time,
            "iterations": iteration_count,
        }

        logger.info(
            f"✅ Multi-agent execution complete: {completed_count}/{len(tasks)} tasks, "
            f"{failed_count} failed, {total_retries} retries, {execution_time:.2f}s, {iteration_count} iterations"
        )

        return summary

    async def _emergency_shutdown(self) -> None:
        """Emergency shutdown: retire all agents and cancel pending tasks."""
        logger.warning("🚨 Emergency shutdown initiated")
        try:
            # Retire all active agents
            if hasattr(self, "agent_pool"):
                agent_status = self.agent_pool.get_agent_status()
                for agent_id in list(agent_status.keys()):
                    try:
                        self.agent_pool.retire_agent(agent_id)
                        logger.debug(f"Retired agent {agent_id}")
                    except Exception as e:
                        logger.warning(f"Failed to retire agent {agent_id}: {e}")

            logger.info("Emergency shutdown complete")
        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")

    async def _assign_and_execute_task(self, task: Task, retry_counts: Dict[int, int]) -> bool:
        """
        Assign task to agent and execute asynchronously.

        Args:
            task: Task object to execute
            retry_counts: Dictionary tracking retry counts per task

        Returns:
            True if task succeeded, False if failed

        Workflow:
        1. Determine agent type using SimpleAgentAssigner
        2. Get or create agent from pool
        3. Mark agent as busy
        4. Execute task via agent
        5. Update task status in database
        6. Mark agent as idle
        7. Broadcast task status changes
        """
        try:
            # Determine agent type
            task_dict = {"id": task.id, "title": task.title, "description": task.description}
            agent_type = self.agent_assigner.assign_agent_type(task_dict)

            logger.info(f"Assigning task {task.id} ({task.title}) to {agent_type}")

            # Get or create agent
            agent_id = self.agent_pool_manager.get_or_create_agent(agent_type)

            # Mark agent busy
            self.agent_pool_manager.mark_agent_busy(agent_id, task.id)

            # Update task with assigned agent and status (Issue #248 fix)
            # Set assigned_to BEFORE status change so UI shows assignment immediately
            self.db.update_task(task.id, {"assigned_to": agent_id})
            self.db.update_task(task.id, {"status": "in_progress"})

            # Get agent instance
            agent_instance = self.agent_pool_manager.get_agent_instance(agent_id)

            # Phase 3: Track SDK session ID for hybrid agents
            session_id = getattr(agent_instance, "session_id", None)
            if session_id:
                self._sdk_sessions[agent_id] = session_id
                logger.debug(f"Tracking SDK session for {agent_id}: {session_id}")

            # Execute task (assuming agents have execute_task method)
            logger.info(f"Agent {agent_id} executing task {task.id}")

            # Worker agents now use async execute_task - no threading needed
            await agent_instance.execute_task(task_dict)

            # Step 11: Code Review (Sprint 9)
            # Review the code changes before marking task as completed
            logger.info(f"Initiating code review for task {task.id}")
            try:
                # Get or create review agent
                review_agent_id = self.agent_pool_manager.get_or_create_agent("review")
                review_agent = self.agent_pool_manager.get_agent_instance(review_agent_id)

                # Execute review
                review_report = await review_agent.execute_task(task_dict)

                logger.info(
                    f"Review completed: status={review_report.status}, "
                    f"score={review_report.overall_score:.1f}"
                )

                # If review rejected or needs changes, blocker already created by ReviewWorkerAgent
                # Don't mark task as completed yet - wait for blocker resolution
                if review_report.status in ["rejected", "changes_requested"]:
                    logger.warning(
                        f"Task {task.id} review failed: {review_report.status}. "
                        f"Blocker created, task remains in_progress."
                    )
                    # Mark review agent idle
                    self.agent_pool_manager.mark_agent_idle(review_agent_id)
                    # Mark worker agent idle
                    self.agent_pool_manager.mark_agent_idle(agent_id)
                    return False  # Task not completed due to review failure

                # Mark review agent idle
                self.agent_pool_manager.mark_agent_idle(review_agent_id)

            except Exception as e:
                logger.error(f"Code review failed for task {task.id}: {e}")
                # Continue with task completion even if review fails (graceful degradation)
                # In production, you might want to create an ASYNC blocker here

            # Task succeeded and passed review
            self.db.update_task(task.id, {"status": "completed"})
            logger.info(f"Task {task.id} completed successfully by agent {agent_id}")

            # Mark agent idle
            self.agent_pool_manager.mark_agent_idle(agent_id)

            return True

        except Exception:
            logger.exception(f"Task {task.id} execution failed")

            # Don't update task status here - let coordination loop decide
            # whether to retry or mark as permanently failed based on retry_counts

            # Mark agent idle if it was assigned
            try:
                if "agent_id" in locals():
                    self.agent_pool_manager.mark_agent_idle(agent_id)
            except Exception:
                pass

            return False

    async def can_assign_task(self, task_id: int) -> bool:
        """
        Check if a task can be assigned to an agent (T036, T037).

        Implements SYNC blocker dependency handling:
        - SYNC blockers: Block all dependent tasks until resolved
        - ASYNC blockers: Allow dependent tasks to continue (informational only)

        Args:
            task_id: Database ID of the task

        Returns:
            True if task can be assigned, False if blocked

        Blocking Conditions:
        1. Task has pending SYNC blocker (direct block)
        2. Task depends on another task with pending SYNC blocker (transitive block)
        3. ASYNC blockers do NOT block task assignment
        """
        # Get task details
        task = self.db.get_task(task_id)
        if not task:
            return False

        # Check if this task itself has a pending SYNC blocker
        blockers = self.db.list_blockers(project_id=self.project_id, status="PENDING")

        for blocker in blockers.get("blockers", []):
            if blocker.get("task_id") == task_id and blocker.get("blocker_type") == "SYNC":
                logger.debug(
                    f"Task {task_id} blocked: has pending SYNC blocker {blocker.get('id')}"
                )
                return False

        # Check if task depends on tasks with pending SYNC blockers
        # Note: task.depends_on defaults to "" so no None check needed
        depends_on_str = task.depends_on
        if depends_on_str and depends_on_str.strip():
            # Parse depends_on field (JSON array or comma-separated format)
            # Similar to dependency_resolver.py lines 71-83
            depends_on_str = depends_on_str.strip()
            dep_ids = []

            if depends_on_str.startswith("[") and depends_on_str.endswith("]"):
                # JSON array format: "[1, 2, 3]"
                try:
                    dep_ids = json.loads(depends_on_str)
                    # Normalize to integers
                    dep_ids = [int(dep_id) for dep_id in dep_ids]
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning(
                        f"Invalid JSON in depends_on for task {task_id}: {depends_on_str}. Error: {e}"
                    )
                    dep_ids = []
            else:
                # Comma-separated format or single value
                try:
                    dep_ids = [int(x.strip()) for x in depends_on_str.split(",") if x.strip()]
                except ValueError:
                    logger.warning(
                        f"Invalid depends_on format for task {task_id}: {depends_on_str}"
                    )
                    dep_ids = []

            # Check each dependency for SYNC blockers
            for dep_id in dep_ids:
                # Recursively check if dependency is blocked
                can_assign_dependency = await self.can_assign_task(dep_id)
                if not can_assign_dependency:
                    logger.debug(
                        f"Task {task_id} blocked: depends on task {dep_id} "
                        f"which has pending SYNC blocker"
                    )
                    return False

                # Also check if dependency task has pending SYNC blocker
                for blocker in blockers.get("blockers", []):
                    if blocker.get("task_id") == dep_id and blocker.get("blocker_type") == "SYNC":
                        logger.debug(
                            f"Task {task_id} blocked: dependency task {dep_id} "
                            f"has pending SYNC blocker {blocker.get('id')}"
                        )
                        return False

        # No blocking conditions found
        return True

    def _all_tasks_complete(self) -> bool:
        """
        Check if all tasks are completed or failed.
        Detects deadlock scenario where all remaining tasks are blocked.

        Returns:
            True if all tasks are in terminal state (completed/failed) OR deadlocked
        """
        tasks = self.db.get_project_tasks(self.project_id)

        incomplete = []
        blocked = []

        for task in tasks:
            status = task.status
            if status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                incomplete.append(task.id)
                if status == TaskStatus.BLOCKED:
                    blocked.append(task.id)

        # No incomplete tasks means all done
        if not incomplete:
            return True

        # Deadlock detection: if all remaining tasks are blocked, we're stuck
        if incomplete and len(blocked) == len(incomplete):
            logger.error(
                f"❌ DEADLOCK DETECTED: All {len(incomplete)} remaining tasks are blocked: {blocked}"
            )
            return True  # Force exit to prevent infinite loop

        logger.debug(f"Tasks remaining: {len(incomplete)} ({len(blocked)} blocked)")
        return False

    # ============================================================================
    # Session Lifecycle Management (014-session-lifecycle)
    # ============================================================================

    def _get_session_summary(self) -> str:
        """Generate summary of completed tasks in last session.

        Returns:
            Human-readable summary string
        """
        tasks = self.db.get_recently_completed_tasks(self.project_id, limit=10)
        if not tasks:
            return "No tasks completed"

        # Build summary from task titles
        task_summaries = []
        for task in tasks[:3]:  # Show max 3 tasks in summary
            task_summaries.append(f"Task #{task['id']} ({task['title']})")

        summary = f"Completed {', '.join(task_summaries)}"
        if len(tasks) > 3:
            summary += f" and {len(tasks) - 3} more"

        return summary

    def _get_completed_task_ids(self) -> List[int]:
        """Get IDs of recently completed tasks.

        Returns:
            List of task IDs
        """
        tasks = self.db.get_recently_completed_tasks(self.project_id, limit=10)
        return [task["id"] for task in tasks]

    def _format_time_ago(self, timestamp: str) -> str:
        """Format ISO timestamp as 'X hours/days ago'.

        Args:
            timestamp: ISO 8601 timestamp string

        Returns:
            Human-readable time ago string
        """
        from datetime import datetime, timedelta

        try:
            dt = datetime.fromisoformat(timestamp)
            now = datetime.now()
            delta = now - dt

            if delta < timedelta(minutes=1):
                return "just now"
            elif delta < timedelta(hours=1):
                minutes = int(delta.total_seconds() / 60)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif delta < timedelta(days=1):
                hours = int(delta.total_seconds() / 3600)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            elif delta < timedelta(days=30):
                days = delta.days
                return f"{days} day{'s' if days != 1 else ''} ago"
            else:
                return timestamp.split("T")[0]  # Just return date
        except (ValueError, AttributeError):
            return "unknown time"

    def _get_pending_actions(self) -> List[str]:
        """Get next pending actions for next actions queue.

        Returns:
            List of action strings (max 5)
        """
        tasks = self.db.get_pending_tasks(self.project_id, limit=5)
        actions = []
        for task in tasks:
            actions.append(f"{task['title']} (Task #{task['id']})")
        return actions

    def _get_blocker_summaries(self) -> List[Dict]:
        """Get active blocker summaries.

        Returns:
            List of blocker dicts with id, question, priority
        """
        resp = self.db.list_blockers(self.project_id, status="PENDING")
        blockers = resp.get("blockers", [])
        summaries = []
        for blocker in blockers[:10]:  # Max 10 blockers
            summaries.append(
                {
                    "id": blocker["id"],
                    "question": blocker["question"],
                    "priority": blocker.get("priority", "medium"),
                }
            )
        return summaries

    def _get_progress_percentage(self) -> float:
        """Calculate project progress percentage.

        Returns:
            Progress percentage (0-100)
        """
        stats = self.db.get_project_stats(self.project_id)
        total = stats["total_tasks"]
        completed = stats["completed_tasks"]

        if total == 0:
            return 0.0

        return (completed / total) * 100

    def on_session_start(self) -> None:
        """Restore and display session context on CLI startup."""
        if not self.session_manager:
            logger.debug("SessionManager not initialized, skipping session restoration")
            return

        session = self.session_manager.load_session()

        if not session:
            print("\n🚀 Starting new session...\n")
            return

        # Validate session structure
        if not isinstance(session, dict):
            logger.warning("Session data is not a dict, treating as new session")
            print("\n🚀 Starting new session...\n")
            return

        # Validate last_session structure
        last_session = session.get("last_session")
        if (
            not isinstance(last_session, dict)
            or "summary" not in last_session
            or "timestamp" not in last_session
        ):
            logger.warning("Session missing valid 'last_session' data, treating as new session")
            print("\n🚀 Starting new session...\n")
            return

        # Display formatted session context with safe access
        print("\n📋 Restoring session...\n")
        print("Last Session:")

        # Safe summary access
        summary = last_session.get("summary", "No activity")
        if not isinstance(summary, str):
            summary = str(summary) if summary else "No activity"
        print(f"  Summary: {summary}")

        # Safe timestamp formatting
        timestamp = last_session.get("timestamp", "")
        try:
            time_ago = self._format_time_ago(timestamp) if timestamp else "Unknown time"
        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Failed to format timestamp: {e}")
            time_ago = "Recently"
        print(f"  Time: {time_ago}")
        print()

        # Display next actions if available
        next_actions = session.get("next_actions", [])
        if isinstance(next_actions, list) and next_actions:
            print("Next Actions:")
            for i, action in enumerate(next_actions[:5], 1):
                # Ensure action is printable
                action_str = str(action) if action else ""
                if action_str:
                    print(f"  {i}. {action_str}")
            print()

        # Display progress with safe access
        progress_pct = session.get("progress_pct", 0)
        if not isinstance(progress_pct, (int, float)):
            try:
                progress_pct = float(progress_pct)
            except (ValueError, TypeError):
                progress_pct = 0

        try:
            stats = self.db.get_project_stats(self.project_id)
            completed = stats.get("completed_tasks", 0)
            total = stats.get("total_tasks", 0)
            print(f"Progress: {round(progress_pct)}% ({completed}/{total} tasks complete)")
        except Exception as e:
            logger.debug(f"Failed to get project stats: {e}")
            print(f"Progress: {round(progress_pct)}%")

        # Display blockers with safe access
        active_blockers = session.get("active_blockers", [])
        if not isinstance(active_blockers, list):
            active_blockers = []

        if active_blockers:
            print(f"Blockers: {len(active_blockers)} active")
        else:
            print("Blockers: None")
        print()

        # Prompt to continue
        print("Press Enter to continue or Ctrl+C to cancel...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n✓ Cancelled")
            raise

    def on_session_end(self) -> None:
        """Save session state before CLI exit."""
        if not self.session_manager:
            logger.debug("SessionManager not initialized, skipping session save")
            return

        try:
            # Gather SDK sessions from agent pool
            sdk_sessions = self._get_sdk_sessions()

            # Gather session state
            state = {
                "summary": self._get_session_summary(),
                "completed_tasks": self._get_completed_task_ids(),
                "next_actions": self._get_pending_actions(),
                "current_plan": self.current_task,
                "active_blockers": self._get_blocker_summaries(),
                "progress_pct": self._get_progress_percentage(),
                "sdk_sessions": sdk_sessions,  # Phase 3: Track SDK sessions for resume
            }

            # Save to file
            self.session_manager.save_session(state)
            logger.debug(f"Session state saved successfully (SDK sessions: {len(sdk_sessions)})")
        except Exception as e:
            logger.error(f"Failed to save session state: {e}")

    def _get_sdk_sessions(self) -> Dict[str, str]:
        """Get SDK session IDs from all hybrid agents in pool.

        Phase 3: Track SDK sessions for conversation resume capability.
        Each hybrid agent may have a session_id that allows resuming
        conversations when the agent is reused.

        Returns:
            Dictionary mapping agent_id to session_id for hybrid agents
        """
        sdk_sessions = {}

        try:
            agent_status = self.agent_pool_manager.get_agent_status()

            for agent_id, info in agent_status.items():
                # Only include hybrid agents with valid session IDs
                if info.get("is_hybrid") and info.get("session_id"):
                    sdk_sessions[agent_id] = info["session_id"]

            logger.debug(f"Gathered {len(sdk_sessions)} SDK sessions from agent pool")

        except Exception as e:
            logger.warning(f"Failed to gather SDK sessions: {e}")

        return sdk_sessions
