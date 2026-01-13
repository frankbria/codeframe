"""Repository for Memory Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

from typing import List, Optional, Dict, Any
import logging


from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class MemoryRepository(BaseRepository):
    """Repository for memory repository operations."""


    def create_memory(
        self,
        project_id: int,
        category: str,
        key: str,
        value: str,
    ) -> int:
        """Create a memory entry.

        Args:
            project_id: Project ID
            category: Memory category (pattern, decision, gotcha, preference, conversation)
            key: Memory key (role for conversation: user_1, assistant_1, etc.)
            value: Memory value (content)

        Returns:
            Memory ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory (project_id, category, key, value)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, category, key, value),
        )
        self.conn.commit()
        return cursor.lastrowid

    def upsert_memory(
        self,
        project_id: int,
        category: str,
        key: str,
        value: str,
    ) -> int:
        """Create or update a memory entry.

        Uses INSERT OR REPLACE to handle UNIQUE constraint on (project_id, category, key).

        Args:
            project_id: Project ID
            category: Memory category
            key: Memory key
            value: Memory value (content)

        Returns:
            Memory ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO memory (project_id, category, key, value)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, category, key, value),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get memory entry by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM memory WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        return dict(row) if row else None



    def get_project_memories(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all memory entries for a project.

        Args:
            project_id: Project ID

        Returns:
            List of memory dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]



    def get_conversation(self, project_id: int) -> List[Dict[str, Any]]:
        """Get conversation history for a project.

        Conversation messages are stored in memory table with category='conversation'.

        Args:
            project_id: Project ID

        Returns:
            List of conversation message dictionaries ordered by insertion (id)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM memory
            WHERE project_id = ? AND category = 'conversation'
            ORDER BY id
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Additional Issue methods (cf-16.2)
