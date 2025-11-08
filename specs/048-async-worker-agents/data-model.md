# Data Model: Async Worker Agents

**Branch**: `048-async-worker-agents` | **Date**: 2025-11-07
**Phase**: Phase 1 (Design & Contracts)

---

## Overview

This refactoring does **not introduce new data models or database schemas**. It modifies the internal implementation of existing worker agent classes to use async/await patterns. This document describes the affected classes and their state management.

---

## Affected Classes

### 1. BackendWorkerAgent

**Location**: `codeframe/agents/backend_worker_agent.py`

**Class Signature**:
```python
class BackendWorkerAgent:
    """Autonomous agent that executes backend development tasks."""
```

**State (Instance Variables)**:
```python
def __init__(
    self,
    project_id: int,
    db: Database,
    codebase_index: CodebaseIndex,
    provider: str = "claude",
    api_key: Optional[str] = None,
    project_root: Path = Path("."),
    ws_manager = None
):
    self.project_id: int
    self.db: Database
    self.codebase_index: CodebaseIndex
    self.provider: str
    self.api_key: Optional[str]
    self.project_root: Path
    self.ws_manager: Optional[ConnectionManager]
```

**Key Methods (Converting to Async)**:
- `async def execute_task(task: Dict[str, Any]) -> Dict[str, Any]`
- `async def generate_code(context: Dict[str, Any]) -> Dict[str, Any]`
- `async def _run_and_record_tests(task_id: int) -> None`
- `async def _self_correction_loop(task: Dict, test_result_id: int) -> bool`
- `async def _attempt_self_correction(task: Dict, test_result_id: int, attempt: int) -> Dict`

**Methods Remaining Sync** (fast operations):
- `fetch_next_task() -> Optional[Dict]` (sync DB query)
- `build_context(task: Dict) -> Dict` (in-memory operations)
- `apply_file_changes(files: List[Dict]) -> List[str]` (local file I/O)
- `update_task_status(task_id, status, output) -> None` (sync DB update)

**Method Removed**:
- ~~`_broadcast_async(broadcast_func, *args, **kwargs)`~~ - Replaced with direct `await` calls

---

### 2. FrontendWorkerAgent

**Location**: `codeframe/agents/frontend_worker_agent.py`

**Class Signature**:
```python
class FrontendWorkerAgent:
    """Autonomous agent that executes frontend development tasks."""
```

**State** (similar to BackendWorkerAgent):
```python
def __init__(
    self,
    project_id: int,
    db: Database,
    codebase_index: CodebaseIndex,
    api_key: Optional[str] = None,
    project_root: Path = Path("."),
    ws_manager = None
):
    self.project_id: int
    self.db: Database
    self.codebase_index: CodebaseIndex
    self.api_key: Optional[str]
    self.project_root: Path
    self.ws_manager: Optional[ConnectionManager]
```

**Key Methods (Converting to Async)**:
- `async def execute_task(task: Dict[str, Any]) -> Dict[str, Any]`
- `async def generate_code(context: Dict[str, Any]) -> Dict[str, Any]`
- Other helper methods as needed

---

### 3. TestWorkerAgent

**Location**: `codeframe/agents/test_worker_agent.py`

**Class Signature**:
```python
class TestWorkerAgent:
    """Autonomous agent that executes testing tasks."""
```

**State** (similar pattern):
```python
def __init__(
    self,
    project_id: int,
    db: Database,
    codebase_index: CodebaseIndex,
    api_key: Optional[str] = None,
    project_root: Path = Path("."),
    ws_manager = None
):
    self.project_id: int
    self.db: Database
    self.codebase_index: CodebaseIndex
    self.api_key: Optional[str]
    self.project_root: Path
    self.ws_manager: Optional[ConnectionManager]
```

**Key Methods (Converting to Async)**:
- `async def execute_task(task: Dict[str, Any]) -> Dict[str, Any]`
- `async def generate_code(context: Dict[str, Any]) -> Dict[str, Any]`
- Other helper methods as needed

---

### 4. LeadAgent (Integration Point)

**Location**: `codeframe/agents/lead_agent.py`

**Affected Method**:
```python
async def _assign_and_execute_task(
    self,
    task: Task,
    retry_counts: Dict[int, int]
) -> bool:
    """Assign task to appropriate agent and execute it."""
```

**Change**:
```python
# Before:
await loop.run_in_executor(
    None,
    agent_instance.execute_task,
    task_dict
)

# After:
await agent_instance.execute_task(task_dict)
```

**No State Changes**: LeadAgent's state remains unchanged

---

## Anthropic Client Changes

### Before (Sync Client)
```python
import anthropic

client = anthropic.Anthropic(api_key=self.api_key)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=system_prompt,
    messages=[{"role": "user", "content": user_prompt}]
)
```

### After (Async Client)
```python
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=self.api_key)

response = await client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=system_prompt,
    messages=[{"role": "user", "content": user_prompt}]
)
```

**Note**: Client instantiation becomes a class variable to avoid recreating on each call.

---

## Broadcast Pattern Changes

### Before (Wrapper Pattern - Problematic)
```python
def _broadcast_async(self, broadcast_func, *args, **kwargs) -> None:
    """Helper to broadcast WebSocket messages (handles async event loop safely)."""
    if not self.ws_manager:
        return

    try:
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(
            broadcast_func(*args, **kwargs),
            loop
        )
    except RuntimeError:
        logger.debug(f"Skipped broadcast (no event loop): {broadcast_func.__name__}")

# Usage:
self._broadcast_async(
    broadcast_task_status,
    self.ws_manager,
    self.project_id,
    task_id,
    status
)
```

### After (Direct Await - Correct)
```python
# Usage (in async method):
if self.ws_manager:
    try:
        from codeframe.ui.websocket_broadcasts import broadcast_task_status
        await broadcast_task_status(
            self.ws_manager,
            self.project_id,
            task_id,
            status,
            agent_id="backend-worker"
        )
    except Exception as e:
        logger.debug(f"Failed to broadcast task status: {e}")
```

**Benefits**:
- No event loop detection issues
- Simpler code
- Proper error handling
- No silent failures

---

## Error Handling Patterns

### Task Cancellation
```python
async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # Task execution logic
        ...
    except asyncio.CancelledError:
        logger.info(f"Task {task['id']} cancelled")
        self.update_task_status(task["id"], TaskStatus.CANCELLED.value)
        raise  # Re-raise to propagate cancellation
    except Exception as e:
        logger.error(f"Task {task['id']} failed: {e}")
        self.update_task_status(task["id"], TaskStatus.FAILED.value, str(e))
        return {"status": "failed", "error": str(e)}
```

### Broadcast Errors (Non-Critical)
```python
try:
    await broadcast_task_status(...)
except Exception as e:
    logger.warning(f"Broadcast failed (non-critical): {e}")
    # Continue execution - broadcasts should not block task execution
```

### Timeout Handling
```python
try:
    async with asyncio.timeout(300):  # 5 minute timeout
        result = await self.generate_code(context)
except asyncio.TimeoutError:
    logger.error(f"Code generation timed out for task {task_id}")
    return {"status": "failed", "error": "Timeout"}
```

---

## State Transitions

### Task Execution Flow (Unchanged Conceptually, Now Async)

```
                    ┌─────────────┐
                    │   PENDING   │
                    └──────┬──────┘
                           │
                           │ fetch_next_task()
                           │
                    ┌──────▼──────┐
                    │ IN_PROGRESS │
                    └──────┬──────┘
                           │
                ┌──────────┴──────────┐
                │                     │
         Tests Pass              Tests Fail
                │                     │
        ┌───────▼────────┐   ┌────────▼────────┐
        │   COMPLETED    │   │ SELF-CORRECTION │
        └────────────────┘   │  (max 3 attempts)│
                             └────────┬─────────┘
                                      │
                              ┌───────┴────────┐
                              │                │
                       Tests Pass      All Attempts Fail
                              │                │
                      ┌───────▼────┐   ┌───────▼────┐
                      │ COMPLETED  │   │  BLOCKED   │
                      └────────────┘   └────────────┘
```

**Key Point**: State transitions remain the same, only the execution mechanism changes from sync+threads to async/await.

---

## Validation Rules

### Unchanged
- Path validation (no absolute paths, no traversal)
- Task status transitions
- API key validation
- Database constraints

### New Async Validation
- Ensure `await` used for all async calls
- Proper exception handling for `asyncio.CancelledError`
- Timeout enforcement for long-running operations

---

## Database Schema

**No Changes**: This refactoring does not modify any database tables, columns, or constraints.

**Tables Referenced** (read-only for this feature):
- `tasks` (read/write task status)
- `projects` (read project info)
- `test_results` (write test outcomes)
- `correction_attempts` (write self-correction data)
- `blockers` (write blocker info)

---

## Type Definitions

### Task Dictionary Structure (Unchanged)
```python
TaskDict = {
    "id": int,
    "project_id": int,
    "issue_id": int,
    "task_number": str,
    "title": str,
    "description": str,
    "status": str,  # "pending", "in_progress", "completed", "failed", "blocked"
    "assigned_to": str,
    "depends_on": str,
    "can_parallelize": bool,
    "priority": int,
    "workflow_step": int,
    "requires_mcp": bool,
    "estimated_tokens": int,
    "actual_tokens": int,
    "created_at": str,
    "completed_at": Optional[str]
}
```

### Execution Result Structure (Unchanged)
```python
ExecutionResult = {
    "status": str,  # "completed", "failed", "blocked"
    "files_modified": List[str],
    "output": str,
    "error": Optional[str]
}
```

### Generation Result Structure (Unchanged)
```python
GenerationResult = {
    "files": List[FileChange],
    "explanation": str
}

FileChange = {
    "path": str,
    "content": str,
    "action": str  # "create", "modify", "delete"
}
```

---

## Concurrency Considerations

### Agent Pool Execution (Unchanged Behavior)
```python
# LeadAgent manages multiple agents concurrently
tasks = [
    agent1.execute_task(task1),
    agent2.execute_task(task2),
    agent3.execute_task(task3)
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Key Point**: Async/await enables true concurrent execution without threading overhead.

---

## Memory Management

### Before (Threads)
- Each thread: ~8MB stack
- 10 concurrent agents: ~80MB overhead
- Thread context switching overhead

### After (Async)
- Coroutines: ~1-2KB each
- 10 concurrent agents: ~20KB overhead
- No thread context switching

**Expected Result**: Lower memory usage, faster context switching

---

## Summary of Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Execution Model** | Sync methods + threads | Async/await |
| **LLM Client** | `Anthropic` | `AsyncAnthropic` |
| **Broadcasts** | `_broadcast_async()` wrapper | Direct `await` |
| **Event Loop** | `run_in_executor()` | Native async |
| **Error Handling** | Try/except | Try/except + `CancelledError` |
| **Concurrency** | Thread pool (10 max) | Asyncio tasks (10 max) |
| **Memory** | ~80MB (threads) | ~20KB (coroutines) |
| **Test Framework** | Standard pytest | pytest-asyncio |

---

## Backward Compatibility

**API Compatibility**: ✅ Maintained
- All public methods have same signatures (just async)
- Return types unchanged
- Constructor parameters unchanged

**Test Compatibility**: ⚠️ Requires Updates
- Tests need `@pytest.mark.asyncio` decorator
- Mock objects need `AsyncMock` for async methods
- Fixtures may need async updates

**Database Compatibility**: ✅ Unchanged
- Same tables, schemas, queries
- Same transaction patterns

**WebSocket Compatibility**: ✅ Improved
- Broadcasts now work reliably
- No event loop issues

---

**Data Model Complete**: 2025-11-07
**Next**: contracts/ (API specifications)
