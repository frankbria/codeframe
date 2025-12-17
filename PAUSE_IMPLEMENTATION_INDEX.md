# Project.pause() Implementation Index

## Overview

This is the analysis for implementing `Project.pause()` functionality in CodeFRAME. The pause feature will gracefully pause project execution, trigger flash save for context archival, create a recovery checkpoint, and maintain full state for resumption.

## Documentation Structure

### 1. **PAUSE_ANALYSIS_SUMMARY.md** (Quick Start - 297 lines)

**Start here for a quick overview.** Contains:
- Key findings (synchronous vs async)
- Integration flow diagram
- Method signatures
- Critical file locations (line numbers)
- Database changes required
- Three-phase implementation roadmap
- Success criteria

**Best for**: Getting oriented, understanding the overall approach, finding which files to modify.

### 2. **PAUSE_IMPLEMENTATION_ANALYSIS.md** (Comprehensive Reference - 795 lines)

**Detailed technical reference.** Contains:
- 14 major sections with complete code examples
- Method signatures with full docstrings
- Error handling patterns
- Database schema details
- Migration file naming conventions
- Async/await patterns
- ContextManager integration guide
- CheckpointManager integration guide
- Testing patterns
- Summary table of all integration points
- Code location references with line numbers

**Best for**: Implementation details, copy-paste code patterns, understanding integration points.

### 3. **PAUSE_IMPLEMENTATION_INDEX.md** (This File)

Navigation guide for the analysis.

---

## Implementation Guide

### Phase 1: Database Schema

**Duration**: 1-2 hours

**Files to create**:
- [ ] `codeframe/persistence/migrations/migration_010_pause_functionality.py`

**Files to modify**:
- [ ] `codeframe/persistence/migrations/__init__.py`

**Key reference**:
- Section 4 in PAUSE_IMPLEMENTATION_ANALYSIS.md (Migration patterns)
- Section 5 in PAUSE_ANALYSIS_SUMMARY.md (Database changes)

### Phase 2: Core Implementation

**Duration**: 3-4 hours

**Files to modify**:
- [ ] `codeframe/core/project.py` (lines 198-202)

**Key reference**:
- Section 1 in PAUSE_IMPLEMENTATION_ANALYSIS.md (Method signatures)
- Section 2 in PAUSE_IMPLEMENTATION_ANALYSIS.md (Error handling)
- Section 6 in PAUSE_IMPLEMENTATION_ANALYSIS.md (ContextManager integration)
- Section 7 in PAUSE_IMPLEMENTATION_ANALYSIS.md (CheckpointManager integration)

**Implementation steps**:
1. Add imports: `ContextManager`, `CheckpointManager`
2. Validate prerequisites using `_get_validated_project_id()`
3. Trigger flash save for context archival
4. Create pause checkpoint
5. Update project status
6. Implement error handling with rollback

### Phase 3: API & WebSocket

**Duration**: 2-3 hours

**Files to create/modify**:
- [ ] `codeframe/ui/websocket_broadcasts.py` (add `broadcast_project_paused()`)
- [ ] Create FastAPI endpoint routes for pause

**Key reference**:
- Section 1.5 in PAUSE_IMPLEMENTATION_ANALYSIS.md (WebSocket broadcast pattern)
- Section 9 in PAUSE_IMPLEMENTATION_ANALYSIS.md (WebSocket broadcasting details)

---

## Key Technical Decisions

### Decision 1: Synchronous Method
- `Project.pause()` should be **synchronous** (not async)
- Matches `Project.start()` and `Project.resume()` patterns
- Database operations use synchronous SQLite
- WebSocket broadcasting happens in async API routes
- **Reference**: Section 5 in PAUSE_ANALYSIS_SUMMARY.md

### Decision 2: Flash Save Always Triggers
- Flash save should ALWAYS execute when pausing
- Archives COLD tier context items (importance_score < 0.4)
- Reduces token usage by 30-50%
- Creates separate checkpoint with context snapshot
- **Reference**: Section 6 in PAUSE_IMPLEMENTATION_ANALYSIS.md

### Decision 3: Checkpoint for State Recovery
- Create explicit checkpoint on pause
- Captures: git state, database state, context snapshot
- Enables complete rollback if needed
- Stores pause metadata (reason, timestamp)
- **Reference**: Section 7 in PAUSE_IMPLEMENTATION_ANALYSIS.md

### Decision 4: Error Handling with Rollback
- Save `previous_status` before changes
- Use try/except/except pattern (nested exception handling)
- Rollback database status on any error
- Don't fail pause if WebSocket broadcast fails
- **Reference**: Section 2 in PAUSE_IMPLEMENTATION_ANALYSIS.md

---

## Code Examples by Location

### Getting project_id (Section 8.1)
```python
project_config = self.config.load()
cursor = self.db.conn.cursor()
cursor.execute("SELECT id FROM projects WHERE name = ?", (project_config.project_name,))
row = cursor.fetchone()
if not row:
    raise ValueError("Project not found in database")
project_id = row["id"]
```
**Reference**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 8.1

### Triggering flash save (Section 6.1)
```python
from codeframe.lib.context_manager import ContextManager

context_mgr = ContextManager(db=self.db)
if context_mgr.should_flash_save(project_id, agent_id="orchestrator"):
    result = context_mgr.flash_save(project_id, agent_id="orchestrator")
```
**Reference**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 6.1

### Creating checkpoint (Section 7.1)
```python
from codeframe.lib.checkpoint_manager import CheckpointManager

checkpoint_mgr = CheckpointManager(
    db=self.db,
    project_root=self.project_dir,
    project_id=project_id
)
checkpoint = checkpoint_mgr.create_checkpoint(
    name="Project paused",
    description=f"Project paused: {reason}",
    trigger="pause"
)
```
**Reference**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 7.1

### Updating project status (Section 1.4)
```python
self.db.update_project(
    project_id,
    {"status": ProjectStatus.PAUSED.value}
)
```
**Reference**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 1.4

### Error handling pattern (Section 2.2)
```python
previous_status = self._status

try:
    # Perform operations
    self._status = ProjectStatus.PAUSED
    self.db.update_project(project_id, {"status": self._status.value})
except Exception as e:
    logger.error(f"Failed to pause: {e}", exc_info=True)
    try:
        self._status = previous_status
        if 'project_id' in locals():
            self.db.update_project(project_id, {"status": previous_status.value})
    except Exception as rollback_err:
        logger.error(f"Rollback failed: {rollback_err}")
    raise
```
**Reference**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 2.2

---

## File Locations

### Core Implementation File
- **File**: `codeframe/core/project.py`
- **Stub location**: Lines 198-202
- **Template (start)**: Lines 125-196
- **Template (resume)**: Lines 204-258

### Database Operations
- **File**: `codeframe/persistence/database.py`
- **update_project()**: Lines 1163-1195
- **get_project()**: Lines 602-607

### Context Management
- **File**: `codeframe/lib/context_manager.py`
- **flash_save()**: Lines 185-285
- **should_flash_save()**: Lines 148-183

### Checkpoint Management
- **File**: `codeframe/lib/checkpoint_manager.py`
- **create_checkpoint()**: Lines 54-134
- **_generate_metadata()**: Lines 347-425

### Data Models
- **File**: `codeframe/core/models.py`
- **ProjectStatus enum**: Lines 30-39

### WebSocket Broadcasting
- **File**: `codeframe/ui/websocket_broadcasts.py`
- **Similar functions**: Lines 36-602 (examples for broadcasting patterns)

### Shared State & Connection Manager
- **File**: `codeframe/ui/shared.py`
- **ConnectionManager**: Lines 17-45
- **SharedState**: Lines 48-115
- **start_agent() pattern**: Lines 117-217

### Migration Templates
- **Directory**: `codeframe/persistence/migrations/`
- **Example migration**: `migration_007_sprint10_review_polish.py`

---

## Testing Strategy

### Unit Tests (50+ tests)
- Pause with various project states
- Flash save integration
- Checkpoint creation
- Error scenarios
- Rollback on failure
- Pause metadata storage

**Reference**: Section 12 in PAUSE_IMPLEMENTATION_ANALYSIS.md

### Integration Tests (20+ tests)
- Full pause workflow end-to-end
- Flash save integration with real data
- Checkpoint restoration after pause
- WebSocket broadcasting
- Resume after pause

**Reference**: Section 12 in PAUSE_IMPLEMENTATION_ANALYSIS.md

### Test Coverage Target
- **>85% code coverage**
- **100% pass rate**
- **70+ total tests**

---

## Database Schema Changes

### Migration 010: Add Pause Support

```sql
-- Add pause metadata to projects table
ALTER TABLE projects ADD COLUMN pause_metadata JSON;

-- Add pause reason to checkpoints table
ALTER TABLE checkpoints ADD COLUMN pause_reason TEXT;
```

**Note**: No changes to existing tables needed. ProjectStatus enum already includes "paused".

**Reference**: Section 3 in PAUSE_ANALYSIS_SUMMARY.md

---

## Method Signature

```python
def pause(self, reason: Optional[str] = None) -> Dict[str, Any]:
    """Pause project execution.

    Creates a pause checkpoint, triggers flash save for context archival,
    and updates project status to PAUSED.

    Args:
        reason: Optional reason for pause
               (e.g., "user_request", "resource_limit", "manual")

    Returns:
        Dictionary with:
        - success: bool (always True if no exception)
        - checkpoint_id: int (created checkpoint ID)
        - tokens_before: int (context tokens before archive)
        - tokens_after: int (context tokens after archive)
        - reduction_percentage: float (% of tokens archived)
        - items_archived: int (number of COLD tier items archived)
        - paused_at: str (ISO 8601 timestamp)

    Raises:
        RuntimeError: If database not initialized or flash save fails
        ValueError: If project not found or invalid state
    """
```

---

## Return Value Example

```python
{
    "success": True,
    "checkpoint_id": 5,
    "tokens_before": 120000,
    "tokens_after": 45000,
    "reduction_percentage": 62.5,
    "items_archived": 150,
    "paused_at": "2025-11-23T14:30:00Z"
}
```

---

## Error Scenarios

| Scenario | Exception | Handling |
|----------|-----------|----------|
| DB not initialized | `RuntimeError` | User must call `Project.create()` first |
| Project not found | `ValueError` | Check project exists in database |
| Flash save fails | `RuntimeError` | Rollback status, log error, re-raise |
| Checkpoint fails | `RuntimeError` | Rollback status, log error, re-raise |
| Git operations fail | `RuntimeError` | Rollback status, log error, re-raise |

**Reference**: Section 14 in PAUSE_IMPLEMENTATION_ANALYSIS.md

---

## Integration Points Summary

| Component | Method | Returns | Location |
|-----------|--------|---------|----------|
| ContextManager | `flash_save()` | Dict with token stats | `lib/context_manager.py:185` |
| CheckpointManager | `create_checkpoint()` | Checkpoint object | `lib/checkpoint_manager.py:54` |
| Database | `update_project()` | int (rows affected) | `persistence/database.py:1163` |
| WebSocket | `broadcast_project_paused()` | None (async) | `ui/websocket_broadcasts.py` |
| Models | ProjectStatus | Enum | `core/models.py:30` |

---

## Implementation Checklist

### Phase 1: Database (1-2 hours)
- [ ] Create `migration_010_pause_functionality.py`
- [ ] Add `pause_metadata` column to projects
- [ ] Add `pause_reason` column to checkpoints
- [ ] Register migration in `__init__.py`
- [ ] Test migration with pytest

### Phase 2: Core (3-4 hours)
- [ ] Implement `Project.pause()` method
- [ ] Integrate `ContextManager.flash_save()`
- [ ] Integrate `CheckpointManager.create_checkpoint()`
- [ ] Implement error handling & rollback
- [ ] Add comprehensive logging (DEBUG/INFO/ERROR)
- [ ] Write 50+ unit tests
- [ ] Verify test coverage >85%

### Phase 3: API & WebSocket (2-3 hours)
- [ ] Add `broadcast_project_paused()` function
- [ ] Create FastAPI endpoint `POST /api/projects/{id}/pause`
- [ ] Create FastAPI endpoint `GET /api/projects/{id}/pause-status`
- [ ] Write 20+ integration tests
- [ ] Verify WebSocket broadcasts work
- [ ] Verify thread-safety

---

## Success Criteria

- ✅ All 70+ tests passing
- ✅ Code coverage >85%
- ✅ Project status updated to PAUSED
- ✅ Flash save triggered for context archival
- ✅ Pause checkpoint created with full state
- ✅ Error handling with automatic rollback
- ✅ Comprehensive logging at DEBUG/INFO/ERROR levels
- ✅ WebSocket broadcasting for pause events
- ✅ API endpoints working correctly
- ✅ Documentation updated

---

## Next Steps

1. **Start with PAUSE_ANALYSIS_SUMMARY.md** for orientation
2. **Refer to PAUSE_IMPLEMENTATION_ANALYSIS.md** for each implementation step
3. **Use code examples** from the sections referenced above
4. **Follow the 3-phase roadmap** for structured implementation
5. **Run tests continuously** during development

---

## Quick Reference Links

- **Migration file naming**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 4.1
- **Migration class structure**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 4.2
- **Method signature**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 1.1
- **Error handling**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 2
- **Database schema**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 3
- **WebSocket pattern**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 1.5
- **Testing strategy**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 12
- **Flash save workflow**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 6
- **Checkpoint workflow**: PAUSE_IMPLEMENTATION_ANALYSIS.md, Section 7

---

## Related Documentation

- **Resume implementation**: `codeframe/core/project.py:204-258`
- **Start implementation**: `codeframe/core/project.py:125-196`
- **Context Management system**: `CLAUDE.md` → "Context Management System (007-context-management)"
- **Checkpoint & Recovery**: `CLAUDE.md` → "Checkpoint & Recovery System"
- **Sprint 10 Review & Polish**: `CLAUDE.md` → "Sprint 10: Review & Polish"

---

**Version**: 1.0
**Created**: 2025-12-17
**Last Updated**: 2025-12-17
