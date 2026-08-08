"""Workspace management for CodeFRAME v2.

A workspace represents a CodeFRAME-managed repository. Each workspace has:
- A .codeframe/ directory for state storage
- A SQLite database for persistent state
- Configuration and event logs

This module is headless - no FastAPI or HTTP dependencies.
"""

import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codeframe.core.atomic_io import fsync_directory

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

# State directory name
CODEFRAME_DIR = ".codeframe"
STATE_DB_NAME = "state.db"

# Stamped into ``PRAGMA user_version`` after ``_init_database`` /
# ``_ensure_schema_upgrades``. Bump by 1 whenever either function gains a new
# table/column/index so existing workspaces re-enter the (idempotent)
# migration path exactly once. Gates #733: steady-state loads skip all DDL.
# 3: batch_runs.config_reloads (#957).
# 4: batch_runs.cloud_timeout_minutes (#959).
# 5: prds.chain_id backfill for legacy child rows (#961).
SCHEMA_VERSION = 5

# Per-workspace config file written by the Settings page (issue #556).
# Owned by the UI layer today; kept here so a future core consumer can
# read it without importing from codeframe/ui/.
WORKSPACE_CONFIG_FILENAME = "workspace_config.json"


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


def _open_db(db_path: str | Path) -> sqlite3.Connection:
    """Open a workspace SQLite connection with concurrency safeguards.

    Mirrors ``codeframe/platform_store/database.py``. The substantive change is
    enabling **WAL journaling**: readers no longer block writers, which removes
    the rollback-journal case where a writer hits ``database is locked``
    immediately (the busy handler is skipped for that reader/writer deadlock).
    WAL is a persistent, database-level setting, so applying it on every
    connection is idempotent. ``busy_timeout`` is set to 5000ms to match
    platform_store and make the value explicit (Python's ``sqlite3.connect``
    already defaults to a 5s timeout). Matters under parallel batch execution
    where multiple processes and background agent threads write the same DB.

    The caller is responsible for closing the connection.
    """
    # NOTE: pass ``db_path`` through unchanged (sqlite3.connect accepts both str
    # and PathLike). Do NOT wrap in ``str()`` — that would coerce a non-path
    # (e.g. a test's MagicMock) into a literal filename and silently create a
    # junk DB file instead of raising, diverging from the prior connect call.
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    # SQLite ignores every FK clause unless this is set PER CONNECTION (#1061).
    # Without it the workspace schema's foreign keys were decorative: deleting a
    # task left its blockers, runs, run_logs and diagnostic_reports behind
    # forever. The control-plane DB has always enabled it; this one had not.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _create_token_usage_schema(cursor: sqlite3.Cursor) -> None:
    """Create the per-workspace `token_usage` table + indexes (issue #712).

    Shared by initial creation and the upgrade path so the two never drift.
    Columns match the repository INSERT (token_repository.save_token_usage);
    task_id/agent_id/project_id are TEXT because v2 task IDs are UUID strings.
    Columns are intentionally nullable: the INSERT omits some (e.g.
    actual_cost_usd) — do not add NOT NULL constraints back.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            agent_id TEXT,
            project_id TEXT,
            model_name TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost_usd REAL DEFAULT 0,
            actual_cost_usd REAL,
            call_type TEXT,
            timestamp TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp ON token_usage(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_task_id ON token_usage(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_token_usage_agent_id ON token_usage(agent_id)")


def _create_core_tables(cursor: sqlite3.Cursor) -> None:
    """Create every workspace table, idempotently (#1060).

    Tables only — indexes live in ``_create_core_indexes`` because their
    ordering is constrained on the upgrade path; see that docstring.

    The single definition of the workspace schema, called by BOTH
    ``_init_database`` (fresh workspace) and ``_ensure_schema_upgrades``
    (existing workspace) — the pattern ``_create_token_usage_schema`` already
    demonstrated, applied to the rest.

    Before this existed the DDL was copy-pasted between those two paths and had
    already drifted: ``blockers``, ``checkpoints``, ``events``, ``prds``,
    ``tasks`` and ``workspace`` plus five indexes were created only on the
    fresh path, so a workspace that reached the upgrade path missing one never
    got it back. Drift like that surfaces as a runtime error on whichever path
    is less exercised, which is exactly the one nobody tests.

    Every statement is ``IF NOT EXISTS``, so calling this on an existing
    database adds what is absent and touches nothing else. Column-level
    migrations (ALTER TABLE) stay in ``_ensure_schema_upgrades``: this function
    only guarantees that every object exists.
    """
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
            estimated_hours REAL,
            complexity_score INTEGER CHECK(complexity_score IS NULL OR (complexity_score BETWEEN 1 AND 5)),
            uncertainty_level TEXT CHECK(uncertainty_level IS NULL OR uncertainty_level IN ('low', 'medium', 'high')),
            parent_id TEXT,
            lineage TEXT DEFAULT '[]',
            is_leaf INTEGER DEFAULT 1,
            hierarchical_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (prd_id) REFERENCES prds(id),
            CHECK (status IN ('BACKLOG', 'READY', 'IN_PROGRESS', 'BLOCKED', 'FAILED', 'DONE', 'MERGED'))
        )
    """)

    # Migration: Add columns to existing tasks table
    # SQLite doesn't support IF NOT EXISTS for ALTER TABLE, so we check first
    cursor.execute("PRAGMA table_info(tasks)")
    columns = {row[1] for row in cursor.fetchall()}
    if "depends_on" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT DEFAULT '[]'")
    if "estimated_hours" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN estimated_hours REAL")
    if "complexity_score" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN complexity_score INTEGER")
    if "uncertainty_level" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN uncertainty_level TEXT")
    if "github_issue_number" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN github_issue_number INTEGER")
    if "parent_id" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN parent_id TEXT")
    if "lineage" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN lineage TEXT DEFAULT '[]'")
    if "is_leaf" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN is_leaf INTEGER DEFAULT 1")
    if "hierarchical_id" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN hierarchical_id TEXT")
    if "requirement_ids" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN requirement_ids TEXT DEFAULT '[]'")
    if "external_url" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN external_url TEXT")
    if "auto_close_github_issue" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN auto_close_github_issue INTEGER DEFAULT 0")

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
            created_by TEXT NOT NULL DEFAULT 'human',
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            CHECK (status IN ('OPEN', 'ANSWERED', 'RESOLVED')),
            CHECK (created_by IN ('system', 'agent', 'human'))
        )
    """)

    # Migration: Add created_by column to existing blockers table
    cursor.execute("PRAGMA table_info(blockers)")
    blocker_columns = {row[1] for row in cursor.fetchall()}
    if "created_by" not in blocker_columns:
        cursor.execute("ALTER TABLE blockers ADD COLUMN created_by TEXT NOT NULL DEFAULT 'human'")

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
            engine TEXT NOT NULL DEFAULT 'plan',
            isolation TEXT NOT NULL DEFAULT 'none',
            stall_timeout_s INTEGER NOT NULL DEFAULT 300,
            stall_action TEXT NOT NULL DEFAULT 'blocker',
            concurrency_by_status TEXT,
            llm_provider TEXT,
            llm_model TEXT,
            config_reloads TEXT,
            cloud_timeout_minutes INTEGER NOT NULL DEFAULT 30,
            FOREIGN KEY (workspace_id) REFERENCES workspace(id),
            CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED', 'CANCELLED'))
        )
    """)

    # Run logs (structured logging per run)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS run_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            log_level TEXT NOT NULL DEFAULT 'INFO',
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id),
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR'))
        )
    """)

    # Diagnostic reports (LLM analysis of run failures)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diagnostic_reports (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            root_cause TEXT NOT NULL,
            failure_category TEXT NOT NULL,
            severity TEXT NOT NULL,
            recommendations TEXT NOT NULL,
            log_summary TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            FOREIGN KEY (run_id) REFERENCES runs(id),
            CHECK (severity IN ('critical', 'high', 'medium', 'low'))
        )
    """)

    # Engine performance tracking: per-run log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS run_engine_log (
            run_id TEXT PRIMARY KEY,
            engine TEXT NOT NULL,
            task_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms INTEGER,
            tokens_used INTEGER DEFAULT 0,
            gates_passed INTEGER,
            self_corrections INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Engine performance tracking: aggregate stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS engine_stats (
            workspace_id TEXT NOT NULL,
            engine TEXT NOT NULL,
            metric TEXT NOT NULL,
            value REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (workspace_id, engine, metric)
        )
    """)

    # Execution trace tables (for debug/replay mode)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            step_type TEXT NOT NULL,
            description TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'started',
            input_context TEXT,
            output_result TEXT,
            metadata TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_interactions (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL,
            model TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            timestamp TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'execution',
            FOREIGN KEY (run_id) REFERENCES runs(id),
            FOREIGN KEY (step_id) REFERENCES execution_steps(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_operations (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content_before TEXT,
            content_after TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id),
            FOREIGN KEY (step_id) REFERENCES execution_steps(id),
            CHECK (operation_type IN ('create', 'edit', 'delete'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cloud_run_metadata (
            run_id TEXT PRIMARY KEY,
            sandbox_minutes REAL NOT NULL,
            cost_usd_estimate REAL NOT NULL,
            files_uploaded INTEGER NOT NULL,
            files_downloaded INTEGER NOT NULL,
            credential_scan_blocked INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Per-workspace token/cost tracking (issue #712 — was never created here,
    # so every save_token_usage() raised "no such table" and cost data dropped).
    _create_token_usage_schema(cursor)


def _create_core_indexes(cursor: sqlite3.Cursor) -> None:
    """Create every workspace index, idempotently (#1060).

    Split from ``_create_core_tables`` because ORDER MATTERS on the upgrade
    path, in two ways a whole-table-drop test cannot reveal:

    * ``idx_prds_chain``/``idx_prds_depends_on`` index columns that older
      workspaces do not have yet. Creating them before the guarded ALTER TABLE
      migrations raises ``no such column: chain_id`` and the workspace fails to
      open instead of upgrading.
    * ``idx_tasks_external_url`` is UNIQUE. A workspace that imported the same
      GitHub issue twice must be deduped first, or the index raises
      IntegrityError and there is no way back in.

    So the upgrade path creates tables early (safe — pure IF NOT EXISTS) and
    calls this only at the end, after every column migration and data fixup.
    """
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
    # Atomic duplicate-import protection (#565): one task per (workspace, issue
    # URL). SQLite treats NULLs as distinct, so non-imported tasks (NULL
    # external_url) are unaffected.
    #
    # The only statement here that can fail on real data, so the #943 guard
    # lives WITH it rather than at one call site: if duplicates survived the
    # dedupe, warn and carry on without the index. A missing optimisation is
    # recoverable; a workspace that will not open is not. Unreachable on a
    # fresh database, which has no rows yet.
    try:
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_external_url "
            "ON tasks(workspace_id, external_url)"
        )
    except sqlite3.IntegrityError as exc:
        logger.warning(
            "Could not create the unique external_url index (%s). Duplicate "
            "GitHub-import protection is OFF for this workspace; the "
            "workspace still opens normally.",
            exc,
        )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_workspace ON events(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_blockers_workspace ON blockers(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_blockers_status ON blockers(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_workspace ON batch_runs(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_runs_status ON batch_runs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_parent ON prds(parent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_chain ON prds(chain_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prds_depends_on ON prds(depends_on)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_run ON run_logs(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_logs_task ON run_logs(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diagnostic_reports_task ON diagnostic_reports(task_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diagnostic_reports_run ON diagnostic_reports(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_engine_log_ws_engine ON run_engine_log(workspace_id, engine)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_engine_stats_ws ON engine_stats(workspace_id, engine)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_steps_run ON execution_steps(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_steps_run_step ON execution_steps(run_id, step_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_interactions_run ON llm_interactions(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_llm_interactions_step ON llm_interactions(step_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_run ON file_operations(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_operations_step ON file_operations(step_id)")


def _create_core_schema(cursor: sqlite3.Cursor) -> None:
    """Tables then indexes — the fresh-workspace path, where order is trivial.

    A new database has no legacy columns to migrate and no duplicate rows, so
    both halves can run back to back. ``_ensure_schema_upgrades`` deliberately
    does NOT use this; see ``_create_core_indexes`` for why.
    """
    _create_core_tables(cursor)
    _create_core_indexes(cursor)


def _init_database(db_path: Path) -> None:
    """Initialize the workspace SQLite database with v2 schema.

    The schema itself lives in ``_create_core_schema``, shared with the upgrade
    path so the two cannot drift (#1060).
    """
    conn = _open_db(db_path)
    cursor = conn.cursor()

    _create_core_schema(cursor)

    # PRAGMA doesn't accept ? placeholders; SCHEMA_VERSION is a module int constant.
    cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    conn.close()



def _dedupe_external_urls(conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
    """Clear duplicate (workspace_id, external_url) rows before indexing (#943).

    Keeps the OLDEST row per pair — the first import is the one whose id other
    tables may already reference — and blanks the later ones' external_url
    rather than deleting the tasks. Deleting a user's task to add an index would
    be a cure worse than the disease; an unlinked duplicate is visible and
    fixable, a vanished task is not.
    """
    try:
        cursor.execute(
            """
            SELECT id FROM tasks
            WHERE external_url IS NOT NULL AND external_url != ''
              AND rowid NOT IN (
                  SELECT MIN(rowid) FROM tasks
                  WHERE external_url IS NOT NULL AND external_url != ''
                  GROUP BY workspace_id, external_url
              )
            """
        )
        dupes = [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as exc:
        logger.warning("Could not scan for duplicate external_url rows: %s", exc)
        return

    if not dupes:
        return

    logger.warning(
        "Unlinking %d duplicate GitHub-import task(s) so the unique index can "
        "be created; the tasks themselves are kept.",
        len(dupes),
    )
    cursor.executemany(
        "UPDATE tasks SET external_url = NULL WHERE id = ?", [(d,) for d in dupes]
    )
    conn.commit()


def _ensure_schema_upgrades(db_path: Path) -> None:
    """Ensure schema upgrades for existing databases.

    This function is idempotent and adds any new tables/columns
    that were added after the initial schema creation.

    Gated behind ``PRAGMA user_version`` (#733): once a database is stamped
    with the current ``SCHEMA_VERSION``, this returns after a single read —
    zero DDL, zero write commits — so per-request workspace loads are cheap.
    """
    conn = _open_db(db_path)
    try:
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    except Exception:
        conn.close()
        raise
    if current_version >= SCHEMA_VERSION:
        conn.close()
        return

    cursor = conn.cursor()

    # Every table, from the SAME definition the fresh path uses, so the two
    # cannot drift (#1060). Pure IF NOT EXISTS, so this adds whatever is absent
    # and touches nothing else. Indexes are deliberately NOT created here —
    # they run at the very end, once the ALTER TABLE migrations below have
    # added the columns they index and the data fixups have made the UNIQUE
    # ones satisfiable.
    _create_core_tables(cursor)
    conn.commit()

    # Add columns that were introduced after the initial batch_runs schema
    # (migration for existing databases). Each ALTER is guarded by a column
    # existence check so this is idempotent. isolation + stall/provider/
    # concurrency columns were added for #741 so `batch resume` restores the
    # original run settings instead of silently falling back to defaults.
    cursor.execute("PRAGMA table_info(batch_runs)")
    batch_columns = {row[1] for row in cursor.fetchall()}
    batch_migrations = (
        ("engine", "ALTER TABLE batch_runs ADD COLUMN engine TEXT NOT NULL DEFAULT 'plan'"),
        ("isolation", "ALTER TABLE batch_runs ADD COLUMN isolation TEXT NOT NULL DEFAULT 'none'"),
        ("stall_timeout_s", "ALTER TABLE batch_runs ADD COLUMN stall_timeout_s INTEGER NOT NULL DEFAULT 300"),
        ("stall_action", "ALTER TABLE batch_runs ADD COLUMN stall_action TEXT NOT NULL DEFAULT 'blocker'"),
        ("concurrency_by_status", "ALTER TABLE batch_runs ADD COLUMN concurrency_by_status TEXT"),
        ("llm_provider", "ALTER TABLE batch_runs ADD COLUMN llm_provider TEXT"),
        ("llm_model", "ALTER TABLE batch_runs ADD COLUMN llm_model TEXT"),
        # #957: config-reload bookkeeping moved off the results JSON blob.
        ("config_reloads", "ALTER TABLE batch_runs ADD COLUMN config_reloads TEXT"),
        # #959: the user's --cloud-timeout must survive a resume.
        ("cloud_timeout_minutes", "ALTER TABLE batch_runs ADD COLUMN cloud_timeout_minutes INTEGER NOT NULL DEFAULT 30"),
    )
    for column, ddl in batch_migrations:
        if column not in batch_columns:
            cursor.execute(ddl)
    conn.commit()

    # Add tech_stack column to workspace table if it doesn't exist
    # First check if workspace table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(workspace)")
        columns = {row[1] for row in cursor.fetchall()}
        if "tech_stack" not in columns:
            cursor.execute("ALTER TABLE workspace ADD COLUMN tech_stack TEXT")
            conn.commit()

    # Add versioning columns to prds table if they don't exist
    # First check if prds table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prds'"
    )
    if cursor.fetchone():
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
            conn.commit()

        # Backfill any PRD still missing a chain_id (#961). This runs on every
        # upgrade, not only when the column is first added: the original
        # backfill above set chain_id only WHERE parent_id IS NULL, so every
        # legacy *child* row kept a NULL chain_id — and because SQL's
        # `NULL = NULL` never matches, list_chains' join dropped those PRDs
        # from the workspace entirely. The recursive CTE walks each row up to
        # its root so children join their parent's chain rather than forming
        # spurious one-row chains. Rows whose parent is missing keep their own
        # id (COALESCE), which is the best available answer.
        cursor.execute("""
            WITH RECURSIVE root_of(id, root) AS (
                SELECT id, id FROM prds WHERE parent_id IS NULL
                UNION ALL
                SELECT p.id, r.root
                FROM prds p JOIN root_of r ON p.parent_id = r.id
            )
            UPDATE prds
            SET chain_id = COALESCE(
                (SELECT root FROM root_of WHERE root_of.id = prds.id), id
            )
            WHERE chain_id IS NULL
        """)
        conn.commit()

        # Add depends_on column to prds table if it doesn't exist
        # Re-check prd_columns as it may have changed
        cursor.execute("PRAGMA table_info(prds)")
        prd_columns = {row[1] for row in cursor.fetchall()}
        if "depends_on" not in prd_columns:
            cursor.execute("ALTER TABLE prds ADD COLUMN depends_on TEXT")
            conn.commit()

        conn.commit()

    # Add new columns to tasks table if they don't exist
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
    )
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(tasks)")
        task_columns = {row[1] for row in cursor.fetchall()}
        if "depends_on" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT DEFAULT '[]'")
            conn.commit()
        if "estimated_hours" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN estimated_hours REAL")
            conn.commit()
        if "complexity_score" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN complexity_score INTEGER")
            conn.commit()
        if "uncertainty_level" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN uncertainty_level TEXT")
            conn.commit()
        if "parent_id" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN parent_id TEXT")
            conn.commit()
        if "lineage" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN lineage TEXT DEFAULT '[]'")
            conn.commit()
        if "is_leaf" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN is_leaf INTEGER DEFAULT 1")
            conn.commit()
        if "hierarchical_id" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN hierarchical_id TEXT")
            conn.commit()
        if "requirement_ids" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN requirement_ids TEXT DEFAULT '[]'")
            conn.commit()
        if "github_issue_number" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN github_issue_number INTEGER")
            conn.commit()
        if "external_url" not in task_columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN external_url TEXT")
            conn.commit()
        if "auto_close_github_issue" not in task_columns:
            cursor.execute(
                "ALTER TABLE tasks ADD COLUMN auto_close_github_issue INTEGER DEFAULT 0"
            )
            conn.commit()
        # Atomic duplicate-import protection (#565) for existing workspaces.
        #
        # This ran unconditionally, so a workspace that already held duplicate
        # external_url rows raised on EVERY get_workspace — bricking both the
        # CLI and the server with no recovery path (#943). Dedupe first, and if
        # that cannot be done, warn and carry on without the index: a missing
        # optimisation is recoverable, an unopenable workspace is not.
        # Dedupe only. The index itself is created — once, and guarded — by
        # _create_core_indexes at the end of this function. Creating it here as
        # well left an UNGUARDED second attempt downstream, which reintroduced
        # the exact IntegrityError brick this guard exists to survive.
        _dedupe_external_urls(conn, cursor)
        conn.commit()

    conn.commit()

    # LAST, and from the same definition the fresh path uses. Everything above
    # has run: the ALTER TABLE migrations have added the columns these index,
    # and _dedupe_external_urls has made the UNIQUE one satisfiable. Creating
    # them any earlier fails a real legacy workspace outright (#1060).
    _create_core_indexes(cursor)

    # PRAGMA doesn't accept ? placeholders; SCHEMA_VERSION is a module int constant.
    cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

    conn.close()



def _ensure_state_dir_ignored(state_dir: Path) -> None:
    """Keep .codeframe/ out of the user's git history (#942).

    The sandbox code assumed this was ignored, but nothing ever wrote the rule —
    so `cf commit --all` (and any `git add -A`) could stage state.db, WAL files
    and worktree gitlinks into the user's repository.

    The rule goes in `.codeframe/.gitignore` rather than the repo's root
    `.gitignore`: that file belongs to the user, may be committed, and is not
    ours to edit. A self-ignoring directory needs no cooperation from it, works
    in a repo that has no .gitignore at all, and disappears with the directory.
    """
    marker = state_dir / ".gitignore"
    if marker.exists():
        return
    try:
        marker.write_text(
            "# Managed by CodeFRAME (#942). This directory holds local state —\n"
            "# SQLite databases, WAL files, worktree gitlinks — that must never\n"
            "# enter the repository's history.\n"
            "*\n",
            encoding="utf-8",
        )
    except OSError as exc:
        # Not fatal: a read-only checkout still gets a working workspace, it
        # just does not get the guard.
        logger.warning("Could not write %s: %s", marker, exc)


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
    _ensure_state_dir_ignored(state_dir)

    # Build the whole database at a temp path and only move it into place once
    # the workspace row is committed (#954). Writing straight to state.db meant a
    # crash between _init_database and the INSERT left a schema-complete but
    # rowless DB; every later call then took the `db_path.exists()` branch above
    # and get_workspace raised "contains no workspace record" forever, with no
    # way out but deleting .codeframe by hand. Now a mid-init failure leaves no
    # state.db at all, so `cf init` simply works on the next run.
    workspace_id = str(uuid.uuid4())
    now = _utc_now().isoformat()

    # Deliberately NOT tempfile.mkstemp: that forces 0600, and os.replace
    # preserves it, so state.db would be silently tightened from the mode sqlite
    # gives it. Reproducing that mode by hand is also wrong — sqlite creates with
    # a 0644 base, not open()'s 0666, so `0o666 & ~umask` turns state.db
    # group-WRITABLE under a 002/007 umask (raised by the GLM reviewer, and my
    # first test for it was tautological: the same formula on both sides).
    # Letting sqlite create the file is the only version with no permission math
    # to get wrong. uuid4 makes the name unique per writer, which is all mkstemp
    # was buying here.
    tmp_db = state_dir / f".{STATE_DB_NAME}.{uuid.uuid4().hex}.tmp"
    try:
        _init_database(tmp_db)

        conn = _open_db(tmp_db)
        try:
            conn.execute(
                "INSERT INTO workspace (id, repo_path, tech_stack, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (workspace_id, str(repo_path), tech_stack, now, now),
            )
            conn.commit()
            # _open_db enables WAL, so committed rows can still live in the
            # sidecar -wal file. Fold them into the main database before the
            # rename — otherwise os.replace moves a file whose newest pages were
            # left behind in a temp-named WAL.
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

        os.replace(tmp_db, db_path)
        # os.replace is atomic but not durable on its own: a power loss right
        # after it can lose the directory entry, so `cf init` would report
        # success and come back to an uninitialized workspace (raised by
        # `codex review`).
        fsync_directory(state_dir)
    except BaseException:
        # Remove the partial DB and its WAL/SHM siblings so nothing is left to
        # confuse the next run.
        for leftover in (tmp_db, Path(f"{tmp_db}-wal"), Path(f"{tmp_db}-shm")):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return Workspace(
        id=workspace_id,
        repo_path=repo_path,
        state_dir=state_dir,
        created_at=datetime.fromisoformat(now),
        tech_stack=tech_stack,
    )


def find_workspace_root(start: Path) -> Optional[Path]:
    """The nearest enclosing workspace root, or None (#926).

    ``get_workspace`` looks for ``.codeframe/`` in exactly the directory it is
    given. So ``cf pr merge`` from ``repo/src/`` raised FileNotFoundError, which
    ``_check_merge_gate`` reads as "no workspace here, nothing to gate" — the
    #731 PROOF9 merge gate silently did not apply, with no warning and no audit
    record, from the directory people actually run git commands in.

    Walks up from ``start``, so a nested workspace wins over its parent: the one
    you are *in* is the one that governs.

    The marker is the state database, not the ``.codeframe/`` directory alone.
    The machine-wide ``~/.codeframe`` holds the credential store, agent homes
    and logs — so matching on the directory name would make every path under
    ``$HOME`` resolve to a "workspace" rooted at the home directory, and
    ``/tmp/.codeframe`` would do the same for every temp path.
    """
    try:
        current = start.resolve()
    except OSError:
        return None

    for candidate in (current, *current.parents):
        if (candidate / CODEFRAME_DIR / STATE_DB_NAME).is_file():
            return candidate
    return None


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

    conn = _open_db(db_path)
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
    return _open_db(workspace.db_path)


def get_db_connection_by_path(db_path: str | Path) -> sqlite3.Connection:
    """Open a workspace DB connection from a raw path (WAL + busy_timeout).

    Same connection setup as :func:`get_db_connection`, for callers that hold a
    path rather than a :class:`Workspace` (e.g. the costs router's helpers that
    tolerate fresh/locked DBs). The caller is responsible for closing it.
    """
    return _open_db(db_path)


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

    conn = _open_db(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE workspace SET tech_stack = ?, updated_at = ?",
        (tech_stack, now),
    )
    conn.commit()
    conn.close()

    return get_workspace(repo_path)
