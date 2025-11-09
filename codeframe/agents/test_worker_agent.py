"""
Test Worker Agent for pytest test generation (Sprint 4: cf-49).

This agent specializes in generating pytest test cases,
analyzing code for test requirements, and self-correcting failing tests.
"""

import os
import sys
import json
import logging
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
        max_correction_attempts: int = 3
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
        Create a blocker when agent needs human input (049-human-in-loop).

        Args:
            question: Question for the user (max 2000 chars)
            blocker_type: 'SYNC' (critical) or 'ASYNC' (clarification), default 'ASYNC'
            task_id: Associated task ID (defaults to self.current_task_id)

        Returns:
            Blocker ID

        Raises:
            ValueError: If question is empty or too long
        """
        if not question or len(question.strip()) == 0:
            raise ValueError("Question cannot be empty")

        if len(question) > 2000:
            raise ValueError("Question exceeds 2000 character limit")

        # Use provided task_id or fall back to current task
        blocker_task_id = task_id if task_id is not None else getattr(self, 'current_task_id', None)

        # Get agent ID from self or use class name
        agent_id = getattr(self, 'id', None) or f"test-worker-{self.project_id}"

        # Create blocker in database
        blocker_id = self.database.create_blocker(
            agent_id=agent_id,
            task_id=blocker_task_id,
            blocker_type=blocker_type,
            question=question.strip()
        )

        logger.info(f"Blocker {blocker_id} created by {agent_id}: {question[:50]}...")

        # Broadcast blocker creation via WebSocket (if manager available)
        if self.websocket_manager:
            try:
                from codeframe.ui.websocket_broadcasts import broadcast_blocker_created
                await broadcast_blocker_created(
                    manager=self.websocket_manager,
                    project_id=self.project_id,
                    blocker_id=blocker_id,
                    agent_id=agent_id,
                    task_id=blocker_task_id,
                    blocker_type=blocker_type,
                    question=question.strip()
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast blocker creation: {e}")

        return blocker_id