"""Agent lifecycle management service.

This module provides business logic for managing agent lifecycle operations
such as starting, stopping, pausing, and resuming agents.
"""

from typing import Dict, Optional
import asyncio
import logging

from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent lifecycle operations."""

    def __init__(self, db: Database, running_agents: Dict[int, LeadAgent]):
        """Initialize agent service.

        Args:
            db: Database connection
            running_agents: Dictionary mapping project_id to LeadAgent instances
        """
        self.db = db
        self.running_agents = running_agents

    async def stop_agent(self, project_id: int) -> bool:
        """Stop a running agent for a project.

        Args:
            project_id: Project ID

        Returns:
            True if agent was stopped, False if no agent was running
        """
        if project_id not in self.running_agents:
            logger.warning(f"No running agent found for project {project_id}")
            return False

        try:
            # Update project status first (atomic persistence)
            await asyncio.to_thread(
                self.db.update_project,
                project_id,
                {"status": ProjectStatus.STOPPED.value}
            )

            # Remove agent from tracking after status is persisted
            self.running_agents.pop(project_id, None)

            logger.info(f"Stopped agent for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop agent for project {project_id}: {e}", exc_info=True)
            return False

    async def pause_agent(self, project_id: int) -> bool:
        """Pause a running agent without stopping it.

        Args:
            project_id: Project ID

        Returns:
            True if agent was paused, False if no agent was running
        """
        if project_id not in self.running_agents:
            logger.warning(f"No running agent found for project {project_id}")
            return False

        try:
            # Update project status to PAUSED
            await asyncio.to_thread(
                self.db.update_project,
                project_id,
                {"status": ProjectStatus.PAUSED.value}
            )

            logger.info(f"Paused agent for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to pause agent for project {project_id}: {e}", exc_info=True)
            return False

    async def resume_agent(self, project_id: int) -> bool:
        """Resume a paused agent.

        Args:
            project_id: Project ID

        Returns:
            True if agent was resumed, False if no agent was found
        """
        if project_id not in self.running_agents:
            logger.warning(f"No running agent found for project {project_id}")
            return False

        try:
            # Update project status back to RUNNING
            await asyncio.to_thread(
                self.db.update_project,
                project_id,
                {"status": ProjectStatus.RUNNING.value}
            )

            logger.info(f"Resumed agent for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to resume agent for project {project_id}: {e}", exc_info=True)
            return False

    def get_running_agent(self, project_id: int) -> Optional[LeadAgent]:
        """Get the running agent for a project.

        Args:
            project_id: Project ID

        Returns:
            LeadAgent instance if running, None otherwise
        """
        return self.running_agents.get(project_id)

    def is_agent_running(self, project_id: int) -> bool:
        """Check if an agent is running for a project.

        Args:
            project_id: Project ID

        Returns:
            True if agent is running, False otherwise
        """
        return project_id in self.running_agents
