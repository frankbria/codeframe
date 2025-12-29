"""Worker Agent implementation for CodeFRAME."""

import os
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from collections import deque

if TYPE_CHECKING:
    from codeframe.enforcement.evidence_verifier import Evidence

from anthropic import (
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from codeframe.core.models import (
    Task, TaskStatus, AgentMaturity, ContextItemType, ContextTier, CallType
)
from codeframe.enforcement.quality_tracker import QualityTracker, QualityMetrics

logger = logging.getLogger(__name__)

# Supported Claude models for execute_task
SUPPORTED_MODELS = [
    "claude-sonnet-4-5",
    "claude-opus-4",
    "claude-haiku-4",
    "claude-3-5-haiku-20241022",  # Actual API model name for Haiku 3.5
    "claude-3-5-sonnet-20241022",  # Actual API model name for Sonnet 3.5
    "claude-3-opus-20240229",      # Actual API model name for Opus 3
]

# Model pricing (USD per million tokens) - as of 2025-11
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 0.000003, "output": 0.000015},
    "claude-opus-4": {"input": 0.000015, "output": 0.000075},
    "claude-haiku-4": {"input": 0.0000008, "output": 0.000004},
    # Versioned model names with same pricing as their friendly names
    "claude-3-5-haiku-20241022": {"input": 0.0000008, "output": 0.000004},
    "claude-3-5-sonnet-20241022": {"input": 0.000003, "output": 0.000015},
    "claude-3-opus-20240229": {"input": 0.000015, "output": 0.000075},
}


class WorkerAgent:
    """
    Worker Agent - Specialized agent for specific tasks (Backend, Frontend, Test, Review).
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        provider: str,
        maturity: AgentMaturity = AgentMaturity.D1,
        system_prompt: str | None = None,
        db: Optional[Any] = None,
        model_name: str = "claude-sonnet-4-5",
    ):
        """Initialize Worker Agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (backend, frontend, test, review)
            provider: LLM provider (anthropic, openai, etc.)
            maturity: Agent maturity level (D1-D4)
            system_prompt: Custom system prompt
            db: Database connection
            model_name: Default LLM model name for execute_task (default: claude-sonnet-4-5)

        Note:
            Agents are now project-agnostic at creation time.
            Project context is derived from the current task being executed.
            Use Database.assign_agent_to_project() to assign agents to projects.
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.provider = provider
        self.maturity = maturity
        self.system_prompt = system_prompt
        self.current_task: Task | None = None
        self.db = db
        self.model_name = model_name

        # Rate limiting (MEDIUM-1 fix)
        self._api_calls: deque = deque(maxlen=100)  # Track last 100 calls
        self._rate_limit = int(os.getenv("AGENT_RATE_LIMIT", "10"))  # Max calls per minute
        self._rate_limit_lock = asyncio.Lock()

        # Quality tracking integration
        self.response_count: int = 0  # Track AI conversation length
        self.quality_tracker: Optional[QualityTracker] = None  # Lazy-initialized

    def _get_project_id(self) -> int:
        """Get project ID from current task.

        Returns:
            Project ID from current task

        Raises:
            ValueError: If no task is currently assigned or task has no project_id
        """
        if not self.current_task:
            raise ValueError(
                "No task currently assigned. Project context is derived from active task. "
                "Assign a task first using execute_task() or complete_task()."
            )

        if not self.current_task.project_id:
            raise ValueError(
                f"Task {self.current_task.id} has no project_id. "
                "Task must be associated with a project."
            )

        return self.current_task.project_id

    def _ensure_quality_tracker(self) -> Optional[QualityTracker]:
        """Lazily initialize quality tracker when project context is available.

        The quality tracker is initialized when:
        1. A database connection is available
        2. A current task with project_id is set
        3. The project has a workspace_path in the database

        Returns:
            QualityTracker instance if initialization succeeds, None otherwise

        Example:
            >>> agent = WorkerAgent(agent_id="backend-001", ...)
            >>> agent.current_task = task  # Task with project_id
            >>> tracker = agent._ensure_quality_tracker()
            >>> if tracker:
            ...     tracker.record(metrics)
        """
        if self.quality_tracker is not None:
            return self.quality_tracker

        if not self.db or not self.current_task:
            return None

        try:
            project_id = self._get_project_id()

            # Get project workspace path from database
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT workspace_path FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()

            if not row or not row[0]:
                logger.debug(f"No workspace_path found for project {project_id}")
                return None

            workspace_path = row[0]
            self.quality_tracker = QualityTracker(project_path=workspace_path)
            logger.debug(f"Initialized quality tracker for project {project_id}")
            return self.quality_tracker

        except Exception as e:
            logger.warning(f"Failed to initialize quality tracker: {e}")
            return None

    def _estimate_cost(self, model_name: str, input_tokens: int, max_output_tokens: int) -> float:
        """Estimate maximum cost for an LLM call.

        Args:
            model_name: Model identifier
            input_tokens: Estimated input tokens
            max_output_tokens: Maximum output tokens

        Returns:
            Estimated cost in USD
        """
        if model_name not in MODEL_PRICING:
            logger.warning(f"Unknown model pricing for {model_name}, using Sonnet rates")
            model_name = "claude-sonnet-4-5"

        pricing = MODEL_PRICING[model_name]
        input_cost = input_tokens * pricing["input"]
        max_output_cost = max_output_tokens * pricing["output"]

        return input_cost + max_output_cost

    def _sanitize_prompt_input(self, text: str) -> str:
        """Sanitize user input for LLM prompts to prevent injection attacks.

        Args:
            text: Raw user input

        Returns:
            Sanitized text safe for LLM prompts
        """
        if not text:
            return "No description provided."

        # Remove excessive whitespace and control characters
        sanitized = " ".join(text.split())

        # Limit length to prevent context overflow
        max_length = 4000
        if len(sanitized) > max_length:
            logger.warning(
                f"Input truncated from {len(sanitized)} to {max_length} chars",
                extra={"event": "input_truncated", "original_length": len(sanitized)}
            )
            sanitized = sanitized[:max_length] + "... (truncated)"

        # Detect potential prompt injection patterns
        dangerous_phrases = [
            "ignore all previous instructions",
            "disregard",
            "instead, output",
            "forget everything",
        ]

        lower_text = sanitized.lower()
        for phrase in dangerous_phrases:
            if phrase in lower_text:
                logger.warning(
                    "Potential prompt injection detected",
                    extra={
                        "event": "prompt_injection_attempt",
                        "phrase": phrase,
                        "agent_id": self.agent_id
                    }
                )

        return sanitized

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _call_llm_with_retry(
        self,
        client: AsyncAnthropic,
        model_name: str,
        max_tokens: int,
        system: str,
        messages: List[Dict[str, str]],
        timeout: float,
    ):
        """Call LLM with automatic retry for transient failures.

        Retries up to 3 times with exponential backoff:
        - Attempt 1: immediate
        - Attempt 2: wait 2s
        - Attempt 3: wait 4-10s

        Args:
            client: Anthropic client
            model_name: Model identifier
            max_tokens: Maximum output tokens
            system: System prompt
            messages: Conversation messages
            timeout: Request timeout in seconds

        Returns:
            API response

        Raises:
            RateLimitError: After retry exhaustion
            APIConnectionError: After retry exhaustion
            TimeoutError: After retry exhaustion
        """
        return await client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            timeout=timeout,
        )

    async def execute_task(
        self,
        task: Task,
        model_name: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """
        Execute assigned task using the Anthropic LLM API.

        This method sends the task to Claude for completion and tracks token usage.
        It handles various error scenarios including authentication failures,
        rate limits, and network issues.

        Args:
            task: Task to execute
            model_name: Model identifier (default: uses self.model_name from __init__).
                Supported models: claude-sonnet-4-5, claude-opus-4, claude-haiku-4,
                claude-3-5-haiku-20241022, claude-3-5-sonnet-20241022, claude-3-opus-20240229
            max_tokens: Maximum tokens in the response (default: 4096).
                Increase for complex code generation tasks.

        Returns:
            Task execution result dict with keys:
                - status: "completed" or "failed"
                - output: LLM response text or error message
                - usage: dict with input_tokens and output_tokens (on success)
                - model: model name used (on success)
                - token_tracking_failed: bool indicating if token tracking failed (on success)
                - error: error message (on failure)

        Raises:
            ValueError: If ANTHROPIC_API_KEY environment variable is not set,
                or if model_name is not a supported model.

        Example:
            >>> agent = WorkerAgent(agent_id="backend-001", agent_type="backend",
            ...                     provider="anthropic", db=db)
            >>> task = Task(id=1, project_id=1, title="Add logging",
            ...             description="Add structured logging to auth module")
            >>> result = await agent.execute_task(task)
            >>> if result["status"] == "completed":
            ...     print(f"Output: {result['output'][:100]}...")
            ...     print(f"Tokens: {result['usage']}")
        """
        # Set current task to establish project context
        self.current_task = task

        # Extract task fields (handle both Task objects and dicts)
        if isinstance(task, dict):
            task_id = task.get("id")
            task_title = task.get("title", "Untitled")
            project_id = task.get("project_id")
        else:
            task_id = task.id
            task_title = task.title
            project_id = task.project_id

        # MEDIUM-1 FIX: Rate limiting protection
        async with self._rate_limit_lock:
            now = datetime.now()
            one_minute_ago = now - timedelta(minutes=1)

            # Remove old calls
            while self._api_calls and self._api_calls[0] < one_minute_ago:
                self._api_calls.popleft()

            # Check limit
            if len(self._api_calls) >= self._rate_limit:
                logger.warning(
                    f"Agent rate limit reached: {len(self._api_calls)} calls in last minute",
                    extra={
                        "event": "agent_rate_limit_exceeded",
                        "agent_id": self.agent_id,
                        "rate_limit": self._rate_limit
                    }
                )
                return {
                    "status": "failed",
                    "output": f"Agent rate limit exceeded ({self._rate_limit} calls/min). Wait before retrying.",
                    "error": "AGENT_RATE_LIMIT_EXCEEDED",
                }

            # Record this call
            self._api_calls.append(now)

        # Use instance model_name if not specified
        if model_name is None:
            model_name = self.model_name

        # Validate model name
        if model_name not in SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model: {model_name}. "
                f"Supported models: {', '.join(SUPPORTED_MODELS)}"
            )

        # CRITICAL-2 FIX: Get and validate API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "See .env.example for configuration."
            )

        # Validate Anthropic key format
        if not api_key.startswith("sk-ant-"):
            logger.error("Invalid ANTHROPIC_API_KEY format (must start with 'sk-ant-')")
            raise ValueError("Invalid ANTHROPIC_API_KEY format. Expected format: sk-ant-xxxxx")

        # CRITICAL-2 FIX: Never log the actual key - only masked version
        logger.debug(f"API key loaded: sk-ant-***{api_key[-4:]}")

        # Initialize AsyncAnthropic client
        client = AsyncAnthropic(api_key=api_key)

        # Build prompt from task
        prompt = self._build_task_prompt(task)

        # Cost estimation and guardrails
        estimated_input_tokens = len(prompt) // 4  # Rough estimate (1 token ≈ 4 chars)
        estimated_cost = self._estimate_cost(model_name, estimated_input_tokens, max_tokens)

        max_cost_per_task = float(os.getenv("MAX_COST_PER_TASK", "1.0"))
        if estimated_cost > max_cost_per_task:
            logger.warning(
                f"Task {task_id} estimated cost ${estimated_cost:.4f} exceeds limit ${max_cost_per_task}",
                extra={
                    "event": "cost_limit_exceeded",
                    "estimated_cost": estimated_cost,
                    "limit": max_cost_per_task,
                    "model": model_name,
                    "agent_id": self.agent_id,
                }
            )
            return {
                "status": "failed",
                "output": f"Task exceeds cost limit (estimated ${estimated_cost:.4f} > ${max_cost_per_task})",
                "error": "COST_LIMIT_EXCEEDED",
            }

        # HIGH-2 FIX: Enhanced audit logging - call start
        call_start_time = datetime.now(timezone.utc)
        logger.info(
            "LLM API call initiated",
            extra={
                "event": "llm_call_start",
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "task_id": task_id,
                "task_title": task_title,
                "project_id": project_id,
                "model": model_name,
                "max_tokens": max_tokens,
                "estimated_cost_usd": estimated_cost,
                "timestamp": call_start_time.isoformat(),
            }
        )

        # CRITICAL-1 FIX: Calculate timeout based on max_tokens
        base_timeout = 30.0  # seconds
        timeout_per_1k_tokens = 15.0  # seconds per 1000 tokens
        timeout = base_timeout + (max_tokens / 1000.0) * timeout_per_1k_tokens

        try:
            # HIGH-1 & CRITICAL-1 FIX: Make API call with retry and timeout
            response = await self._call_llm_with_retry(
                client,
                model_name,
                max_tokens,
                self.system_prompt or "You are a helpful software development assistant.",
                [{"role": "user", "content": prompt}],
                timeout,
            )

            # Extract response content and token usage
            if not response.content:
                logger.warning(f"Empty response from LLM for task {task_id}")
                content = ""
            else:
                content = response.content[0].text

            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Calculate actual cost
            actual_cost = self._estimate_cost(model_name, input_tokens, output_tokens)
            call_duration_ms = (datetime.now(timezone.utc) - call_start_time).total_seconds() * 1000

            # HIGH-2 FIX: Enhanced audit logging - call success
            logger.info(
                "LLM API call completed",
                extra={
                    "event": "llm_call_success",
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "project_id": project_id,
                    "model": model_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "estimated_cost_usd": actual_cost,
                    "duration_ms": call_duration_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Record token usage (non-blocking - failures should not block task execution)
            token_tracking_failed = await self._record_token_usage(
                task=task,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # Increment response count for quality tracking
            self.response_count += 1
            logger.debug(
                f"Agent {self.agent_id} response count: {self.response_count}",
                extra={"event": "response_count_increment", "count": self.response_count}
            )

            return {
                "status": "completed",
                "output": content,
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
                "model": model_name,
                "token_tracking_failed": token_tracking_failed,
            }

        except AuthenticationError as e:
            # HIGH-2 FIX: Enhanced error logging
            logger.error(
                "LLM API call failed - authentication",
                extra={
                    "event": "llm_call_failure",
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "project_id": project_id,
                    "model": model_name,
                    "error_type": "AuthenticationError",
                    "error_message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return {
                "status": "failed",
                "output": "API authentication failed. Check your ANTHROPIC_API_KEY.",
                "error": str(e),
            }

        except (RateLimitError, APIConnectionError, TimeoutError) as e:
            # HIGH-1 FIX: These errors trigger retry, so if we're here, retry exhausted
            logger.error(
                "LLM API call failed after 3 retries",
                extra={
                    "event": "llm_call_failure_retry_exhausted",
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "project_id": project_id,
                    "model": model_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "retries_attempted": 3,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return {
                "status": "failed",
                "output": f"Failed after 3 retry attempts: {type(e).__name__}",
                "error": str(e),
            }

        except Exception as e:
            # HIGH-2 FIX: Enhanced error logging for unexpected errors
            logger.error(
                "LLM API call failed - unexpected error",
                extra={
                    "event": "llm_call_failure_unexpected",
                    "agent_id": self.agent_id,
                    "task_id": task_id,
                    "project_id": project_id,
                    "model": model_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return {
                "status": "failed",
                "output": f"An unexpected error occurred: {type(e).__name__}",
                "error": str(e),
            }

    def _build_task_prompt(self, task: Task | Dict[str, Any]) -> str:
        """Build a structured prompt from the task.

        Args:
            task: Task to build prompt for (Task object or dict)

        Returns:
            Formatted prompt string
        """
        # Handle both Task objects and dicts
        if isinstance(task, dict):
            task_number = task.get("task_number", "N/A")
            title = task.get("title", "Untitled")
            description = task.get("description", "No description provided.")
        else:
            task_number = task.task_number
            title = task.title
            description = task.description or "No description provided."

        # MEDIUM-2 FIX: Sanitize inputs to prevent prompt injection
        title = self._sanitize_prompt_input(title)
        description = self._sanitize_prompt_input(description)

        prompt_parts = [
            f"Task #{task_number}: {title}",
            "",
            "Description:",
            description,
            "",
            "Please complete this task and provide a summary of the work done.",
        ]
        return "\n".join(prompt_parts)

    async def _record_token_usage(
        self,
        task: Task | Dict[str, Any],
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> bool:
        """Record token usage via MetricsTracker.

        Token tracking failures are logged but do not block task execution.

        Args:
            task: Task that was executed (Task object or dict)
            model_name: Model used for the call
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            True if token tracking failed, False if successful or skipped.
        """
        if not self.db:
            logger.debug("Database not configured, skipping token tracking")
            return False

        try:
            from codeframe.lib.metrics_tracker import MetricsTracker

            tracker = MetricsTracker(db=self.db)

            # Handle both Task objects and dicts
            if isinstance(task, dict):
                task_id = task.get("id")
                project_id = task.get("project_id")
            else:
                task_id = task.id
                project_id = task.project_id

            # Fail fast if project_id is missing
            if project_id is None:
                raise ValueError(
                    f"Task {task_id} must have a project_id for token tracking. "
                    "Ensure the task is properly associated with a project."
                )

            # Skip recording if both tokens are zero (no-op for zero usage)
            if input_tokens == 0 and output_tokens == 0:
                logger.debug(f"Skipping token tracking for task {task_id}: zero tokens")
                return False

            await tracker.record_token_usage(
                task_id=task_id,
                agent_id=self.agent_id,
                project_id=project_id,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                call_type=CallType.TASK_EXECUTION,
            )
            logger.debug(f"Token usage recorded for task {task_id}")
            return False
        except Exception as e:
            # Log warning but don't block task execution
            # Handle both Task objects and dicts for error logging
            task_id = task.get("id", "UNKNOWN") if isinstance(task, dict) else getattr(task, "id", "UNKNOWN")
            logger.warning(f"Failed to record token usage for task {task_id}: {e}")
            return True

    def assess_maturity(self) -> Dict[str, Any]:
        """Assess and update agent maturity level based on task performance history.

        This method analyzes the agent's completed task history to calculate a
        maturity score based on three weighted metrics:
        - Completion Rate (40%): Ratio of completed tasks to total tasks
        - Test Pass Rate (30%): Average test pass rate across completed tasks
        - Self-Correction Rate (30%): Ratio of tasks that succeeded on first attempt

        The weighted score is then mapped to maturity levels:
        - directive (D1, Novice): score < 0.5
        - coaching (D2, Intermediate): 0.5 <= score < 0.7
        - supporting (D3, Advanced): 0.7 <= score < 0.9
        - delegating (D4, Expert): score >= 0.9

        Returns:
            dict with keys:
                - maturity_level: AgentMaturity enum value
                - maturity_score: float (0.0-1.0)
                - metrics: dict with detailed performance metrics
                - changed: bool - whether maturity level changed

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = WorkerAgent(agent_id="backend-001", agent_type="backend",
            ...                     provider="anthropic", db=db)
            >>> result = agent.assess_maturity()
            >>> print(f"Maturity: {result['maturity_level'].value}")
            Maturity: coaching
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Get old maturity level for comparison
        old_maturity = self._get_current_maturity()

        # Step 1: Query task history for this agent
        tasks = self.db.get_tasks_by_agent(self.agent_id)

        # If no tasks, set to novice (D1)
        if not tasks:
            new_maturity = AgentMaturity.D1
            metrics = {
                "task_count": 0,
                "completion_rate": 0.0,
                "avg_test_pass_rate": 0.0,
                "self_correction_rate": 0.0,
                "maturity_score": 0.0,
                "last_assessed": datetime.now(timezone.utc).isoformat(),
                "maturity_level": new_maturity.value,
            }

            # Update agent in database
            self._update_agent_maturity(new_maturity, metrics)

            # Log audit event
            self._log_maturity_assessment(old_maturity, new_maturity, metrics)

            return {
                "maturity_level": new_maturity,
                "maturity_score": 0.0,
                "metrics": metrics,
                "changed": old_maturity != new_maturity if old_maturity else True,
            }

        # Step 2: Calculate completion rate
        total_tasks = len(tasks)
        completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        completion_rate = len(completed_tasks) / total_tasks if total_tasks > 0 else 0.0

        # Step 3: Calculate average test pass rate
        test_pass_rates = []
        for task in completed_tasks:
            test_results = self.db.get_test_results_by_task(task.id)
            if test_results:
                # Get the most recent test result
                latest_result = test_results[0]  # Already ordered by created_at DESC
                passed = latest_result.get("passed", 0)
                failed = latest_result.get("failed", 0)
                total_tests = passed + failed
                if total_tests > 0:
                    task_pass_rate = passed / total_tests
                    test_pass_rates.append(task_pass_rate)

        avg_test_pass_rate = (
            sum(test_pass_rates) / len(test_pass_rates) if test_pass_rates else 0.0
        )

        # Step 4: Calculate self-correction rate
        # Tasks that succeeded on first attempt (no correction attempts needed)
        first_attempt_success_count = 0
        for task in completed_tasks:
            correction_attempts = self.db.get_correction_attempts_by_task(task.id)
            if not correction_attempts:
                # No correction attempts means first attempt succeeded
                first_attempt_success_count += 1
            # Tasks with any correction_attempts records required fixes,
            # so they don't count as first-attempt successes

        self_correction_rate = (
            first_attempt_success_count / len(completed_tasks)
            if completed_tasks
            else 0.0
        )

        # Step 5: Compute weighted maturity score
        # Formula: score = (completion_rate * 0.4) + (avg_test_pass_rate * 0.3) + (self_correction_rate * 0.3)
        maturity_score = (
            (completion_rate * 0.4)
            + (avg_test_pass_rate * 0.3)
            + (self_correction_rate * 0.3)
        )

        # Step 6: Map score to maturity level
        if maturity_score >= 0.9:
            new_maturity = AgentMaturity.D4  # Expert / delegating
        elif maturity_score >= 0.7:
            new_maturity = AgentMaturity.D3  # Advanced / supporting
        elif maturity_score >= 0.5:
            new_maturity = AgentMaturity.D2  # Intermediate / coaching
        else:
            new_maturity = AgentMaturity.D1  # Novice / directive

        # Step 7: Build metrics dictionary
        metrics = {
            "task_count": total_tasks,
            "completed_count": len(completed_tasks),
            "completion_rate": round(completion_rate, 4),
            "tasks_with_tests": len(test_pass_rates),
            "avg_test_pass_rate": round(avg_test_pass_rate, 4),
            "first_attempt_success_count": first_attempt_success_count,
            "self_correction_rate": round(self_correction_rate, 4),
            "maturity_score": round(maturity_score, 4),
            "last_assessed": datetime.now(timezone.utc).isoformat(),
            "maturity_level": new_maturity.value,
        }

        # Step 8: Update agent in database
        self._update_agent_maturity(new_maturity, metrics)

        # Step 9: Log audit event
        self._log_maturity_assessment(old_maturity, new_maturity, metrics)

        # Update instance maturity level
        self.maturity = new_maturity

        maturity_changed = old_maturity != new_maturity if old_maturity else True

        logger.info(
            f"Agent {self.agent_id} maturity assessed: {new_maturity.value} "
            f"(score: {maturity_score:.2f}, changed: {maturity_changed})"
        )

        return {
            "maturity_level": new_maturity,
            "maturity_score": maturity_score,
            "metrics": metrics,
            "changed": maturity_changed,
        }

    def _get_current_maturity(self) -> Optional[AgentMaturity]:
        """Get the current maturity level from the database.

        Returns:
            AgentMaturity enum value or None if not set
        """
        if not self.db:
            return None

        agent_data = self.db.get_agent(self.agent_id)
        if not agent_data:
            return None

        maturity_str = agent_data.get("maturity_level")
        if not maturity_str:
            return None

        try:
            return AgentMaturity(maturity_str)
        except ValueError:
            logger.warning(f"Invalid maturity level in database: {maturity_str}")
            return None

    def _update_agent_maturity(
        self, maturity: AgentMaturity, metrics: Dict[str, Any]
    ) -> None:
        """Update the agent's maturity level and metrics in the database.

        Args:
            maturity: New maturity level
            metrics: Performance metrics dictionary
        """
        import json

        if not self.db:
            return

        try:
            self.db.update_agent(
                self.agent_id,
                {
                    "maturity_level": maturity,
                    "metrics": json.dumps(metrics),
                },
            )
        except Exception as e:
            logger.error(f"Failed to update agent maturity in database: {e}")

    def _log_maturity_assessment(
        self,
        old_maturity: Optional[AgentMaturity],
        new_maturity: AgentMaturity,
        metrics: Dict[str, Any],
    ) -> None:
        """Log the maturity assessment to the audit log.

        Args:
            old_maturity: Previous maturity level (None if first assessment)
            new_maturity: New maturity level
            metrics: Performance metrics dictionary
        """
        if not self.db:
            return

        try:
            metadata = {
                "agent_id": self.agent_id,
                "old_maturity": old_maturity.value if old_maturity else None,
                "new_maturity": new_maturity.value,
                "maturity_score": metrics.get("maturity_score"),
                "metrics": metrics,
                "changed": old_maturity != new_maturity if old_maturity else True,
            }

            self.db.create_audit_log(
                event_type="agent.maturity.assessed",
                user_id=None,  # System-initiated assessment
                resource_type="agent",
                resource_id=None,  # Agents use string IDs, not integers
                ip_address=None,  # Server-side operation
                metadata=metadata,  # Pass as dict, repository serializes
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.warning(f"Failed to log maturity assessment: {e}")

    def should_assess_maturity(self, min_tasks_since_last: int = 5) -> bool:
        """Determine if maturity assessment should be triggered.

        Assessment is recommended when:
        1. Agent has completed at least `min_tasks_since_last` new tasks since last assessment
        2. 24 hours have passed since last assessment
        3. Agent has never been assessed

        Args:
            min_tasks_since_last: Minimum completed tasks to trigger assessment (default: 5)

        Returns:
            bool: True if assessment should run

        Example:
            >>> if agent.should_assess_maturity():
            ...     agent.assess_maturity()
        """
        import json

        if not self.db:
            return False

        # Get agent data to check last assessment
        agent_data = self.db.get_agent(self.agent_id)
        if not agent_data:
            return True  # Agent not in DB, needs assessment

        # Parse metrics JSON
        metrics_json = agent_data.get("metrics")
        if not metrics_json:
            return True  # Never assessed

        try:
            metrics = json.loads(metrics_json) if isinstance(metrics_json, str) else metrics_json
        except (json.JSONDecodeError, TypeError):
            return True  # Invalid metrics, needs reassessment

        # Check last assessment time
        last_assessed_str = metrics.get("last_assessed")
        if not last_assessed_str:
            return True  # No timestamp, needs assessment

        try:
            last_assessed = datetime.fromisoformat(last_assessed_str.replace("Z", "+00:00"))
            hours_since_assessment = (
                datetime.now(timezone.utc) - last_assessed
            ).total_seconds() / 3600

            if hours_since_assessment >= 24:
                return True  # 24 hours passed
        except (ValueError, TypeError):
            return True  # Invalid timestamp

        # Check completed task count since last assessment
        current_tasks = self.db.get_tasks_by_agent(self.agent_id)

        # Count completed tasks
        current_completed = len([t for t in current_tasks if t.status == TaskStatus.COMPLETED])
        last_completed = metrics.get("completed_count", 0)

        if current_completed - last_completed >= min_tasks_since_last:
            return True  # Enough new completed tasks

        return False

    async def flash_save(self) -> Dict[str, Any]:
        """Save current state before context compactification (T056).

        Creates a checkpoint with full context state and archives COLD tier items
        to reduce memory footprint. This method is called automatically when context
        approaches the token limit or manually via API.

        Returns:
            dict: Flash save response with checkpoint_id, tokens_before, tokens_after, reduction_percentage

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = BackendWorkerAgent(agent_id="backend-001", db=db)
            >>> # Assign task to establish project context
            >>> agent.execute_task(task)
            >>> result = await agent.flash_save()
            >>> print(f"Reduced from {result['tokens_before']} to {result['tokens_after']} tokens")
            Reduced from 150000 to 50000 tokens
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Get project_id from current task
        project_id = self._get_project_id()

        from codeframe.lib.context_manager import ContextManager

        # Create context manager and execute flash save
        context_mgr = ContextManager(db=self.db)
        result = context_mgr.flash_save(project_id, self.agent_id)

        return result

    async def should_flash_save(self) -> bool:
        """Check if flash save should be triggered (T057).

        Determines if this agent's context has exceeded the token threshold
        (80% of 180k = 144k tokens) and flash save should be triggered.

        Returns:
            bool: True if flash save should be triggered, False otherwise

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = BackendWorkerAgent(agent_id="backend-001", db=db)
            >>> # Assign task to establish project context
            >>> agent.execute_task(task)
            >>> if await agent.should_flash_save():
            ...     await agent.flash_save()
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Get project_id from current task
        project_id = self._get_project_id()

        from codeframe.lib.context_manager import ContextManager

        # Create context manager and check threshold
        context_mgr = ContextManager(db=self.db)
        return context_mgr.should_flash_save(project_id, self.agent_id, force=False)

    async def save_context_item(self, item_type: ContextItemType, content: str) -> str:
        """Save a context item for this agent.

        Args:
            item_type: Type of context (TASK, CODE, ERROR, TEST_RESULT, PRD_SECTION)
            content: The context content to save

        Returns:
            str: The created context item ID (UUID)

        Raises:
            ValueError: If db is not initialized or content is empty
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        if not content or not content.strip():
            raise ValueError("Content cannot be empty")

        # Get project_id from current task
        project_id = self._get_project_id()

        # Call database create_context_item - score is auto-calculated (Phase 4)
        item_id = self.db.create_context_item(
            project_id=project_id,
            agent_id=self.agent_id,
            item_type=item_type.value,
            content=content,
        )

        return item_id

    async def load_context(
        self, tier: Optional[ContextTier] = ContextTier.HOT
    ) -> List[Dict[str, Any]]:
        """Load context items for this agent, optionally filtered by tier.

        Args:
            tier: Tier to filter by (HOT/WARM/COLD), or None for all tiers

        Returns:
            list[dict]: Context items for this agent

        Raises:
            ValueError: If db is not initialized
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Get project_id from current task
        project_id = self._get_project_id()

        # Call database list_context_items with:
        # - project_id from current task
        # - agent_id=self.agent_id
        # - tier=tier.value if tier else None
        # - limit=100
        tier_value = tier.value if tier else None
        items = self.db.list_context_items(
            project_id=project_id, agent_id=self.agent_id, tier=tier_value, limit=100
        )

        # Update access tracking for each loaded item
        for item in items:
            self.db.update_context_item_access(item["id"])

        return items

    async def get_context_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific context item by ID.

        Args:
            item_id: The context item ID (UUID string)

        Returns:
            dict | None: The context item, or None if not found

        Raises:
            ValueError: If db is not initialized
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Call database get_context_item
        item = self.db.get_context_item(item_id)

        # Update access tracking if item exists
        if item:
            self.db.update_context_item_access(item_id)

        return item

    async def update_tiers(self) -> int:
        """Recalculate scores and reassign tiers for all context items (T043).

        This method triggers batch tier reassignment for all context items
        belonging to this agent. It:
        1. Recalculates importance scores based on current age/access patterns
        2. Reassigns tiers (HOT >= 0.8, WARM 0.4-0.8, COLD < 0.4)

        Use cases:
        - Periodic maintenance (called by scheduler/cron)
        - Manual trigger to move aged items to lower tiers
        - After major time passage (e.g., daily cleanup)

        Returns:
            int: Number of context items updated with new tiers

        Raises:
            ValueError: If db is not initialized

        Example:
            >>> agent = FrontendWorkerAgent(agent_id="frontend-001", db=db)
            >>> # Assign task to establish project context
            >>> agent.execute_task(task)
            >>> updated = await agent.update_tiers()
            >>> print(f"Updated {updated} items")
            Updated 25 items
        """
        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Get project_id from current task
        project_id = self._get_project_id()

        from codeframe.lib.context_manager import ContextManager

        # Create context manager and trigger tier updates
        context_mgr = ContextManager(db=self.db)
        updated_count = context_mgr.update_tiers_for_agent(project_id, self.agent_id)

        return updated_count

    # ========================================================================
    # Sprint 10 Phase 3: Quality Gates Integration (T060-T061)
    # ========================================================================

    async def complete_task(self, task: Task, project_root: Optional[Any] = None) -> Dict[str, Any]:
        """Complete a task after running quality gates.

        This method is called when an agent has finished working on a task and wants
        to mark it as complete. Before allowing completion, it runs all quality gates
        to ensure code quality standards are met.

        Workflow:
            1. Run all quality gates (tests, type checking, coverage, review, linting)
            2. If any gate fails → create blocker, keep task in_progress, return failure
            3. If all gates pass → mark task as completed, return success
            4. If risky changes detected → set requires_human_approval flag

        Args:
            task: Task to complete
            project_root: Project root directory path (optional, defaults to workspace_path from DB)

        Returns:
            dict with keys:
                - success: bool - Whether task was completed successfully
                - status: str - 'completed', 'blocked', or 'failed'
                - quality_gate_result: QualityGateResult object
                - blocker_id: int (optional) - ID of created blocker if gates failed
                - message: str - Human-readable result message

        Raises:
            ValueError: If db is not initialized or project_id is missing

        Example:
            >>> agent = WorkerAgent(agent_id="backend-001", agent_type="backend",
            ...                     provider="anthropic", db=db)
            >>> result = await agent.complete_task(task, project_root=Path("/app"))
            >>> if result['success']:
            ...     print("Task completed successfully!")
            ... else:
            ...     print(f"Task blocked: {result['message']}")
        """
        import logging
        from pathlib import Path
        from codeframe.lib.quality_gates import QualityGates

        logger = logging.getLogger(__name__)

        if not self.db:
            raise ValueError("Database not initialized. Pass db parameter to __init__")

        # Set current task to establish project context
        self.current_task = task

        # Get project_id from task
        project_id = self._get_project_id()

        # Get project root from database if not provided
        if project_root is None:
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT workspace_path FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Project {project_id} not found")
            project_root = Path(row[0])

        logger.info(f"Agent {self.agent_id} attempting to complete task {task.id}")

        # Step 1: Run quality gates
        quality_gates = QualityGates(
            db=self.db,
            project_id=project_id,
            project_root=project_root,
        )

        quality_result = await quality_gates.run_all_gates(task)

        # Step 2: Evidence Verification (Evidence-Based Quality Enforcement)
        from codeframe.enforcement.evidence_verifier import EvidenceVerifier
        from codeframe.enforcement.language_detector import LanguageDetector

        # Detect project language
        detector = LanguageDetector(str(project_root))
        lang_info = detector.detect()

        # Extract test results and skip violations from quality gate result
        test_result = quality_gates.get_test_results_from_gate_result(quality_result)
        skip_violations = quality_gates.get_skip_violations_from_gate_result(quality_result)

        # Handle case where quality gates didn't run tests (no test result available)
        if test_result is None:
            from codeframe.enforcement.adaptive_test_runner import TestResult
            test_result = TestResult(
                success=True,
                output="No tests run - quality gates passed without test execution",
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                pass_rate=100.0,
                coverage=None,
            )

        # Initialize EvidenceVerifier with configuration from environment
        from codeframe.config.security import get_evidence_config
        evidence_config = get_evidence_config()
        verifier = EvidenceVerifier(**evidence_config)

        # Collect evidence
        evidence = verifier.collect_evidence(
            test_result=test_result,
            skip_violations=skip_violations,
            language=lang_info.language,
            agent_id=self.agent_id,
            task_description=task.title,
            framework=lang_info.framework,
        )

        # Verify evidence
        is_valid = verifier.verify(evidence)

        # If evidence verification failed, create blocker and return
        if not is_valid:
            logger.warning(
                f"Evidence verification failed for task {task.id}: {evidence.verification_errors}"
            )

            # Generate verification report
            report = verifier.generate_report(evidence)

            # Create blocker with verification errors
            blocker_id = self._create_evidence_blocker(task, evidence, report)

            # Store failed evidence for audit trail
            self.db.task_repository.save_task_evidence(task.id, evidence)

            return {
                "success": False,
                "status": "blocked",
                "quality_gate_result": quality_result,
                "blocker_id": blocker_id,
                "message": "Evidence verification failed. See blocker for details.",
                "evidence_errors": evidence.verification_errors,
            }

        logger.info(f"Evidence verified successfully for task {task.id}")

        # Step 3: Record quality metrics for tracking
        await self._record_quality_metrics(quality_result, project_root)

        # Step 4: Check for quality degradation
        degradation_result = self._check_quality_degradation()
        if degradation_result and degradation_result.get("has_degradation"):
            # Quality has degraded significantly - create blocker
            logger.warning(
                f"Task {task.id} blocked due to quality degradation: {degradation_result.get('issues')}"
            )

            # Create blocker for degradation
            blocker_id = self._create_degradation_blocker(task, degradation_result)

            return {
                "success": False,
                "status": "blocked",
                "quality_gate_result": quality_result,
                "blocker_id": blocker_id,
                "message": f"Quality degradation detected. {degradation_result.get('recommendation', 'Consider context reset.')}",
                "degradation": degradation_result,
            }

        # Step 5: Check if gates passed
        if quality_result.passed:
            # All gates passed - store evidence and mark task as completed
            # Use transaction to ensure atomicity

            try:
                # Store evidence in database (deferred commit for transaction atomicity)
                evidence_id = self.db.task_repository.save_task_evidence(
                    task.id, evidence, commit=False
                )
                logger.debug(f"Prepared evidence {evidence_id} for task {task.id}")

                # Update task status
                cursor = self.db.conn.cursor()
                cursor.execute(
                    """
                    UPDATE tasks
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (TaskStatus.COMPLETED.value, task.id),
                )

                # Commit both operations atomically
                self.db.conn.commit()

                logger.info(
                    f"Task {task.id} completed successfully - "
                    f"all quality gates passed and evidence {evidence_id} verified"
                )

                return {
                    "success": True,
                    "status": "completed",
                    "quality_gate_result": quality_result,
                    "evidence_verified": True,
                    "evidence_id": evidence_id,
                    "message": "Task completed successfully - all quality gates passed and evidence verified",
                }
            except Exception as e:
                # Rollback both operations on any error to maintain consistency
                self.db.conn.rollback()
                logger.error(f"Failed to complete task {task.id} with evidence: {e}")
                raise
        else:
            # Quality gates failed - task remains in_progress, blocker created
            logger.warning(
                f"Task {task.id} blocked by quality gates - {len(quality_result.failures)} failures"
            )

            # Get blocker ID (created by quality gates)
            cursor = self.db.conn.cursor()
            cursor.execute(
                "SELECT id FROM blockers WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
                (task.id,),
            )
            blocker_row = cursor.fetchone()
            blocker_id = blocker_row[0] if blocker_row else None

            return {
                "success": False,
                "status": "blocked",
                "quality_gate_result": quality_result,
                "blocker_id": blocker_id,
                "message": f"Task blocked by quality gates - {len(quality_result.failures)} failures. "
                f"Fix issues and try again.",
            }

    def _create_quality_blocker(self, task: Task, failures: List[Any]) -> int:
        """Create a SYNC blocker for quality gate failures.

        This is a helper method called by complete_task when quality gates fail.
        It creates a blocker with detailed information about the failures.

        Args:
            task: Task that failed quality gates
            failures: List of QualityGateFailure objects

        Returns:
            int: ID of the created blocker

        Example:
            >>> blocker_id = agent._create_quality_blocker(task, failures)
            >>> print(f"Created blocker {blocker_id}")
        """
        from codeframe.core.models import BlockerType, Severity

        if not failures:
            raise ValueError("Cannot create blocker without failures")

        # Format failures into blocker question
        question_parts = [
            f"Quality gates failed for task #{task.task_number} ({task.title}):",
            "",
        ]

        for i, failure in enumerate(failures[:10], 1):  # Limit to 10 failures
            severity_emoji = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "⚪",
            }
            emoji = severity_emoji.get(failure.severity, "⚪")

            question_parts.append(f"{i}. {emoji} [{failure.gate.value.upper()}] {failure.reason}")

            if failure.details:
                # Truncate details to first 3 lines
                detail_lines = failure.details.split("\n")[:3]
                for line in detail_lines:
                    question_parts.append(f"   {line}")

            question_parts.append("")

        question_parts.append(
            "Fix these issues before completing the task. Type 'resolved' when fixed."
        )

        question = "\n".join(question_parts)

        # Get project_id from task
        project_id = task.project_id if task.project_id else self._get_project_id()

        # Create SYNC blocker
        blocker_id = self.db.create_blocker(
            agent_id=self.agent_id,
            project_id=project_id,
            task_id=task.id,
            blocker_type=BlockerType.SYNC,
            question=question,
        )

        return blocker_id

    # ========================================================================
    # Quality Tracking Integration Methods
    # ========================================================================

    async def _record_quality_metrics(
        self,
        quality_result: Any,
        project_root: Any,
    ) -> None:
        """Record quality metrics after quality gates run.

        This method extracts metrics from quality gate results and records them
        using the QualityTracker for trend analysis and degradation detection.

        Args:
            quality_result: QualityGateResult from quality gates
            project_root: Project root path for language detection

        Example:
            >>> await agent._record_quality_metrics(quality_result, Path("/app"))
        """
        from codeframe.enforcement.language_detector import LanguageDetector

        tracker = self._ensure_quality_tracker()
        if not tracker:
            logger.debug("Quality tracker not available, skipping metrics recording")
            return

        try:
            # Extract metrics from quality gate result
            test_pass_rate = 100.0
            coverage_percentage = 0.0
            total_tests = 0
            passed_tests = 0
            failed_tests = 0

            # Parse failures to extract test and coverage metrics
            for failure in quality_result.failures:
                gate_name = getattr(failure, "gate", None)
                if gate_name:
                    gate_value = gate_name.value if hasattr(gate_name, "value") else str(gate_name)

                    if gate_value == "tests":
                        # Extract test counts from failure
                        reason = getattr(failure, "reason", "")
                        # Parse patterns like "3 tests failed" or "Pytest failed: 5 failed"
                        import re
                        failed_match = re.search(r"(\d+)\s*failed", reason)
                        if failed_match:
                            failed_tests = int(failed_match.group(1))

                        passed_match = re.search(r"(\d+)\s*passed", reason)
                        if passed_match:
                            passed_tests = int(passed_match.group(1))

                        total_tests = passed_tests + failed_tests
                        if total_tests > 0:
                            test_pass_rate = (passed_tests / total_tests) * 100

                    elif gate_value == "coverage":
                        # Extract coverage percentage from failure
                        reason = getattr(failure, "reason", "")
                        coverage_match = re.search(r"(\d+(?:\.\d+)?)\s*%", reason)
                        if coverage_match:
                            coverage_percentage = float(coverage_match.group(1))

            # If no failures, assume perfect scores
            if not quality_result.failures:
                test_pass_rate = 100.0
                # Try to get coverage from other sources if available
                coverage_percentage = 100.0  # Assume passed coverage check

            # Detect language for context
            language = "unknown"
            framework = None
            try:
                detector = LanguageDetector(str(project_root) if project_root else ".")
                lang_info = detector.detect()
                language = lang_info.language
                framework = lang_info.framework
            except Exception as e:
                logger.debug(f"Language detection failed: {e}")

            # Create and record metrics
            metrics = QualityMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                response_count=self.response_count,
                test_pass_rate=test_pass_rate,
                coverage_percentage=coverage_percentage,
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                language=language,
                framework=framework,
            )

            tracker.record(metrics)
            logger.info(
                f"Quality metrics recorded: pass_rate={test_pass_rate:.1f}%, "
                f"coverage={coverage_percentage:.1f}%, response_count={self.response_count}"
            )

        except Exception as e:
            # Don't fail task completion if metrics recording fails
            logger.warning(f"Failed to record quality metrics: {e}")

    def _check_quality_degradation(self, threshold_percent: float = 10.0) -> Optional[Dict[str, Any]]:
        """Check if quality has degraded significantly.

        Args:
            threshold_percent: Degradation threshold (default: 10%)

        Returns:
            Dict with degradation info if degraded, None otherwise

        Example:
            >>> result = agent._check_quality_degradation()
            >>> if result and result.get("has_degradation"):
            ...     print("Quality degraded!")
        """
        tracker = self._ensure_quality_tracker()
        if not tracker:
            return None

        try:
            return tracker.check_degradation(threshold_percent=threshold_percent)
        except Exception as e:
            logger.warning(f"Failed to check quality degradation: {e}")
            return None

    def _create_degradation_blocker(self, task: Task, degradation: Dict[str, Any]) -> int:
        """Create a SYNC blocker for quality degradation.

        Args:
            task: Task that triggered degradation check
            degradation: Degradation result from QualityTracker

        Returns:
            int: ID of the created blocker

        Example:
            >>> blocker_id = agent._create_degradation_blocker(task, degradation)
        """
        from codeframe.core.models import BlockerType

        # Format degradation info into blocker question
        question_parts = [
            f"Quality degradation detected for task #{task.task_number} ({task.title}):",
            "",
            "Issues found:",
        ]

        issues = degradation.get("issues", [])
        for i, issue in enumerate(issues[:5], 1):
            question_parts.append(f"  {i}. {issue}")

        question_parts.extend([
            "",
            f"Recommendation: {degradation.get('recommendation', 'Consider context reset.')}",
            "",
            "Options:",
            "  1. Reset context and continue with fresh conversation",
            "  2. Investigate and fix quality issues",
            "  3. Type 'continue' to proceed anyway (not recommended)",
        ])

        question = "\n".join(question_parts)

        # Get project_id from task
        project_id = task.project_id if task.project_id else self._get_project_id()

        # Create SYNC blocker
        blocker_id = self.db.create_blocker(
            agent_id=self.agent_id,
            project_id=project_id,
            task_id=task.id,
            blocker_type=BlockerType.SYNC,
            question=question,
        )

        logger.info(f"Created degradation blocker {blocker_id} for task {task.id}")
        return blocker_id

    def _create_evidence_blocker(self, task: Task, evidence: "Evidence", report: str) -> int:
        """Create a SYNC blocker for evidence verification failure.

        Args:
            task: Task that failed evidence verification
            evidence: Evidence object with verification errors
            report: Formatted verification report

        Returns:
            int: ID of the created blocker

        Example:
            >>> blocker_id = agent._create_evidence_blocker(task, evidence, report)
        """
        from codeframe.core.models import BlockerType
        from codeframe.config.security import get_evidence_config

        # Get evidence config for context
        evidence_config = get_evidence_config()

        question_parts = [
            f"Evidence verification failed for task #{task.task_number} ({task.title}):",
            "",
            "Test Results:",
            f"  • Total: {evidence.test_result.total_tests}",
            f"  • Passed: {evidence.test_result.passed_tests}",
            f"  • Failed: {evidence.test_result.failed_tests}",
            f"  • Skipped: {evidence.test_result.skipped_tests}",
            f"  • Pass Rate: {evidence.test_result.pass_rate:.1f}%",
        ]

        if evidence.test_result.coverage is not None:
            question_parts.append(
                f"  • Coverage: {evidence.test_result.coverage:.1f}% "
                f"(minimum: {evidence_config['min_coverage']:.1f}%)"
            )
        else:
            question_parts.append("  • Coverage: Not available")

        question_parts.extend([
            "",
            "Verification Errors:",
        ])

        # Limit error display to prevent unbounded messages
        MAX_ERRORS_DISPLAY = 10
        errors_to_display = evidence.verification_errors[:MAX_ERRORS_DISPLAY]

        for i, error in enumerate(errors_to_display, 1):
            question_parts.append(f"  {i}. {error}")

        if len(evidence.verification_errors) > MAX_ERRORS_DISPLAY:
            remaining = len(evidence.verification_errors) - MAX_ERRORS_DISPLAY
            question_parts.append(
                f"  ... and {remaining} more error(s) (see full evidence report)"
            )

        question_parts.extend([
            "",
            "Full Verification Report:",
            "```",
            report,
            "```",
            "",
            "Required Actions:",
            "  1. Fix the issues listed above",
            "  2. Ensure all tests pass with required coverage",
            "  3. Remove any skip patterns from tests",
            "  4. Re-run quality gates",
            "",
            "Type 'resolved' when all issues are fixed."
        ])

        question = "\n".join(question_parts)

        project_id = task.project_id if task.project_id else self._get_project_id()

        blocker_id = self.db.create_blocker(
            agent_id=self.agent_id,
            project_id=project_id,
            task_id=task.id,
            blocker_type=BlockerType.SYNC,
            question=question,
        )

        logger.info(f"Created evidence verification blocker {blocker_id} for task {task.id}")
        return blocker_id

    async def should_recommend_context_reset(self, max_responses: int = 20) -> Dict[str, Any]:
        """Check if context reset should be recommended.

        This method checks both response count and quality degradation to determine
        if the conversation context should be reset. Use this before starting new
        tasks or periodically during long-running sessions.

        Args:
            max_responses: Maximum responses before reset is recommended (default: 20)

        Returns:
            Dict with:
                - should_reset: bool
                - reasons: List[str]
                - recommendation: str

        Example:
            >>> result = await agent.should_recommend_context_reset()
            >>> if result["should_reset"]:
            ...     print(f"Reset recommended: {result['reasons']}")
        """
        tracker = self._ensure_quality_tracker()
        if not tracker:
            # Fallback to just response count check
            if self.response_count >= max_responses:
                return {
                    "should_reset": True,
                    "reasons": [f"Response count ({self.response_count}) exceeds maximum ({max_responses})"],
                    "recommendation": "Context reset recommended due to conversation length",
                }
            return {
                "should_reset": False,
                "reasons": [],
                "recommendation": "Context can continue",
            }

        try:
            return tracker.should_reset_context(
                response_count=self.response_count,
                max_responses=max_responses,
                check_degradation=True,
            )
        except Exception as e:
            logger.warning(f"Failed to check context reset recommendation: {e}")
            return {
                "should_reset": False,
                "reasons": [],
                "recommendation": f"Check failed: {e}",
            }
