"""Repository for interactive agent session operations."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, UTC
from typing import Optional

from codeframe.persistence.repositories.base import BaseRepository


class InteractiveSessionRepository(BaseRepository):
    """Repository for interactive_sessions and session_messages tables."""

    # -------------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------------

    def create(
        self,
        workspace_path: str,
        task_id: Optional[str] = None,
        agent_type: str = "claude",
        model: Optional[str] = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        session_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO interactive_sessions
                (id, workspace_path, task_id, state, agent_type, model,
                 cost_usd, input_tokens, output_tokens, created_at, updated_at, ended_at)
            VALUES (?, ?, ?, 'active', ?, ?, 0.0, 0, 0, ?, ?, NULL)
            """,
            (session_id, workspace_path, task_id, agent_type, model, now, now),
        )
        self._commit()
        return self.get(session_id)

    def get(self, session_id: str) -> Optional[dict]:
        row = self._fetchone(
            "SELECT * FROM interactive_sessions WHERE id = ?", (session_id,)
        )
        return self._row_to_dict(row) if row else None

    def list(
        self,
        workspace_path: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        query = "SELECT * FROM interactive_sessions WHERE 1=1"
        params: list = []
        if workspace_path is not None:
            query += " AND workspace_path = ?"
            params.append(workspace_path)
        if state is not None:
            query += " AND state = ?"
            params.append(state)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._fetchall(query, tuple(params))
        return [self._row_to_dict(r) for r in rows]

    def update_state(self, session_id: str, state: str) -> None:
        """Update session state. Called internally by the agent runtime, not via REST API.

        Callers are responsible for validating state against VALID_STATES before calling.
        """
        now = datetime.now(UTC).isoformat()
        self._execute(
            "UPDATE interactive_sessions SET state = ?, updated_at = ? WHERE id = ?",
            (state, now, session_id),
        )
        self._commit()

    def update_cost(
        self, session_id: str, cost_usd: float, input_tokens: int, output_tokens: int
    ) -> None:
        """Accumulate cost and token counts. Called internally by the agent runtime, not via REST API.

        The increment is applied atomically at the DB level to prevent lost-update races.
        """
        now = datetime.now(UTC).isoformat()
        self._execute(
            """
            UPDATE interactive_sessions
            SET cost_usd = cost_usd + ?, input_tokens = input_tokens + ?,
                output_tokens = output_tokens + ?, updated_at = ?
            WHERE id = ?
            """,
            (cost_usd, input_tokens, output_tokens, now, session_id),
        )
        self._commit()

    def end(self, session_id: str) -> Optional[dict]:
        """End a session. Returns the updated row, or None if session_id not found."""
        now = datetime.now(UTC).isoformat()
        cursor = self._execute(
            """
            UPDATE interactive_sessions
            SET state = 'ended', ended_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, session_id),
        )
        self._commit()
        if cursor.rowcount == 0:
            return None
        return self.get(session_id)

    # -------------------------------------------------------------------------
    # Messages
    # -------------------------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        message_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata) if metadata is not None else None
        self._execute(
            """
            INSERT INTO session_messages (id, session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, metadata_json, now),
        )
        self._commit()
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata,
            "created_at": now,
        }

    def get_messages(
        self, session_id: str, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        rows = self._fetchall(
            """
            SELECT * FROM session_messages
            WHERE session_id = ?
            ORDER BY created_at
            LIMIT ? OFFSET ?
            """,
            (session_id, limit, offset),
        )
        result = []
        for row in rows:
            d = self._row_to_dict(row)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (json.JSONDecodeError, TypeError):
                    d["metadata"] = None
            result.append(d)
        return result
