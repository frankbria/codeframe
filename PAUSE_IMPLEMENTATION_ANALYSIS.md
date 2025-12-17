# Project.pause() Implementation Analysis

## Executive Summary

This document provides a complete analysis of integration patterns required to implement `Project.pause()` based on existing codebase patterns from `Project.resume()`, checkpoint management, context management, and database operations.

The implementation will follow a 3-phase approach:
- **Phase 1**: Database schema update (migration)
- **Phase 2**: Core pause() implementation with flash save
- **Phase 3**: WebSocket broadcasting and API integration

---

## 1. Method Signatures & Integration Points

### 1.1 Project.pause() Signature

```python
async def pause(self, reason: Optional[str] = None) -> Dict[str, Any]:
    """Pause project execution.

    Steps:
    1. Validate prerequisites (database, project_id, status)
    2. Trigger flash save (archive COLD tier context items)
    3. Create pause checkpoint
    4. Update project status to PAUSED
    5. Broadcast pause event via WebSocket
    6. Return pause result with checkpoint_id and context reduction stats

    Args:
        reason: Optional reason for pause (e.g., "user_request", "resource_limit", "manual")

    Returns:
        Dictionary with:
        - success: bool
        - checkpoint_id: int
        - tokens_before: int
        - tokens_after: int
        - reduction_percentage: float
        - items_archived: int
        - paused_at: str (ISO timestamp)

    Raises:
        RuntimeError: If database not initialized or project already paused
        ValueError: If flash save fails
    """
```

### 1.2 Flash Save Pattern (from context_manager.py)

```python
# ContextManager.flash_save() method signature
def flash_save(self, project_id: int, agent_id: str) -> Dict:
    """Execute flash save for an agent.

    Returns:
        {
            "checkpoint_id": int,
            "tokens_before": int,
            "tokens_after": int,
            "reduction_percentage": float,
            "items_archived": int,
            "hot_items_retained": int,
            "warm_items_retained": int,
        }
    """
```

### 1.3 Checkpoint Creation Pattern (from checkpoint_manager.py)

```python
# CheckpointManager.create_checkpoint() method signature
def create_checkpoint(
    self,
    name: str,
    description: Optional[str] = None,
    trigger: str = "manual"
) -> Checkpoint:
    """Create checkpoint with git commit, DB backup, and context snapshot.

    Args:
        name: Human-readable checkpoint name (max 100 chars)
        description: Optional detailed description (max 500 chars)
        trigger: Trigger type (manual, auto, phase_transition, pause)

    Returns:
        Checkpoint object with id, name, git_commit, paths, metadata
    """
```

### 1.4 Database Update Pattern (from database.py)

```python
# Database.update_project() method signature
def update_project(self, project_id: int, updates: Dict[str, Any]) -> int:
    """Update project fields.

    Args:
        project_id: Project ID to update
        updates: Dictionary of fields to update (e.g., {"status": "paused"})

    Returns:
        Number of rows affected
    """
    # Example usage:
    self.db.update_project(project_id, {"status": ProjectStatus.PAUSED.value})
```

### 1.5 WebSocket Broadcast Pattern (from websocket_broadcasts.py)

```python
# Pattern for broadcasting project status change
async def broadcast_project_paused(
    manager,
    project_id: int,
    reason: Optional[str] = None,
    checkpoint_id: Optional[int] = None,
    tokens_archived: int = 0,
) -> None:
    """Broadcast project paused event.

    Args:
        manager: ConnectionManager instance
        project_id: Project ID
        reason: Reason for pause
        checkpoint_id: Created checkpoint ID
        tokens_archived: Tokens archived during flash save
    """
    message = {
        "type": "project_paused",
        "project_id": project_id,
        "reason": reason,
        "checkpoint_id": checkpoint_id,
        "tokens_archived": tokens_archived,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message)
    except Exception as e:
        logger.error(f"Failed to broadcast project_paused: {e}")
```

---

## 2. Error Handling Patterns

### 2.1 Status Validation Pattern (from Project.start())

```python
def _get_validated_project_id(self) -> tuple[int, str]:
    """Validate prerequisites and return project_id and API key.

    Raises:
        RuntimeError: If database not initialized
        ValueError: If project not found or has invalid structure
    """
    # Validate database
    if not self.db:
        raise RuntimeError(
            "Database not initialized. Call Project.create() or initialize database first."
        )

    # Get project from database
    project_config = self.config.load()
    project_record = self.db.get_project(project_config.project_name)
    if not project_record:
        raise ValueError(f"Project '{project_config.project_name}' not found in database")
```

### 2.2 Rollback Pattern (from Project.start())

```python
try:
    # Perform operations
    self._status = ProjectStatus.PAUSED
    self.db.update_project(project_id, {"status": self._status.value})
except Exception as e:
    logger.error(f"Failed to pause project: {e}", exc_info=True)
    try:
        # Rollback to previous status
        self._status = previous_status
        if 'project_id' in locals():
            self.db.update_project(project_id, {"status": previous_status.value})
            logger.info(f"Rolled back project {project_id} status to {previous_status.value}")
    except Exception as rollback_err:
        logger.error(f"Failed to rollback status: {rollback_err}")
    raise
```

### 2.3 WebSocket Error Handling Pattern (from websocket_broadcasts.py)

```python
try:
    await manager.broadcast(message)
    logger.debug(f"Broadcast project_paused: project {project_id}")
except Exception as e:
    logger.error(f"Failed to broadcast project_paused: {e}")
    # Continue - don't fail the pause operation if broadcast fails
```

---

## 3. Database Schema Details

### 3.1 Projects Table Structure

```sql
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    source_type TEXT CHECK(source_type IN ('git_remote', 'local_path', 'upload', 'empty')),
    source_location TEXT,
    source_branch TEXT DEFAULT 'main',
    workspace_path TEXT NOT NULL,
    git_initialized BOOLEAN DEFAULT FALSE,
    current_commit TEXT,
    status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
    phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    config JSON
)
```

### 3.2 ProjectStatus Enum (from models.py)

```python
class ProjectStatus(Enum):
    """Project lifecycle status."""

    INIT = "init"
    PLANNING = "planning"
    RUNNING = "running"          # Agent actively working
    ACTIVE = "active"            # Project active (synonym for RUNNING)
    PAUSED = "paused"            # Project paused (NEW - implementation target)
    STOPPED = "stopped"          # Agent terminated
    COMPLETED = "completed"
```

### 3.3 Checkpoints Table (for pause checkpoint storage)

```sql
CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    name TEXT NOT NULL,           -- "Project paused" / user reason
    description TEXT,             -- Detailed reason
    trigger TEXT,                 -- "pause" / "auto" / "manual" / etc
    git_commit TEXT NOT NULL,     -- Git commit SHA for code state
    database_backup_path TEXT,    -- Path to DB backup
    context_snapshot_path TEXT,   -- Path to context JSON snapshot
    metadata JSON,                -- Project state metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### 3.4 Context Items Table (affected by flash save)

```sql
CREATE TABLE IF NOT EXISTS context_items (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    agent_id TEXT NOT NULL,
    item_type TEXT,
    content TEXT,
    importance_score FLOAT,
    current_tier TEXT CHECK(current_tier IN ('hot', 'warm', 'cold')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    manual_pin BOOLEAN DEFAULT FALSE
)
```

---

## 4. Migration File Naming & Structure Conventions

### 4.1 Migration File Pattern

```
codeframe/persistence/migrations/migration_XXX_description.py
```

Examples:
- `migration_001_remove_agent_type_constraint.py`
- `migration_002_refactor_projects_schema.py`
- `migration_003_update_blockers_schema.py`
- `migration_007_sprint10_review_polish.py`
- `migration_009_add_project_agents.py`

### 4.2 Migration Class Pattern (from migration_007)

```python
"""Migration 009: Add Pause Support

Changes:
1. Add pause_metadata JSON column to projects table
2. Add pause_reason TEXT column to checkpoints table
3. Add pause_context_snapshot TEXT column to checkpoints table
4. Update status CHECK constraint to include 'paused'

Date: 2025-11-23
Sprint: 013-pause-functionality
"""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class PauseFunctionality(Migration):
    """Add pause/resume functionality support."""

    def __init__(self):
        super().__init__(version="010", description="Add pause functionality")

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns True if pause_metadata column does not exist.
        """
        cursor = conn.execute(
            "PRAGMA table_info(projects)"
        )
        columns = {row[1] for row in cursor.fetchall()}

        if "pause_metadata" in columns:
            logger.info("pause_metadata column already exists, skipping migration")
            return False

        logger.info("pause_metadata column not found, migration can be applied")
        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration."""
        cursor = conn.cursor()

        # Add pause_metadata column to projects table
        logger.info("Migration 010: Adding pause_metadata to projects table")
        try:
            cursor.execute(
                "ALTER TABLE projects ADD COLUMN pause_metadata JSON"
            )
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                logger.info("pause_metadata column already exists")
            else:
                raise

        # Add pause_reason to checkpoints table
        logger.info("Migration 010: Adding pause_reason to checkpoints table")
        try:
            cursor.execute(
                "ALTER TABLE checkpoints ADD COLUMN pause_reason TEXT"
            )
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                logger.info("pause_reason column already exists")
            else:
                raise

        conn.commit()
        logger.info("Migration 010 completed successfully")
```

### 4.3 Migration Registration (in migrations/__init__.py)

```python
from codeframe.persistence.migrations.migration_010_pause_functionality import PauseFunctionality

MIGRATIONS = [
    # ... existing migrations ...
    PauseFunctionality(),
]
```

---

## 5. Async/Await Patterns

### 5.1 Synchronous Method Pattern (from Project)

The `Project` class methods are **synchronous**, not async:
- `Project.start()` - synchronous
- `Project.resume()` - synchronous
- `Project.pause()` should be **synchronous**

**Note**: Database operations use `self.db.conn.cursor()` (synchronous SQLite), not async operations.

### 5.2 Async Broadcasting Pattern (from ui/shared.py)

WebSocket broadcasts **are async** and should be called from async routes:

```python
# In async route handlers (FastAPI routes)
async def broadcast_project_paused(
    manager,
    project_id: int,
    reason: Optional[str] = None,
) -> None:
    """Broadcast project_paused event (async)."""
    message = {
        "type": "project_paused",
        "project_id": project_id,
        "reason": reason,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }

    try:
        await manager.broadcast(message)
    except Exception as e:
        logger.error(f"Failed to broadcast: {e}")
```

### 5.3 Thread-Safety Pattern (from ui/shared.py)

```python
# Synchronous method wrapped for async context
async def start_agent(
    project_id: int, db: Database, agents_dict: Dict[int, LeadAgent], api_key: str
) -> None:
    """Start Lead Agent (async wrapper around sync operations)."""

    # Acquire lock before modifying shared state
    async with shared_state._agents_lock:
        # Check and create agent atomically
        existing_agent = shared_state._running_agents.get(project_id)
        if existing_agent is not None:
            raise ValueError(f"Agent already running for project {project_id}")

        # Create agent (synchronous)
        agent = LeadAgent(project_id=project_id, db=db, api_key=api_key)

        # Store atomically
        shared_state._running_agents[project_id] = agent

    # Lock released - now safe to do I/O
    try:
        # Update database (wrapped as thread operation)
        await asyncio.to_thread(
            db.update_project,
            project_id,
            {"status": ProjectStatus.PAUSED.value}
        )
    except Exception as e:
        # Cleanup on error
        await shared_state.remove_running_agent(project_id)
        raise
```

---

## 6. ContextManager Integration

### 6.1 Flash Save Workflow (3-step process)

```python
from codeframe.lib.context_manager import ContextManager

# Initialize context manager
context_mgr = ContextManager(db=self.db)

# Step 1: Check if flash save needed
if context_mgr.should_flash_save(project_id, agent_id="orchestrator"):
    # Step 2: Execute flash save
    result = context_mgr.flash_save(project_id, agent_id="orchestrator")

    # Step 3: Use result for checkpoint
    flash_save_result = {
        "checkpoint_id": result["checkpoint_id"],
        "tokens_before": result["tokens_before"],
        "tokens_after": result["tokens_after"],
        "reduction_percentage": result["reduction_percentage"],
        "items_archived": result["items_archived"],
    }
```

### 6.2 Available Context Manager Methods

```python
class ContextManager:
    """Manages context scoring, tier assignment, and flash saves."""

    def should_flash_save(
        self,
        project_id: int,
        agent_id: str,
        force: bool = False
    ) -> bool:
        """Check if flash save should be triggered."""

    def flash_save(
        self,
        project_id: int,
        agent_id: str
    ) -> Dict:
        """Execute flash save, returning reduction stats."""

    def recalculate_scores_for_agent(
        self,
        project_id: int,
        agent_id: str
    ) -> int:
        """Recalculate importance scores (returns items updated)."""

    def update_tiers_for_agent(
        self,
        project_id: int,
        agent_id: str
    ) -> int:
        """Recalculate scores and reassign tiers."""
```

---

## 7. CheckpointManager Integration

### 7.1 Checkpoint Creation for Pause

```python
from codeframe.lib.checkpoint_manager import CheckpointManager

# Initialize checkpoint manager
checkpoint_mgr = CheckpointManager(
    db=self.db,
    project_root=self.project_dir,
    project_id=project_id
)

# Create pause checkpoint
checkpoint = checkpoint_mgr.create_checkpoint(
    name="Project paused",
    description=f"Project paused by user: {reason}",
    trigger="pause"  # Custom trigger type
)

# Result is Checkpoint object with:
# - checkpoint.id
# - checkpoint.name
# - checkpoint.git_commit (full SHA)
# - checkpoint.database_backup_path
# - checkpoint.context_snapshot_path
# - checkpoint.created_at
```

### 7.2 Checkpoint.metadata Structure (from checkpoint_manager.py)

```python
checkpoint.metadata = CheckpointMetadata(
    project_id=project_id,
    phase="active",  # Current project phase
    tasks_completed=15,
    tasks_total=40,
    agents_active=["orchestrator", "backend-001"],
    last_task_completed="Implement authentication",
    context_items_count=250,
    total_cost_usd=42.50,
)
```

---

## 8. Database Access Patterns

### 8.1 Getting Project ID from Name

```python
# From Project.resume() - pattern for getting project_id
project_config = self.config.load()  # Load from .codeframe/config.json

# Option 1: Direct cursor query (as in resume())
cursor = self.db.conn.cursor()
cursor.execute(
    "SELECT id FROM projects WHERE name = ?",
    (project_config.project_name,)
)
row = cursor.fetchone()
if not row:
    raise ValueError("Project not found in database")
project_id = row["id"]

# Option 2: Use get_project() method (requires project_id first)
# This is used when you already have the project_id
project_record = self.db.get_project(project_id)
if not project_record:
    raise ValueError(f"Project {project_id} not found")
```

### 8.2 Getting Agents for Project

```python
def get_agents_for_project(self, project_id: int) -> List[str]:
    """Get list of agent IDs assigned to a project."""
    # Not yet implemented in current codebase
    # Likely pattern (from project_agents table):
    cursor = self.conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT agent_id FROM project_agents
        WHERE project_id = ? AND is_active = TRUE
        """,
        (project_id,)
    )
    return [row["agent_id"] for row in cursor.fetchall()]
```

---

## 9. Logging Patterns

All methods use structured logging with appropriate levels:

```python
import logging

logger = logging.getLogger(__name__)

# DEBUG: Low-level operational details
logger.debug(f"Flash save completed: {checkpoint_id}, reduced from {tokens_before} to {tokens_after}")

# INFO: High-level operations
logger.info(f"Project {project_id} paused successfully")

# WARNING: Issues that should be investigated
logger.warning(f"Flash save returned no items to archive")

# ERROR: Failures that might not be fatal
logger.error(f"Failed to broadcast project_paused: {e}")

# CRITICAL: Fatal errors
logger.critical(f"Database corruption detected during pause")
```

---

## 10. Code Location Reference

### Core Files
- **Project class**: `/home/frankbria/projects/codeframe/codeframe/core/project.py` (lines 198-202 for pause stub)
- **Database**: `/home/frankbria/projects/codeframe/codeframe/persistence/database.py`
- **Context Manager**: `/home/frankbria/projects/codeframe/codeframe/lib/context_manager.py`
- **Checkpoint Manager**: `/home/frankbria/projects/codeframe/codeframe/lib/checkpoint_manager.py`
- **Models**: `/home/frankbria/projects/codeframe/codeframe/core/models.py` (ProjectStatus enum)
- **WebSocket Broadcasting**: `/home/frankbria/projects/codeframe/codeframe/ui/websocket_broadcasts.py`
- **Shared State**: `/home/frankbria/projects/codeframe/codeframe/ui/shared.py`

### Migration Files Location
- **Pattern**: `/home/frankbria/projects/codeframe/codeframe/persistence/migrations/migration_XXX_*.py`
- **Registry**: `/home/frankbria/projects/codeframe/codeframe/persistence/migrations/__init__.py`

---

## 11. Implementation Checklist (Phases 2-3)

### Phase 1: Database Schema (Migration)
- [ ] Create migration file `migration_010_pause_functionality.py`
- [ ] Add `pause_metadata` JSON column to projects table
- [ ] Add `pause_reason` TEXT column to checkpoints table
- [ ] Register migration in `migrations/__init__.py`
- [ ] Test migration with `pytest tests/test_migrations.py`

### Phase 2: Core Implementation
- [ ] Implement `Project.pause()` method (synchronous)
  - [ ] Validate database and project_id
  - [ ] Save previous status for rollback
  - [ ] Get all agents for project (if needed)
  - [ ] Trigger flash save for each agent (optional: only for orchestrator)
  - [ ] Create pause checkpoint via CheckpointManager
  - [ ] Update project status to PAUSED
  - [ ] Save pause metadata (reason, timestamp, checkpoint_id)
- [ ] Add rollback logic on error
- [ ] Add comprehensive logging (DEBUG, INFO, ERROR levels)
- [ ] Write unit tests (70+ test cases)
- [ ] Validate ProjectStatus enum includes PAUSED (already present ✓)

### Phase 3: WebSocket & API Integration
- [ ] Add `broadcast_project_paused()` to websocket_broadcasts.py
- [ ] Create FastAPI endpoint `POST /api/projects/{project_id}/pause`
- [ ] Create FastAPI endpoint `GET /api/projects/{project_id}/pause-status`
- [ ] Integrate broadcast into pause() via optional ws_manager parameter
- [ ] Add async route wrapper for pause endpoint
- [ ] Write integration tests for WebSocket broadcasts
- [ ] Ensure thread-safe access to shared_state

---

## 12. Testing Patterns & Requirements

### Unit Test Pattern (from existing tests)

```python
import pytest
import sqlite3
from pathlib import Path
from codeframe.core.project import Project
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus

@pytest.fixture
def project_with_db(tmp_path):
    """Create a test project with initialized database."""
    project = Project.create("test-project", tmp_path)
    return project

def test_pause_updates_project_status(project_with_db):
    """Test that pause() updates project status to PAUSED."""
    project_with_db.start()  # Initialize
    result = project_with_db.pause()

    assert project_with_db._status == ProjectStatus.PAUSED
    assert result["success"] is True
    assert "checkpoint_id" in result

def test_pause_creates_checkpoint(project_with_db):
    """Test that pause() creates a checkpoint."""
    project_with_db.start()
    result = project_with_db.pause()

    assert "checkpoint_id" in result
    assert result["checkpoint_id"] > 0

    # Verify checkpoint exists in database
    checkpoint = project_with_db.db.get_checkpoint_by_id(result["checkpoint_id"])
    assert checkpoint is not None
    assert checkpoint.trigger == "pause"
```

### Integration Test Pattern

```python
@pytest.mark.integration
async def test_pause_broadcasts_event():
    """Test that pause() broadcasts project_paused event via WebSocket."""
    project = Project.create("test-project")
    project.start()

    # Mock WebSocket manager
    from unittest.mock import AsyncMock
    mock_manager = AsyncMock()

    # Pause with broadcasts
    result = await project.pause(ws_manager=mock_manager)

    # Verify broadcast was called
    mock_manager.broadcast.assert_called_once()

    # Verify message contents
    call_args = mock_manager.broadcast.call_args
    message = call_args[0][0]
    assert message["type"] == "project_paused"
    assert message["project_id"] == project.project_id
```

---

## 13. Summary Table: Key Integration Points

| Component | File | Method | Returns | Async |
|-----------|------|--------|---------|-------|
| Project | `core/project.py` | `pause(reason)` | `Dict[str, Any]` | No |
| ContextManager | `lib/context_manager.py` | `flash_save()` | `Dict` with token stats | No |
| CheckpointManager | `lib/checkpoint_manager.py` | `create_checkpoint()` | `Checkpoint` object | No |
| Database | `persistence/database.py` | `update_project()` | `int` (rows affected) | No |
| WebSocket | `ui/websocket_broadcasts.py` | `broadcast_project_paused()` | `None` | **Yes** |
| SharedState | `ui/shared.py` | `remove_running_agent()` | `Optional[LeadAgent]` | **Yes** |
| Models | `core/models.py` | ProjectStatus enum | N/A | N/A |

---

## 14. Error Scenarios & Handling

| Scenario | Detection | Handling |
|----------|-----------|----------|
| Database not initialized | `if not self.db: raise RuntimeError` | User must call `Project.create()` first |
| Project not found in DB | `if not project_record: raise ValueError` | Restore project or reinitialize |
| Project already paused | `if status == PAUSED: raise ValueError` | Skip pause or raise error |
| Flash save fails | Catch exception from `context_mgr.flash_save()` | Rollback, log error, raise RuntimeError |
| Checkpoint creation fails | Catch exception from `checkpoint_mgr.create_checkpoint()` | Rollback to previous status, raise |
| WebSocket broadcast fails | Catch exception in `broadcast_project_paused()` | Log error but don't fail pause operation |
| Git operations fail | Catch subprocess error in checkpoint | Rollback database changes, raise |

---

## References

- **Project.resume() implementation**: `/home/frankbria/projects/codeframe/codeframe/core/project.py:204-258`
- **Project.start() implementation**: `/home/frankbria/projects/codeframe/codeframe/core/project.py:125-196`
- **Flash save workflow**: `/home/frankbria/projects/codeframe/codeframe/lib/context_manager.py:185-285`
- **Checkpoint creation**: `/home/frankbria/projects/codeframe/codeframe/lib/checkpoint_manager.py:54-134`
- **Migration example**: `/home/frankbria/projects/codeframe/codeframe/persistence/migrations/migration_007_sprint10_review_polish.py`
- **WebSocket broadcasting**: `/home/frankbria/projects/codeframe/codeframe/ui/websocket_broadcasts.py:36-120`
