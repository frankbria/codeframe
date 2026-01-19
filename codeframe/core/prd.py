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


class PrdHasDependentTasksError(Exception):
    """Raised when attempting to delete a PRD that has dependent tasks."""

    def __init__(self, prd_id: str, task_count: int):
        self.prd_id = prd_id
        self.task_count = task_count
        super().__init__(
            f"Cannot delete PRD {prd_id}: {task_count} task(s) depend on it. "
            "Use check_dependencies=False to force deletion."
        )


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
        version: Version number (starts at 1)
        parent_id: ID of the previous version (None for first version)
        change_summary: Description of changes from parent version
        chain_id: ID that groups all versions of a PRD together (equals id for v1)
    """

    id: str
    workspace_id: str
    title: str
    content: str
    metadata: dict
    created_at: datetime
    version: int = 1
    parent_id: Optional[str] = None
    change_summary: Optional[str] = None
    chain_id: Optional[str] = None


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

    # For new PRDs, chain_id equals the PRD's own id
    chain_id = prd_id

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO prds
            (id, workspace_id, title, content, metadata, created_at,
             version, parent_id, change_summary, chain_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (prd_id, workspace.id, title, content, meta_json, now, 1, None, None, chain_id),
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
        version=1,
        parent_id=None,
        change_summary=None,
        chain_id=chain_id,
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
        SELECT id, workspace_id, title, content, metadata, created_at,
               version, parent_id, change_summary, chain_id
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
        version=row[6] or 1,
        parent_id=row[7],
        change_summary=row[8],
        chain_id=row[9],
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
        SELECT id, workspace_id, title, content, metadata, created_at,
               version, parent_id, change_summary, chain_id
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
        version=row[6] or 1,
        parent_id=row[7],
        change_summary=row[8],
        chain_id=row[9],
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
        SELECT id, workspace_id, title, content, metadata, created_at,
               version, parent_id, change_summary, chain_id
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
            version=row[6] or 1,
            parent_id=row[7],
            change_summary=row[8],
            chain_id=row[9],
        )
        for row in rows
    ]


def list_chains(workspace: Workspace) -> list[PrdRecord]:
    """List unique PRD chains, returning the latest version of each.

    A chain represents a PRD and all its versions. This function returns
    one entry per chain (the most recent version).

    Args:
        workspace: Workspace to query

    Returns:
        List of PrdRecords (latest version per chain), newest first
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    # Get the latest version for each unique chain_id
    cursor.execute(
        """
        SELECT p.id, p.workspace_id, p.title, p.content, p.metadata, p.created_at,
               p.version, p.parent_id, p.change_summary, p.chain_id
        FROM prds p
        INNER JOIN (
            SELECT chain_id, MAX(version) as max_version
            FROM prds
            WHERE workspace_id = ?
            GROUP BY chain_id
        ) latest ON p.chain_id = latest.chain_id AND p.version = latest.max_version
        WHERE p.workspace_id = ?
        ORDER BY p.created_at DESC
        """,
        (workspace.id, workspace.id),
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
            version=row[6] or 1,
            parent_id=row[7],
            change_summary=row[8],
            chain_id=row[9],
        )
        for row in rows
    ]


def delete(
    workspace: Workspace,
    prd_id: str,
    check_dependencies: bool = False,
) -> bool:
    """Delete a PRD from the workspace.

    Args:
        workspace: Workspace containing the PRD
        prd_id: PRD identifier to delete
        check_dependencies: If True, check for dependent tasks and raise error

    Returns:
        True if a PRD was deleted, False if not found

    Raises:
        PrdHasDependentTasksError: If check_dependencies=True and tasks depend on this PRD
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    # Check for dependent tasks if requested
    if check_dependencies:
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND prd_id = ?",
            (workspace.id, prd_id),
        )
        task_count = cursor.fetchone()[0]
        if task_count > 0:
            conn.close()
            raise PrdHasDependentTasksError(prd_id, task_count)

    cursor.execute(
        """
        DELETE FROM prds
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, prd_id),
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return deleted


def export_to_file(
    workspace: Workspace,
    prd_id: str,
    file_path: Path,
    force: bool = False,
) -> bool:
    """Export a PRD to a file.

    Args:
        workspace: Workspace containing the PRD
        prd_id: PRD identifier to export
        file_path: Target file path
        force: If True, overwrite existing file

    Returns:
        True if exported successfully, False if PRD not found

    Raises:
        FileExistsError: If file exists and force=False
    """
    record = get_by_id(workspace, prd_id)
    if not record:
        return False

    file_path = Path(file_path)

    # Check if file exists
    if file_path.exists() and not force:
        raise FileExistsError(f"File already exists: {file_path}")

    # Create parent directories if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Write content
    file_path.write_text(record.content, encoding="utf-8")

    return True


# ============================================================================
# PRD Versioning Functions
# ============================================================================


def create_new_version(
    workspace: Workspace,
    parent_prd_id: str,
    new_content: str,
    change_summary: str,
) -> Optional[PrdRecord]:
    """Create a new version of an existing PRD.

    Uses an explicit transaction to ensure atomic version number increment.

    Args:
        workspace: Workspace containing the PRD
        parent_prd_id: ID of the PRD to create a new version from
        new_content: New content for the PRD
        change_summary: Description of changes

    Returns:
        New PrdRecord if successful, None if parent not found
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    try:
        # Start explicit transaction for atomic version increment
        cursor.execute("BEGIN IMMEDIATE")

        # Get the parent PRD within the transaction
        cursor.execute(
            """
            SELECT id, workspace_id, title, content, metadata, created_at,
                   version, parent_id, change_summary, chain_id
            FROM prds
            WHERE workspace_id = ? AND id = ?
            """,
            (workspace.id, parent_prd_id),
        )
        row = cursor.fetchone()

        if not row:
            cursor.execute("ROLLBACK")
            conn.close()
            return None

        parent_title = row[2]
        parent_metadata = json.loads(row[4]) if row[4] else {}
        parent_version = row[6] or 1
        parent_chain_id = row[9]

        prd_id = str(uuid.uuid4())
        now = _utc_now().isoformat()
        new_version = parent_version + 1

        # Copy chain_id from parent (maintains version grouping)
        chain_id = parent_chain_id or parent_prd_id

        cursor.execute(
            """
            INSERT INTO prds
                (id, workspace_id, title, content, metadata, created_at,
                 version, parent_id, change_summary, chain_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prd_id,
                workspace.id,
                parent_title,  # Keep same title
                new_content,
                json.dumps(parent_metadata),
                now,
                new_version,
                parent_prd_id,
                change_summary,
                chain_id,
            ),
        )
        conn.commit()

        return PrdRecord(
            id=prd_id,
            workspace_id=workspace.id,
            title=parent_title,
            content=new_content,
            metadata=parent_metadata,
            created_at=datetime.fromisoformat(now),
            version=new_version,
            parent_id=parent_prd_id,
            change_summary=change_summary,
            chain_id=chain_id,
        )
    except Exception:
        cursor.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def get_versions(workspace: Workspace, prd_id: str) -> list[PrdRecord]:
    """Get all versions of a PRD.

    Uses chain_id for efficient single-query lookup of all versions.

    Args:
        workspace: Workspace to query
        prd_id: ID of any PRD in the version chain

    Returns:
        List of PrdRecords for all versions, newest first
    """
    # First, get the chain_id for this PRD
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT chain_id FROM prds WHERE workspace_id = ? AND id = ?",
        (workspace.id, prd_id),
    )
    row = cursor.fetchone()

    if not row:
        conn.close()
        return []

    chain_id = row[0]

    # If chain_id is None (legacy data), fall back to the PRD's own id
    if chain_id is None:
        chain_id = prd_id

    # Single query to get all versions in the chain
    cursor.execute(
        """
        SELECT id, workspace_id, title, content, metadata, created_at,
               version, parent_id, change_summary, chain_id
        FROM prds
        WHERE workspace_id = ? AND chain_id = ?
        ORDER BY version DESC
        """,
        (workspace.id, chain_id),
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
            version=row[6] or 1,
            parent_id=row[7],
            change_summary=row[8],
            chain_id=row[9],
        )
        for row in rows
    ]


def get_version(
    workspace: Workspace,
    prd_id: str,
    version_number: int,
) -> Optional[PrdRecord]:
    """Get a specific version of a PRD.

    Args:
        workspace: Workspace to query
        prd_id: ID of any PRD in the version chain
        version_number: Version number to retrieve

    Returns:
        PrdRecord if version exists, None otherwise
    """
    versions = get_versions(workspace, prd_id)
    for v in versions:
        if v.version == version_number:
            return v
    return None


def diff_versions(
    workspace: Workspace,
    prd_id: str,
    version1: int,
    version2: int,
) -> Optional[str]:
    """Generate a diff between two versions of a PRD.

    Args:
        workspace: Workspace to query
        prd_id: ID of any PRD in the version chain
        version1: First version number
        version2: Second version number

    Returns:
        Unified diff string, or None if either version doesn't exist
    """
    import difflib

    v1 = get_version(workspace, prd_id, version1)
    v2 = get_version(workspace, prd_id, version2)

    if not v1 or not v2:
        return None

    # Generate unified diff
    lines1 = v1.content.splitlines(keepends=True)
    lines2 = v2.content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        lines1,
        lines2,
        fromfile=f"Version {version1}",
        tofile=f"Version {version2}",
        lineterm="",
    )

    return "".join(diff)
