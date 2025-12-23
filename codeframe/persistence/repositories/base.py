"""Base repository class for database operations."""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import logging

import aiosqlite

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base class for all repositories.

    Provides common database utilities and connection management.
    Each repository handles a specific domain (projects, issues, tasks, etc.).

    Supports both synchronous (sqlite3) and asynchronous (aiosqlite) operations.
    """

    def __init__(
        self,
        sync_conn: Optional[sqlite3.Connection] = None,
        async_conn: Optional[aiosqlite.Connection] = None,
        database: Optional[Any] = None
    ):
        """Initialize repository with database connections.

        Args:
            sync_conn: Synchronous sqlite3.Connection
            async_conn: Asynchronous aiosqlite.Connection
            database: Reference to parent Database instance (for cross-repository operations)

        Note:
            At least one connection must be provided. Both can be provided
            to support repositories with both sync and async methods.
        """
        if sync_conn is None and async_conn is None:
            raise ValueError("At least one connection (sync or async) must be provided")

        self.conn = sync_conn  # For backward compatibility
        self._async_conn = async_conn
        self._database = database  # Reference to parent Database instance

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query synchronously.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor with query results

        Raises:
            RuntimeError: If sync connection is not available
        """
        if self.conn is None:
            raise RuntimeError("Sync connection not available, use async methods")
        return self.conn.execute(query, params)

    def _fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row synchronously.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Row or None if no results
        """
        cursor = self._execute(query, params)
        return cursor.fetchone()

    def _fetchall(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Fetch all rows synchronously.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows
        """
        cursor = self._execute(query, params)
        return cursor.fetchall()

    def _commit(self) -> None:
        """Commit the current transaction synchronously.

        Raises:
            RuntimeError: If sync connection is not available
        """
        if self.conn is None:
            raise RuntimeError("Sync connection not available, use async methods")
        self.conn.commit()

    async def _execute_async(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a query asynchronously.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor with query results

        Raises:
            RuntimeError: If async connection is not available
        """
        if self._async_conn is None:
            raise RuntimeError("Async connection not available, use sync methods")
        return await self._async_conn.execute(query, params)

    async def _fetchone_async(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        """Fetch a single row asynchronously.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Row or None if no results
        """
        cursor = await self._execute_async(query, params)
        return await cursor.fetchone()

    async def _fetchall_async(self, query: str, params: tuple = ()) -> List[aiosqlite.Row]:
        """Fetch all rows asynchronously.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            List of rows
        """
        cursor = await self._execute_async(query, params)
        return await cursor.fetchall()

    async def _commit_async(self) -> None:
        """Commit the current transaction asynchronously.

        Raises:
            RuntimeError: If async connection is not available
        """
        if self._async_conn is None:
            raise RuntimeError("Async connection not available, use sync methods")
        await self._async_conn.commit()

    def _row_to_dict(self, row: Union[sqlite3.Row, aiosqlite.Row]) -> Dict[str, Any]:
        """Convert a database row to a dictionary.

        Args:
            row: SQLite Row object (sync or async)

        Returns:
            Dictionary with column names as keys

        Note:
            Both sqlite3.Row and aiosqlite.Row support dictionary-style access
            and keys() method for column names.
        """
        if row is None:
            return {}
        return {key: row[key] for key in row.keys()}

    def _parse_datetime(
        self,
        dt_str: Optional[str],
        field_name: str = "",
        row_id: Optional[int] = None
    ) -> Optional[datetime]:
        """Parse datetime string to datetime object.

        Args:
            dt_str: ISO format datetime string or None
            field_name: Field name for logging (optional)
            row_id: Row ID for logging (optional)

        Returns:
            datetime object or None if input is None

        Raises:
            ValueError: If datetime string is malformed
        """
        if dt_str is None:
            return None

        try:
            # Parse ISO format: "2024-11-23T10:30:00" or "2024-11-23 10:30:00"
            # Handle both 'T' and space separators
            dt_str_normalized = dt_str.replace("T", " ")

            # Try with microseconds first
            try:
                return datetime.fromisoformat(dt_str_normalized)
            except ValueError:
                # Try without microseconds
                return datetime.strptime(dt_str_normalized, "%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError) as e:
            context = f" for {field_name}" if field_name else ""
            row_context = f" (row {row_id})" if row_id else ""
            logger.warning(
                f"Failed to parse datetime '{dt_str}'{context}{row_context}: {e}"
            )
            raise ValueError(f"Invalid datetime format: {dt_str}") from e

    def _format_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Format datetime object to ISO string for database storage.

        Args:
            dt: datetime object or None

        Returns:
            ISO format datetime string or None
        """
        if dt is None:
            return None
        return dt.isoformat()

    def _get_last_insert_id(self) -> int:
        """Get the last inserted row ID.

        Returns:
            Last row ID

        Raises:
            RuntimeError: If sync connection is not available
        """
        if self.conn is None:
            raise RuntimeError("Sync connection not available, use async methods")
        cursor = self.conn.cursor()
        return cursor.lastrowid

    async def _get_last_insert_id_async(self) -> int:
        """Get the last inserted row ID asynchronously.

        Returns:
            Last row ID

        Raises:
            RuntimeError: If async connection is not available
        """
        if self._async_conn is None:
            raise RuntimeError("Async connection not available, use sync methods")
        cursor = await self._async_conn.cursor()
        return cursor.lastrowid
