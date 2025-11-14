"""
Test Worker Agent for pytest test generation (Sprint 4: cf-49).

This agent specializes in generating pytest test cases,
analyzing code for test requirements, and self-correcting failing tests.
"""

import os
import sys
import json
import logging
import asyncio
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from anthropic import AsyncAnthropic

from codeframe.core.models import Task, AgentMaturity
from codeframe.agents.worker_agent import WorkerAgent

logger = logging.getLogger(__name__)


class TestWorkerAgent(WorkerAgent):
    """
    Test Worker Agent - Specialized in pytest test generation and validation.

    Capabilities:
    - Generate pytest test cases for Python code
    - Analyze target code to understand test requirements
    - Execute generated tests and validate results
    - Self-correct failing tests (up to 3 attempts)
    - Follow pytest conventions (fixtures, parametrize, mocks)
    - Integrate with WebSocket broadcasts for test results
    """

    def __init__(
        self,
        agent_id: str,
        provider: str = "anthropic",
        maturity: AgentMaturity = AgentMaturity.D1,
        api_key: Optional[str] = None,
        websocket_manager=None,
        max_correction_attempts: int = 3,
        db=None,
        project_id: Optional[int] = None
    ):
        """
        Initialize Test Worker Agent.

        Args:
            agent_id: Unique agent identifier
            provider: LLM provider (default: anthropic)
            maturity: Agent maturity level
            api_key: API key for LLM provider
            websocket_manager: WebSocket connection manager
            max_correction_attempts: Maximum self-correction attempts
            db: Database instance for blocker management (optional)
            project_id: Project ID for blocker context (optional)
        """
        super().__init__(
            agent_id=agent_id,
            agent_type="test",
            provider=provider,
            maturity=maturity,
            system_prompt=self._build_system_prompt()
        )
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = AsyncAnthropic(api_key=self.api_key) if self.api_key else None
        self.websocket_manager = websocket_manager
        self.max_correction_attempts = max_correction_attempts
        self.db = db
        self.project_id = project_id
        self.project_root = Path(__file__).parent.parent.parent
        self.tests_dir = self.project_root / "tests"

    def _build_system_prompt(self) -> str:
        """Build system prompt for test-specific tasks."""
        return """You are a Test Worker Agent specializing in pytest test generation.

Your responsibilities:
1. Generate comprehensive pytest test cases for Python code
2. Follow pytest best practices:
   - Use fixtures for setup/teardown
   - Use parametrize for multiple test cases
   - Proper mocking of external dependencies
   - Clear, descriptive test names
   - Arrange-Act-Assert pattern
3. Test edge cases and error conditions
4. Write self-contained, independent tests
5. Avoid anti-patterns (testing implementation details, brittle tests)

Output format:
- Provide complete, working test code
- Include all necessary imports
- Add docstrings for test functions
- Use proper assertion messages
- Ensure proper async/await handling for async code
"""

    async def execute_task(self, task: Task, project_id: int = 1) -> Dict[str, Any]:
        """
        Execute test generation task.

        Args:
            task: Task with target code specification
            project_id: Project ID for broadcasts

        Returns:
            Execution result with test status
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
                        progress=0
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task status: {e}")

            logger.info(f"Test agent {self.agent_id} executing task {task.id}: {task.title}")

            # Parse task for target code
            test_spec = self._parse_test_spec(task.description)

            # Analyze target code
            code_analysis = self._analyze_target_code(test_spec.get("target_file"))

            # Generate test code
            test_code = await self._generate_pytest_tests(test_spec, code_analysis)

            # Create test file
            test_file = self._create_test_file(test_spec["test_name"], test_code)

            # Execute tests and self-correct if needed
            test_result = await self._execute_and_correct_tests(
                test_file,
                test_spec,
                code_analysis,
                project_id,
                task.id
            )

            # Broadcast completion or failure
            final_status = "completed" if test_result["passed"] else "failed"
            if self.websocket_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_task_status
                    await broadcast_task_status(
                        self.websocket_manager,
                        project_id,
                        task.id,
                        final_status,
                        agent_id=self.agent_id,
                        progress=100
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task status: {e}")

            logger.info(
                f"Test agent {self.agent_id} completed task {task.id}: "
                f"{test_result['passed_count']}/{test_result['total_count']} tests passed"
            )

            return {
                "status": final_status,
                "output": f"Generated {test_result['total_count']} tests, "
                         f"{test_result['passed_count']} passed",
                "test_file": str(test_file),
                "test_results": test_result
            }

        except Exception as e:
            logger.error(f"Test agent {self.agent_id} failed task {task.id}: {e}")

            if self.websocket_manager:
                try:
                    from codeframe.ui.websocket_broadcasts import broadcast_task_status
                    await broadcast_task_status(
                        self.websocket_manager,
                        project_id,
                        task.id,
                        "failed",
                        agent_id=self.agent_id
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast task status: {e}")

            return {
                "status": "failed",
                "output": str(e),
                "error": str(e)
            }

    def _parse_test_spec(self, description: str) -> Dict[str, Any]:
        """
        Parse task description to extract test specification.

        Args:
            description: Task description

        Returns:
            Test specification dict
        """
        try:
            spec = json.loads(description)
            if "target_file" in spec or "test_name" in spec:
                return spec
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: extract from plain text
        test_name = "test_new_feature"
        target_file = None

        lines = description.strip().split("\n")
        for line in lines:
            if "test:" in line.lower() or "test file:" in line.lower():
                test_name = line.split(":")[-1].strip()
            elif "target:" in line.lower() or "code:" in line.lower():
                target_file = line.split(":")[-1].strip()

        return {
            "test_name": test_name,
            "target_file": target_file,
            "description": description
        }

    def _analyze_target_code(self, target_file: Optional[str]) -> Dict[str, Any]:
        """
        Analyze target code to understand test requirements.

        Args:
            target_file: Path to target code file

        Returns:
            Code analysis dict
        """
        if not target_file:
            return {"functions": [], "classes": [], "imports": []}

        try:
            file_path = self.project_root / target_file
            if not file_path.exists():
                logger.warning(f"Target file not found: {target_file}")
                return {"functions": [], "classes": [], "imports": []}

            code = file_path.read_text(encoding="utf-8")

            # Simple regex-based extraction (could be improved with AST)
            functions = re.findall(r'^(?:async )?def (\w+)\(', code, re.MULTILINE)
            classes = re.findall(r'^class (\w+)', code, re.MULTILINE)
            imports = re.findall(r'^(?:from .+ )?import .+', code, re.MULTILINE)

            return {
                "functions": functions,
                "classes": classes,
                "imports": imports[:10],  # Limit imports
                "code_snippet": code[:2000]  # First 2000 chars for context
            }

        except Exception as e:
            logger.error(f"Failed to analyze target code: {e}")
            return {"functions": [], "classes": [], "imports": []}

    async def _generate_pytest_tests(
        self,
        spec: Dict[str, Any],
        code_analysis: Dict[str, Any]
    ) -> str:
        """
        Generate pytest test code.

        Args:
            spec: Test specification
            code_analysis: Code analysis results

        Returns:
            Generated test code
        """
        if not self.client:
            return self._generate_basic_test_template(spec, code_analysis)

        # Build context from code analysis
        context = ""
        if code_analysis.get("functions"):
            context += f"\nFunctions to test: {', '.join(code_analysis['functions'])}"
        if code_analysis.get("classes"):
            context += f"\nClasses to test: {', '.join(code_analysis['classes'])}"
        if code_analysis.get("code_snippet"):
            context += f"\n\nCode snippet:\n```python\n{code_analysis['code_snippet']}\n```"

        prompt = f"""Generate comprehensive pytest test cases for the following:

Test Name: {spec['test_name']}
Description: {spec.get('description', 'Generate tests for the target code')}
{context}

Requirements:
- Use pytest fixtures where appropriate
- Use parametrize for testing multiple inputs
- Mock external dependencies
- Test edge cases and error conditions
- Follow Arrange-Act-Assert pattern
- Include docstrings
- Ensure tests are independent

Provide ONLY the test code, no explanations."""

        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )

            code = response.content[0].text

            # Remove markdown code blocks
            if "```" in code:
                code = code.split("```")[1]
                if code.startswith("python"):
                    code = "\n".join(code.split("\n")[1:])

            return code.strip()

        except Exception as e:
            logger.error(f"Failed to generate tests with Claude API: {e}")
            return self._generate_basic_test_template(spec, code_analysis)

    def _generate_basic_test_template(
        self,
        spec: Dict[str, Any],
        code_analysis: Dict[str, Any]
    ) -> str:
        """Generate basic test template as fallback."""
        test_name = spec.get("test_name", "test_feature")
        target_file = spec.get("target_file", "")

        imports = "import pytest\n"
        if target_file:
            module = target_file.replace("/", ".").replace(".py", "")
            imports += f"from {module} import *\n"

        return f'''{imports}

def {test_name}():
    """Test basic functionality."""
    # Arrange
    expected = True

    # Act
    result = True

    # Assert
    assert result == expected, "Test not yet implemented"
'''

    def _create_test_file(self, test_name: str, test_code: str) -> Path:
        """
        Create test file in tests directory.

        Args:
            test_name: Name of test file
            test_code: Test code content

        Returns:
            Path to created test file
        """
        # Ensure tests directory exists
        self.tests_dir.mkdir(parents=True, exist_ok=True)

        # Ensure test name starts with "test_"
        if not test_name.startswith("test_"):
            test_name = f"test_{test_name}"

        # Ensure .py extension
        if not test_name.endswith(".py"):
            test_name = f"{test_name}.py"

        test_file = self.tests_dir / test_name

        # Write test file
        test_file.write_text(test_code, encoding="utf-8")

        return test_file

    def _execute_tests(self, test_file: Path) -> Tuple[bool, str, Dict[str, int]]:
        """
        Execute pytest tests.

        Args:
            test_file: Path to test file

        Returns:
            Tuple of (all_passed, output, counts)
        """
        try:
            # Use python -m pytest to ensure we use the correct pytest from the current environment
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60
            )

            output = result.stdout + result.stderr

            # Parse pytest output for counts
            passed = len(re.findall(r'PASSED', output))
            failed = len(re.findall(r'FAILED', output))
            errors = len(re.findall(r'ERROR', output))

            counts = {
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "total": passed + failed + errors
            }

            all_passed = result.returncode == 0

            return all_passed, output, counts

        except subprocess.TimeoutExpired:
            return False, "Test execution timeout", {"passed": 0, "failed": 0, "errors": 1, "total": 1}
        except Exception as e:
            return False, str(e), {"passed": 0, "failed": 0, "errors": 1, "total": 1}

    async def _execute_and_correct_tests(
        self,
        test_file: Path,
        test_spec: Dict[str, Any],
        code_analysis: Dict[str, Any],
        project_id: int,
        task_id: int
    ) -> Dict[str, Any]:
        """
        Execute tests and self-correct if they fail.

        Args:
            test_file: Path to test file
            test_spec: Test specification
            code_analysis: Code analysis
            project_id: Project ID
            task_id: Task ID

        Returns:
            Final test results
        """
        for attempt in range(1, self.max_correction_attempts + 1):
            logger.info(f"Test execution attempt {attempt}/{self.max_correction_attempts}")

            # Execute tests
            all_passed, output, counts = self._execute_tests(test_file)

            # Broadcast test results
            if self.websocket_manager:
                await self._broadcast_test_result(
                    project_id,
                    task_id,
                    counts,
                    all_passed
                )

            if all_passed:
                return {
                    "passed": True,
                    "attempts": attempt,
                    "passed_count": counts["passed"],
                    "failed_count": counts["failed"],
                    "errors_count": counts["errors"],
                    "total_count": counts["total"],
                    "output": output
                }

            # If tests failed and we have attempts remaining, try to correct
            if attempt < self.max_correction_attempts:
                logger.info(f"Attempting to fix failing tests (attempt {attempt})")

                corrected_code = await self._correct_failing_tests(
                    test_file.read_text(),
                    output,
                    test_spec,
                    code_analysis
                )

                if corrected_code:
                    test_file.write_text(corrected_code, encoding="utf-8")
                else:
                    logger.warning("Failed to generate corrected tests")
                    break

        # Final result after all attempts
        return {
            "passed": False,
            "attempts": self.max_correction_attempts,
            "passed_count": counts["passed"],
            "failed_count": counts["failed"],
            "errors_count": counts["errors"],
            "total_count": counts["total"],
            "output": output
        }

    async def _correct_failing_tests(
        self,
        original_code: str,
        error_output: str,
        test_spec: Dict[str, Any],
        code_analysis: Dict[str, Any]
    ) -> Optional[str]:
        """
        Attempt to correct failing tests using Claude API.

        Args:
            original_code: Original test code
            error_output: Error output from pytest
            test_spec: Test specification
            code_analysis: Code analysis

        Returns:
            Corrected test code or None
        """
        if not self.client:
            return None

        prompt = f"""Fix the following failing pytest tests:

Original Test Code:
```python
{original_code}
```

Error Output:
```
{error_output[:2000]}
```

Requirements:
- Fix all failing tests
- Maintain test coverage
- Follow pytest best practices
- Ensure tests are independent
- Do not remove any test cases

Provide ONLY the corrected test code, no explanations."""

        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )

            code = response.content[0].text

            # Remove markdown code blocks
            if "```" in code:
                code = code.split("```")[1]
                if code.startswith("python"):
                    code = "\n".join(code.split("\n")[1:])

            return code.strip()

        except Exception as e:
            logger.error(f"Failed to correct tests: {e}")
            return None

    async def _broadcast_test_result(
        self,
        project_id: int,
        task_id: int,
        counts: Dict[str, int],
        all_passed: bool
    ) -> None:
        """Broadcast test result via WebSocket."""
        if not self.websocket_manager:
            return

        from codeframe.ui.websocket_broadcasts import broadcast_test_result

        status = "passed" if all_passed else "failed"

        try:
            await broadcast_test_result(
                self.websocket_manager,
                project_id,
                task_id,
                status,
                passed=counts.get("passed", 0),
                failed=counts.get("failed", 0),
                errors=counts.get("errors", 0)
            )
        except Exception as e:
            logger.debug(f"Failed to broadcast test result: {e}")

    async def create_blocker(
        self,
        question: str,
        blocker_type: str = "ASYNC",
        task_id: Optional[int] = None
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
        blocker_task_id = task_id if task_id is not None else getattr(self, 'current_task_id', None)

        # Create blocker in database
        blocker_id = self.db.create_blocker(
            agent_id=self.agent_id,
            task_id=blocker_task_id,
            blocker_type=blocker_type,
            question=question.strip()
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
                    question=question.strip()
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast blocker creation: {e}")

        # Send webhook notification for SYNC blockers (T042: 049-human-in-loop)
        if blocker_type == "SYNC":
            try:
                from datetime import datetime
                from pathlib import Path
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
                        dashboard_base_url=f"http://{global_config.api_host}:{global_config.api_port}"
                    )

                    # Send notification (fire-and-forget)
                    webhook_service.send_blocker_notification_background(
                        blocker_id=blocker_id,
                        question=question.strip(),
                        agent_id=self.agent_id,
                        task_id=blocker_task_id or 0,
                        blocker_type=BlockerType.SYNC,
                        created_at=datetime.now()
                    )
                    logger.debug(f"Webhook notification queued for SYNC blocker {blocker_id}")
                else:
                    logger.debug("BLOCKER_WEBHOOK_URL not configured, skipping webhook notification")

            except Exception as e:
                # Log error but don't block blocker creation
                logger.warning(f"Failed to send webhook notification for blocker {blocker_id}: {e}")

        return blocker_id

    async def wait_for_blocker_resolution(
        self,
        blocker_id: int,
        poll_interval: float = 5.0,
        timeout: float = 600.0
    ) -> str:
        """
        Wait for a blocker to be resolved by polling the database (049-human-in-loop, T030).

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
            blocker_id = await agent.create_blocker("Should I use pytest or unittest?")
            answer = await agent.wait_for_blocker_resolution(blocker_id)
            # answer = "Use pytest for consistency"
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
                if self.websocket_manager:
                    try:
                        from codeframe.ui.websocket_broadcasts import broadcast_agent_resumed
                        await broadcast_agent_resumed(
                            manager=self.websocket_manager,
                            project_id=self.project_id,
                            agent_id=self.agent_id,
                            task_id=getattr(self, 'current_task_id', None) or blocker.get("task_id"),
                            blocker_id=blocker_id
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
        timeout: float = 600.0
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
            context = {"task": task, "test_requirements": requirements}

            # Ask user for guidance
            enriched_context = await agent.create_blocker_and_wait(
                question="Should I use pytest or unittest for this test suite?",
                context=context,
                blocker_type="ASYNC"
            )

            # Continue execution with user's answer in context
            result = await self.generate_tests(enriched_context)
            # The answer "Use pytest for consistency" is now part of context
        """
        # Extract task_id from context if not provided
        if task_id is None:
            task_id = context.get("task", {}).get("id")

        # 1. Create blocker
        blocker_id = await self.create_blocker(
            question=question,
            blocker_type=blocker_type,
            task_id=task_id
        )

        logger.info(f"Created blocker {blocker_id}, waiting for resolution...")

        # 2. Wait for user to resolve blocker
        answer = await self.wait_for_blocker_resolution(
            blocker_id=blocker_id,
            poll_interval=poll_interval,
            timeout=timeout
        )

        logger.info(f"Blocker {blocker_id} resolved with answer: {answer[:50]}...")

        # 3. Inject answer into context
        enriched_context = {
            **context,
            "blocker_answer": answer,
            "blocker_question": question,
            "blocker_id": blocker_id
        }

        return enriched_context