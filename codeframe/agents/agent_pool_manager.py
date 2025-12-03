"""
Agent Pool Manager for parallel task execution (Sprint 4: cf-24).

This module manages a pool of worker agents, enabling reuse and parallel execution.
Supports both traditional WorkerAgents and HybridWorkerAgents for SDK execution.

Usage with SDK mode:
--------------------
```python
# Create pool with SDK mode enabled
pool = AgentPoolManager(
    project_id=1,
    db=db,
    use_sdk=True,  # Enable SDK execution
)

# Create hybrid agent (uses SDK for execution)
agent_id = pool.create_agent("backend")

# Get agent instance for task execution
agent = pool.get_agent_instance(agent_id)
result = await agent.execute_task(task)
```

Feature flags:
- `use_sdk=True`: Create HybridWorkerAgent instances (SDK execution)
- `use_sdk=False`: Create traditional WorkerAgent instances (default)
"""

import logging
import asyncio
import os
from typing import Dict, Optional, Any, Union
from threading import RLock

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent
from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.agents.review_worker_agent import ReviewWorkerAgent
from codeframe.agents.hybrid_worker import HybridWorkerAgent
from codeframe.core.models import AgentMaturity
from codeframe.ui.websocket_broadcasts import broadcast_agent_created, broadcast_agent_retired

logger = logging.getLogger(__name__)

# SDK availability check
try:
    from codeframe.providers.sdk_client import SDKClientWrapper

    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    logger.warning("SDK client not available - falling back to traditional agents")


class AgentPoolManager:
    """
    Agent Pool Manager for parallel task execution.

    Capabilities:
    - Create worker agents of different types (backend, frontend, test)
    - Reuse idle agents to minimize overhead
    - Track agent status (idle, busy, blocked)
    - Enforce maximum agent limit
    - Retire agents and cleanup resources
    - Broadcast agent lifecycle events via WebSocket
    """

    def __init__(
        self,
        project_id: int,
        db,
        ws_manager=None,
        max_agents: int = 10,
        api_key: Optional[str] = None,
        use_sdk: bool = False,
        model: str = "claude-sonnet-4-20250514",
        cwd: Optional[str] = None,
        codebase_index=None,
    ):
        """
        Initialize Agent Pool Manager.

        Args:
            project_id: Project ID for this pool
            db: Database instance
            ws_manager: WebSocket manager for broadcasts (optional)
            max_agents: Maximum number of concurrent agents (default: 10)
            api_key: Anthropic API key (optional, will use env var if not provided)
            use_sdk: Whether to create HybridWorkerAgents with SDK execution (default: False)
            model: Model to use for SDK agents (default: claude-sonnet-4-20250514)
            cwd: Working directory for SDK agents (default: current directory)
            codebase_index: CodebaseIndex instance for pattern searching (optional)
        """
        self.project_id = project_id
        self.db = db
        self.ws_manager = ws_manager
        self.max_agents = max_agents
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.use_sdk = use_sdk and SDK_AVAILABLE
        self.model = model
        self.cwd = cwd or os.getcwd()
        self.codebase_index = codebase_index

        # Agent pool: {agent_id: agent_info}
        self.agent_pool: Dict[str, Dict[str, Any]] = {}

        # Agent ID counter
        self.next_agent_number = 1

        # Thread lock for pool operations (using RLock for reentrancy)
        self.lock = RLock()

        # Log SDK mode status
        if use_sdk and not SDK_AVAILABLE:
            logger.warning("SDK requested but not available - using traditional agents")

        logger.info(
            f"Agent Pool Manager initialized: project_id={project_id}, "
            f"max_agents={max_agents}, use_sdk={self.use_sdk}"
        )

    def create_agent(self, agent_type: str, use_sdk: Optional[bool] = None) -> str:
        """
        Create new worker agent of specified type.

        Args:
            agent_type: Type of agent to create (backend, frontend, test, review)
            use_sdk: Override pool's use_sdk setting for this agent (optional)

        Returns:
            agent_id: ID of created agent

        Raises:
            ValueError: If unknown agent type
            RuntimeError: If agent pool at maximum capacity
        """
        # Determine whether to use SDK for this agent
        create_hybrid = use_sdk if use_sdk is not None else self.use_sdk

        with self.lock:
            # Check pool capacity
            if len(self.agent_pool) >= self.max_agents:
                raise RuntimeError(
                    f"Agent pool at maximum capacity ({self.max_agents} agents). "
                    "Retire an agent before creating a new one."
                )

            # Generate agent ID
            agent_id = f"{agent_type}-worker-{self.next_agent_number:03d}"
            self.next_agent_number += 1

            # Create agent instance based on mode and type
            if create_hybrid and SDK_AVAILABLE:
                agent_instance = self._create_hybrid_agent(agent_id, agent_type)
            else:
                agent_instance = self._create_traditional_agent(agent_id, agent_type)

            is_hybrid = create_hybrid and SDK_AVAILABLE

            # Add to pool
            self.agent_pool[agent_id] = {
                "instance": agent_instance,
                "status": "idle",  # idle | busy | blocked
                "current_task": None,
                "agent_type": agent_type,
                "tasks_completed": 0,
                "blocked_by": None,
                "is_hybrid": is_hybrid,
                "session_id": getattr(agent_instance, "session_id", None),
            }

            logger.info(f"Created agent: {agent_id} (type: {agent_type}, hybrid={is_hybrid})")

            # Broadcast agent creation
            self._broadcast_async(self.project_id, agent_id, agent_type, event_type="agent_created")

            return agent_id

    def get_or_create_agent(self, agent_type: str) -> str:
        """
        Get idle agent of specified type or create new one.

        Reuses idle agents before creating new ones to minimize overhead.

        Args:
            agent_type: Type of agent needed (backend, frontend, test)

        Returns:
            agent_id: ID of available agent
        """
        with self.lock:
            # Look for idle agent of this type
            for agent_id, agent_info in self.agent_pool.items():
                if agent_info["agent_type"] == agent_type and agent_info["status"] == "idle":
                    logger.debug(f"Reusing idle agent: {agent_id}")
                    return agent_id

            # No idle agent found - create new one
            return self.create_agent(agent_type)

    def mark_agent_busy(self, agent_id: str, task_id: int) -> None:
        """
        Mark agent as busy with a task.

        Args:
            agent_id: ID of agent to mark busy
            task_id: ID of task being executed

        Raises:
            KeyError: If agent not in pool
        """
        with self.lock:
            if agent_id not in self.agent_pool:
                raise KeyError(f"Agent {agent_id} not in pool")

            self.agent_pool[agent_id]["status"] = "busy"
            self.agent_pool[agent_id]["current_task"] = task_id

            logger.debug(f"Agent {agent_id} marked busy with task {task_id}")

    def mark_agent_idle(self, agent_id: str) -> None:
        """
        Mark agent as idle and ready for new task.

        Args:
            agent_id: ID of agent to mark idle

        Raises:
            KeyError: If agent not in pool
        """
        with self.lock:
            if agent_id not in self.agent_pool:
                raise KeyError(f"Agent {agent_id} not in pool")

            self.agent_pool[agent_id]["status"] = "idle"
            self.agent_pool[agent_id]["current_task"] = None

            # Increment tasks completed
            self.agent_pool[agent_id]["tasks_completed"] += 1

            logger.debug(
                f"Agent {agent_id} marked idle (completed {self.agent_pool[agent_id]['tasks_completed']} tasks)"
            )

    def mark_agent_blocked(self, agent_id: str, blocked_by: list) -> None:
        """
        Mark agent as blocked by dependencies.

        Args:
            agent_id: ID of agent to mark blocked
            blocked_by: List of task IDs blocking this agent

        Raises:
            KeyError: If agent not in pool
        """
        with self.lock:
            if agent_id not in self.agent_pool:
                raise KeyError(f"Agent {agent_id} not in pool")

            self.agent_pool[agent_id]["status"] = "blocked"
            self.agent_pool[agent_id]["blocked_by"] = blocked_by

            logger.debug(f"Agent {agent_id} marked blocked by tasks: {blocked_by}")

    def retire_agent(self, agent_id: str) -> None:
        """
        Retire agent and remove from pool.

        Args:
            agent_id: ID of agent to retire

        Raises:
            KeyError: If agent not in pool
        """
        with self.lock:
            if agent_id not in self.agent_pool:
                raise KeyError(f"Agent {agent_id} not in pool")

            agent_info = self.agent_pool.pop(agent_id)

            logger.info(
                f"Retired agent: {agent_id} " f"(completed {agent_info['tasks_completed']} tasks)"
            )

            # Broadcast agent retirement
            self._broadcast_async(
                self.project_id, agent_id, agent_info["agent_type"], event_type="agent_retired"
            )

    def get_agent_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all agents in pool.

        Returns:
            Dict mapping agent_id to agent status info
        """
        with self.lock:
            status = {}

            for agent_id, agent_info in self.agent_pool.items():
                status[agent_id] = {
                    "agent_type": agent_info["agent_type"],
                    "status": agent_info["status"],
                    "current_task": agent_info["current_task"],
                    "tasks_completed": agent_info["tasks_completed"],
                    "blocked_by": agent_info.get("blocked_by"),
                    "is_hybrid": agent_info.get("is_hybrid", False),
                    "session_id": agent_info.get("session_id"),
                }

            return status

    def get_agent_instance(self, agent_id: str):
        """
        Get agent instance for task execution.

        Args:
            agent_id: ID of agent to retrieve

        Returns:
            Agent instance

        Raises:
            KeyError: If agent not in pool
        """
        with self.lock:
            if agent_id not in self.agent_pool:
                raise KeyError(f"Agent {agent_id} not in pool")

            return self.agent_pool[agent_id]["instance"]

    def _broadcast_async(
        self, project_id: int, agent_id: str, agent_type: str, event_type: str
    ) -> None:
        """
        Helper to broadcast agent lifecycle events (handles async safely).

        Args:
            project_id: Project ID
            agent_id: Agent ID
            agent_type: Type of agent
            event_type: Type of event (agent_created, agent_retired)
        """
        if not self.ws_manager:
            return

        try:
            loop = asyncio.get_running_loop()

            if event_type == "agent_created":
                tasks_completed = self.agent_pool.get(agent_id, {}).get("tasks_completed", 0)
                loop.create_task(
                    broadcast_agent_created(
                        self.ws_manager, project_id, agent_id, agent_type, tasks_completed
                    )
                )
            elif event_type == "agent_retired":
                loop.create_task(broadcast_agent_retired(self.ws_manager, project_id, agent_id))

        except RuntimeError:
            # No event loop running (sync context, testing)
            logger.debug(f"Skipped broadcast: {event_type} for {agent_id} (no event loop)")

    def _create_hybrid_agent(self, agent_id: str, agent_type: str) -> HybridWorkerAgent:
        """
        Create a HybridWorkerAgent with SDK client for task execution.

        Args:
            agent_id: ID for the new agent
            agent_type: Type of agent (backend, frontend, test, review)

        Returns:
            HybridWorkerAgent instance configured for SDK execution
        """
        # Map agent types to system prompts
        system_prompts = {
            "backend": "You are a backend developer specializing in Python, FastAPI, and databases.",
            "frontend": "You are a frontend developer specializing in React, TypeScript, and Tailwind CSS.",
            "test": "You are a test engineer specializing in pytest, test automation, and quality assurance.",
            "review": "You are a code reviewer specializing in security, performance, and best practices.",
        }

        # Normalize agent type
        base_type = agent_type.split("-")[0]  # backend-worker -> backend
        system_prompt = system_prompts.get(base_type, f"You are a {base_type} specialist.")

        # Map to SDK tools
        tool_sets = {
            "backend": ["Read", "Write", "Bash", "Glob", "Grep"],
            "frontend": ["Read", "Write", "Bash", "Glob", "Grep"],
            "test": ["Read", "Write", "Bash", "Glob", "Grep"],
            "review": ["Read", "Glob", "Grep", "Bash"],
        }
        allowed_tools = tool_sets.get(base_type, ["Read", "Write", "Bash", "Glob", "Grep"])

        logger.debug(f"Creating SDK client for {agent_id} with tools: {allowed_tools}")

        # Create SDK client
        sdk_client = SDKClientWrapper(
            api_key=self.api_key,
            model=self.model,
            system_prompt=system_prompt,
            allowed_tools=allowed_tools,
            cwd=self.cwd,
        )

        # Create hybrid agent
        agent = HybridWorkerAgent(
            agent_id=agent_id,
            agent_type=base_type,
            db=self.db,
            sdk_client=sdk_client,
            provider="sdk",
            maturity=AgentMaturity.D2,  # Default to coaching level
            system_prompt=system_prompt,
        )

        logger.info(f"Created HybridWorkerAgent: {agent_id}")
        return agent

    def _create_traditional_agent(
        self, agent_id: str, agent_type: str
    ) -> Union[BackendWorkerAgent, FrontendWorkerAgent, TestWorkerAgent, ReviewWorkerAgent]:
        """
        Create a traditional WorkerAgent (non-SDK).

        Args:
            agent_id: ID for the new agent
            agent_type: Type of agent (backend, frontend, test, review)

        Returns:
            WorkerAgent instance (BackendWorkerAgent, FrontendWorkerAgent, etc.)

        Raises:
            ValueError: If unknown agent type
        """
        if agent_type == "backend" or agent_type == "backend-worker":
            return BackendWorkerAgent(
                db=self.db,
                codebase_index=self.codebase_index,
                provider="anthropic",
                api_key=self.api_key,
            )
        elif agent_type == "frontend" or agent_type == "frontend-specialist":
            return FrontendWorkerAgent(
                agent_id=agent_id,
                provider="anthropic",
                api_key=self.api_key,
                websocket_manager=self.ws_manager,
                db=self.db,
            )
        elif agent_type == "test" or agent_type == "test-engineer":
            return TestWorkerAgent(
                agent_id=agent_id,
                provider="anthropic",
                api_key=self.api_key,
                websocket_manager=self.ws_manager,
                db=self.db,
            )
        elif agent_type == "review" or agent_type == "review-worker":
            return ReviewWorkerAgent(
                agent_id=agent_id,
                db=self.db,
                provider="anthropic",
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

    def clear(self) -> None:
        """Clear all agents from pool (for testing/reset)."""
        with self.lock:
            self.agent_pool.clear()
            self.next_agent_number = 1
            logger.info("Agent pool cleared")
