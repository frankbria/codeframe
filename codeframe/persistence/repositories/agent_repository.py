"""Repository for Agent Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

from typing import List, Optional, Dict, Any
import logging


from codeframe.core.models import (
    AgentMaturity,
)
from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AgentRepository(BaseRepository):
    """Repository for agent repository operations."""


    def create_agent(
        self,
        agent_id: str,
        agent_type: str,
        provider: str,
        maturity_level: AgentMaturity,
    ) -> str:
        """Create a new agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (lead, backend, frontend, test, review)
            provider: AI provider (claude, gpt4)
            maturity_level: Maturity level (D1-D4)

        Returns:
            Agent ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (id, type, provider, maturity_level, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, agent_type, provider, maturity_level.value, "idle"),
        )
        self.conn.commit()
        return agent_id



    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None



    # Whitelist of allowed agent fields for updates (prevents SQL injection)
    ALLOWED_AGENT_FIELDS = {
        "type",
        "project_id",
        "provider",
        "maturity_level",
        "status",
        "current_task_id",
        "last_heartbeat",
        "metrics",
    }

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> int:
        """Update agent fields.

        Args:
            agent_id: Agent ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected

        Raises:
            ValueError: If any update key is not in the allowed fields whitelist
        """
        if not updates:
            return 0

        # Validate all keys against whitelist to prevent SQL injection
        invalid_fields = set(updates.keys()) - self.ALLOWED_AGENT_FIELDS
        if invalid_fields:
            raise ValueError(
                f"Invalid agent fields: {invalid_fields}. "
                f"Allowed fields: {self.ALLOWED_AGENT_FIELDS}"
            )

        fields = []
        values = []
        for key, value in updates.items():
            # Safe to use key here since it's been validated against whitelist
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, AgentMaturity):
                values.append(value.value)
            else:
                values.append(value)

        values.append(agent_id)

        query = f"UPDATE agents SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount



    def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents.

        Returns:
            List of agent dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents ORDER BY id")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]



    def assign_agent_to_project(self, project_id: int, agent_id: str, role: str = "worker") -> int:
        """Assign an agent to a project.

        Args:
            project_id: Project ID
            agent_id: Agent ID
            role: Agent's role in this project

        Returns:
            Assignment ID

        Raises:
            sqlite3.IntegrityError: If agent already assigned to project (while active)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO project_agents (project_id, agent_id, role, is_active)
            VALUES (?, ?, ?, TRUE)
            """,
            (project_id, agent_id, role),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_agents_for_project(
        self, project_id: int, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all agents assigned to a project.

        Args:
            project_id: Project ID
            active_only: If True, only return currently assigned agents

        Returns:
            List of agent dictionaries with assignment metadata
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                a.id AS agent_id,
                a.type,
                a.provider,
                a.maturity_level,
                a.status,
                a.current_task_id,
                a.last_heartbeat,
                a.metrics,
                pa.id AS assignment_id,
                pa.role,
                pa.assigned_at,
                pa.unassigned_at,
                pa.is_active
            FROM agents a
            JOIN project_agents pa ON a.id = pa.agent_id
            WHERE pa.project_id = ?
        """

        if active_only:
            query += " AND pa.is_active = TRUE"

        query += " ORDER BY pa.assigned_at DESC"

        cursor.execute(query, (project_id,))
        return [dict(row) for row in cursor.fetchall()]



    def get_projects_for_agent(
        self, agent_id: str, active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all projects an agent is assigned to.

        Args:
            agent_id: Agent ID
            active_only: If True, only return active assignments

        Returns:
            List of project dictionaries with assignment metadata
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                p.id AS project_id,
                p.name,
                p.description,
                p.status,
                p.phase,
                pa.role,
                pa.assigned_at,
                pa.unassigned_at,
                pa.is_active
            FROM projects p
            JOIN project_agents pa ON p.id = pa.project_id
            WHERE pa.agent_id = ?
        """

        if active_only:
            query += " AND pa.is_active = TRUE"

        query += " ORDER BY pa.assigned_at DESC"

        cursor.execute(query, (agent_id,))
        return [dict(row) for row in cursor.fetchall()]



    def remove_agent_from_project(self, project_id: int, agent_id: str) -> int:
        """Remove an agent from a project (soft delete).

        Args:
            project_id: Project ID
            agent_id: Agent ID

        Returns:
            Number of rows affected (0 if not assigned, 1 if unassigned)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE project_agents
            SET is_active = FALSE,
                unassigned_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
              AND agent_id = ?
              AND is_active = TRUE
            """,
            (project_id, agent_id),
        )
        self.conn.commit()
        return cursor.rowcount



    def reassign_agent_role(self, project_id: int, agent_id: str, new_role: str) -> int:
        """Update an agent's role on a project.

        Args:
            project_id: Project ID
            agent_id: Agent ID
            new_role: New role for the agent

        Returns:
            Number of rows affected
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE project_agents
            SET role = ?
            WHERE project_id = ?
              AND agent_id = ?
              AND is_active = TRUE
            """,
            (new_role, project_id, agent_id),
        )
        self.conn.commit()
        return cursor.rowcount



    def get_agent_assignment(self, project_id: int, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get assignment details for a specific agent-project pair.

        Args:
            project_id: Project ID
            agent_id: Agent ID

        Returns:
            Assignment dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT
                id,
                project_id,
                agent_id,
                role,
                assigned_at,
                unassigned_at,
                is_active
            FROM project_agents
            WHERE project_id = ? AND agent_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (project_id, agent_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None



    def get_available_agents(
        self, agent_type: Optional[str] = None, exclude_project_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get agents available for assignment (not at capacity).

        Args:
            agent_type: Filter by agent type (optional)
            exclude_project_id: Exclude agents already on this project

        Returns:
            List of available agent dictionaries
        """
        cursor = self.conn.cursor()

        query = """
            SELECT
                a.*,
                COUNT(pa.id) AS active_assignments
            FROM agents a
            LEFT JOIN project_agents pa ON a.id = pa.agent_id
                AND pa.is_active = TRUE
        """

        params = []
        conditions = []

        if exclude_project_id:
            conditions.append("(pa.project_id IS NULL OR pa.project_id != ?)")
            params.append(exclude_project_id)

        if agent_type:
            conditions.append("a.type = ?")
            params.append(agent_type)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            GROUP BY a.id
            HAVING active_assignments < 3
            ORDER BY active_assignments ASC, a.last_heartbeat DESC
        """

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

