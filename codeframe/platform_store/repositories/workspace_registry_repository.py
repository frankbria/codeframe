"""Repository for the workspace registry (issue #601).

The registry lives in the global control-plane DB and stores only project
metadata + a pointer (``repo_path``) to each per-workspace
``.codeframe/state.db``. It enables server-side listing of "your projects" so
the web UI switcher can be backed by the server (with a localStorage fallback)
instead of living purely in the browser.

It is intentionally NOT a revival of the v1 global ``projects`` table — no
domain data is stored here, only pointers and metadata.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from codeframe.platform_store.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WorkspaceRegistryRepository(BaseRepository):
    """Repository for workspace registry operations."""

    def upsert(
        self,
        repo_path: str,
        name: Optional[str] = None,
        tech_stack: Optional[str] = None,
        owner_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Register (or refresh) a workspace by its repo path.

        Idempotent on ``repo_path``: a second call for the same path updates the
        existing row (name/tech_stack/owner + ``last_opened_at``) instead of
        creating a duplicate, preserving the original ``id`` and ``created_at``.

        Args:
            repo_path: Absolute path to the repository (unique key).
            name: Human-readable display name (defaults to last path segment).
            tech_stack: Natural-language tech stack description.
            owner_user_id: Owning user id (nullable until auth is enforced).

        Returns:
            The registry entry as a dict.
        """
        now = datetime.now(timezone.utc).isoformat()
        new_id = str(uuid.uuid4())

        # INSERT ... ON CONFLICT(repo_path) DO UPDATE keeps the original id and
        # created_at while refreshing the mutable metadata and recency stamp.
        self._execute(
            """
            INSERT INTO workspaces_registry (
                id, repo_path, name, owner_user_id, tech_stack,
                created_at, last_opened_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repo_path) DO UPDATE SET
                -- COALESCE so a refresh that omits name/tech_stack (None) keeps the
                -- previously-stored value instead of nulling it.
                name = COALESCE(excluded.name, workspaces_registry.name),
                -- COALESCE so a refresh that omits the owner (None) keeps the
                -- recorded owner instead of nulling it (#720).
                owner_user_id = COALESCE(excluded.owner_user_id, workspaces_registry.owner_user_id),
                tech_stack = COALESCE(excluded.tech_stack, workspaces_registry.tech_stack),
                last_opened_at = excluded.last_opened_at
            """,
            (new_id, repo_path, name, owner_user_id, tech_stack, now, now),
        )
        self._commit()

        # Re-read so callers always get the canonical row (stable id on conflict).
        entry = self.get_by_path(repo_path)
        if entry is None:
            # Should be unreachable right after a successful upsert. Raise a real
            # error (not assert, which `python -O` strips) so the dict-return
            # contract holds in every execution mode.
            raise RuntimeError(
                f"workspaces_registry upsert succeeded but row not found: {repo_path}"
            )
        return entry

    def list_all(self, owner_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List all registered workspaces, optionally filtered by owner.

        Args:
            owner_user_id: When provided, only entries owned by this user are
                returned. When ``None``, all entries are returned (the current
                behaviour until auth is enforced on v2 routers).

        Returns:
            List of registry entries ordered by ``last_opened_at`` descending.
        """
        if owner_user_id is not None:
            rows = self._fetchall(
                """
                SELECT id, repo_path, name, owner_user_id, tech_stack,
                       created_at, last_opened_at
                FROM workspaces_registry
                WHERE owner_user_id = ?
                ORDER BY last_opened_at DESC
                """,
                (owner_user_id,),
            )
        else:
            rows = self._fetchall(
                """
                SELECT id, repo_path, name, owner_user_id, tech_stack,
                       created_at, last_opened_at
                FROM workspaces_registry
                ORDER BY last_opened_at DESC
                """
            )

        return [self._row_to_workspace_registry(row) for row in rows]

    def get_by_id(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get a registry entry by its id, or None if not found."""
        row = self._fetchone(
            """
            SELECT id, repo_path, name, owner_user_id, tech_stack,
                   created_at, last_opened_at
            FROM workspaces_registry
            WHERE id = ?
            """,
            (workspace_id,),
        )
        return self._row_to_workspace_registry(row) if row is not None else None

    def get_by_path(self, repo_path: str) -> Optional[Dict[str, Any]]:
        """Get a registry entry by its repo path, or None if not found."""
        row = self._fetchone(
            """
            SELECT id, repo_path, name, owner_user_id, tech_stack,
                   created_at, last_opened_at
            FROM workspaces_registry
            WHERE repo_path = ?
            """,
            (repo_path,),
        )
        return self._row_to_workspace_registry(row) if row is not None else None

    def update_last_opened(self, workspace_id: str) -> None:
        """Bump ``last_opened_at`` for a registry entry to maintain recency."""
        now = datetime.now(timezone.utc).isoformat()
        self._execute(
            "UPDATE workspaces_registry SET last_opened_at = ? WHERE id = ?",
            (now, workspace_id),
        )
        self._commit()

    def delete(self, workspace_id: str, owner_user_id: Optional[int] = None) -> bool:
        """Deregister a workspace (registry-only — never touches disk files).

        Args:
            workspace_id: Registry entry id to remove.
            owner_user_id: When provided (auth enabled), only an entry owned by
                this user is removed — a tenant cannot delete another's entry
                (#720). When ``None`` (auth disabled/local), no owner filter is
                applied and behavior is unchanged.

        Returns:
            True if a row was removed, False if the id was not found (or not
            owned by ``owner_user_id`` when supplied).
        """
        if owner_user_id is not None:
            cursor = self._execute(
                "DELETE FROM workspaces_registry WHERE id = ? AND owner_user_id = ?",
                (workspace_id, owner_user_id),
            )
        else:
            cursor = self._execute(
                "DELETE FROM workspaces_registry WHERE id = ?",
                (workspace_id,),
            )
        self._commit()
        return cursor.rowcount > 0

    def _row_to_workspace_registry(self, row) -> Dict[str, Any]:
        """Convert a database row to a registry dict."""
        return {
            "id": row["id"],
            "repo_path": row["repo_path"],
            "name": row["name"],
            "owner_user_id": row["owner_user_id"],
            "tech_stack": row["tech_stack"],
            "created_at": self._ensure_rfc3339(row["created_at"]),
            "last_opened_at": self._ensure_rfc3339(row["last_opened_at"]),
        }
