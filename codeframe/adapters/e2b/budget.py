"""Cloud run metadata persistence for E2B budget tracking.

Records sandbox execution metrics (minutes, cost, file counts) in the
cloud_run_metadata SQLite table and provides lookup for the work show command.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def record_cloud_run(
    workspace: Any,
    run_id: str,
    sandbox_minutes: float,
    cost_usd: float,
    files_uploaded: int,
    files_downloaded: int,
    scan_blocked: int,
) -> None:
    """Insert a cloud run record into cloud_run_metadata.

    Args:
        workspace: Workspace instance with db_path attribute.
        run_id: CodeFrame run identifier.
        sandbox_minutes: Wall-clock minutes the sandbox was alive.
        cost_usd: Estimated cost in USD.
        files_uploaded: Number of files uploaded to the sandbox.
        files_downloaded: Number of changed files downloaded from sandbox.
        scan_blocked: Number of files blocked by credential scanner.
    """
    created_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(workspace.db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO cloud_run_metadata
                (run_id, sandbox_minutes, cost_usd_estimate,
                 files_uploaded, files_downloaded,
                 credential_scan_blocked, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, sandbox_minutes, cost_usd,
             files_uploaded, files_downloaded, scan_blocked, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_cloud_run(workspace: Any, run_id: str) -> dict | None:
    """Retrieve a cloud run record by run_id.

    Args:
        workspace: Workspace instance with db_path attribute.
        run_id: CodeFrame run identifier.

    Returns:
        Dict with cloud run fields, or None if not found.
    """
    conn = sqlite3.connect(workspace.db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM cloud_run_metadata WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
