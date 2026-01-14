"""PRD (Product Requirements Document) management for CodeFRAME v2.

Handles storage and retrieval of PRD documents. A workspace can have
multiple PRDs, but typically works with the "latest" one.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codeframe.core.workspace import Workspace, get_db_connection


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass
class PrdRecord:
    """Represents a stored PRD.

    Attributes:
        id: Unique PRD identifier (UUID)
        workspace_id: Workspace this PRD belongs to
        title: Extracted or provided title
        content: Full PRD text content
        metadata: Optional JSON metadata
        created_at: When the PRD was stored
    """

    id: str
    workspace_id: str
    title: str
    content: str
    metadata: dict
    created_at: datetime


def load_file(file_path: Path) -> str:
    """Load PRD content from a file.

    Args:
        file_path: Path to the PRD file (typically markdown)

    Returns:
        File contents as string

    Raises:
        FileNotFoundError: If file doesn't exist
        IOError: If file can't be read
    """
    file_path = Path(file_path).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"PRD file not found: {file_path}")

    if not file_path.is_file():
        raise IOError(f"Path is not a file: {file_path}")

    return file_path.read_text(encoding="utf-8")


def extract_title(content: str, file_path: Optional[Path] = None) -> str:
    """Extract a title from PRD content.

    Tries to find a markdown H1 heading, falls back to filename.

    Args:
        content: PRD text content
        file_path: Optional source file path for fallback

    Returns:
        Extracted or generated title
    """
    # Try to find first H1 heading (# Title)
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    # Try to find title in YAML frontmatter
    frontmatter_match = re.search(r"^---\s*\n.*?title:\s*(.+?)\n.*?---", content, re.DOTALL)
    if frontmatter_match:
        return frontmatter_match.group(1).strip().strip('"').strip("'")

    # Fall back to filename
    if file_path:
        return file_path.stem.replace("_", " ").replace("-", " ").title()

    return "Untitled PRD"


def store(
    workspace: Workspace,
    content: str,
    title: Optional[str] = None,
    metadata: Optional[dict] = None,
    source_path: Optional[Path] = None,
) -> PrdRecord:
    """Store a PRD in the workspace.

    Args:
        workspace: Target workspace
        content: PRD text content
        title: Optional title (extracted from content if not provided)
        metadata: Optional additional metadata
        source_path: Optional source file path (used for title extraction)

    Returns:
        Created PrdRecord
    """
    prd_id = str(uuid.uuid4())
    now = _utc_now().isoformat()

    # Extract title if not provided
    if not title:
        title = extract_title(content, source_path)

    # Build metadata
    meta = metadata or {}
    if source_path:
        meta["source_file"] = str(source_path)
    meta_json = json.dumps(meta)

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO prds (id, workspace_id, title, content, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (prd_id, workspace.id, title, content, meta_json, now),
    )
    conn.commit()
    conn.close()

    return PrdRecord(
        id=prd_id,
        workspace_id=workspace.id,
        title=title,
        content=content,
        metadata=meta,
        created_at=datetime.fromisoformat(now),
    )


def get_latest(workspace: Workspace) -> Optional[PrdRecord]:
    """Get the most recently added PRD for a workspace.

    Args:
        workspace: Workspace to query

    Returns:
        PrdRecord if one exists, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, title, content, metadata, created_at
        FROM prds
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (workspace.id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return PrdRecord(
        id=row[0],
        workspace_id=row[1],
        title=row[2],
        content=row[3],
        metadata=json.loads(row[4]) if row[4] else {},
        created_at=datetime.fromisoformat(row[5]),
    )


def get_by_id(workspace: Workspace, prd_id: str) -> Optional[PrdRecord]:
    """Get a specific PRD by ID.

    Args:
        workspace: Workspace to query
        prd_id: PRD identifier

    Returns:
        PrdRecord if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, title, content, metadata, created_at
        FROM prds
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, prd_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return PrdRecord(
        id=row[0],
        workspace_id=row[1],
        title=row[2],
        content=row[3],
        metadata=json.loads(row[4]) if row[4] else {},
        created_at=datetime.fromisoformat(row[5]),
    )


def list_all(workspace: Workspace) -> list[PrdRecord]:
    """List all PRDs in a workspace.

    Args:
        workspace: Workspace to query

    Returns:
        List of PrdRecords, newest first
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, title, content, metadata, created_at
        FROM prds
        WHERE workspace_id = ?
        ORDER BY created_at DESC
        """,
        (workspace.id,),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        PrdRecord(
            id=row[0],
            workspace_id=row[1],
            title=row[2],
            content=row[3],
            metadata=json.loads(row[4]) if row[4] else {},
            created_at=datetime.fromisoformat(row[5]),
        )
        for row in rows
    ]
