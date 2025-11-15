"""Lead Agent orchestrator for CodeFRAME."""

import logging
import asyncio
from typing import TYPE_CHECKING, List, Dict, Any, Optional

from codeframe.providers.anthropic import AnthropicProvider
from codeframe.persistence.database import Database
from codeframe.discovery.questions import DiscoveryQuestionFramework
from codeframe.discovery.answers import AnswerCapture
from codeframe.planning.issue_generator import IssueGenerator
from codeframe.planning.task_decomposer import TaskDecomposer
from codeframe.core.models import Issue, Task
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.agents.agent_pool_manager import AgentPoolManager
from codeframe.agents.dependency_resolver import DependencyResolver
from codeframe.agents.simple_assignment import SimpleAgentAssigner

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
        ws_manager=None,
        max_agents: int = 10,
    ):
        """Initialize Lead Agent with database and Anthropic provider.

        Args:
            project_id: Project ID for conversation context
            db: Database connection for conversation persistence
            api_key: Anthropic API key (required)
            model: Claude model to use (default: claude-sonnet-4-20250514)
            ws_manager: WebSocket manager for broadcasts (optional)
            max_agents: Maximum number of concurrent agents (default: 10)

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

        # Codebase indexing
        self.codebase_index: Optional[CodebaseIndex] = None

        # Multi-agent coordination (Sprint 4)
        self.agent_pool_manager = AgentPoolManager(
            project_id=project_id,
            db=db,
            ws_manager=ws_manager,
            max_agents=max_agents,
            api_key=api_key,
        )
        self.dependency_resolver = DependencyResolver()
        self.agent_assigner = SimpleAgentAssigner()

        # Git workflow manager (cf-33)
        from codeframe.git.workflow_manager import GitWorkflowManager
        from pathlib import Path
        import git

        project = self.db.get_project(project_id)
        project_root_str = project.get("root_path")

        # Only initialize GitWorkflowManager if root_path is set and is a valid git repo
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
            logger.warning(f"process_discovery_answer called in state: {self._discovery_state}")
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

        # Add progress indicators and current question if in discovering state
        if self._discovery_state == "discovering" and self._current_question_id:
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

            # Find current question details
            current_q = next((q for q in questions if q["id"] == self._current_question_id), None)
            if current_q:
                status["current_question"] = current_q

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

                logger.debug(f"Saved issue {issue.issue_number}: {issue.title} (id={issue_id})")

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
                f"Issue {issue['issue_number']} already has an active branch: "
                f"{existing_branch['branch_name']}"
            )

        # 3. Create feature branch via GitWorkflowManager
        branch_name = self.git_workflow.create_feature_branch(issue["issue_number"], issue["title"])

        # 4. Record in git_branches table (already done by GitWorkflowManager)
        # GitWorkflowManager.create_feature_branch() already stores in database

        # 5. Return branch info
        logger.info(f"Started work on issue {issue['issue_number']}: created branch {branch_name}")

        return {
            "branch_name": branch_name,
            "issue_number": issue["issue_number"],
            "status": "created",
        }

    def complete_issue(self, issue_id: int) -> Dict[str, Any]:
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

        # 2. Validate all tasks completed using GitWorkflowManager
        if not self.git_workflow.is_issue_complete(issue_id):
            raise ValueError(
                f"Cannot complete issue {issue['issue_number']}: incomplete tasks remain"
            )

        # 3. Get active branch for issue
        branch_record = self.db.get_branch_for_issue(issue_id)
        if not branch_record:
            raise ValueError(f"No active branch found for issue {issue['issue_number']}")

        # 4. Merge to main via GitWorkflowManager
        merge_result = self.git_workflow.merge_to_main(issue["issue_number"])

        # 5. Update issue status to 'completed'
        self.db.update_issue(issue_id, {"status": "completed"})

        # 6. Count tasks
        tasks = self.db.get_tasks_by_issue(issue_id)
        tasks_completed = len(tasks)

        # 7. Trigger deployment after successful merge
        from codeframe.deployment.deployer import Deployer

        deployer = Deployer(self.git_workflow.project_root, self.db)
        deployment_result = deployer.trigger_deployment(
            commit_hash=merge_result["merge_commit"], environment="staging"
        )

        logger.info(
            f"Completed issue {issue['issue_number']}: merged {merge_result['branch_name']} "
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
        print(f"\n🚀 DEBUG: start_multi_agent_execution ENTERED (timeout={timeout})")
        try:
            print("🚀 DEBUG: Creating asyncio.timeout context...")
            async with asyncio.timeout(timeout):
                print("🚀 DEBUG: Inside timeout context, calling _execute_coordination_loop...")
                return await self._execute_coordination_loop(max_retries, max_concurrent)
        except asyncio.TimeoutError:
            print("❌ DEBUG: Caught TimeoutError!")
            logger.error(f"❌ Multi-agent execution timed out after {timeout}s")
            await self._emergency_shutdown()
            raise

    async def _execute_coordination_loop(
        self, max_retries: int = 3, max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """Internal coordination loop extracted for timeout wrapping."""
        print(
            f"\n🔄 DEBUG: _execute_coordination_loop ENTERED (max_retries={max_retries}, max_concurrent={max_concurrent})"
        )
        import time

        print("🔄 DEBUG: Imported time module")
        start_time = time.time()
        print(f"🔄 DEBUG: Start time: {start_time}")

        # Load all tasks for project
        print(f"🔄 DEBUG: Loading tasks for project {self.project_id}...")
        task_dicts = self.db.get_project_tasks(self.project_id)
        print(f"🔄 DEBUG: Loaded {len(task_dicts)} task_dicts")
        if not task_dicts:
            raise ValueError(f"No tasks found for project {self.project_id}")

        # Convert to Task objects
        print("🔄 DEBUG: Converting to Task objects...")
        tasks = []
        for task_dict in task_dicts:
            task = Task(
                id=task_dict["id"],
                project_id=task_dict["project_id"],
                issue_id=task_dict.get("issue_id"),
                task_number=task_dict["task_number"],
                parent_issue_number=task_dict.get("parent_issue_number"),
                title=task_dict["title"],
                description=task_dict["description"],
                status=task_dict["status"],
                priority=task_dict.get("priority", "medium"),
                workflow_step=task_dict.get("workflow_step"),
                can_parallelize=task_dict.get("can_parallelize", False),
                requires_mcp=task_dict.get("requires_mcp", False),
                depends_on=task_dict.get("depends_on", "[]"),
            )
            tasks.append(task)
        print(f"🔄 DEBUG: Converted {len(tasks)} Task objects")

        logger.info(f"🚀 Multi-agent execution started: {len(tasks)} tasks")
        print(f"🔄 DEBUG: Logged execution start")

        # Build dependency graph
        print("🔄 DEBUG: Building dependency graph...")
        self.dependency_resolver.build_dependency_graph(tasks)
        print("🔄 DEBUG: Dependency graph built ✅")

        # Track execution state
        print("🔄 DEBUG: Initializing execution state...")
        retry_counts = {}  # task_id -> retry_count
        running_tasks = {}  # task_id -> asyncio.Task
        total_retries = 0
        iteration_count = 0
        max_iterations = 1000  # Safety watchdog
        print("🔄 DEBUG: Execution state initialized ✅")

        print("🔄 DEBUG: Entering try block...")
        try:
            print("🔄 DEBUG: About to enter main while loop...")
            # Main execution loop
            while not self._all_tasks_complete():
                print(f"🔄 DEBUG: While loop iteration {iteration_count}")
                iteration_count += 1
                print(
                    f"🔄 DEBUG: Checking watchdog (iteration={iteration_count}, max={max_iterations})..."
                )
                if iteration_count > max_iterations:
                    logger.error(f"❌ WATCHDOG: Hit max iterations {max_iterations}")
                    logger.error(f"Running tasks: {len(running_tasks)}")
                    logger.error(f"Retry counts: {retry_counts}")
                    await self._emergency_shutdown()
                    break

                # Get ready tasks (dependencies satisfied, not completed/running)
                print(f"🔄 DEBUG: Getting ready tasks from dependency_resolver...")
                ready_task_ids = self.dependency_resolver.get_ready_tasks(exclude_completed=True)
                print(f"🔄 DEBUG: Got {len(ready_task_ids)} ready task IDs: {ready_task_ids}")

                # Filter out already running tasks
                print(
                    f"🔄 DEBUG: Filtering out running tasks (currently {len(running_tasks)} running)..."
                )
                ready_task_ids = [tid for tid in ready_task_ids if tid not in running_tasks]
                print(f"🔄 DEBUG: After filtering: {len(ready_task_ids)} ready tasks")

                # Log loop state
                print(f"🔄 DEBUG: Calculating loop state...")
                completed_count = len(
                    [t for t in tasks if t.id in self.dependency_resolver.completed_tasks]
                )
                print(
                    f"🔄 DEBUG: Loop state: ready={len(ready_task_ids)}, running={len(running_tasks)}, completed={completed_count}/{len(tasks)}"
                )
                logger.debug(
                    f"🔄 Loop {iteration_count}: {len(ready_task_ids)} ready, "
                    f"{len(running_tasks)} running, {completed_count}/{len(tasks)} complete"
                )

                # Assign and execute ready tasks (up to max_concurrent)
                print(f"🔄 DEBUG: About to assign tasks (max_concurrent={max_concurrent})...")
                for task_id in ready_task_ids[: max_concurrent - len(running_tasks)]:
                    print(f"🔄 DEBUG: Processing task {task_id}...")
                    task = next((t for t in tasks if t.id == task_id), None)
                    if not task:
                        print(f"🔄 DEBUG: Task {task_id} not found in tasks list, skipping")
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
                    print(f"🔄 DEBUG: Assigning task {task_id}: {task.title}")
                    task_future = asyncio.create_task(
                        self._assign_and_execute_task(task, retry_counts)
                    )
                    running_tasks[task_id] = task_future

                # Wait for at least one task to complete
                if running_tasks:
                    print(f"🔄 DEBUG: About to wait for tasks...")
                    done, _ = await asyncio.wait(
                        running_tasks.values(), return_when=asyncio.FIRST_COMPLETED
                    )

                    # Process completed tasks
                    print(f"🔄 DEBUG: Processing completed tasks...")
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
                                    print(f"🔄 DEBUG: Task {task_id} completed successfully")
                                    # Unblock dependent tasks
                                    unblocked = self.dependency_resolver.unblock_dependent_tasks(
                                        task_id
                                    )
                                    if unblocked:
                                        print(f"🔄 DEBUG: Task {task_id} unblocked: {unblocked}")
                                else:
                                    # Task failed - increment retry count
                                    retry_counts[task_id] = retry_counts.get(task_id, 0) + 1
                                    total_retries += 1
                                    print(
                                        f"🔄 DEBUG: Task {task_id} failed, retry {retry_counts[task_id]}/{max_retries}"
                                    )
                            except Exception as e:
                                logger.exception(f"Error processing task {task_id}")
                                retry_counts[task_id] = retry_counts.get(task_id, 0) + 1
                                total_retries += 1
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

        except Exception as e:
            logger.exception("Critical error in multi-agent execution")
            raise

        # Calculate summary statistics
        execution_time = time.time() - start_time
        completed_count = len(
            [t for t in tasks if t.id in self.dependency_resolver.completed_tasks]
        )
        failed_count = len([t for t in tasks if self.db.get_task(t.id).get("status") == "failed"])

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

            # Update task status to in_progress
            self.db.update_task(task.id, {"status": "in_progress"})

            # Get agent instance
            agent_instance = self.agent_pool_manager.get_agent_instance(agent_id)

            # Execute task (assuming agents have execute_task method)
            logger.info(f"Agent {agent_id} executing task {task.id}")

            # Worker agents now use async execute_task - no threading needed
            await agent_instance.execute_task(task_dict)

            # Task succeeded
            self.db.update_task(task.id, {"status": "completed"})
            logger.info(f"Task {task.id} completed successfully by agent {agent_id}")

            # Mark agent idle
            self.agent_pool_manager.mark_agent_idle(agent_id)

            return True

        except Exception as e:
            logger.exception(f"Task {task.id} execution failed")

            # Update task status
            self.db.update_task(task.id, {"status": "failed"})

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
        depends_on = task.get("depends_on", "")
        if depends_on:
            # Get all project tasks to resolve dependencies
            all_tasks = self.db.get_project_tasks(self.project_id)

            # Find the task this depends on
            dependency_task = None
            for t in all_tasks:
                if t["task_number"] == depends_on:
                    dependency_task = t
                    break

            if dependency_task:
                # Recursively check if dependency is blocked
                can_assign_dependency = await self.can_assign_task(dependency_task["id"])
                if not can_assign_dependency:
                    logger.debug(
                        f"Task {task_id} blocked: depends on task {dependency_task['id']} "
                        f"which has SYNC blocker"
                    )
                    return False

                # Also check if dependency task has pending SYNC blocker
                for blocker in blockers.get("blockers", []):
                    if (
                        blocker.get("task_id") == dependency_task["id"]
                        and blocker.get("blocker_type") == "SYNC"
                    ):
                        logger.debug(
                            f"Task {task_id} blocked: dependency task {dependency_task['id']} "
                            f"has SYNC blocker {blocker.get('id')}"
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
        print("🔍 DEBUG: _all_tasks_complete called")
        print(f"🔍 DEBUG: Getting tasks for project {self.project_id}...")
        task_dicts = self.db.get_project_tasks(self.project_id)
        print(f"🔍 DEBUG: Got {len(task_dicts)} tasks")

        incomplete = []
        blocked = []

        print("🔍 DEBUG: Iterating through tasks...")
        for task_dict in task_dicts:
            status = task_dict.get("status", "pending")
            print(f"🔍 DEBUG: Task {task_dict['id']}: status={status}")
            if status not in ("completed", "failed"):
                incomplete.append(task_dict["id"])
                if status == "blocked":
                    blocked.append(task_dict["id"])

        print(f"🔍 DEBUG: incomplete={incomplete}, blocked={blocked}")

        # No incomplete tasks means all done
        if not incomplete:
            print("🔍 DEBUG: All tasks complete!")
            return True

        # Deadlock detection: if all remaining tasks are blocked, we're stuck
        if incomplete and len(blocked) == len(incomplete):
            print(f"🔍 DEBUG: DEADLOCK DETECTED!")
            logger.error(
                f"❌ DEADLOCK DETECTED: All {len(incomplete)} remaining tasks are blocked: {blocked}"
            )
            return True  # Force exit to prevent infinite loop

        logger.debug(f"Tasks remaining: {len(incomplete)} ({len(blocked)} blocked)")
        return False
