"""Database management for CodeFRAME state.

Refactored to use domain-specific repositories for better maintainability.
The Database class now acts as a facade, delegating operations to repositories.
"""

import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import logging

import asyncio
import aiosqlite

from codeframe.persistence.schema_manager import SchemaManager
from codeframe.persistence.repositories import (
    ProjectRepository,
    IssueRepository,
    TaskRepository,
    AgentRepository,
    BlockerRepository,
    MemoryRepository,
    ContextRepository,
    CheckpointRepository,
    GitRepository,
    TestRepository,
    LintRepository,
    ReviewRepository,
    QualityRepository,
    TokenRepository,
    CorrectionRepository,
    ActivityRepository,
    AuditRepository,
    PRRepository,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class Database:
    """SQLite database manager for project state.

    This class acts as a facade, delegating operations to domain-specific repositories.
    All methods maintain 100% backward compatibility with the original monolithic Database class.

    Repositories:
        - projects: Project management (create, update, delete, list)
        - issues: Issue tracking and management
        - tasks: Task lifecycle and dependencies
        - agents: Agent creation and assignment
        - blockers: Human-in-the-loop blocking questions
        - memories: Conversation and decision memory
        - context_items: Context management for long-running sessions
        - checkpoints: Project state checkpoints
        - git_branches: Git branch tracking
        - test_results: Test execution results
        - lint_results: Linting results
        - code_reviews: Code review findings
        - quality_gates: Quality gate status
        - token_usage: LLM token usage tracking
        - correction_attempts: Error correction tracking
        - activities: Activity logs and PRD
        - audit_logs: Audit logging

    Supports both synchronous (sqlite3) and asynchronous (aiosqlite) operations.
    """

    def __init__(self, db_path: Path | str):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file or ":memory:"
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._async_conn: Optional[aiosqlite.Connection] = None
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.Lock()  # Thread-safe access to sync connection

        # Initialize repositories (will be set after connections are created)
        self.projects: Optional[ProjectRepository] = None
        self.issues: Optional[IssueRepository] = None
        self.tasks: Optional[TaskRepository] = None
        self.agents: Optional[AgentRepository] = None
        self.blockers: Optional[BlockerRepository] = None
        self.memories: Optional[MemoryRepository] = None
        self.context_items: Optional[ContextRepository] = None
        self.checkpoints: Optional[CheckpointRepository] = None
        self.git_branches: Optional[GitRepository] = None
        self.test_results: Optional[TestRepository] = None
        self.lint_results: Optional[LintRepository] = None
        self.code_reviews: Optional[ReviewRepository] = None
        self.quality_gates: Optional[QualityRepository] = None
        self.token_usage: Optional[TokenRepository] = None
        self.correction_attempts: Optional[CorrectionRepository] = None
        self.activities: Optional[ActivityRepository] = None
        self.audit_logs: Optional[AuditRepository] = None
        self.pull_requests: Optional[PRRepository] = None

    def initialize(self) -> None:
        """Initialize database schema and repositories."""
        # Create parent directories if needed
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create sync connection
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrent access (allows reads during writes)
        self.conn.execute("PRAGMA journal_mode = WAL")
        # Set busy timeout to handle concurrent access contention
        self.conn.execute("PRAGMA busy_timeout = 5000")

        # Create schema using SchemaManager
        schema_mgr = SchemaManager(self.conn)
        schema_mgr.create_schema()

        # Initialize all repositories with sync connection
        self._initialize_repositories()

    def _initialize_repositories(self) -> None:
        """Initialize all repository instances."""
        # Pass both sync and async connections to support mixed operations
        # Also pass self (Database instance) for cross-repository operations
        # Pass sync_lock for thread-safe access to the shared connection
        self.projects = ProjectRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.issues = IssueRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.tasks = TaskRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.agents = AgentRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.blockers = BlockerRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.memories = MemoryRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.context_items = ContextRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.checkpoints = CheckpointRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.git_branches = GitRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.test_results = TestRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.lint_results = LintRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.code_reviews = ReviewRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.quality_gates = QualityRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.token_usage = TokenRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.correction_attempts = CorrectionRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.activities = ActivityRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.audit_logs = AuditRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)
        self.pull_requests = PRRepository(sync_conn=self.conn, async_conn=self._async_conn, database=self, sync_lock=self._sync_lock)

    # Backward compatibility properties (maintain old *_repository naming)
    @property
    def task_repository(self) -> TaskRepository:
        """Backward compatibility: Access tasks repository."""
        return self.tasks

    @property
    def blocker_repository(self) -> BlockerRepository:
        """Backward compatibility: Access blockers repository."""
        return self.blockers

    # Connection management methods
    def close(self) -> None:
        """Close database connection (sync only)."""
        if self.conn:
            self.conn.close()
            self.conn = None

    async def close_async(self) -> None:
        """Close async database connection."""
        if self._async_conn:
            await self._async_conn.close()
            self._async_conn = None

    async def close_all(self) -> None:
        """Close both sync and async database connections."""
        self.close()
        await self.close_async()

    def __del__(self) -> None:
        """Destructor with warning for unclosed connections."""
        if self._async_conn is not None:
            logger.warning(
                f"Database async connection for {self.db_path} was not explicitly closed. "
                "Use 'async with db:' or call close_async() to properly close async connections."
            )
        if self.conn is not None:
            self.close()

    async def initialize_async(self) -> None:
        """Explicitly initialize the async database connection."""
        async with self._async_lock:
            if self._async_conn is None:
                self._async_conn = await aiosqlite.connect(str(self.db_path))
                self._async_conn.row_factory = aiosqlite.Row
                # Match sync connection pragmas for consistency
                await self._async_conn.execute("PRAGMA foreign_keys = ON")
                await self._async_conn.execute("PRAGMA journal_mode = WAL")
                await self._async_conn.execute("PRAGMA busy_timeout = 5000")
                logger.debug(f"Async connection initialized for {self.db_path}")
                # Update repository async connections
                if self.projects:
                    self._update_repository_async_connections()

    def _update_repository_async_connections(self) -> None:
        """Update async connections in all repositories."""
        for repo in [self.projects, self.issues, self.tasks, self.agents, self.blockers,
                     self.memories, self.context_items, self.checkpoints, self.git_branches,
                     self.test_results, self.lint_results, self.code_reviews, self.quality_gates,
                     self.token_usage, self.correction_attempts, self.activities, self.audit_logs]:
            if repo:
                repo._async_conn = self._async_conn

    async def _get_async_conn(self) -> aiosqlite.Connection:
        """Get async connection with health check and automatic reconnection."""
        async with self._async_lock:
            if self._async_conn is None:
                self._async_conn = await aiosqlite.connect(str(self.db_path))
                self._async_conn.row_factory = aiosqlite.Row
                # Match sync connection pragmas for consistency
                await self._async_conn.execute("PRAGMA foreign_keys = ON")
                await self._async_conn.execute("PRAGMA journal_mode = WAL")
                await self._async_conn.execute("PRAGMA busy_timeout = 5000")
                logger.debug(f"Async connection created (lazy init) for {self.db_path}")
                self._update_repository_async_connections()
                return self._async_conn

            try:
                await self._async_conn.execute("SELECT 1")
                return self._async_conn
            except Exception as e:
                logger.warning(f"Async connection health check failed: {e}, reconnecting...")
                try:
                    await self._async_conn.close()
                except Exception:
                    pass

                self._async_conn = await aiosqlite.connect(str(self.db_path))
                self._async_conn.row_factory = aiosqlite.Row
                # Match sync connection pragmas for consistency
                await self._async_conn.execute("PRAGMA foreign_keys = ON")
                await self._async_conn.execute("PRAGMA journal_mode = WAL")
                await self._async_conn.execute("PRAGMA busy_timeout = 5000")
                logger.info(f"Async connection reconnected for {self.db_path}")
                self._update_repository_async_connections()
                return self._async_conn

    # Context managers
    def __enter__(self) -> "Database":
        """Context manager entry."""
        if not self.conn:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    async def __aenter__(self) -> "Database":
        """Async context manager entry."""
        if not self.conn:
            self.initialize()
        await self.initialize_async()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_async()

    # Backward compatibility: Parse datetime helper (used by many tests)
    def _parse_datetime(
        self, value: str, field_name: str, row_id: Optional[int] = None
    ) -> Optional[datetime]:
        """Parse ISO datetime string with logging for failures."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError) as e:
            row_context = f" (row {row_id})" if row_id else ""
            logger.warning(
                f"Failed to parse {field_name}{row_context}: '{value}', error: {e}"
            )
            return None

    def create_project(self, *args, **kwargs):
        """Delegate to projects.create_project()."""
        return self.projects.create_project(*args, **kwargs)

    def get_project(self, *args, **kwargs):
        """Delegate to projects.get_project()."""
        return self.projects.get_project(*args, **kwargs)

    def list_projects(self, *args, **kwargs):
        """Delegate to projects.list_projects()."""
        return self.projects.list_projects(*args, **kwargs)

    def update_project(self, *args, **kwargs):
        """Delegate to projects.update_project()."""
        return self.projects.update_project(*args, **kwargs)

    def delete_project(self, *args, **kwargs):
        """Delegate to projects.delete_project()."""
        return self.projects.delete_project(*args, **kwargs)

    def _row_to_project(self, *args, **kwargs):
        """Delegate to projects._row_to_project()."""
        return self.projects._row_to_project(*args, **kwargs)

    def _calculate_project_progress(self, *args, **kwargs):
        """Delegate to projects._calculate_project_progress()."""
        return self.projects._calculate_project_progress(*args, **kwargs)

    def get_project_tasks(self, *args, **kwargs):
        """Delegate to projects.get_project_tasks()."""
        return self.projects.get_project_tasks(*args, **kwargs)

    def get_project_stats(self, *args, **kwargs):
        """Delegate to projects.get_project_stats()."""
        return self.projects.get_project_stats(*args, **kwargs)

    def get_user_projects(self, *args, **kwargs):
        """Delegate to projects.get_user_projects()."""
        return self.projects.get_user_projects(*args, **kwargs)

    def user_has_project_access(self, *args, **kwargs):
        """Delegate to projects.user_has_project_access()."""
        return self.projects.user_has_project_access(*args, **kwargs)

    def create_issue(self, *args, **kwargs):
        """Delegate to issues.create_issue()."""
        return self.issues.create_issue(*args, **kwargs)

    def get_issue(self, *args, **kwargs):
        """Delegate to issues.get_issue()."""
        return self.issues.get_issue(*args, **kwargs)

    def get_project_issues(self, *args, **kwargs):
        """Delegate to issues.get_project_issues()."""
        return self.issues.get_project_issues(*args, **kwargs)

    def get_issues_with_tasks(self, *args, **kwargs):
        """Delegate to issues.get_issues_with_tasks()."""
        return self.issues.get_issues_with_tasks(*args, **kwargs)

    def list_issues_with_progress(self, *args, **kwargs):
        """Delegate to issues.list_issues_with_progress()."""
        return self.issues.list_issues_with_progress(*args, **kwargs)

    def get_issue_with_task_counts(self, *args, **kwargs):
        """Delegate to issues.get_issue_with_task_counts()."""
        return self.issues.get_issue_with_task_counts(*args, **kwargs)

    def _row_to_issue(self, *args, **kwargs):
        """Delegate to issues._row_to_issue()."""
        return self.issues._row_to_issue(*args, **kwargs)

    def list_issues(self, *args, **kwargs):
        """Delegate to issues.list_issues()."""
        return self.issues.list_issues(*args, **kwargs)

    def update_issue(self, *args, **kwargs):
        """Delegate to issues.update_issue()."""
        return self.issues.update_issue(*args, **kwargs)

    def get_issue_completion_status(self, *args, **kwargs):
        """Delegate to issues.get_issue_completion_status()."""
        return self.issues.get_issue_completion_status(*args, **kwargs)

    def create_task(self, *args, **kwargs):
        """Delegate to tasks.create_task()."""
        return self.tasks.create_task(*args, **kwargs)

    def get_task(self, *args, **kwargs):
        """Delegate to tasks.get_task()."""
        return self.tasks.get_task(*args, **kwargs)

    def update_task(self, *args, **kwargs):
        """Delegate to tasks.update_task()."""
        return self.tasks.update_task(*args, **kwargs)

    def create_task_with_issue(self, *args, **kwargs):
        """Delegate to tasks.create_task_with_issue()."""
        return self.tasks.create_task_with_issue(*args, **kwargs)

    def get_tasks_by_parent_issue_number(self, *args, **kwargs):
        """Delegate to tasks.get_tasks_by_parent_issue_number()."""
        return self.tasks.get_tasks_by_parent_issue_number(*args, **kwargs)

    def get_pending_tasks(self, *args, **kwargs):
        """Delegate to tasks.get_pending_tasks()."""
        return self.tasks.get_pending_tasks(*args, **kwargs)

    def get_tasks_by_issue(self, *args, **kwargs):
        """Delegate to tasks.get_tasks_by_issue()."""
        return self.tasks.get_tasks_by_issue(*args, **kwargs)

    def add_task_dependency(self, *args, **kwargs):
        """Delegate to tasks.add_task_dependency()."""
        return self.tasks.add_task_dependency(*args, **kwargs)

    def get_task_dependencies(self, *args, **kwargs):
        """Delegate to tasks.get_task_dependencies()."""
        return self.tasks.get_task_dependencies(*args, **kwargs)

    def _row_to_task(self, *args, **kwargs):
        """Delegate to tasks._row_to_task()."""
        return self.tasks._row_to_task(*args, **kwargs)

    def get_dependent_tasks(self, *args, **kwargs):
        """Delegate to tasks.get_dependent_tasks()."""
        return self.tasks.get_dependent_tasks(*args, **kwargs)

    def remove_task_dependency(self, *args, **kwargs):
        """Delegate to tasks.remove_task_dependency()."""
        return self.tasks.remove_task_dependency(*args, **kwargs)

    def clear_all_task_dependencies(self, *args, **kwargs):
        """Delegate to tasks.clear_all_task_dependencies()."""
        return self.tasks.clear_all_task_dependencies(*args, **kwargs)

    def update_task_commit_sha(self, *args, **kwargs):
        """Delegate to tasks.update_task_commit_sha()."""
        return self.tasks.update_task_commit_sha(*args, **kwargs)

    def get_task_by_commit(self, *args, **kwargs):
        """Delegate to tasks.get_task_by_commit()."""
        return self.tasks.get_task_by_commit(*args, **kwargs)

    def get_recently_completed_tasks(self, *args, **kwargs):
        """Delegate to tasks.get_recently_completed_tasks()."""
        return self.tasks.get_recently_completed_tasks(*args, **kwargs)

    def get_tasks_by_agent(self, *args, **kwargs):
        """Delegate to tasks.get_tasks_by_agent()."""
        return self.tasks.get_tasks_by_agent(*args, **kwargs)

    async def get_tasks_by_agent_async(self, *args, **kwargs):
        """Delegate to tasks.get_tasks_by_agent_async()."""
        return await self.tasks.get_tasks_by_agent_async(*args, **kwargs)

    def create_agent(self, *args, **kwargs):
        """Delegate to agents.create_agent()."""
        return self.agents.create_agent(*args, **kwargs)

    def get_agent(self, *args, **kwargs):
        """Delegate to agents.get_agent()."""
        return self.agents.get_agent(*args, **kwargs)

    def update_agent(self, *args, **kwargs):
        """Delegate to agents.update_agent()."""
        return self.agents.update_agent(*args, **kwargs)

    def list_agents(self, *args, **kwargs):
        """Delegate to agents.list_agents()."""
        return self.agents.list_agents(*args, **kwargs)

    def assign_agent_to_project(self, *args, **kwargs):
        """Delegate to agents.assign_agent_to_project()."""
        return self.agents.assign_agent_to_project(*args, **kwargs)

    def get_agents_for_project(self, *args, **kwargs):
        """Delegate to agents.get_agents_for_project()."""
        return self.agents.get_agents_for_project(*args, **kwargs)

    def get_projects_for_agent(self, *args, **kwargs):
        """Delegate to agents.get_projects_for_agent()."""
        return self.agents.get_projects_for_agent(*args, **kwargs)

    def remove_agent_from_project(self, *args, **kwargs):
        """Delegate to agents.remove_agent_from_project()."""
        return self.agents.remove_agent_from_project(*args, **kwargs)

    def reassign_agent_role(self, *args, **kwargs):
        """Delegate to agents.reassign_agent_role()."""
        return self.agents.reassign_agent_role(*args, **kwargs)

    def get_agent_assignment(self, *args, **kwargs):
        """Delegate to agents.get_agent_assignment()."""
        return self.agents.get_agent_assignment(*args, **kwargs)

    def get_available_agents(self, *args, **kwargs):
        """Delegate to agents.get_available_agents()."""
        return self.agents.get_available_agents(*args, **kwargs)

    def create_blocker(self, *args, **kwargs):
        """Delegate to blockers.create_blocker()."""
        return self.blockers.create_blocker(*args, **kwargs)

    def get_blocker(self, *args, **kwargs):
        """Delegate to blockers.get_blocker()."""
        return self.blockers.get_blocker(*args, **kwargs)

    def resolve_blocker(self, *args, **kwargs):
        """Delegate to blockers.resolve_blocker()."""
        return self.blockers.resolve_blocker(*args, **kwargs)

    def list_blockers(self, *args, **kwargs):
        """Delegate to blockers.list_blockers()."""
        return self.blockers.list_blockers(*args, **kwargs)

    def get_pending_blocker(self, *args, **kwargs):
        """Delegate to blockers.get_pending_blocker()."""
        return self.blockers.get_pending_blocker(*args, **kwargs)

    def expire_stale_blockers(self, *args, **kwargs):
        """Delegate to blockers.expire_stale_blockers()."""
        return self.blockers.expire_stale_blockers(*args, **kwargs)

    def get_blocker_metrics(self, *args, **kwargs):
        """Delegate to blockers.get_blocker_metrics()."""
        return self.blockers.get_blocker_metrics(*args, **kwargs)

    def create_memory(self, *args, **kwargs):
        """Delegate to memories.create_memory()."""
        return self.memories.create_memory(*args, **kwargs)

    def upsert_memory(self, *args, **kwargs):
        """Delegate to memories.upsert_memory()."""
        return self.memories.upsert_memory(*args, **kwargs)

    def get_memory(self, *args, **kwargs):
        """Delegate to memories.get_memory()."""
        return self.memories.get_memory(*args, **kwargs)

    def get_project_memories(self, *args, **kwargs):
        """Delegate to memories.get_project_memories()."""
        return self.memories.get_project_memories(*args, **kwargs)

    def get_memories_by_category(self, *args, **kwargs):
        """Delegate to memories.get_memories_by_category()."""
        return self.memories.get_memories_by_category(*args, **kwargs)

    def get_conversation(self, *args, **kwargs):
        """Delegate to memories.get_conversation()."""
        return self.memories.get_conversation(*args, **kwargs)

    def create_context_item(self, *args, **kwargs):
        """Delegate to context_items.create_context_item()."""
        return self.context_items.create_context_item(*args, **kwargs)

    def get_context_item(self, *args, **kwargs):
        """Delegate to context_items.get_context_item()."""
        return self.context_items.get_context_item(*args, **kwargs)

    def list_context_items(self, *args, **kwargs):
        """Delegate to context_items.list_context_items()."""
        return self.context_items.list_context_items(*args, **kwargs)

    def update_context_item_tier(self, *args, **kwargs):
        """Delegate to context_items.update_context_item_tier()."""
        return self.context_items.update_context_item_tier(*args, **kwargs)

    def delete_context_item(self, *args, **kwargs):
        """Delegate to context_items.delete_context_item()."""
        return self.context_items.delete_context_item(*args, **kwargs)

    def update_context_item_access(self, *args, **kwargs):
        """Delegate to context_items.update_context_item_access()."""
        return self.context_items.update_context_item_access(*args, **kwargs)

    def archive_cold_items(self, *args, **kwargs):
        """Delegate to context_items.archive_cold_items()."""
        return self.context_items.archive_cold_items(*args, **kwargs)

    def create_checkpoint(self, *args, **kwargs):
        """Delegate to checkpoints.create_checkpoint()."""
        return self.checkpoints.create_checkpoint(*args, **kwargs)

    def list_checkpoints(self, *args, **kwargs):
        """Delegate to checkpoints.list_checkpoints()."""
        return self.checkpoints.list_checkpoints(*args, **kwargs)

    def get_checkpoint(self, *args, **kwargs):
        """Delegate to checkpoints.get_checkpoint()."""
        return self.checkpoints.get_checkpoint(*args, **kwargs)

    def save_checkpoint(self, *args, **kwargs):
        """Delegate to checkpoints.save_checkpoint()."""
        return self.checkpoints.save_checkpoint(*args, **kwargs)

    def get_checkpoints(self, *args, **kwargs):
        """Delegate to checkpoints.get_checkpoints()."""
        return self.checkpoints.get_checkpoints(*args, **kwargs)

    def get_checkpoint_by_id(self, *args, **kwargs):
        """Delegate to checkpoints.get_checkpoint_by_id()."""
        return self.checkpoints.get_checkpoint_by_id(*args, **kwargs)

    def delete_checkpoint(self, *args, **kwargs):
        """Delegate to checkpoints.delete_checkpoint()."""
        return self.checkpoints.delete_checkpoint(*args, **kwargs)

    def create_git_branch(self, *args, **kwargs):
        """Delegate to git_branches.create_git_branch()."""
        return self.git_branches.create_git_branch(*args, **kwargs)

    def get_branch_for_issue(self, *args, **kwargs):
        """Delegate to git_branches.get_branch_for_issue()."""
        return self.git_branches.get_branch_for_issue(*args, **kwargs)

    def mark_branch_merged(self, *args, **kwargs):
        """Delegate to git_branches.mark_branch_merged()."""
        return self.git_branches.mark_branch_merged(*args, **kwargs)

    def mark_branch_abandoned(self, *args, **kwargs):
        """Delegate to git_branches.mark_branch_abandoned()."""
        return self.git_branches.mark_branch_abandoned(*args, **kwargs)

    def get_branch_statistics(self, *args, **kwargs):
        """Delegate to git_branches.get_branch_statistics()."""
        return self.git_branches.get_branch_statistics(*args, **kwargs)

    def delete_git_branch(self, *args, **kwargs):
        """Delegate to git_branches.delete_git_branch()."""
        return self.git_branches.delete_git_branch(*args, **kwargs)

    def get_branches_by_status(self, *args, **kwargs):
        """Delegate to git_branches.get_branches_by_status()."""
        return self.git_branches.get_branches_by_status(*args, **kwargs)

    def get_all_branches_for_issue(self, *args, **kwargs):
        """Delegate to git_branches.get_all_branches_for_issue()."""
        return self.git_branches.get_all_branches_for_issue(*args, **kwargs)

    def count_branches_for_issue(self, *args, **kwargs):
        """Delegate to git_branches.count_branches_for_issue()."""
        return self.git_branches.count_branches_for_issue(*args, **kwargs)

    def get_branch_by_name_and_issues(self, *args, **kwargs):
        """Delegate to git_branches.get_branch_by_name_and_issues()."""
        return self.git_branches.get_branch_by_name_and_issues(*args, **kwargs)

    def create_test_result(self, *args, **kwargs):
        """Delegate to test_results.create_test_result()."""
        return self.test_results.create_test_result(*args, **kwargs)

    def get_test_results_by_task(self, *args, **kwargs):
        """Delegate to test_results.get_test_results_by_task()."""
        return self.test_results.get_test_results_by_task(*args, **kwargs)

    def create_lint_result(self, *args, **kwargs):
        """Delegate to lint_results.create_lint_result()."""
        return self.lint_results.create_lint_result(*args, **kwargs)

    def get_lint_results_for_task(self, *args, **kwargs):
        """Delegate to lint_results.get_lint_results_for_task()."""
        return self.lint_results.get_lint_results_for_task(*args, **kwargs)

    def get_lint_trend(self, *args, **kwargs):
        """Delegate to lint_results.get_lint_trend()."""
        return self.lint_results.get_lint_trend(*args, **kwargs)

    def save_code_review(self, *args, **kwargs):
        """Delegate to code_reviews.save_code_review()."""
        return self.code_reviews.save_code_review(*args, **kwargs)

    def get_code_reviews(self, *args, **kwargs):
        """Delegate to code_reviews.get_code_reviews()."""
        return self.code_reviews.get_code_reviews(*args, **kwargs)

    def get_code_reviews_by_severity(self, *args, **kwargs):
        """Delegate to code_reviews.get_code_reviews_by_severity()."""
        return self.code_reviews.get_code_reviews_by_severity(*args, **kwargs)

    def get_code_reviews_by_project(self, *args, **kwargs):
        """Delegate to code_reviews.get_code_reviews_by_project()."""
        return self.code_reviews.get_code_reviews_by_project(*args, **kwargs)

    def update_quality_gate_status(self, *args, **kwargs):
        """Delegate to quality_gates.update_quality_gate_status()."""
        return self.quality_gates.update_quality_gate_status(*args, **kwargs)

    def get_quality_gate_status(self, *args, **kwargs):
        """Delegate to quality_gates.get_quality_gate_status()."""
        return self.quality_gates.get_quality_gate_status(*args, **kwargs)

    def save_token_usage(self, *args, **kwargs):
        """Delegate to token_usage.save_token_usage()."""
        return self.token_usage.save_token_usage(*args, **kwargs)

    def get_token_usage(self, *args, **kwargs):
        """Delegate to token_usage.get_token_usage()."""
        return self.token_usage.get_token_usage(*args, **kwargs)

    def get_project_costs_aggregate(self, *args, **kwargs):
        """Delegate to token_usage.get_project_costs_aggregate()."""
        return self.token_usage.get_project_costs_aggregate(*args, **kwargs)

    def create_correction_attempt(self, *args, **kwargs):
        """Delegate to correction_attempts.create_correction_attempt()."""
        return self.correction_attempts.create_correction_attempt(*args, **kwargs)

    def get_correction_attempts_by_task(self, *args, **kwargs):
        """Delegate to correction_attempts.get_correction_attempts_by_task()."""
        return self.correction_attempts.get_correction_attempts_by_task(*args, **kwargs)

    def get_latest_correction_attempt(self, *args, **kwargs):
        """Delegate to correction_attempts.get_latest_correction_attempt()."""
        return self.correction_attempts.get_latest_correction_attempt(*args, **kwargs)

    def count_correction_attempts(self, *args, **kwargs):
        """Delegate to correction_attempts.count_correction_attempts()."""
        return self.correction_attempts.count_correction_attempts(*args, **kwargs)

    def get_recent_activity(self, *args, **kwargs):
        """Delegate to activities.get_recent_activity()."""
        return self.activities.get_recent_activity(*args, **kwargs)

    def get_prd(self, *args, **kwargs):
        """Delegate to activities.get_prd()."""
        return self.activities.get_prd(*args, **kwargs)

    def delete_prd(self, *args, **kwargs):
        """Delegate to activities.delete_prd()."""
        return self.activities.delete_prd(*args, **kwargs)

    def delete_discovery_answers(self, *args, **kwargs):
        """Delegate to activities.delete_discovery_answers()."""
        return self.activities.delete_discovery_answers(*args, **kwargs)

    def delete_project_tasks_and_issues(self, project_id: int) -> dict:
        """Delete all tasks and issues for a project atomically.

        Performs cascading delete in a single transaction:
        1. Deletes task dependencies, test results, correction attempts
        2. Deletes tasks (code_reviews and task_evidence cascade automatically)
        3. Deletes issues

        This method delegates to TaskRepository and IssueRepository for proper
        separation of concerns and handles all FK constraints correctly.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with counts: {"tasks": int, "issues": int}
        """
        with self._sync_lock:
            cursor = self.conn.cursor()

            try:
                # Count before deletion for return value
                cursor.execute(
                    "SELECT COUNT(*) FROM tasks WHERE project_id = ?",
                    (project_id,),
                )
                task_count = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM issues WHERE project_id = ?",
                    (project_id,),
                )
                issue_count = cursor.fetchone()[0]

                # Delete tasks first with all FK dependencies (single transaction)
                # Pass cursor to avoid intermediate commits
                self.tasks.delete_all_project_tasks(project_id, cursor=cursor)

                # Then delete issues
                self.issues.delete_all_project_issues(project_id, cursor=cursor)

                # Commit the entire operation atomically
                self.conn.commit()
                return {"tasks": task_count, "issues": issue_count}

            except Exception:
                self.conn.rollback()
                raise

    def create_audit_log(self, *args, **kwargs):
        """Delegate to audit_logs.create_audit_log()."""
        return self.audit_logs.create_audit_log(*args, **kwargs)

    async def cleanup_expired_sessions(self, *args, **kwargs):
        """Delegate to projects.cleanup_expired_sessions()."""
        return await self.projects.cleanup_expired_sessions(*args, **kwargs)

    # End of delegated methods
