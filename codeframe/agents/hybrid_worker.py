"""Hybrid Worker Agent - SDK execution with CodeFRAME coordination.

Uses SDK for task execution while preserving CodeFRAME's coordination,
context management, and quality gates integration.

This is the transitional agent pattern that bridges YAML-defined agents
with the Claude Agent SDK's execution model.

Usage:
------
```python
from codeframe.agents.hybrid_worker import HybridWorkerAgent
from codeframe.providers.sdk_client import SDKClientWrapper

# Create SDK client
sdk_client = SDKClientWrapper(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    model="claude-sonnet-4-20250514",
    system_prompt="You are a backend developer...",
    allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
    cwd="/path/to/project",
)

# Create hybrid agent
agent = HybridWorkerAgent(
    agent_id="backend-001",
    agent_type="backend",
    project_id=1,
    db=db,
    sdk_client=sdk_client,
)

# Execute task
result = await agent.execute_task(task)

# Complete with quality gates
completion_result = await agent.complete_task(task, project_root="/path/to/project")
```
"""

import logging
from typing import Optional, Dict, Any, List

from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import (
    Task,
    AgentMaturity,
    ContextItemType,
    ContextTier,
    CallType,
)
from codeframe.providers.sdk_client import SDKClientWrapper

logger = logging.getLogger(__name__)


class HybridWorkerAgent(WorkerAgent):
    """Worker agent using SDK for execution, CodeFRAME for coordination.

    This hybrid agent pattern enables gradual migration to the Claude Agent SDK
    while preserving CodeFRAME's key features:

    - **Context Management**: Tiered memory (HOT/WARM/COLD) with importance scoring
    - **Quality Gates**: Pre-completion checks (tests, types, coverage, review)
    - **Token Tracking**: Per-task token usage with MetricsTracker
    - **Session Management**: SDK session ID tracking for resume capability

    The execution flow is:
    1. Load context (HOT + WARM tiers)
    2. Build prompt with context
    3. Execute via SDK
    4. Save results to context
    5. Record token usage
    6. (On complete_task) Run quality gates

    Attributes:
        sdk_client: SDKClientWrapper instance for LLM execution
        session_id: Current SDK session ID (for tracking/resume)
        definition: AgentDefinition (optional, set by AgentFactory)
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        project_id: int,
        db: Any,
        sdk_client: SDKClientWrapper,
        provider: str = "sdk",
        maturity: AgentMaturity = AgentMaturity.D1,
        system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Initialize HybridWorkerAgent.

        Args:
            agent_id: Unique identifier for this agent instance
            agent_type: Type category (backend, frontend, test, review)
            project_id: Project context for multi-agent coordination
            db: Database instance for persistence
            sdk_client: Pre-configured SDKClientWrapper for LLM calls
            provider: Provider name (default: "sdk")
            maturity: Agent maturity level D1-D4
            system_prompt: System prompt override (optional, loaded from definition)
            session_id: Existing SDK session ID for resume (optional)
        """
        super().__init__(
            agent_id=agent_id,
            agent_type=agent_type,
            provider=provider,
            project_id=project_id,
            maturity=maturity,
            system_prompt=system_prompt,
            db=db,
        )

        self.sdk_client = sdk_client
        self.session_id = session_id
        self.definition = None  # Set by AgentFactory if using YAML definitions

        logger.info(
            f"HybridWorkerAgent initialized: {agent_id} (type={agent_type}, "
            f"project_id={project_id}, maturity={maturity.value})"
        )

    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute task using SDK with CodeFRAME coordination.

        This method:
        1. Loads context from tiered memory (HOT + WARM)
        2. Builds a contextual prompt for the task
        3. Executes via SDK (with tool use)
        4. Saves task result to context
        5. Records token usage metrics

        Args:
            task: Task to execute

        Returns:
            dict with keys:
                - status: "completed" | "failed" | "blocked"
                - content: LLM response content
                - output: Same as content (for compatibility)
                - files_changed: List of modified file paths (if any)
                - usage: Token usage dict {input_tokens, output_tokens}
                - session_id: SDK session ID (for tracking)

        Raises:
            ValueError: If db or project_id not initialized
        """
        self.current_task = task

        logger.info(f"Agent {self.agent_id} executing task {task.id}: {task.title}")

        # Step 1: Load context from tiered memory
        hot_context = await self.load_context(tier=ContextTier.HOT)
        warm_context = await self.load_context(tier=ContextTier.WARM)

        logger.debug(
            f"Loaded context: {len(hot_context)} HOT items, {len(warm_context)} WARM items"
        )

        # Step 2: Build contextual prompt
        prompt = self._build_execution_prompt(task, hot_context, warm_context)

        # Step 3: Execute via SDK
        try:
            response = await self.sdk_client.send_message([{"role": "user", "content": prompt}])
        except Exception as e:
            logger.error(f"SDK execution failed for task {task.id}: {e}")
            return {
                "status": "failed",
                "content": str(e),
                "output": str(e),
                "files_changed": [],
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "session_id": self.session_id,
            }

        # Step 4: Save task result to context
        result_summary = self._summarize_result(response.get("content", ""))
        await self.save_context_item(
            item_type=ContextItemType.TASK,
            content=f"Task {task.id} result: {result_summary}",
        )

        # Step 5: Record token usage metrics
        await self._record_token_usage(task, response)

        # Step 6: Check if flash save needed
        if await self.should_flash_save():
            logger.info(f"Token threshold exceeded, triggering flash save for {self.agent_id}")
            await self.flash_save()

        logger.info(
            f"Task {task.id} executed successfully - "
            f"{response.get('usage', {}).get('input_tokens', 0)} input, "
            f"{response.get('usage', {}).get('output_tokens', 0)} output tokens"
        )

        return {
            "status": "completed",
            "content": response.get("content", ""),
            "output": response.get("content", ""),
            "files_changed": self._extract_changed_files(response.get("content", "")),
            "usage": response.get("usage", {"input_tokens": 0, "output_tokens": 0}),
            "session_id": self.session_id,
        }

    def _build_execution_prompt(
        self,
        task: Task,
        hot_context: List[Dict[str, Any]],
        warm_context: List[Dict[str, Any]],
    ) -> str:
        """Build prompt with context and task description.

        Args:
            task: Task to execute
            hot_context: High-priority context items
            warm_context: Medium-priority context items

        Returns:
            Complete prompt string for SDK execution
        """
        # Build context section
        context_items = []
        for item in hot_context + warm_context[:20]:  # Limit warm context
            item_type = item.get("item_type", "UNKNOWN")
            content = item.get("content", "")
            # Truncate long items
            if len(content) > 500:
                content = content[:500] + "..."
            context_items.append(f"[{item_type}] {content}")

        context_section = "\n".join(context_items) if context_items else "No prior context."

        # Build task section
        task_section = f"""## Task #{task.task_number}: {task.title}

{task.description or "No description provided."}"""

        # Add dependencies if present
        depends_section = ""
        if task.depends_on:
            depends_section = f"\n\n### Dependencies\nDepends on tasks: {task.depends_on}"

        # Build complete prompt
        return f"""## Context
{context_section}

{task_section}{depends_section}

## Instructions
Complete this task using the available tools. Follow these guidelines:
- Read existing code before modifying
- Follow the coding standards and patterns in the codebase
- Write tests for new functionality
- Use meaningful commit messages
- Handle errors gracefully

When you have completed the task, provide a summary of what was done."""

    def _summarize_result(self, content: str, max_length: int = 500) -> str:
        """Summarize task result for context storage.

        Args:
            content: Full LLM response content
            max_length: Maximum length of summary

        Returns:
            Truncated summary string
        """
        if not content:
            return "No output"

        # Take first paragraph or max_length characters
        first_para = content.split("\n\n")[0]
        if len(first_para) <= max_length:
            return first_para

        return first_para[:max_length] + "..."

    def _extract_changed_files(self, content: str) -> List[str]:
        """Extract file paths from response content.

        Attempts to find file paths mentioned in the LLM response.

        Args:
            content: LLM response content

        Returns:
            List of file paths found in content
        """
        import re

        # Pattern to match common file path patterns
        patterns = [
            r'(?:created|modified|updated|wrote|saved)\s+[`"]?([a-zA-Z0-9_/\-\.]+\.[a-z]+)[`"]?',
            r'(?:file|path):\s*[`"]?([a-zA-Z0-9_/\-\.]+\.[a-z]+)[`"]?',
            r"`([a-zA-Z0-9_/\-]+(?:/[a-zA-Z0-9_\-\.]+)+\.[a-z]+)`",
        ]

        files = set()
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            files.update(matches)

        return sorted(list(files))

    async def _record_token_usage(self, task: Task, response: Dict[str, Any]) -> None:
        """Record token usage metrics for this task.

        Args:
            task: Task that was executed
            response: SDK response with usage info
        """
        try:
            from codeframe.lib.metrics_tracker import MetricsTracker

            usage = response.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)

            if input_tokens == 0 and output_tokens == 0:
                return  # No tokens to record

            tracker = MetricsTracker(db=self.db)
            await tracker.record_token_usage(
                task_id=task.id,
                agent_id=self.agent_id,
                project_id=self.project_id,
                model_name="claude-sonnet-4-20250514",  # TODO: Get from SDK client
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                call_type=CallType.TASK_EXECUTION.value,
                session_id=self.session_id,
            )
        except Exception as e:
            # Don't fail task execution if metrics recording fails
            logger.warning(f"Failed to record token usage: {e}")

    async def execute_with_streaming(self, task: Task):
        """Execute task with streaming response.

        Similar to execute_task but yields intermediate results for
        real-time UI updates. This is an async generator.

        Args:
            task: Task to execute

        Yields:
            dict with keys:
                - status: "streaming" for intermediate, "completed" for final
                - content_chunk: Partial content (for streaming chunks)
                - content: Full content (for final result)
                - task_id: Task ID
                - files_changed: List of modified files (final only)
                - session_id: SDK session ID (final only)
        """
        self.current_task = task

        # Load context
        hot_context = await self.load_context(tier=ContextTier.HOT)
        warm_context = await self.load_context(tier=ContextTier.WARM)

        # Build prompt
        prompt = self._build_execution_prompt(task, hot_context, warm_context)

        # Stream execution
        full_content = []

        async for message in self.sdk_client.send_message_streaming(prompt):
            if hasattr(message, "content"):
                content_chunk = str(message.content)
                full_content.append(content_chunk)
                yield {
                    "status": "streaming",
                    "content_chunk": content_chunk,
                    "task_id": task.id,
                }

        # Combine and yield final result
        final_content = "".join(full_content)

        # Save to context
        result_summary = self._summarize_result(final_content)
        await self.save_context_item(
            item_type=ContextItemType.TASK,
            content=f"Task {task.id} result: {result_summary}",
        )

        # Yield final result (async generators can't use return with value)
        yield {
            "status": "completed",
            "content": final_content,
            "output": final_content,
            "files_changed": self._extract_changed_files(final_content),
            "session_id": self.session_id,
        }

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information.

        Returns:
            dict with agent and session details
        """
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "project_id": self.project_id,
            "maturity": self.maturity.value,
            "session_id": self.session_id,
            "has_sdk_client": self.sdk_client is not None,
            "definition_name": self.definition.name if self.definition else None,
        }
