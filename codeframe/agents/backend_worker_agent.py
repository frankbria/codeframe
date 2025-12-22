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
from typing import Dict, Any, Optional, List
import json
import asyncio
from datetime import datetime
from pathlib import Path

from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.core.models import TaskStatus
from codeframe.providers.sdk_client import SDKClientWrapper


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
        db: Database,
        codebase_index: CodebaseIndex,
        provider: str = "claude",
        api_key: Optional[str] = None,
        project_root: str = ".",
        ws_manager=None,
        use_sdk: bool = True,
    ):
        """
        Initialize Backend Worker Agent.

        Args:
            db: Database instance for task/status management
            codebase_index: Indexed codebase for context retrieval
            provider: LLM provider (default: "claude")
            api_key: API key for LLM provider (uses ANTHROPIC_API_KEY env var if not provided)
            project_root: Project root directory for file operations (string path)
            ws_manager: Optional WebSocket ConnectionManager for real-time updates (cf-45)
            use_sdk: Whether to use Claude Agent SDK (default: True)

        Raises:
            ValueError: If database not initialized
        """
        self.db = db
        self.codebase_index = codebase_index
        self.provider = provider
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.project_root = project_root  # String path for SDK compatibility
        self.ws_manager = ws_manager
        self.use_sdk = use_sdk

        # Initialize SDK client if enabled
        if self.use_sdk:
            self.sdk_client = SDKClientWrapper(
                api_key=self.api_key,
                model="claude-sonnet-4-20250514",
                system_prompt=self._build_system_prompt(),
                allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
                cwd=self.project_root,
                permission_mode="acceptEdits",
            )
            # If SDK client is in fallback mode, disable SDK behavior for file operations
            if not getattr(self.sdk_client, "_use_sdk", True):
                logger.warning(
                    "SDK client initialized in fallback mode; disabling SDK behavior "
                    "for file operations to ensure actual file writes occur."
                )
                self.use_sdk = False
        else:
            self.sdk_client = None

        # Validate project exists
        if not self.db:
            raise ValueError("Database instance is required")

        logger.info(
            f"Initialized BackendWorkerAgent: provider={provider}, project_root={project_root}, "
            f"ws_enabled={ws_manager is not None}, use_sdk={use_sdk}"
        )

    def _build_system_prompt(self) -> str:
        """Build system prompt for backend agent."""
        return """You are a Backend Worker Agent in the CodeFRAME autonomous development system.

Your role:
- Read the task description carefully
- Analyze existing codebase structure
- Write clean, tested Python code
- Follow project conventions and patterns

Important: When writing files, use the Write tool. When reading files, use the Read tool.
The Write tool automatically creates parent directories and handles file safety.

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
        # Get project_id from current_task context
        project_id = (
            getattr(self.current_task, "project_id", None)
            if hasattr(self, "current_task") and self.current_task
            else None
        )
        if not project_id:
            logger.warning("No current task context available, unable to fetch tasks")
            return None

        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE project_id = ? AND status = ?
            ORDER BY priority ASC, workflow_step ASC, id ASC
            LIMIT 1
            """,
            (project_id, TaskStatus.PENDING.value),
        )

        row = cursor.fetchone()
        if row:
            task = dict(row)
            logger.info(
                f"Fetched task {task['id']}: {task['title']} "
                f"(priority={task['priority']}, workflow_step={task['workflow_step']})"
            )
            return task

        logger.debug(f"No pending tasks for project {project_id}")
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
            "issue_context": issue_context,
        }

    async def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate code using LLM based on context.

        Constructs prompts from context and calls Claude API (via SDK or direct)
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
        task = context["task"]
        related_symbols = context.get("related_symbols", [])
        related_files = context.get("related_files", [])
        issue_context = context.get("issue_context")

        # Build user prompt
        user_prompt_parts = [
            f"Task: {task.get('title', 'Untitled task')}",
            "",
            "Description:",
            task.get("description", "No description provided"),
            "",
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
            user_prompt_parts.append(f"- Issue: {issue_context.title}")
            user_prompt_parts.append(
                f"- Description: {issue_context.description}"
            )
            user_prompt_parts.append("")

        user_prompt_parts.append("Please implement this task following TDD methodology.")
        user_prompt_parts.append("")
        user_prompt_parts.append("Use the Write tool to create or modify files.")
        user_prompt_parts.append("Return JSON with the structure specified in the system prompt.")
        user_prompt = "\n".join(user_prompt_parts)

        logger.debug(
            f"Generating code for task {task.get('id', 'unknown')} (use_sdk={self.use_sdk})"
        )

        if self.use_sdk and self.sdk_client:
            # SDK path - let SDK handle file operations via tools
            response = await self.sdk_client.send_message(
                [{"role": "user", "content": user_prompt}]
            )

            # Parse JSON response from SDK
            response_text = response.get("content", "{}")
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # Fallback if SDK doesn't return JSON
                result = {
                    "files": [],
                    "explanation": "SDK execution completed but no structured output returned",
                }
        else:
            # Fallback to direct Anthropic API
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=self.api_key)

            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=self._build_system_prompt(),
                messages=[{"role": "user", "content": user_prompt}],
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

        When using SDK (use_sdk=True), files have already been written by the SDK's
        Write tool, so this method just validates and returns paths.

        When not using SDK, safely writes, modifies, or deletes files with security
        validation and atomic operations.

        Args:
            files: List of file change dictionaries from generate_code()

        Returns:
            List of modified file paths

        Raises:
            ValueError: If path traversal or absolute path detected
            FileNotFoundError: If file to modify/delete doesn't exist (non-SDK mode only)
        """
        from pathlib import Path

        modified_paths = []

        for file_spec in files:
            path = file_spec["path"]
            action = file_spec["action"]
            content = file_spec.get("content", "")

            # Security: Validate path (no absolute paths, no traversal)
            path_obj = Path(path)
            if path_obj.is_absolute():
                raise ValueError(f"Absolute path not allowed: {path}")

            # Resolve path and check it stays within project_root
            project_root_path = Path(self.project_root)
            target_path = (project_root_path / path).resolve()
            try:
                target_path.relative_to(project_root_path.resolve())
            except ValueError:
                raise ValueError(f"Path traversal detected: {path}")

            if self.use_sdk:
                # SDK mode: Files already written by SDK Write tool
                # Just validate and track paths
                logger.info(f"SDK handled {action} for: {path}")
                modified_paths.append(path)
            else:
                # Non-SDK mode: Perform file operations directly
                if action == "create" or action == "modify":
                    if action == "modify" and not target_path.exists():
                        raise FileNotFoundError(f"Cannot modify non-existent file: {path}")

                    # Create parent directories if needed
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Write file
                    target_path.write_text(content, encoding="utf-8")
                    logger.info(f"{action.capitalize()}d file: {path}")

                elif action == "delete":
                    if not target_path.exists():
                        raise FileNotFoundError(f"Cannot delete non-existent file: {path}")

                    target_path.unlink()
                    logger.info(f"Deleted file: {path}")

                modified_paths.append(path)

        logger.info(f"Applied {len(modified_paths)} file changes (sdk={self.use_sdk})")
        return modified_paths

    def update_task_status(
        self,
        task_id: int,
        status: str,
        output: Optional[str] = None,
        agent_id: str = "backend-worker",
    ) -> None:
        """
        Update task status in database and broadcast via WebSocket (cf-45).

        Args:
            task_id: Task ID
            status: New status ("in_progress", "completed", "failed")
            output: Optional execution output/error message
            agent_id: Agent identifier for broadcast
        """
        from datetime import datetime

        cursor = self.db.conn.cursor()

        # Update status and completed_at if status is completed
        if status == TaskStatus.COMPLETED.value:
            cursor.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                (status, datetime.now().isoformat(), task_id),
            )
        else:
            cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))

        self.db.conn.commit()
        logger.info(f"Updated task {task_id} to status: {status}")

        if output:
            logger.debug(f"Task {task_id} output: {output[:200]}")

    async def _run_and_check_linting(self, task: Dict[str, Any], files_modified: List[str]) -> None:
        """
        Run linting on modified files and create blocker if critical errors found (T111).

        This method executes linting on Python files modified during task execution,
        stores results in the database, and creates a blocker if critical errors are found.

        Args:
            task: Task dictionary
            files_modified: List of file paths that were modified

        Raises:
            ValueError: If linting fails with critical errors (blocker created)
        """
        if not files_modified:
            logger.debug("No files modified, skipping linting")
            return

        task_id = task["id"]

        # Filter for Python files only
        python_files = [Path(f) for f in files_modified if f.endswith(".py")]

        if not python_files:
            logger.debug("No Python files modified, skipping linting")
            return

        try:
            from codeframe.testing.lint_runner import LintRunner
            from codeframe.lib.lint_utils import format_lint_blocker

            # Initialize LintRunner
            lint_runner = LintRunner(self.project_root)

            logger.info(f"Running linting on {len(python_files)} Python files for task {task_id}")

            # Run linting
            lint_results = await lint_runner.run_lint(python_files)

            # Store results in database
            for result in lint_results:
                self.db.create_lint_result(
                    task_id=task_id,
                    linter=result.linter,
                    error_count=result.error_count,
                    warning_count=result.warning_count,
                    files_linted=result.files_linted,
                    output=result.output,
                )

            # Check quality gate
            if lint_runner.has_critical_errors(lint_results):
                # Create blocker with lint findings
                blocker_description = format_lint_blocker(lint_results)
                total_errors = sum(r.error_count for r in lint_results)

                # Format question with title and description combined
                question = (
                    f"Linting failed: {total_errors} critical errors\n\n{blocker_description}"
                )

                self.db.create_blocker(
                    agent_id=self.agent_id,
                    project_id=task["project_id"],
                    task_id=task_id,
                    blocker_type="SYNC",
                    question=question,
                )

                logger.error(f"Task {task_id} blocked by {total_errors} lint errors")

                # Broadcast lint failure via WebSocket (T119)
                if self.ws_manager:
                    try:
                        from codeframe.ui.websocket_broadcasts import broadcast_to_project

                        project_id = task.get("project_id") or (
                            self.current_task.project_id
                            if hasattr(self, "current_task") and self.current_task
                            else None
                        )
                        if project_id:
                            await broadcast_to_project(
                                self.ws_manager,
                                project_id,
                                {
                                    "type": "lint_failed",
                                    "task_id": task_id,
                                    "error_count": total_errors,
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            )
                    except Exception as e:
                        logger.debug(f"Failed to broadcast lint failure: {e}")

                raise ValueError(f"Linting failed - {total_errors} critical errors found")

            # Log warnings (non-blocking)
            total_warnings = sum(r.warning_count for r in lint_results)
            if total_warnings > 0:
                logger.warning(f"Task {task_id}: {total_warnings} lint warnings (non-blocking)")

            # Broadcast lint success via WebSocket (T119)
            if self.ws_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_to_project

                    project_id = task.get("project_id") or (
                        self.current_task.project_id
                        if hasattr(self, "current_task") and self.current_task
                        else None
                    )
                    if project_id:
                        await broadcast_to_project(
                            self.ws_manager,
                            project_id,
                            {
                                "type": "lint_completed",
                                "task_id": task_id,
                                "error_count": 0,
                                "warning_count": total_warnings,
                                "timestamp": datetime.utcnow().isoformat(),
                            },
                        )
                except Exception as e:
                    logger.debug(f"Failed to broadcast lint success: {e}")

        except ImportError:
            logger.warning("LintRunner not available - skipping lint check")
        except Exception as e:
            # Don't block task on lint infrastructure failure (unless it's our ValueError)
            if isinstance(e, ValueError) and "Linting failed" in str(e):
                raise
            logger.error(f"Lint check failed: {e}")

    async def _run_and_record_tests(self, task_id: int) -> None:
        """
        Run tests and record results in database (cf-42 Phase 3).

        Uses TestRunner to execute pytest on the project, parses results,
        and stores them in the database for self-correction (cf-43) and
        tracking purposes.

        Args:
            task_id: Task ID for which to record test results

        Note:
            This method does not raise exceptions if tests fail - it only
            records the results. Self-correction (cf-43) will handle failures.
        """
        from codeframe.testing.test_runner import TestRunner
        import json

        # Initialize test runner with project root
        test_runner = TestRunner(project_root=self.project_root)

        # Run tests
        logger.info(f"Running tests for task {task_id}")
        test_result = test_runner.run_tests()

        # Convert output dict to JSON string if it's not already a string
        output_str = None
        if test_result.output is not None:
            if isinstance(test_result.output, dict):
                output_str = json.dumps(test_result.output)
            else:
                output_str = str(test_result.output)

        # Record results in database
        self.db.create_test_result(
            task_id=task_id,
            status=test_result.status,
            passed=test_result.passed,
            failed=test_result.failed,
            errors=test_result.errors,
            skipped=test_result.skipped,
            duration=test_result.duration,
            output=output_str,
        )

        logger.info(
            f"Test results for task {task_id}: {test_result.status} - "
            f"{test_result.passed}/{test_result.total} passed, "
            f"{test_result.failed} failed, {test_result.errors} errors"
        )

        # Broadcast test results via WebSocket (cf-45)
        if self.ws_manager:
            try:
                from codeframe.ui.websocket_broadcasts import (
                    broadcast_test_result,
                    broadcast_activity_update,
                )

                # Broadcast test result
                project_id = (
                    self.current_task.project_id
                    if hasattr(self, "current_task") and self.current_task
                    else None
                )
                if project_id:
                    await broadcast_test_result(
                        self.ws_manager,
                        project_id,
                        task_id,
                        test_result.status,
                        test_result.passed,
                        test_result.failed,
                        test_result.errors,
                        test_result.total,
                        test_result.duration,
                    )

                # Broadcast activity update
                if test_result.status == "passed":
                    activity_message = f"All tests passed for task #{task_id} ({test_result.passed}/{test_result.total})"
                else:
                    activity_message = f"Tests {test_result.status} for task #{task_id} ({test_result.passed}/{test_result.total} passed)"

                if project_id:
                    await broadcast_activity_update(
                        self.ws_manager,
                        project_id,
                        "tests_completed",
                        "backend-worker",
                        activity_message,
                        task_id=task_id,
                    )
            except Exception as e:
                logger.debug(f"Failed to broadcast test result: {e}")

    async def _attempt_self_correction(
        self, task: Dict[str, Any], test_result_id: int, attempt_number: int
    ) -> Dict[str, Any]:
        """
        Attempt to fix failing tests by analyzing errors and regenerating code.

        This implements the self-correction loop (cf-43) where the agent:
        1. Analyzes test failure output
        2. Generates code fixes
        3. Applies the fixes
        4. Returns the result

        Args:
            task: Task dictionary
            test_result_id: ID of the failed test result
            attempt_number: Which correction attempt this is (1-3)

        Returns:
            Dict with:
                - "error_analysis": str - Analysis of what went wrong
                - "fix_description": str - Description of the fix
                - "code_changes": List[Dict] - File changes to apply
        """
        task_id = task["id"]
        logger.info(f"Attempting self-correction #{attempt_number} for task {task_id}")

        # Get the test result to analyze
        test_results = self.db.get_test_results_by_task(task_id)
        latest_result = test_results[-1] if test_results else None

        if not latest_result:
            raise RuntimeError(f"No test results found for task {task_id}")

        # Build context with test failure information
        context = self.build_context(task)
        context["test_failure"] = {
            "status": latest_result["status"],
            "failed": latest_result["failed"],
            "errors": latest_result["errors"],
            "output": latest_result["output"],
        }
        context["attempt_number"] = attempt_number

        # Generate corrective code using LLM
        # Modify the prompt to focus on fixing the specific test failures
        correction_prompt = f"""
Previous attempt failed with test errors. Please analyze the failures and fix them.

Test Results:
- Status: {latest_result['status']}
- Failed: {latest_result['failed']} tests
- Errors: {latest_result['errors']} errors

Test Output:
{latest_result['output']}

This is correction attempt #{attempt_number} of 3.

Please:
1. Analyze what went wrong
2. Identify the root cause
3. Generate fixes for the failing code
4. Return the corrected files

Focus ONLY on fixing the test failures. Do not make unrelated changes.
"""

        # Generate code with correction context
        try:
            # Add correction context to the generation
            context["correction_mode"] = True
            context["correction_prompt"] = correction_prompt

            generation_result = await self.generate_code(context)

            # Extract analysis from generation output
            error_analysis = (
                latest_result["output"][:500]
                if latest_result["output"]
                else "Test failures detected"
            )
            fix_description = generation_result.get("explanation", "Applied code corrections")

            return {
                "error_analysis": error_analysis,
                "fix_description": fix_description,
                "code_changes": generation_result["files"],
            }

        except Exception as e:
            logger.error(f"Self-correction attempt {attempt_number} failed: {e}")
            return {
                "error_analysis": str(e),
                "fix_description": f"Correction attempt failed: {e}",
                "code_changes": [],
            }

    async def _self_correction_loop(
        self, task: Dict[str, Any], initial_test_result_id: int
    ) -> bool:
        """
        Execute self-correction loop to fix failing tests (cf-43).

        Attempts to fix failing tests up to 3 times. For each attempt:
        1. Analyze test failures
        2. Generate corrective code
        3. Apply changes
        4. Re-run tests
        5. Record correction attempt

        If tests pass after any attempt, returns True.
        If all 3 attempts fail, escalates to blocker and returns False.

        Args:
            task: Task dictionary
            initial_test_result_id: ID of the failed test result that triggered correction

        Returns:
            True if tests eventually pass, False if all attempts exhausted
        """
        task_id = task["id"]
        max_attempts = 3

        for attempt_num in range(1, max_attempts + 1):
            logger.info(f"Self-correction attempt {attempt_num}/{max_attempts} for task {task_id}")

            # Broadcast correction attempt start (cf-45)
            if self.ws_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_correction_attempt

                    project_id = (
                        self.current_task.project_id
                        if hasattr(self, "current_task") and self.current_task
                        else None
                    )
                    if project_id:
                        await broadcast_correction_attempt(
                            self.ws_manager,
                            project_id,
                            task_id,
                            attempt_num,
                            max_attempts,
                            "in_progress",
                        )
                except Exception as e:
                    logger.debug(f"Failed to broadcast correction attempt: {e}")

            # Attempt correction
            correction = await self._attempt_self_correction(
                task, initial_test_result_id, attempt_num
            )

            # Record the correction attempt
            attempt_id = self.db.create_correction_attempt(
                task_id=task_id,
                attempt_number=attempt_num,
                error_analysis=correction["error_analysis"],
                fix_description=correction["fix_description"],
                code_changes=str(correction.get("code_changes", [])),
                test_result_id=initial_test_result_id,
            )
            logger.info(f"Recorded correction attempt {attempt_id}")

            # Apply the code changes if any
            if correction["code_changes"]:
                try:
                    files_modified = self.apply_file_changes(correction["code_changes"])
                    logger.info(f"Applied corrections to {len(files_modified)} files")
                except Exception as e:
                    logger.error(f"Failed to apply corrections: {e}")
                    continue

            # Re-run tests
            await self._run_and_record_tests(task_id)

            # Check if tests now pass
            test_results = self.db.get_test_results_by_task(task_id)
            latest_result = test_results[-1] if test_results else None

            if latest_result and latest_result["status"] == "passed":
                logger.info(f"Self-correction successful after {attempt_num} attempt(s)!")

                # Broadcast success (cf-45)
                if self.ws_manager:
                    try:
                        from codeframe.ui.websocket_broadcasts import (
                            broadcast_correction_attempt,
                            broadcast_activity_update,
                        )

                        if project_id:
                            await broadcast_correction_attempt(
                                self.ws_manager,
                                project_id,
                                task_id,
                                attempt_num,
                                max_attempts,
                                "success",
                            )
                            await broadcast_activity_update(
                                self.ws_manager,
                                project_id,
                                "correction_success",
                                "backend-worker",
                                f"Self-correction successful after {attempt_num} attempt(s) for task #{task_id}",
                                task_id=task_id,
                            )
                    except Exception as e:
                        logger.debug(f"Failed to broadcast correction success: {e}")

                return True

            logger.warning(
                f"Attempt {attempt_num} did not resolve failures. "
                f"Status: {latest_result['status'] if latest_result else 'unknown'}"
            )

            # Broadcast attempt failure (cf-45)
            if self.ws_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_correction_attempt

                    error_summary = (
                        f"Status: {latest_result['status'] if latest_result else 'unknown'}"
                    )
                    if project_id:
                        await broadcast_correction_attempt(
                            self.ws_manager,
                            project_id,
                            task_id,
                            attempt_num,
                            max_attempts,
                            "failed",
                            error_summary=error_summary,
                        )
                except Exception as e:
                    logger.debug(f"Failed to broadcast correction failure: {e}")

        # All attempts exhausted - escalate to blocker
        logger.error(
            f"Self-correction failed after {max_attempts} attempts for task {task_id}. "
            f"Escalating to blocker."
        )

        # Create blocker for manual intervention
        # Get project_id from task dict (agents are project-agnostic at creation)
        project_id = task.get("project_id")
        agent_id = getattr(self, "id", None) or getattr(self, "agent_id", "backend-worker")
        question = (
            f"Tests still failing after {max_attempts} self-correction attempts. "
            "Please review the test failures and correction attempts, then provide manual fix."
        )

        if project_id:
            self.db.create_blocker(
                agent_id=agent_id,
                project_id=project_id,
                task_id=task_id,
                blocker_type="SYNC",
                question=question,
            )
        else:
            logger.warning(
                f"Cannot create blocker for task {task_id}: project_id not found in task"
            )

        return False

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single task end-to-end.

        Orchestrates the full task execution pipeline:
        1. Update status to 'in_progress'
        2. Build context from codebase
        3. Generate code using LLM
        4. Apply file changes
        5. Run tests (cf-42)
        6. Self-correct if tests fail (cf-43)
        7. Update status to 'completed' or 'failed'

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
        """
        task_id = task["id"]
        files_modified = []
        error = None

        try:
            # 1. Update status to in_progress
            self.update_task_status(task_id, TaskStatus.IN_PROGRESS.value)
            logger.info(f"Starting execution of task {task_id}: {task['title']}")

            # 2. Build context from codebase
            context = self.build_context(task)

            # 3. Generate code using LLM
            generation_result = await self.generate_code(context)

            # 4. Apply file changes
            files_modified = self.apply_file_changes(generation_result["files"])

            # 4.5. Run linting on modified files (Sprint 9 Phase 5: T111)
            await self._run_and_check_linting(task, files_modified)

            # 5. Run tests (cf-42 Phase 3)
            await self._run_and_record_tests(task_id)

            # 6. Check test results and self-correct if needed (cf-43)
            test_results = self.db.get_test_results_by_task(task_id)
            latest_test = test_results[-1] if test_results else None

            if latest_test and latest_test["status"] != "passed":
                logger.warning(
                    f"Tests failed for task {task_id}. Status: {latest_test['status']}. "
                    f"Starting self-correction loop..."
                )

                # Attempt self-correction (up to 3 attempts)
                correction_successful = await self._self_correction_loop(task, latest_test["id"])

                if not correction_successful:
                    # Self-correction failed - mark task as blocked
                    self.update_task_status(
                        task_id,
                        TaskStatus.BLOCKED.value,
                        output="Tests still failing after 3 correction attempts. Manual intervention required.",
                    )

                    return {
                        "status": "blocked",
                        "files_modified": files_modified,
                        "output": "Self-correction exhausted. See blocker for details.",
                        "error": "Tests failed after 3 correction attempts",
                    }

            # 7. Update status to completed
            output = generation_result.get("explanation", "Task completed")
            self.update_task_status(task_id, TaskStatus.COMPLETED.value, output=output)

            # Broadcast task completion activity (cf-45)
            if self.ws_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_activity_update

                    project_id = (
                        self.current_task.project_id
                        if hasattr(self, "current_task") and self.current_task
                        else None
                    )
                    if project_id:
                        await broadcast_activity_update(
                            self.ws_manager,
                            project_id,
                            "task_completed",
                            "backend-worker",
                            f"Completed task #{task_id}: {task['title']}",
                            task_id=task_id,
                        )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task completion: {e}")

            # T075: Auto-commit task changes after successful completion
            if hasattr(self, "git_workflow") and self.git_workflow and files_modified:
                try:
                    commit_sha = self.git_workflow.commit_task_changes(
                        task=task,
                        files_modified=files_modified,
                        agent_id=getattr(self, "agent_id", "backend-worker"),
                    )

                    # T082: Record commit SHA in database
                    if commit_sha:
                        self.db.update_task_commit_sha(task_id, commit_sha)
                        logger.info(f"Task {task_id} committed with SHA: {commit_sha[:7]}")
                except Exception as e:
                    # T080: Graceful degradation - log warning but don't block task completion
                    logger.warning(f"Auto-commit failed for task {task_id} (non-blocking): {e}")

            logger.info(f"Successfully completed task {task_id}")
            return {
                "status": "completed",
                "files_modified": files_modified,
                "output": output,
                "error": None,
            }

        except Exception as e:
            # Update status to failed
            error = f"{type(e).__name__}: {str(e)}"
            self.update_task_status(task_id, TaskStatus.FAILED.value, output=error)

            logger.error(f"Task {task_id} failed: {error}")
            return {
                "status": "failed",
                "files_modified": files_modified,
                "output": "",
                "error": error,
            }

    async def create_blocker(
        self, question: str, blocker_type: str = "ASYNC", task_id: Optional[int] = None
    ) -> int:
        """
        Create a blocker when agent needs human input (049-human-in-loop, T035).

        The agent determines blocker classification at creation time:
        - SYNC: Critical blocker requiring immediate attention (pauses dependent work)
        - ASYNC: Informational/preferential question (allows parallel work to continue)

        Args:
            question: Question for the user (max 2000 chars)
            blocker_type: 'SYNC' (critical) or 'ASYNC' (clarification), default 'ASYNC'
            task_id: Associated task ID (defaults to self.current_task_id)

        Returns:
            Blocker ID

        Raises:
            ValueError: If question is empty, too long, or blocker_type is invalid
        """
        if not question or len(question.strip()) == 0:
            raise ValueError("Question cannot be empty")

        if len(question) > 2000:
            raise ValueError("Question exceeds 2000 character limit")

        # Validate blocker type (T035: blocker type classification)
        valid_types = ["SYNC", "ASYNC"]
        if blocker_type not in valid_types:
            raise ValueError(f"Invalid blocker_type '{blocker_type}'. Must be 'SYNC' or 'ASYNC'")

        # Use provided task_id or fall back to current task
        blocker_task_id = task_id if task_id is not None else getattr(self, "current_task_id", None)

        # Get project_id from current_task
        project_id = (
            self.current_task.project_id
            if hasattr(self, "current_task") and self.current_task
            else None
        )
        if not project_id:
            raise ValueError("Cannot create blocker without project context")

        # Get agent ID from self or use class name
        agent_id = getattr(self, "id", None) or "backend-worker"

        # Create blocker in database
        blocker_id = self.db.create_blocker(
            agent_id=agent_id,
            project_id=project_id,
            task_id=blocker_task_id,
            blocker_type=blocker_type,
            question=question.strip(),
        )

        logger.info(f"Blocker {blocker_id} created by {agent_id}: {question[:50]}...")

        # Broadcast blocker creation via WebSocket (if manager available)
        if self.ws_manager:
            try:
                from codeframe.ui.websocket_broadcasts import broadcast_blocker_created

                await broadcast_blocker_created(
                    manager=self.ws_manager,
                    project_id=project_id,
                    blocker_id=blocker_id,
                    agent_id=agent_id,
                    task_id=blocker_task_id,
                    blocker_type=blocker_type,
                    question=question.strip(),
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast blocker creation: {e}")

        # Send webhook notification for SYNC blockers (T042: 049-human-in-loop)
        if blocker_type == "SYNC":
            try:
                from datetime import datetime
                from codeframe.core.config import Config
                from codeframe.notifications.webhook import WebhookNotificationService
                from codeframe.core.models import BlockerType

                # Get webhook URL from config
                config = Config(Path.cwd())
                global_config = config.get_global()
                webhook_url = global_config.blocker_webhook_url

                if webhook_url:
                    # Initialize webhook service
                    webhook_service = WebhookNotificationService(
                        webhook_url=webhook_url,
                        timeout=5,
                        dashboard_base_url=f"http://{global_config.api_host}:{global_config.api_port}",
                    )

                    # Send notification (fire-and-forget)
                    webhook_service.send_blocker_notification_background(
                        blocker_id=blocker_id,
                        question=question.strip(),
                        agent_id=agent_id,
                        task_id=blocker_task_id or 0,
                        blocker_type=BlockerType.SYNC,
                        created_at=datetime.now(),
                    )
                    logger.debug(f"Webhook notification queued for SYNC blocker {blocker_id}")
                else:
                    logger.debug(
                        "BLOCKER_WEBHOOK_URL not configured, skipping webhook notification"
                    )

            except Exception as e:
                # Log error but don't block blocker creation
                logger.warning(f"Failed to send webhook notification for blocker {blocker_id}: {e}")

        return blocker_id

    async def wait_for_blocker_resolution(
        self, blocker_id: int, poll_interval: float = 5.0, timeout: float = 600.0
    ) -> str:
        """
        Wait for a blocker to be resolved by polling the database (049-human-in-loop, T028).

        Polls the database at regular intervals until the blocker status changes to RESOLVED
        or the timeout is reached. When resolved, broadcasts an agent_resumed event and returns
        the answer.

        Args:
            blocker_id: ID of the blocker to wait for
            poll_interval: Seconds between database polls (default: 5.0)
            timeout: Maximum seconds to wait before raising TimeoutError (default: 600.0)

        Returns:
            The answer provided by the user when the blocker was resolved

        Raises:
            TimeoutError: If blocker not resolved within timeout period
            ValueError: If blocker not found

        Example:
            blocker_id = await agent.create_blocker("Should I use SQLite?")
            answer = await agent.wait_for_blocker_resolution(blocker_id)
            # answer = "Use SQLite to match existing codebase"
        """
        import time

        start_time = time.time()
        elapsed = 0.0

        logger.info(f"Waiting for blocker {blocker_id} resolution (timeout: {timeout}s)")

        while elapsed < timeout:
            # Poll database for blocker status
            blocker = self.db.get_blocker(blocker_id)

            if not blocker:
                raise ValueError(f"Blocker {blocker_id} not found")

            # Check if resolved
            if blocker.get("status") == "RESOLVED" and blocker.get("answer"):
                answer = blocker["answer"]
                logger.info(f"Blocker {blocker_id} resolved: {answer[:50]}...")

                # Broadcast agent_resumed event via WebSocket (if manager available)
                if self.ws_manager:
                    try:
                        from codeframe.ui.websocket_broadcasts import broadcast_agent_resumed

                        project_id = (
                            self.current_task.project_id
                            if hasattr(self, "current_task") and self.current_task
                            else None
                        )
                        if project_id:
                            await broadcast_agent_resumed(
                                manager=self.ws_manager,
                                project_id=project_id,
                                agent_id=getattr(self, "id", None) or "backend-worker",
                                task_id=getattr(self, "current_task_id", None)
                                or blocker.get("task_id"),
                                blocker_id=blocker_id,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to broadcast agent_resumed: {e}")

                return answer

            # Sleep for poll interval
            await asyncio.sleep(poll_interval)
            elapsed = time.time() - start_time

        # Timeout reached
        raise TimeoutError(f"Blocker {blocker_id} not resolved within {timeout} seconds")

    async def create_blocker_and_wait(
        self,
        question: str,
        context: Dict[str, Any],
        blocker_type: str = "ASYNC",
        task_id: Optional[int] = None,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Create blocker, wait for resolution, and inject answer into context (049-human-in-loop, T031).

        This is a convenience method that orchestrates the full blocker workflow:
        1. Create blocker with question
        2. Wait for user to provide answer
        3. Inject answer into execution context
        4. Return enriched context for continued execution

        The answer is appended to the task context following the pattern from research.md:
        "Previous blocker question: {question}\nUser answer: {answer}\nContinue task execution with this answer."

        Args:
            question: Question for user (max 2000 chars)
            context: Current execution context from build_context()
            blocker_type: SYNC (critical) or ASYNC (clarification)
            task_id: Associated task (defaults to context['task']['id'])
            poll_interval: Seconds between database polls (default: 5.0)
            timeout: Maximum seconds to wait (default: 600.0)

        Returns:
            Enriched context dictionary with blocker_answer field:
            {
                **context,  # Original context fields
                "blocker_answer": str,  # The answer from user
                "blocker_question": str,  # The original question
                "blocker_id": int  # The blocker ID
            }

        Raises:
            TimeoutError: If blocker not resolved within timeout
            ValueError: If question invalid or blocker not found

        Example:
            # During task execution, agent encounters uncertainty
            context = self.build_context(task)

            # Ask user for guidance
            enriched_context = await agent.create_blocker_and_wait(
                question="Should I use SQLite or PostgreSQL for this feature?",
                context=context,
                blocker_type="SYNC"
            )

            # Continue execution with user's answer in context
            result = await self.generate_code(enriched_context)
            # The answer "Use SQLite to match existing codebase" is now part of context
        """
        # Extract task_id from context if not provided
        if task_id is None:
            task_id = context.get("task", {}).get("id")

        # 1. Create blocker
        blocker_id = await self.create_blocker(
            question=question, blocker_type=blocker_type, task_id=task_id
        )

        logger.info(f"Created blocker {blocker_id}, waiting for resolution...")

        # 2. Wait for user to resolve blocker
        answer = await self.wait_for_blocker_resolution(
            blocker_id=blocker_id, poll_interval=poll_interval, timeout=timeout
        )

        logger.info(f"Blocker {blocker_id} resolved with answer: {answer[:50]}...")

        # 3. Inject answer into context
        enriched_context = {
            **context,
            "blocker_answer": answer,
            "blocker_question": question,
            "blocker_id": blocker_id,
        }

        return enriched_context
