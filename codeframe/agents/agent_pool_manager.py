"""
Agent Pool Manager for parallel task execution (Sprint 4: cf-24).

This module manages a pool of worker agents, enabling reuse and parallel execution.
"""

import logging
import asyncio
from typing import Dict, Optional, Any
from threading import RLock

from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.agents.frontend_worker_agent import FrontendWorkerAgent
from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.ui.websocket_broadcasts import broadcast_agent_created, broadcast_agent_retired

logger = logging.getLogger(__name__)


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
        api_key: Optional[str] = None
    ):
        """
        Initialize Agent Pool Manager.

        Args:
            project_id: Project ID for this pool
            db: Database instance
            ws_manager: WebSocket manager for broadcasts (optional)
            max_agents: Maximum number of concurrent agents (default: 10)
            api_key: Anthropic API key (optional, will use env var if not provided)
        """
        self.project_id = project_id
        self.db = db
        self.ws_manager = ws_manager
        self.max_agents = max_agents
        self.api_key = api_key

        # Agent pool: {agent_id: agent_info}
        self.agent_pool: Dict[str, Dict[str, Any]] = {}

        # Agent ID counter
        self.next_agent_number = 1

        # Thread lock for pool operations (using RLock for reentrancy)
        self.lock = RLock()

        logger.info(f"Agent Pool Manager initialized: project_id={project_id}, max_agents={max_agents}")

    def create_agent(self, agent_type: str) -> str:
        """
        Create new worker agent of specified type.

        Args:
            agent_type: Type of agent to create (backend, frontend, test)

        Returns:
            agent_id: ID of created agent

        Raises:
            ValueError: If unknown agent type
            RuntimeError: If agent pool at maximum capacity
        """
        print(f"\n🏭 DEBUG: create_agent called with agent_type={agent_type}")
        with self.lock:
            print(f"🏭 DEBUG: Acquired lock")
            # Check pool capacity
            if len(self.agent_pool) >= self.max_agents:
                raise RuntimeError(
                    f"Agent pool at maximum capacity ({self.max_agents} agents). "
                    "Retire an agent before creating a new one."
                )

            # Generate agent ID
            print(f"🏭 DEBUG: Generating agent ID...")
            agent_id = f"{agent_type}-worker-{self.next_agent_number:03d}"
            self.next_agent_number += 1
            print(f"🏭 DEBUG: Generated agent_id={agent_id}")

            # Create agent instance based on type with correct constructor arguments
            print(f"🏭 DEBUG: About to create {agent_type} agent instance...")
            if agent_type == "backend" or agent_type == "backend-worker":
                print(f"🏭 DEBUG: Calling BackendWorkerAgent constructor...")
                agent_instance = BackendWorkerAgent(
                    project_id=self.project_id,
                    db=self.db,
                    codebase_index=None,  # Optional for workers
                    provider="anthropic",
                    api_key=self.api_key
                )
            elif agent_type == "frontend" or agent_type == "frontend-specialist":
                agent_instance = FrontendWorkerAgent(
                    agent_id=agent_id,
                    provider="anthropic",
                    api_key=self.api_key,
                    websocket_manager=self.ws_manager
                )
            elif agent_type == "test" or agent_type == "test-engineer":
                print(f"🏭 DEBUG: Calling TestWorkerAgent constructor...")
                agent_instance = TestWorkerAgent(
                    agent_id=agent_id,
                    provider="anthropic",
                    api_key=self.api_key,
                    websocket_manager=self.ws_manager
                )
                print(f"🏭 DEBUG: TestWorkerAgent created successfully")
            else:
                print(f"🏭 DEBUG: Unknown agent type: {agent_type}")
                raise ValueError(f"Unknown agent type: {agent_type}")

            print(f"🏭 DEBUG: Agent instance created: {type(agent_instance)}")

            # Add to pool
            self.agent_pool[agent_id] = {
                "instance": agent_instance,
                "status": "idle",  # idle | busy | blocked
                "current_task": None,
                "agent_type": agent_type,
                "tasks_completed": 0,
                "blocked_by": None
            }

            logger.info(f"Created agent: {agent_id} (type: {agent_type})")

            # Broadcast agent creation
            self._broadcast_async(
                self.project_id,
                agent_id,
                agent_type,
                event_type="agent_created"
            )

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
        print(f"\n🔧 DEBUG: get_or_create_agent called with agent_type={agent_type}")
        with self.lock:
            print(f"🔧 DEBUG: Acquired lock in get_or_create_agent")
            # Look for idle agent of this type
            print(f"🔧 DEBUG: Looking for idle {agent_type} agents in pool (pool size: {len(self.agent_pool)})")
            for agent_id, agent_info in self.agent_pool.items():
                if (agent_info["agent_type"] == agent_type and
                    agent_info["status"] == "idle"):
                    logger.debug(f"Reusing idle agent: {agent_id}")
                    print(f"🔧 DEBUG: Found idle agent: {agent_id}")
                    return agent_id

            # No idle agent found - create new one
            print(f"🔧 DEBUG: No idle agent found, calling create_agent({agent_type})")
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
                f"Retired agent: {agent_id} "
                f"(completed {agent_info['tasks_completed']} tasks)"
            )

            # Broadcast agent retirement
            self._broadcast_async(
                self.project_id,
                agent_id,
                agent_info["agent_type"],
                event_type="agent_retired"
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
                    "blocked_by": agent_info.get("blocked_by")
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
        self,
        project_id: int,
        agent_id: str,
        agent_type: str,
        event_type: str
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
                        self.ws_manager,
                        project_id,
                        agent_id,
                        agent_type,
                        tasks_completed
                    )
                )
            elif event_type == "agent_retired":
                loop.create_task(
                    broadcast_agent_retired(
                        self.ws_manager,
                        project_id,
                        agent_id
                    )
                )

        except RuntimeError:
            # No event loop running (sync context, testing)
            logger.debug(f"Skipped broadcast: {event_type} for {agent_id} (no event loop)")

    def clear(self) -> None:
        """Clear all agents from pool (for testing/reset)."""
        with self.lock:
            self.agent_pool.clear()
            self.next_agent_number = 1
            logger.info("Agent pool cleared")