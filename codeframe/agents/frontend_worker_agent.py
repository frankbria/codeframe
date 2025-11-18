"""
Frontend Worker Agent for React/TypeScript component generation (Sprint 4: cf-48).

This agent specializes in generating React components with TypeScript,
following project conventions (Tailwind CSS, functional components).
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from anthropic import AsyncAnthropic

from codeframe.core.models import Task, AgentMaturity
from codeframe.agents.worker_agent import WorkerAgent

logger = logging.getLogger(__name__)


class FrontendWorkerAgent(WorkerAgent):
    """
    Frontend Worker Agent - Specialized in React/TypeScript component generation.

    Capabilities:
    - Generate functional React components with TypeScript
    - Create TypeScript interfaces for props and state
    - Follow project conventions (Tailwind CSS, functional components)
    - Auto-update imports and exports
    - Integrate with WebSocket broadcasts for real-time status
    """

    def __init__(
        self,
        agent_id: str,
        provider: str = "anthropic",
        maturity: AgentMaturity = AgentMaturity.D1,
        api_key: Optional[str] = None,
        websocket_manager=None,
        db=None,
        project_id: Optional[int] = None,
    ):
        """
        Initialize Frontend Worker Agent.

        Args:
            agent_id: Unique agent identifier
            provider: LLM provider (default: anthropic)
            maturity: Agent maturity level
            api_key: API key for LLM provider (uses ANTHROPIC_API_KEY env var if not provided)
            websocket_manager: WebSocket connection manager for broadcasts
            db: Database instance for blocker management (optional)
            project_id: Project ID for blocker context (optional)
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="frontend",
            provider=provider,
            project_id=project_id or 1,  # Default to 1 if not provided
            maturity=maturity,
            system_prompt=self._build_system_prompt(),
            db=db,
        )
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = AsyncAnthropic(api_key=self.api_key) if self.api_key else None
        self.websocket_manager = websocket_manager
        self.project_root = Path(__file__).parent.parent.parent  # codeframe/
        self.web_ui_root = self.project_root / "web-ui"
        self.components_dir = self.web_ui_root / "src" / "components"

    def _build_system_prompt(self) -> str:
        """Build system prompt for frontend-specific tasks."""
        return """You are a Frontend Worker Agent specializing in React/TypeScript development.

Your responsibilities:
1. Generate clean, functional React components using TypeScript
2. Follow project conventions:
   - Functional components with hooks (not class components)
   - Tailwind CSS for styling (no inline styles, CSS modules, or styled-components)
   - TypeScript interfaces for props and state
   - Proper prop destructuring
3. Create well-typed TypeScript interfaces
4. Write accessible, semantic HTML
5. Follow React best practices (key props, useCallback, useMemo when appropriate)

Output format:
- Provide complete, working code
- Include all necessary imports
- Add brief comments for complex logic only
- Ensure proper TypeScript typing (no 'any' types)
"""

    async def execute_task(self, task: Task, project_id: int = 1) -> Dict[str, Any]:
        """
        Execute frontend task: generate React component.

        Args:
            task: Task to execute with component specification
            project_id: Project ID for WebSocket broadcasts

        Returns:
            Execution result with status and output
        """
        self.current_task = task

        try:
            # Broadcast task started
            if self.websocket_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_task_status

                    await broadcast_task_status(
                        self.websocket_manager,
                        project_id,
                        task.id,
                        "in_progress",
                        agent_id=self.agent_id,
                        progress=0,
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task status: {e}")

            logger.info(f"Frontend agent {self.agent_id} executing task {task.id}: {task.title}")

            # Parse task description for component spec
            component_spec = self._parse_component_spec(task.description)

            # Generate component code
            component_code = await self._generate_react_component(component_spec)

            # Generate TypeScript types if needed
            if component_spec.get("generate_types"):
                types_code = self._generate_typescript_types(component_spec)
            else:
                types_code = None

            # Create files in correct location
            file_paths = self._create_component_files(
                component_spec["name"], component_code, types_code
            )

            # Update imports/exports
            self._update_imports_exports(component_spec["name"], file_paths)

            # Run linting on created files (Sprint 9 Phase 5: T112)
            await self._run_and_check_linting(task, file_paths, project_id)

            # Broadcast completion
            if self.websocket_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_task_status

                    await broadcast_task_status(
                        self.websocket_manager,
                        project_id,
                        task.id,
                        "completed",
                        agent_id=self.agent_id,
                        progress=100,
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task status: {e}")

            logger.info(f"Frontend agent {self.agent_id} completed task {task.id}")

            # T076: Auto-commit task changes after successful completion
            if hasattr(self, "git_workflow") and self.git_workflow and file_paths:
                try:
                    # Convert file_paths dict to list of paths
                    files_modified = [path for path in file_paths.values()]

                    # Convert Task object to dict for git_workflow
                    task_dict = {
                        "id": task.id,
                        "project_id": task.project_id,
                        "task_number": task.task_number,
                        "title": task.title,
                        "description": task.description,
                    }

                    commit_sha = self.git_workflow.commit_task_changes(
                        task=task_dict, files_modified=files_modified, agent_id=self.agent_id
                    )

                    # T082: Record commit SHA in database
                    if commit_sha and self.db:
                        self.db.update_task_commit_sha(task.id, commit_sha)
                        logger.info(f"Task {task.id} committed with SHA: {commit_sha[:7]}")
                except Exception as e:
                    # T080: Graceful degradation - log warning but don't block task completion
                    logger.warning(f"Auto-commit failed for task {task.id} (non-blocking): {e}")

            return {
                "status": "completed",
                "output": f"Generated component: {component_spec['name']}",
                "files_created": file_paths,
                "component_name": component_spec["name"],
            }

        except Exception as e:
            logger.error(f"Frontend agent {self.agent_id} failed task {task.id}: {e}")

            # Broadcast failure
            if self.websocket_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_task_status

                    await broadcast_task_status(
                        self.websocket_manager,
                        project_id,
                        task.id,
                        "failed",
                        agent_id=self.agent_id,
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task status: {e}")

            return {"status": "failed", "output": str(e), "error": str(e)}

    def _parse_component_spec(self, description: str) -> Dict[str, Any]:
        """
        Parse task description to extract component specification.

        Args:
            description: Task description (plain text or JSON)

        Returns:
            Component specification dict
        """
        # Try parsing as JSON first
        try:
            spec = json.loads(description)
            if "name" in spec:
                return spec
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: extract from plain text
        # Simple heuristic: first word/phrase is component name
        lines = description.strip().split("\n")
        name = "NewComponent"

        # Look for common patterns
        for line in lines:
            if "component:" in line.lower():
                name = line.split(":")[-1].strip()
                break
            elif "create" in line.lower() and "component" in line.lower():
                # Extract PascalCase words (skip "Create" and "component" keywords)
                words = line.split()
                for i, word in enumerate(words):
                    # Skip keywords and find PascalCase component name
                    if (
                        word[0].isupper()
                        and word.lower() not in ["create", "component", "a", "the"]
                        and "component" not in word.lower()
                    ):
                        name = word
                        break

        return {
            "name": name,
            "description": description,
            "generate_types": True,
            "use_tailwind": True,
        }

    async def _generate_react_component(self, spec: Dict[str, Any]) -> str:
        """
        Generate React component code using Claude API.

        Args:
            spec: Component specification

        Returns:
            Component code as string
        """
        if not self.client:
            # Fallback: generate basic component template
            return self._generate_basic_component_template(spec)

        prompt = f"""Generate a React functional component with the following specification:

Component Name: {spec['name']}
Description: {spec.get('description', 'A new React component')}

Requirements:
- Functional component with TypeScript
- Use Tailwind CSS for styling
- Include proper TypeScript interfaces for props
- Follow React best practices
- Add accessibility attributes (ARIA) where appropriate

Provide ONLY the component code, no explanations."""

        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract code from response
            code = response.content[0].text

            # Remove markdown code blocks if present
            if "```" in code:
                code = code.split("```")[1]
                if code.startswith("tsx") or code.startswith("typescript"):
                    code = "\n".join(code.split("\n")[1:])

            return code.strip()

        except Exception as e:
            logger.error(f"Failed to generate component with Claude API: {e}")
            return self._generate_basic_component_template(spec)

    def _generate_basic_component_template(self, spec: Dict[str, Any]) -> str:
        """
        Generate basic component template as fallback.

        Args:
            spec: Component specification

        Returns:
            Basic component code
        """
        name = spec["name"]
        description = spec.get("description", "A new component")

        return f"""import React from 'react';

interface {name}Props {{
  // Add props here
}}

/**
 * {description}
 */
export const {name}: React.FC<{name}Props> = (props) => {{
  return (
    <div className="p-4">
      <h2 className="text-xl font-bold">{name}</h2>
      <p className="text-gray-600">Component implementation</p>
    </div>
  );
}};
"""

    def _generate_typescript_types(self, spec: Dict[str, Any]) -> Optional[str]:
        """
        Generate TypeScript type definitions for component.

        Args:
            spec: Component specification

        Returns:
            TypeScript types as string, or None if not needed
        """
        # For now, types are included in component file
        # In future, could extract to separate types file
        return None

    def _create_component_files(
        self, component_name: str, component_code: str, types_code: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Create component files in correct directory structure.

        Args:
            component_name: Name of component
            component_code: Component source code
            types_code: Optional TypeScript types

        Returns:
            Dict of created file paths
        """
        # Ensure components directory exists
        self.components_dir.mkdir(parents=True, exist_ok=True)

        # Component file path
        component_file = self.components_dir / f"{component_name}.tsx"

        # Check for conflicts
        if component_file.exists():
            raise FileExistsError(
                f"Component file already exists: {component_file}. "
                "Please choose a different name or delete the existing file."
            )

        # Write component file
        component_file.write_text(component_code, encoding="utf-8")

        # Use relative path from web_ui_root if within temp dir (testing)
        try:
            relative_path = component_file.relative_to(self.project_root)
        except ValueError:
            # In testing with tmp directories
            relative_path = component_file.relative_to(self.web_ui_root.parent)

        file_paths = {"component": str(relative_path)}

        # Write types file if provided
        if types_code:
            types_file = self.components_dir / f"{component_name}.types.ts"
            types_file.write_text(types_code, encoding="utf-8")

            try:
                types_relative = types_file.relative_to(self.project_root)
            except ValueError:
                types_relative = types_file.relative_to(self.web_ui_root.parent)

            file_paths["types"] = str(types_relative)

        return file_paths

    def _update_imports_exports(self, component_name: str, file_paths: Dict[str, str]) -> None:
        """
        Update import/export statements in index files.

        Args:
            component_name: Name of component
            file_paths: Dict of created file paths
        """
        # Update components/index.ts if it exists
        index_file = self.components_dir / "index.ts"

        if not index_file.exists():
            # Create index file
            index_file.write_text(
                f"export {{ {component_name} }} from './{component_name}';\n", encoding="utf-8"
            )
        else:
            # Append export
            current_content = index_file.read_text(encoding="utf-8")
            if f"export {{ {component_name} }}" not in current_content:
                index_file.write_text(
                    current_content + f"export {{ {component_name} }} from './{component_name}';\n",
                    encoding="utf-8",
                )

    async def _run_and_check_linting(
        self, task: Task, file_paths: Dict[str, str], project_id: int
    ) -> None:
        """
        Run linting on created files and create blocker if critical errors found (T112).

        This method executes linting on TypeScript/JavaScript files created during task execution,
        stores results in the database, and creates a blocker if critical errors are found.

        Args:
            task: Task object
            file_paths: Dict of created file paths
            project_id: Project ID for broadcasts

        Raises:
            ValueError: If linting fails with critical errors (blocker created)
        """
        if not file_paths:
            logger.debug("No files created, skipping linting")
            return

        # Convert file_paths dict values to list of Path objects
        files_to_lint = [
            Path(path)
            for path in file_paths.values()
            if path.endswith((".ts", ".tsx", ".js", ".jsx"))
        ]

        if not files_to_lint:
            logger.debug("No TypeScript/JavaScript files created, skipping linting")
            return

        try:
            from codeframe.testing.lint_runner import LintRunner
            from codeframe.lib.lint_utils import format_lint_blocker
            from datetime import datetime

            # Initialize LintRunner with web-ui root for frontend files
            lint_runner = LintRunner(self.web_ui_root)

            logger.info(
                f"Running linting on {len(files_to_lint)} TypeScript files for task {task.id}"
            )

            # Run linting
            lint_results = await lint_runner.run_lint(files_to_lint)

            # Store results in database if db is available
            if self.db:
                for result in lint_results:
                    self.db.create_lint_result(
                        task_id=task.id,
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

                if self.db:
                    self.db.create_blocker(
                        project_id=project_id,
                        blocker_type="SYNC",
                        title=f"Linting failed: {total_errors} critical errors",
                        description=blocker_description,
                        blocking_task_id=task.id,
                    )

                logger.error(f"Task {task.id} blocked by {total_errors} lint errors")

                # Broadcast lint failure via WebSocket (T119)
                if self.websocket_manager:
                    try:
                        from codeframe.ui.websocket_broadcasts import broadcast_to_project

                        await broadcast_to_project(
                            self.websocket_manager,
                            project_id,
                            {
                                "type": "lint_failed",
                                "task_id": task.id,
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
                logger.warning(f"Task {task.id}: {total_warnings} lint warnings (non-blocking)")

            # Broadcast lint success via WebSocket (T119)
            if self.websocket_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_to_project

                    await broadcast_to_project(
                        self.websocket_manager,
                        project_id,
                        {
                            "type": "lint_completed",
                            "task_id": task.id,
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
            task_id: Associated task ID (defaults to self.current_task.id)

        Returns:
            Blocker ID

        Raises:
            ValueError: If question is empty, too long, or blocker_type is invalid
            RuntimeError: If db or project_id not configured
        """
        # Defensive checks for required dependencies
        if self.db is None:
            raise RuntimeError(
                "Database instance required for blocker workflow. Pass db parameter to __init__."
            )

        if self.project_id is None:
            raise RuntimeError(
                "Project ID required for blocker workflow. Pass project_id parameter to __init__."
            )

        if not question or len(question.strip()) == 0:
            raise ValueError("Question cannot be empty")

        if len(question) > 2000:
            raise ValueError("Question exceeds 2000 character limit")

        # Validate blocker type (T035: blocker type classification)
        valid_types = ["SYNC", "ASYNC"]
        if blocker_type not in valid_types:
            raise ValueError(f"Invalid blocker_type '{blocker_type}'. Must be 'SYNC' or 'ASYNC'")

        # Use provided task_id or fall back to current task
        blocker_task_id = (
            task_id
            if task_id is not None
            else (
                self.current_task.id
                if hasattr(self, "current_task") and self.current_task
                else None
            )
        )

        # Create blocker in database
        blocker_id = self.db.create_blocker(
            agent_id=self.agent_id,
            project_id=self.project_id,
            task_id=blocker_task_id,
            blocker_type=blocker_type,
            question=question.strip(),
        )

        logger.info(f"Blocker {blocker_id} created by {self.agent_id}: {question[:50]}...")

        # Broadcast blocker creation via WebSocket (if manager available)
        if self.websocket_manager:
            try:
                from codeframe.ui.websocket_broadcasts import broadcast_blocker_created

                await broadcast_blocker_created(
                    manager=self.websocket_manager,
                    project_id=self.project_id,
                    blocker_id=blocker_id,
                    agent_id=self.agent_id,
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
                        agent_id=self.agent_id,
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
        Wait for a blocker to be resolved by polling the database (049-human-in-loop, T029).

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
            RuntimeError: If db or project_id not configured

        Example:
            blocker_id = await agent.create_blocker("Should I use React or Vue?")
            answer = await agent.wait_for_blocker_resolution(blocker_id)
            # answer = "Use React to match existing stack"
        """
        # Defensive checks for required dependencies
        if self.db is None:
            raise RuntimeError(
                "Database instance required for blocker workflow. Pass db parameter to __init__."
            )

        if self.project_id is None:
            raise RuntimeError(
                "Project ID required for blocker workflow. Pass project_id parameter to __init__."
            )

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
                if self.websocket_manager:
                    try:
                        from codeframe.ui.websocket_broadcasts import broadcast_agent_resumed

                        await broadcast_agent_resumed(
                            manager=self.websocket_manager,
                            project_id=self.project_id,
                            agent_id=self.agent_id,
                            task_id=(
                                self.current_task.id
                                if hasattr(self, "current_task") and self.current_task
                                else None
                            )
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
            context: Current execution context
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
            context = {"task": task, "requirements": requirements}

            # Ask user for guidance
            enriched_context = await agent.create_blocker_and_wait(
                question="Should I use React or Vue for this component?",
                context=context,
                blocker_type="SYNC"
            )

            # Continue execution with user's answer in context
            result = await self.generate_code(enriched_context)
            # The answer "Use React to match existing stack" is now part of context
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
