# Detailed Implementation Plan: T036 & T037 - LeadAgent SYNC/ASYNC Handling

**Date**: 2025-11-08
**Context**: Phase 6, User Story 4
**Dependencies**: T035 complete (blocker type validation in worker agents)

## Overview

Implement LeadAgent coordination logic to handle SYNC and ASYNC blockers differently:
- **SYNC blockers**: Pause dependent tasks by walking DAG, update to "paused" status with blocker_id
- **ASYNC blockers**: Deprioritize blocked task in scheduling queue

## Clarified Requirements (from /speckit.clarify session)

1. **SYNC Pause Scope**: Only tasks that directly or transitively depend on blocked task
2. **Task Status**: Update paused tasks to "paused" status (not "blocked")
3. **Blocker Relationship**: Add blocker_id field to task records (tasks → blocker)
4. **Resume Behavior**: Automatic resume via query by blocker_id, update to "pending"
5. **ASYNC Behavior**: Queue ASYNC-blocked tasks at lower priority

## Database Schema Changes

### Tasks Table
```sql
ALTER TABLE tasks ADD COLUMN blocker_id INTEGER DEFAULT NULL;
ALTER TABLE tasks ADD CONSTRAINT fk_tasks_blocker
  FOREIGN KEY (blocker_id) REFERENCES blockers(id) ON DELETE SET NULL;
```

**New Status Value**: "paused" (in addition to existing: pending, in_progress, completed, failed, blocked)

**Status Semantics**:
- `blocked`: Cannot start due to unsatisfied task dependencies
- `paused`: Was in progress but paused due to SYNC blocker waiting for user input

## T036: Add SYNC Blocker Dependency Handling to LeadAgent

### Implementation Steps

#### Step 1: Add blocker event monitoring to LeadAgent

**File**: `codeframe/agents/lead_agent.py`

```python
async def _monitor_blockers(self):
    """Monitor for new SYNC blockers and pause dependent tasks."""
    # Subscribe to blocker_created WebSocket events
    # OR poll database for new SYNC blockers
    # For each new SYNC blocker:
    #   - Get blocker.task_id
    #   - Call _pause_dependent_tasks(task_id, blocker_id)
```

#### Step 2: Implement dependent task pausing logic

**File**: `codeframe/agents/lead_agent.py`

```python
def _pause_dependent_tasks(self, blocked_task_id: int, blocker_id: int) -> List[int]:
    """
    Pause all tasks that depend on blocked task.

    Uses DependencyResolver to walk DAG and find transitive dependents.
    Updates task status to 'paused' and sets blocker_id.

    Args:
        blocked_task_id: The task that created the blocker
        blocker_id: The blocker causing the pause

    Returns:
        List of paused task IDs
    """
    # 1. Get all dependent task IDs from DependencyResolver
    dependent_ids = self.dependency_resolver.get_all_dependents(blocked_task_id)

    # 2. For each dependent task:
    #    - Skip if already completed or failed
    #    - Update status to 'paused'
    #    - Set blocker_id field
    #    - Update in database

    # 3. Return list of paused task IDs for logging

    # 4. Broadcast paused events via WebSocket (optional)
```

#### Step 3: Add DAG traversal to DependencyResolver

**File**: `codeframe/agents/dependency_resolver.py`

```python
def get_all_dependents(self, task_id: int) -> Set[int]:
    """
    Get all tasks that directly or transitively depend on task_id.

    Walks the reverse DAG (self.dependents) to find all reachable tasks.

    Args:
        task_id: Task to find dependents for

    Returns:
        Set of all dependent task IDs (empty if no dependents)
    """
    # Use BFS or DFS to traverse self.dependents
    # Return set of all discovered task IDs
```

#### Step 4: Implement blocker resolution monitoring

**File**: `codeframe/agents/lead_agent.py`

```python
async def _monitor_blocker_resolutions(self):
    """Monitor for blocker resolutions and resume paused tasks."""
    # Subscribe to blocker_resolved WebSocket events
    # OR poll database for resolved blockers
    # For each resolved blocker:
    #   - Get blocker.id
    #   - Call _resume_paused_tasks(blocker_id)
```

#### Step 5: Implement task resume logic

**File**: `codeframe/agents/lead_agent.py`

```python
def _resume_paused_tasks(self, blocker_id: int) -> List[int]:
    """
    Resume all tasks paused by this blocker.

    Queries tasks by blocker_id, updates status to 'pending', clears blocker_id.

    Args:
        blocker_id: The blocker that was resolved

    Returns:
        List of resumed task IDs
    """
    # 1. Query: SELECT id FROM tasks WHERE blocker_id = ?
    # 2. For each paused task:
    #    - Update status to 'pending'
    #    - Clear blocker_id (set to NULL)
    #    - Update in database

    # 3. Return list of resumed task IDs for logging

    # 4. Broadcast resumed events via WebSocket (optional)
```

### Testing Strategy for T036

**Unit Tests**:
1. Test `get_all_dependents()` with various DAG structures (linear, branching, diamond)
2. Test `_pause_dependent_tasks()` with mock database
3. Test `_resume_paused_tasks()` with mock database

**Integration Tests**:
1. Create task chain A→B→C, create SYNC blocker on B, verify B and C paused
2. Resolve blocker, verify B and C resume to pending
3. Verify independent task D continues execution during pause

## T037: Add ASYNC Blocker Handling to LeadAgent

### Implementation Steps

#### Step 1: Add priority field to task scheduling

**File**: `codeframe/agents/lead_agent.py`

Modify the task selection logic in `execute_project()` or equivalent method:

```python
def _get_next_task(self) -> Optional[Dict]:
    """
    Get next task to execute, considering blocker priority.

    Priority order:
    1. Ready tasks with no blockers
    2. Ready tasks with ASYNC blockers (deprioritized)
    3. No task available
    """
    # 1. Get ready tasks from DependencyResolver
    ready_ids = self.dependency_resolver.get_ready_tasks()

    # 2. Fetch task details from database for ready_ids
    # 3. Separate into two lists:
    #    - high_priority: tasks with no ASYNC blocker
    #    - low_priority: tasks with active ASYNC blocker

    # 4. Return first task from high_priority
    # 5. If high_priority empty, return first from low_priority
    # 6. If both empty, return None
```

#### Step 2: Add helper to check for ASYNC blockers

**File**: `codeframe/agents/lead_agent.py`

```python
def _has_async_blocker(self, task_id: int) -> bool:
    """
    Check if task has an active ASYNC blocker.

    Args:
        task_id: Task to check

    Returns:
        True if task has pending ASYNC blocker, False otherwise
    """
    # Query: SELECT COUNT(*) FROM blockers
    #        WHERE task_id = ? AND blocker_type = 'ASYNC' AND status = 'PENDING'
    # Return count > 0
```

### Testing Strategy for T037

**Unit Tests**:
1. Test `_has_async_blocker()` returns correct boolean
2. Test `_get_next_task()` prioritizes non-blocked tasks

**Integration Tests**:
1. Create tasks A (no blocker), B (ASYNC blocker), C (ready)
2. Verify A or C selected before B
3. Create only task B with ASYNC blocker, verify B still selected (not stuck)

## Implementation Order

**Recommended sequence**:

1. **Database migration** (add blocker_id to tasks table, add "paused" status)
2. **T036 Unit Tests** (RED phase - write failing tests for DAG traversal, pause/resume)
3. **T036 Implementation** (GREEN phase - implement SYNC blocker handling)
4. **T036 Integration Tests** (verify end-to-end SYNC behavior)
5. **T037 Unit Tests** (RED phase - write failing tests for priority queuing)
6. **T037 Implementation** (GREEN phase - implement ASYNC deprioritization)
7. **T037 Integration Tests** (verify ASYNC tasks still execute when no alternatives)
8. **Manual testing** with real LeadAgent execution

## Rollback Plan

If T036/T037 cause regressions:

1. **Database rollback**: ALTER TABLE tasks DROP COLUMN blocker_id
2. **Code rollback**: Remove blocker monitoring from LeadAgent execute loop
3. **Fallback behavior**: All blockers treated as informational only (no pause/deprioritize)

## Success Metrics

- SYNC blocker pauses 100% of dependent tasks (0 false negatives)
- SYNC blocker does NOT pause independent tasks (0 false positives)
- ASYNC blocker allows independent work to proceed
- Task resume happens automatically within 1 second of blocker resolution
- No performance degradation in task scheduling (< 10ms overhead per cycle)
