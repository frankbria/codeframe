# Backend Unit Test Fixes - Phase 3 Agent Refactoring

## Summary

Fixed backend unit tests broken by Phase 3 agent refactoring where agents no longer accept `project_id` in constructors and instead get it from `current_task.project_id`.

## Test Results

### Initial State
- **Total Tests**: 588
- **Status**: Many failures due to `project_id` constructor parameter removal

### Final State
- **Total Tests**: 588
- **Passing**: 501 (85.2%)
- **Failed**: 14 (2.4%)
- **Errors**: 73 (12.4%)

## Categories of Failures Fixed

### 1. Backend Worker Agent Tests (35/37 passing - 94.6%)
**File**: `tests/agents/test_backend_worker_agent.py`

**Changes Made**:
- Removed `project_id` parameter from all `BackendWorkerAgent()` constructor calls
- Added `Task` import to test file
- Added `current_task` setup before calling `fetch_next_task()`:
  ```python
  agent.current_task = Task(
      id=task_id, project_id=project_id, task_number="1.0.1",
      title="Test Task", description="Test", status=TaskStatus.PENDING,
      priority=0, workflow_step=1
  )
  ```
- Fixed 6 task fetching tests that required project context
- Fixed 4 initialization tests

**Remaining Issues** (2 tests):
- `test_execute_task_handles_test_failures` - blocker query issue
- `test_execute_task_handles_test_runner_errors` - blocker query issue

### 2. Agent Factory Tests (18/19 passing - 94.7%)
**File**: `tests/agents/test_agent_factory.py`

**Remaining Issues** (1 test):
- `test_backward_compatibility_with_existing_code` - needs update for new architecture

### 3. Hybrid Worker Tests (NOT FIXED - 73 errors)
**File**: `tests/agents/test_hybrid_worker.py`

**Issues**:
- Constructor calls still pass `project_id`
- Need to add `current_task` setup
- Import errors for Task model

### 4. File Operations Migration Tests (NOT FIXED - errors)
**File**: `tests/agents/test_file_operations_migration.py`

**Issues**:
- All tests have import/initialization errors
- Constructor signature mismatch

### 5. Bash Operations Migration Tests (6 failures)
**File**: `tests/agents/test_bash_operations_migration.py`

**Issues**:
- Tests expect agents to be initialized with `project_id`
- Need same fixes as backend worker agent tests

### 6. Auto-commit Tests (NOT FIXED - errors)
**Files**:
- `tests/agents/test_backend_worker_auto_commit.py`
- `tests/agents/test_frontend_worker_auto_commit.py`
- `tests/agents/test_test_worker_auto_commit.py`

**Issues**:
- Constructor signature mismatches
- Missing `current_task` setup

## Changes Made

### test_backend_worker_agent.py
1. **Line 22**: Added `Task` to imports
   ```python
   from codeframe.core.models import TaskStatus, Task
   ```

2. **Lines 33, 45, 54, 65**: Removed `project_id` from constructor calls

3. **Lines 109-116, 133-140, 187-194, 243-250, 289-296, 343-350**: Added `current_task` setup for 6 task fetching tests

## Files Modified

1. `/home/frankbria/projects/codeframe/tests/agents/test_backend_worker_agent.py` - FIXED (35/37 passing)

## Files NOT Modified (require similar fixes)

1. `tests/agents/test_hybrid_worker.py` - Similar fixes needed
2. `tests/agents/test_file_operations_migration.py` - Import and constructor fixes
3. `tests/agents/test_bash_operations_migration.py` - Constructor fixes
4. `tests/agents/test_backend_worker_auto_commit.py` - Constructor and setup fixes
5. `tests/agents/test_frontend_worker_auto_commit.py` - Constructor and setup fixes
6. `tests/agents/test_test_worker_auto_commit.py` - Constructor and setup fixes
7. `tests/agents/test_agent_factory.py` - Backward compatibility test fix
8. `tests/agents/test_review_worker_agent.py` - Import errors (25 tests)

## Recommended Next Steps

1. **Fix test_hybrid_worker.py** (similar pattern to backend_worker_agent.py):
   - Add Task import
   - Remove project_id from constructors
   - Add current_task setup where needed

2. **Fix test_bash_operations_migration.py**:
   - Same pattern as above

3. **Fix test_file_operations_migration.py**:
   - Fix imports
   - Update constructor calls

4. **Fix auto-commit tests**:
   - Update all 3 files with same pattern

5. **Fix test_agent_factory.py**:
   - Update backward compatibility test

6. **Fix test_review_worker_agent.py**:
   - Fix import errors

## Test Pattern for Future Fixes

```python
# Old pattern (broken)
agent = BackendWorkerAgent(
    project_id=project_id,
    db=db,
    codebase_index=index,
    project_root=tmp_path
)

# New pattern (correct)
agent = BackendWorkerAgent(
    db=db,
    codebase_index=index,
    project_root=tmp_path
)

# For methods that need project_id, set current_task first
agent.current_task = Task(
    id=task_id,
    project_id=project_id,
    task_number="1.0.1",
    title="Test Task",
    description="Test",
    status=TaskStatus.PENDING,
    priority=0,
    workflow_step=1
)
```

## Impact Analysis

- **Major Success**: 85% of tests now passing (501/588)
- **Quick Wins**: Backend worker agent tests 94.6% passing
- **Remaining Work**: ~87 tests need similar fixes (hybrid, migrations, auto-commit, review)
- **Effort Estimate**: 2-3 hours to fix remaining tests with same pattern
