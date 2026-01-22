"""Workspace management for CodeFRAME v2.

A workspace represents a CodeFRAME-managed repository. Each workspace has:
- A .codeframe/ directory for state storage
- A SQLite database for persistent state
- Configuration and event logs

This module is headless - no FastAPI or HTTP dependencies.
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

# State directory name
CODEFRAME_DIR = ".codeframe"
STATE_DB_NAME = "state.db"


@dataclass
class Workspace:
    """Represents a CodeFRAME workspace.

    Attributes:
        id: Unique workspace identifier (UUID)
        repo_path: Absolute path to the repository
        state_dir: Path to .codeframe/ directory
        created_at: When the workspace was initialized
        tech_stack: Natural language description of the project's technology stack
    """

    id: str
    repo_path: Path
    state_dir: Path
    created_at: datetime
    tech_stack: Optional[str] = None

    @property
    def db_path(self) -> Path:
        """Path to the SQLite state database."""
        return self.state_dir / STATE_DB_NAME


def _get_state_dir(repo_path: Path) -> Path:
    """Get the .codeframe/ directory path for a repository."""
    return repo_path / CODEFRAME_DIR


def _init_database(db_path: Path) -> None:
    """Initialize the workspace SQLite database with v2 schema.

    Creates tables for:
    - workspaces: Workspace metadata
    - prds: Product requirements documents
    - tasks: Task state machine
    - events: Append-only event log
    - blockers: Human-in-the-loop blockers
    - checkpoints: State snapshots
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Workspace metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace (
            id TEXT PRIMARY KEY,
            repo_path TEXT NOT NULL,
            tech_stack TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # PRD storage with versioning support
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prds (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            parent_id TEXT,
            change_summary TEXT,
            chain_id TEXT,
            depends_on TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (parent_id) REFERENCES prds(id),
            FOREIGN KEY (chain_id) REFERENCES prds(id)
        )
    """)

    # Task state machine (Golden Path statuses)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            prd_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'BACKLOG',
            priority INTEGER DEFAULT 0,
            depends_on TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (prd_id) REFERENCES prds(id),
            CHECK (status IN ('BACKLOG', 'READY', 'IN_PROGRESS', 'BLOCKED', 'FAILED', 'DONE', 'MERGED'))
        )
    """)

    # Migration: Add depends_on column to existing tasks table
    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we check first
    cursor.execute("PRAGMA table_info(tasks)")
    columns = {row[1] for row in cursor.fetchall()}
    if "depends_on" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT DEFAULT '[]'")

    # Append-only event log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id)
        )
    """)

    # Blockers (human-in-the-loop)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blockers (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            task_id TEXT,
            question TEXT NOT NULL,
            answer TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN',
            created_at TEXT NOT NULL,
            answered_at TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            CHECK (status IN ('OPEN', 'ANSWERED', 'RESOLVED'))
        )
    """)

    # Checkpoints (state snapshots)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            name TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id)
        )
    """)

    # Runs (agent execution records)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED'))
        )
    """)

    # Batch runs (multi-task orchestration)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batch_runs (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            task_ids TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            strategy TEXT NOT NULL DEFAULT 'serial',
            max_parallel INTEGER NOT NULL DEFAULT 4,
            on_failure TEXT NOT NULL DEFAULT 'continue',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            results TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED'))
        )
    """)

    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_workspace ON events(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_blockers_workspace ON blockers(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_blockers_status ON blockers(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_workspace ON batch_runs(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_status ON batch_runs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_parent ON prds(parent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_chain ON prds(chain_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_depends_on ON prds(depends_on)")

    conn.commit()
    conn.close()


def _ensure_schema_upgrades(db_path: Path) -> None:
    """Ensure schema upgrades for existing databases.

    This function is idempotent and adds any new tables/columns
    that were added after the initial schema creation.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if batch_runs table exists, if not create it
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_runs'"
    )
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS batch_runs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                task_ids TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                strategy TEXT NOT NULL DEFAULT 'serial',
                max_parallel INTEGER NOT NULL DEFAULT 4,
                on_failure TEXT NOT NULL DEFAULT 'continue',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                results TEXT,
                FOREIGN KEY (workspace_id) REFERENCES workspace(id),
                CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED'))
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_workspace ON batch_runs(workspace_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_status ON batch_runs(status)")
        conn.commit()

    # Add tech_stack column to workspace table if it doesn't exist
    cursor.execute("PRAGMA table_info(workspace)")
    columns = {row[1] for row in cursor.fetchall()}
    if "tech_stack" not in columns:
        cursor.execute("ALTER TABLE workspace ADD COLUMN tech_stack TEXT")
        conn.commit()

    # Add versioning columns to prds table if they don't exist
    cursor.execute("PRAGMA table_info(prds)")
    prd_columns = {row[1] for row in cursor.fetchall()}
    if "version" not in prd_columns:
        cursor.execute("ALTER TABLE prds ADD COLUMN version INTEGER DEFAULT 1")
        conn.commit()
    if "parent_id" not in prd_columns:
        cursor.execute("ALTER TABLE prds ADD COLUMN parent_id TEXT")
        conn.commit()
    if "change_summary" not in prd_columns:
        cursor.execute("ALTER TABLE prds ADD COLUMN change_summary TEXT")
        conn.commit()
    if "chain_id" not in prd_columns:
        cursor.execute("ALTER TABLE prds ADD COLUMN chain_id TEXT")
        # Backfill chain_id for existing PRDs (set to their own id if no parent)
        cursor.execute("""
            UPDATE prds SET chain_id = id
            WHERE chain_id IS NULL AND parent_id IS NULL
        """)
        conn.commit()

    # Add depends_on column to prds table if it doesn't exist
    # Re-check prd_columns as it may have changed
    cursor.execute("PRAGMA table_info(prds)")
    prd_columns = {row[1] for row in cursor.fetchall()}
    if "depends_on" not in prd_columns:
        cursor.execute("ALTER TABLE prds ADD COLUMN depends_on TEXT")
        conn.commit()

    # Add indexes for PRD version chain queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_parent ON prds(parent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_chain ON prds(chain_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_depends_on ON prds(depends_on)")
    conn.commit()

    conn.close()


def create_or_load_workspace(repo_path: Path, tech_stack: Optional[str] = None) -> Workspace:
    """Create a new workspace or load an existing one.

    This is idempotent - calling it on an already-initialized repo
    will return the existing workspace (tech_stack is ignored if workspace exists).

    Args:
        repo_path: Path to the repository (must exist)
        tech_stack: Optional natural language description of the project's tech stack

    Returns:
        Workspace object with metadata

    Raises:
        FileNotFoundError: If repo_path doesn't exist
        NotADirectoryError: If repo_path is not a directory
    """
    repo_path = repo_path.resolve()

    if not repo_path.exists():
        raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

    if not repo_path.is_dir():
        raise NotADirectoryError(f"Repository path is not a directory: {repo_path}")

    state_dir = _get_state_dir(repo_path)
    db_path = state_dir / STATE_DB_NAME

    # Check if workspace already exists
    if state_dir.exists() and db_path.exists():
        return get_workspace(repo_path)

    # Create .codeframe/ directory
    state_dir.mkdir(exist_ok=True)

    # Initialize database
    _init_database(db_path)

    # Create workspace record
    workspace_id = str(uuid.uuid4())
    now = _utc_now().isoformat()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO workspace (id, repo_path, tech_stack, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (workspace_id, str(repo_path), tech_stack, now, now),
    )
    conn.commit()
    conn.close()

    return Workspace(
        id=workspace_id,
        repo_path=repo_path,
        state_dir=state_dir,
        created_at=datetime.fromisoformat(now),
        tech_stack=tech_stack,
    )


def get_workspace(repo_path: Path) -> Workspace:
    """Load an existing workspace.

    Args:
        repo_path: Path to the repository

    Returns:
        Workspace object

    Raises:
        FileNotFoundError: If no workspace exists at this path
    """
    repo_path = repo_path.resolve()
    state_dir = _get_state_dir(repo_path)
    db_path = state_dir / STATE_DB_NAME

    if not state_dir.exists() or not db_path.exists():
        raise FileNotFoundError(f"No workspace found at {repo_path}")

    # Ensure schema is up to date for existing workspaces
    _ensure_schema_upgrades(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, repo_path, tech_stack, created_at FROM workspace LIMIT 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise FileNotFoundError("Workspace database exists but contains no workspace record")

    return Workspace(
        id=row[0],
        repo_path=Path(row[1]),
        state_dir=state_dir,
        created_at=datetime.fromisoformat(row[3]),
        tech_stack=row[2],
    )


def get_db_connection(workspace: Workspace) -> sqlite3.Connection:
    """Get a database connection for a workspace.

    The caller is responsible for closing the connection.

    Args:
        workspace: Workspace object

    Returns:
        SQLite connection
    """
    return sqlite3.connect(workspace.db_path)


def workspace_exists(repo_path: Path) -> bool:
    """Check if a workspace exists at the given path.

    Args:
        repo_path: Path to check

    Returns:
        True if workspace exists, False otherwise
    """
    state_dir = _get_state_dir(repo_path.resolve())
    db_path = state_dir / STATE_DB_NAME
    return state_dir.exists() and db_path.exists()


def update_workspace_tech_stack(repo_path: Path, tech_stack: Optional[str]) -> Workspace:
    """Update the tech_stack for an existing workspace.

    Args:
        repo_path: Path to the repository
        tech_stack: New tech stack description (or None to clear)

    Returns:
        Updated Workspace object

    Raises:
        FileNotFoundError: If no workspace exists at this path
    """
    repo_path = repo_path.resolve()
    state_dir = _get_state_dir(repo_path)
    db_path = state_dir / STATE_DB_NAME

    if not state_dir.exists() or not db_path.exists():
        raise FileNotFoundError(f"No workspace found at {repo_path}")

    now = _utc_now().isoformat()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE workspace SET tech_stack = ?, updated_at = ?",
        (tech_stack, now),
    )
    conn.commit()
    conn.close()

    return get_workspace(repo_path)
