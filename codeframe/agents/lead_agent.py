"""Lead Agent orchestrator for CodeFRAME."""

import logging
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from codeframe.providers.anthropic import AnthropicProvider
from codeframe.persistence.database import Database
from codeframe.discovery.questions import DiscoveryQuestionFramework
from codeframe.discovery.answers import AnswerCapture
from codeframe.planning.issue_generator import IssueGenerator
from codeframe.planning.task_decomposer import TaskDecomposer
from codeframe.core.models import Issue, Task

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
            conversation = [{
                "role": "user",
                "content": prd_prompt,
            }]

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
        """Assign task to worker agent."""
        # TODO: Implement task assignment logic
        pass

    def detect_bottlenecks(self) -> list:
        """Detect workflow bottlenecks."""
        # TODO: Implement bottleneck detection
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

                logger.debug(
                    f"Saved issue {issue.issue_number}: {issue.title} (id={issue_id})"
                )

            logger.info(f"Successfully generated and saved {len(saved_issues)} issues")
            return saved_issues

        except ValueError as e:
            logger.error(f"Validation error during issue generation: {e}")
            raise

        except Exception as e:
            logger.error(f"Failed to generate issues: {e}", exc_info=True)
            raise

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
                issue_dicts = self.db.get_project_issues(self.project_id)

                if not issue_dicts:
                    raise ValueError(
                        "No issues found in database. "
                        "Generate issues first using generate_issues(sprint_number) "
                        "or provide sprint_number parameter."
                    )

                # Convert dict to Issue objects
                issues = []
                for issue_dict in issue_dicts:
                    issue = Issue(
                        id=issue_dict["id"],
                        project_id=issue_dict["project_id"],
                        issue_number=issue_dict["issue_number"],
                        title=issue_dict["title"],
                        description=issue_dict["description"],
                        priority=issue_dict["priority"],
                        workflow_step=issue_dict["workflow_step"],
                    )
                    issues.append(issue)

            if not issues:
                raise ValueError("No issues available for decomposition")

            # Step 2: Initialize TaskDecomposer
            decomposer = TaskDecomposer()

            # Step 3: Decompose each issue into tasks
            total_tasks = 0
            issues_decomposed = []
            tasks_by_issue = {}

            for issue in issues:
                logger.info(
                    f"Decomposing issue {issue.issue_number}: {issue.title}"
                )

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

                        logger.debug(
                            f"Saved task {task.task_number}: {task.title} (id={task_id})"
                        )
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
                        f"Failed to decompose issue {issue.issue_number}: {e}",
                        exc_info=True
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
