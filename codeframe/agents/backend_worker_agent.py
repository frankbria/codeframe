"""
Backend Worker Agent - Autonomous task execution (cf-41).

This agent reads tasks from the database, builds context from the codebase index,
generates Python code using LLM, writes files, and updates task status.

Key responsibilities:
- Fetch pending tasks from database
- Build execution context from codebase index
- Generate code via Anthropic Claude API
- Apply file changes safely
- Update task status
- Error handling and retry logic

Phase 1 Implementation: Foundation (initialization and task fetching)
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import json

from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.core.models import TaskStatus


logger = logging.getLogger(__name__)


class BackendWorkerAgent:
    """
    Autonomous agent that executes backend development tasks.

    The agent operates in a loop:
    1. Fetch highest priority pending task
    2. Build context from codebase
    3. Generate code using LLM
    4. Write files to disk
    5. Update task status
    6. Repeat

    Integration points:
    - Database (cf-8): Task queue and status management
    - CodebaseIndex (cf-32): Symbol and file discovery
    - Anthropic Claude API: Code generation
    - Git Workflow (cf-33): Feature branch context
    - Test Runner (cf-42): Future integration
    - Self-Correction (cf-43): Future integration
    """

    def __init__(
        self,
        project_id: int,
        db: Database,
        codebase_index: CodebaseIndex,
        provider: str = "claude",
        api_key: Optional[str] = None,
        project_root: Path = Path(".")
    ):
        """
        Initialize Backend Worker Agent.

        Args:
            project_id: Project ID for database context
            db: Database instance for task/status management
            codebase_index: Indexed codebase for context retrieval
            provider: LLM provider (default: "claude")
            api_key: API key for LLM provider (uses ANTHROPIC_API_KEY env var if not provided)
            project_root: Project root directory for file operations

        Raises:
            ValueError: If project_id is invalid or database not initialized
        """
        self.project_id = project_id
        self.db = db
        self.codebase_index = codebase_index
        self.provider = provider
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.project_root = Path(project_root)

        # Validate project exists
        if not self.db:
            raise ValueError("Database instance is required")

        logger.info(
            f"Initialized BackendWorkerAgent: project_id={project_id}, "
            f"provider={provider}, project_root={project_root}"
        )

    def fetch_next_task(self) -> Optional[Dict[str, Any]]:
        """
        Fetch highest priority pending task for this project.

        Tasks are ordered by:
        1. Priority (ascending: 0 = highest, 4 = lowest)
        2. Workflow step (ascending: 1 = first, 15 = last)
        3. ID (ascending: oldest first)

        Returns:
            Task dictionary or None if no tasks available

        Task format:
        {
            "id": int,
            "project_id": int,
            "issue_id": int,
            "task_number": str,  # e.g., "1.5.2"
            "parent_issue_number": str,  # e.g., "1.5"
            "title": str,
            "description": str,
            "status": str,  # "pending", "in_progress", "completed", "failed"
            "assigned_to": str,
            "depends_on": str,
            "can_parallelize": bool,
            "priority": int,  # 0-4
            "workflow_step": int,  # 1-15
            "requires_mcp": bool,
            "estimated_tokens": int,
            "actual_tokens": int,
            "created_at": str,
            "completed_at": str
        }
        """
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE project_id = ? AND status = ?
            ORDER BY priority ASC, workflow_step ASC, id ASC
            LIMIT 1
            """,
            (self.project_id, TaskStatus.PENDING.value),
        )

        row = cursor.fetchone()
        if row:
            task = dict(row)
            logger.info(
                f"Fetched task {task['id']}: {task['title']} "
                f"(priority={task['priority']}, workflow_step={task['workflow_step']})"
            )
            return task

        logger.debug(f"No pending tasks for project {self.project_id}")
        return None

    def build_context(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build execution context from task and codebase.

        This method uses the codebase index (cf-32) to find relevant symbols,
        files, and dependencies that provide context for code generation.

        Args:
            task: Task dictionary from fetch_next_task()

        Returns:
            Context dictionary:
            {
                "task": Dict[str, Any],  # Original task
                "related_files": List[str],  # File paths
                "related_symbols": List[Symbol],  # Symbols from codebase index
                "issue_context": Dict[str, Any]  # Parent issue information
            }
        """
        # Extract keywords from task title and description for symbol search
        search_terms = f"{task.get('title', '')} {task.get('description', '')}"

        # Query codebase index for related symbols
        related_symbols = self.codebase_index.search_pattern(search_terms)

        # Extract unique file paths from symbols
        related_files = list(set(symbol.file_path for symbol in related_symbols))

        # Get parent issue context if available
        issue_context = None
        if task.get("issue_id"):
            issue_context = self.db.get_issue(task["issue_id"])

        logger.debug(
            f"Built context for task {task['id']}: "
            f"{len(related_symbols)} symbols, {len(related_files)} files"
        )

        return {
            "task": task,
            "related_files": related_files,
            "related_symbols": related_symbols,
            "issue_context": issue_context
        }

    def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate code using LLM based on context.

        Constructs prompts from context and calls Anthropic Claude API
        to generate code changes.

        Args:
            context: Context from build_context()

        Returns:
            Generation result:
            {
                "files": [
                    {
                        "path": str,  # Relative to project_root
                        "content": str,  # File content
                        "action": "create" | "modify" | "delete"
                    }
                ],
                "explanation": str  # What was changed and why
            }
        """
        import anthropic

        task = context["task"]
        related_symbols = context.get("related_symbols", [])
        related_files = context.get("related_files", [])
        issue_context = context.get("issue_context")

        # Build system prompt
        system_prompt = """You are a Backend Worker Agent in the CodeFRAME autonomous development system.

Your role:
- Read the task description carefully
- Analyze existing codebase structure
- Write clean, tested Python code
- Follow project conventions and patterns

Output format:
Return a JSON object with this structure:
{
  "files": [
    {
      "path": "relative/path/to/file.py",
      "action": "create" | "modify" | "delete",
      "content": "file content here"
    }
  ],
  "explanation": "Brief explanation of changes"
}

Guidelines:
- Use strict TDD: Write tests before implementation
- Follow existing code style and patterns
- Keep functions small and focused
- Add comprehensive docstrings
- Handle errors gracefully"""

        # Build user prompt
        user_prompt_parts = [
            f"Task: {task.get('title', 'Untitled task')}",
            "",
            "Description:",
            task.get('description', 'No description provided'),
            ""
        ]

        if related_files:
            user_prompt_parts.append("Related Files:")
            for file in related_files[:10]:  # Limit to 10 files
                user_prompt_parts.append(f"- {file}")
            user_prompt_parts.append("")

        if related_symbols:
            user_prompt_parts.append("Related Symbols:")
            for symbol in related_symbols[:20]:  # Limit to 20 symbols
                user_prompt_parts.append(
                    f"- {symbol.name} ({symbol.type.value}) in {symbol.file_path}:{symbol.line_number}"
                )
            user_prompt_parts.append("")

        if issue_context:
            user_prompt_parts.append("Issue Context:")
            user_prompt_parts.append(f"- Issue: {issue_context.get('title', 'Unknown')}")
            user_prompt_parts.append(f"- Description: {issue_context.get('description', 'No description')}")
            user_prompt_parts.append("")

        user_prompt_parts.append("Please implement this task following TDD methodology.")
        user_prompt = "\n".join(user_prompt_parts)

        # Call Anthropic API
        client = anthropic.Anthropic(api_key=self.api_key)

        logger.debug(f"Calling Anthropic API for task {task.get('id', 'unknown')}")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Parse response
        response_text = response.content[0].text
        result = json.loads(response_text)

        logger.info(
            f"Generated {len(result.get('files', []))} file changes for task {task.get('id', 'unknown')}"
        )

        return result

    def apply_file_changes(self, files: List[Dict[str, Any]]) -> List[str]:
        """
        Apply file changes to disk.

        Safely writes, modifies, or deletes files with security validation
        and atomic operations.

        Args:
            files: List of file change dictionaries from generate_code()

        Returns:
            List of modified file paths

        Raises:
            SecurityError: If path traversal detected
            FileOperationError: If file operations fail

        Note: Implementation in Phase 3 (cf-41)
        """
        raise NotImplementedError("apply_file_changes() - Phase 3 implementation")

    def update_task_status(
        self,
        task_id: int,
        status: str,
        output: Optional[str] = None
    ) -> None:
        """
        Update task status in database.

        Args:
            task_id: Task ID
            status: New status ("in_progress", "completed", "failed")
            output: Optional execution output/error message

        Note: Implementation in Phase 3 (cf-41)
        """
        raise NotImplementedError("update_task_status() - Phase 3 implementation")

    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single task end-to-end.

        Orchestrates the full task execution pipeline:
        1. Update status to 'in_progress'
        2. Build context from codebase
        3. Generate code using LLM
        4. Apply file changes
        5. Update status to 'completed' or 'failed'

        Args:
            task: Task dictionary from fetch_next_task()

        Returns:
            Execution result:
            {
                "status": "completed" | "failed",
                "files_modified": List[str],
                "output": str,
                "error": Optional[str]
            }

        Raises:
            TaskExecutionError: If task fails after all retries

        Note: Implementation in Phase 3 (cf-41)
        """
        raise NotImplementedError("execute_task() - Phase 3 implementation")
