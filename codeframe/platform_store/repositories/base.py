"""Base repository class for database operations."""

import contextlib
import sqlite3
import threading
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
    Thread-safe synchronous operations are provided via a shared lock.
    """

    def __init__(
        self,
        sync_conn: Optional[sqlite3.Connection] = None,
        async_conn: Optional[aiosqlite.Connection] = None,
        database: Optional[Any] = None,
        sync_lock: Optional[threading.Lock] = None
    ):
        """Initialize repository with database connections.

        Args:
            sync_conn: Synchronous sqlite3.Connection
            async_conn: Asynchronous aiosqlite.Connection
            database: Reference to parent Database instance (for cross-repository operations)
            sync_lock: Threading lock for thread-safe synchronous operations

        Note:
            At least one connection must be provided. Both can be provided
            to support repositories with both sync and async methods.
            If sync_conn is provided without sync_lock, operations will not be thread-safe.
        """
        if sync_conn is None and async_conn is None:
            raise ValueError("At least one connection (sync or async) must be provided")

        if sync_conn is not None:
            # Repository methods read columns by name (row["total_tokens"]), so
            # they need a Row factory. `Database` sets this on its own
            # connection, which is why they work when reached that way — a
            # caller passing a bare `sqlite3.connect()` got tuples and a
            # `TypeError: tuple indices must be integers` from the first named
            # access (#911 review). Set it here so every caller is correct by
            # construction. sqlite3.Row still supports integer indexing and
            # iteration, so tuple-style access keeps working.
            sync_conn.row_factory = sqlite3.Row

        self.conn = sync_conn  # For backward compatibility
        self._async_conn = async_conn
        self._database = database  # Reference to parent Database instance
        self._sync_lock = sync_lock  # Threading lock for thread-safe sync operations

    def _execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query synchronously with thread-safe locking.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Cursor with query results

        Raises:
            RuntimeError: If sync connection is not available

        Note:
            Uses threading lock if available to ensure thread-safe access
            to the shared connection object.
        """
        if self.conn is None:
            raise RuntimeError("Sync connection not available, use async methods")

        if self._sync_lock is not None:
            with self._sync_lock:
                return self.conn.execute(query, params)
        else:
            return self.conn.execute(query, params)

    def _execute_write(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a statement and commit it as ONE locked critical section.

        ``_execute(...)`` followed by ``_commit()`` takes the lock twice, which
        is not the same thing: sqlite3 opens an implicit transaction on the
        shared connection, so between the two acquisitions another thread can
        slip a write in — and whichever commit lands first flushes the other
        thread's half-written transaction. That is exactly the interleaving
        #953 is about, and holding the lock across both closes it.

        Every single-statement write in this package goes through here. A write
        that needs several statements to land together needs a real transaction
        (``Database.transaction()``), not this helper.

        Args:
            query: SQL statement
            params: Statement parameters

        Returns:
            Cursor for the executed statement (``lastrowid`` / ``rowcount``).

        Raises:
            RuntimeError: If sync connection is not available
        """
        if self.conn is None:
            raise RuntimeError("Sync connection not available, use async methods")

        lock = self._sync_lock if self._sync_lock is not None else contextlib.nullcontext()
        with lock:
            cursor = self.conn.execute(query, params)
            self.conn.commit()
            return cursor

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
        """Commit the current transaction synchronously with thread-safe locking.

        Raises:
            RuntimeError: If sync connection is not available

        Note:
            Uses threading lock if available to ensure thread-safe access
            to the shared connection object.
        """
        if self.conn is None:
            raise RuntimeError("Sync connection not available, use async methods")

        if self._sync_lock is not None:
            with self._sync_lock:
                self.conn.commit()
        else:
            self.conn.commit()

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

    def _ensure_rfc3339(self, timestamp_str: Optional[str]) -> Optional[str]:
        """Ensure timestamp is in RFC 3339 format with timezone.

        Args:
            timestamp_str: Timestamp string (may be SQLite format or RFC 3339)

        Returns:
            RFC 3339 formatted timestamp (with 'Z' suffix for UTC) or None

        Note:
            Converts SQLite timestamps like "2025-10-17 22:01:56" to "2025-10-17T22:01:56Z".
            Timestamps already in RFC 3339 format are returned as-is.
        """
        if not timestamp_str:
            return timestamp_str
        # If already has 'Z' or timezone, return as-is
        if "Z" in timestamp_str or "+" in timestamp_str:
            return timestamp_str
        # Parse and add Z suffix for UTC
        try:
            # SQLite format: "2025-10-17 22:01:56"
            dt = datetime.fromisoformat(timestamp_str)
            return dt.isoformat() + "Z"
        except ValueError:
            return timestamp_str
