# Worker Agent API Contract

**Version**: 2.0.0 (Async)
**Branch**: `048-async-worker-agents`
**Date**: 2025-11-07

---

## Overview

This document defines the API contract for worker agents (Backend, Frontend, Test) after conversion to async/await pattern. This is a **breaking change** at the implementation level but maintains compatibility at the interface level.

---

## Base Worker Agent Interface

### Constructor

```python
def __init__(
    self,
    project_id: int,
    db: Database,
    codebase_index: CodebaseIndex,
    api_key: Optional[str] = None,
    project_root: Path = Path("."),
    ws_manager: Optional[ConnectionManager] = None
) -> None:
    """
    Initialize worker agent.

    Args:
        project_id: Project ID for database context
        db: Database instance for task/status management
        codebase_index: Indexed codebase for context retrieval
        api_key: API key for LLM provider (defaults to ANTHROPIC_API_KEY env var)
        project_root: Project root directory for file operations
        ws_manager: Optional WebSocket ConnectionManager for real-time updates

    Raises:
        ValueError: If project_id is invalid or database not initialized
    """
```

**Compatibility**: ✅ Unchanged

---

## Core Methods

### execute_task (PRIMARY METHOD)

**Before (v1.x - Sync)**:
```python
def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single task end-to-end."""
```

**After (v2.0 - Async)**:
```python
async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a single task end-to-end.

    This is the main entry point for task execution. Orchestrates:
    1. Update status to 'in_progress'
    2. Build context from codebase
    3. Generate code using LLM
    4. Apply file changes
    5. Run tests
    6. Self-correct if tests fail (up to 3 attempts)
    7. Update status to 'completed' or 'failed'

    Args:
        task: Task dictionary with required fields:
            - id (int): Task ID
            - title (str): Task title
            - description (str): Task description
            - project_id (int): Project ID
            - Other fields from database schema

    Returns:
        Execution result dictionary:
        {
            "status": "completed" | "failed" | "blocked",
            "files_modified": List[str],  # Relative paths
            "output": str,  # Explanation or error message
            "error": Optional[str]  # Error details if failed
        }

    Raises:
        asyncio.CancelledError: If task execution is cancelled
        ValueError: If task dictionary is malformed
        Exception: Other errors are caught and returned in result

    Notes:
        - Broadcasts task status updates via WebSocket if ws_manager provided
        - Automatically runs tests and attempts self-correction
        - Updates database with task status and test results
        - Creates blocker if self-correction exhausted
    """
```

**Breaking Change**: ⚠️ Caller must use `await`
**Migration**: `result = agent.execute_task(task)` → `result = await agent.execute_task(task)`

---

### generate_code

**Before (v1.x - Sync)**:
```python
def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate code using LLM based on context."""
```

**After (v2.0 - Async)**:
```python
async def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate code using LLM based on context.

    Constructs prompts from context and calls Anthropic Claude API
    to generate code changes.

    Args:
        context: Context dictionary from build_context():
            - task: Task dictionary
            - related_files: List[str] - File paths
            - related_symbols: List[Symbol] - Symbols from codebase index
            - issue_context: Optional[Dict] - Parent issue information

    Returns:
        Generation result:
        {
            "files": [
                {
                    "path": str,  # Relative to project_root
                    "content": str,  # File content
                    "action": "create" | "modify" | "delete"
                }
            ],
            "explanation": str  # What was changed and why
        }

    Raises:
        asyncio.TimeoutError: If LLM call exceeds timeout (300s)
        anthropic.APIError: If API call fails
        json.JSONDecodeError: If LLM returns invalid JSON

    Notes:
        - Uses AsyncAnthropic client for API calls
        - Timeout set to 300 seconds (5 minutes)
        - Response parsed as JSON
    """
```

**Breaking Change**: ⚠️ Caller must use `await`
**Migration**: `result = agent.generate_code(ctx)` → `result = await agent.generate_code(ctx)`

---

### fetch_next_task

```python
def fetch_next_task(self) -> Optional[Dict[str, Any]]:
    """
    Fetch highest priority pending task for this project.

    Tasks are ordered by:
    1. Priority (ascending: 0 = highest, 4 = lowest)
    2. Workflow step (ascending: 1 = first, 15 = last)
    3. ID (ascending: oldest first)

    Returns:
        Task dictionary or None if no tasks available.
        See TaskDict structure in data-model.md

    Notes:
        - Synchronous (database query is fast)
        - Thread-safe (uses database locking)
    """
```

**Compatibility**: ✅ Unchanged (remains sync)

---

### build_context

```python
def build_context(self, task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build execution context from task and codebase.

    Uses codebase index to find relevant symbols, files, and dependencies
    that provide context for code generation.

    Args:
        task: Task dictionary from fetch_next_task()

    Returns:
        Context dictionary:
        {
            "task": Dict[str, Any],  # Original task
            "related_files": List[str],  # File paths
            "related_symbols": List[Symbol],  # Symbols from codebase index
            "issue_context": Optional[Dict[str, Any]]  # Parent issue info
        }

    Notes:
        - Synchronous (in-memory operations)
        - Searches codebase index for relevant context
        - Limits to 10 files and 20 symbols to control token usage
    """
```

**Compatibility**: ✅ Unchanged (remains sync)

---

### apply_file_changes

```python
def apply_file_changes(self, files: List[Dict[str, Any]]) -> List[str]:
    """
    Apply file changes to disk.

    Safely writes, modifies, or deletes files with security validation
    and atomic operations.

    Args:
        files: List of file change dictionaries:
            - path: str - Relative path
            - action: "create" | "modify" | "delete"
            - content: str - File content (for create/modify)

    Returns:
        List of modified file paths (relative)

    Raises:
        ValueError: If path traversal or absolute path detected
        FileNotFoundError: If file to modify/delete doesn't exist

    Notes:
        - Synchronous (local file I/O is fast)
        - Validates paths for security (no traversal, no absolute paths)
        - Creates parent directories if needed
        - Atomic operations per file
    """
```

**Compatibility**: ✅ Unchanged (remains sync)

---

### update_task_status

```python
def update_task_status(
    self,
    task_id: int,
    status: str,
    output: Optional[str] = None,
    agent_id: str = "backend-worker"
) -> None:
    """
    Update task status in database.

    Args:
        task_id: Task ID
        status: New status ("in_progress", "completed", "failed", "blocked")
        output: Optional execution output/error message
        agent_id: Agent identifier for broadcast

    Notes:
        - Synchronous (database update is fast)
        - Updates completed_at timestamp if status is "completed"
        - Does NOT broadcast (broadcasts handled separately in async methods)
    """
```

**Compatibility**: ✅ Unchanged (remains sync)
**Note**: Broadcasts removed from this method, handled in async execute_task

---

## Removed Methods

### ~~_broadcast_async~~ (REMOVED)

**Before (v1.x)**:
```python
def _broadcast_async(self, broadcast_func, *args, **kwargs) -> None:
    """Helper to broadcast WebSocket messages (handles async event loop safely)."""
```

**Rationale**: No longer needed with async methods. Direct `await` is simpler and more reliable.

**Migration**: Replace calls with direct await:
```python
# Before:
self._broadcast_async(broadcast_task_status, self.ws_manager, ...)

# After:
if self.ws_manager:
    try:
        await broadcast_task_status(self.ws_manager, ...)
    except Exception as e:
        logger.debug(f"Broadcast failed: {e}")
```

---

## Internal Async Methods

These methods are converted to async to support async operations within execute_task.

### _run_and_record_tests

**After (v2.0 - Async)**:
```python
async def _run_and_record_tests(self, task_id: int) -> None:
    """
    Run tests and record results in database.

    Uses TestRunner to execute pytest on the project, parses results,
    and stores them in the database.

    Args:
        task_id: Task ID for which to record test results

    Notes:
        - Does not raise exceptions if tests fail
        - Records results in database
        - Broadcasts test results via WebSocket
        - Test execution may be async in future (currently wraps sync runner)
    """
```

---

### _self_correction_loop

**After (v2.0 - Async)**:
```python
async def _self_correction_loop(
    self,
    task: Dict[str, Any],
    initial_test_result_id: int
) -> bool:
    """
    Execute self-correction loop to fix failing tests.

    Attempts to fix failing tests up to 3 times. For each attempt:
    1. Analyze test failures
    2. Generate corrective code
    3. Apply changes
    4. Re-run tests
    5. Record correction attempt

    Args:
        task: Task dictionary
        initial_test_result_id: ID of the failed test result

    Returns:
        True if tests eventually pass, False if all attempts exhausted

    Notes:
        - Max 3 attempts
        - Creates blocker if all attempts fail
        - Broadcasts correction attempts via WebSocket
    """
```

---

### _attempt_self_correction

**After (v2.0 - Async)**:
```python
async def _attempt_self_correction(
    self,
    task: Dict[str, Any],
    test_result_id: int,
    attempt_number: int
) -> Dict[str, Any]:
    """
    Attempt to fix failing tests by analyzing errors and regenerating code.

    Args:
        task: Task dictionary
        test_result_id: ID of the failed test result
        attempt_number: Which correction attempt this is (1-3)

    Returns:
        Dict with:
            - "error_analysis": str - Analysis of what went wrong
            - "fix_description": str - Description of the fix
            - "code_changes": List[Dict] - File changes to apply

    Notes:
        - Uses LLM to analyze failures and generate fixes
        - Modifies generation prompt to focus on test failures
    """
```

---

## WebSocket Broadcast Integration

### Broadcast Functions (in websocket_broadcasts.py)

All broadcast functions are async and should be awaited directly:

```python
async def broadcast_task_status(
    ws_manager: ConnectionManager,
    project_id: int,
    task_id: int,
    status: str,
    agent_id: str = "worker"
) -> None:
    """Broadcast task status update to all clients."""
```

```python
async def broadcast_test_result(
    ws_manager: ConnectionManager,
    project_id: int,
    task_id: int,
    status: str,
    passed: int,
    failed: int,
    errors: int,
    total: int,
    duration: float
) -> None:
    """Broadcast test results to all clients."""
```

```python
async def broadcast_correction_attempt(
    ws_manager: ConnectionManager,
    project_id: int,
    task_id: int,
    attempt_num: int,
    max_attempts: int,
    status: str,
    error_summary: Optional[str] = None
) -> None:
    """Broadcast self-correction attempt to all clients."""
```

```python
async def broadcast_activity_update(
    ws_manager: ConnectionManager,
    project_id: int,
    activity_type: str,
    agent_id: str,
    message: str,
    task_id: Optional[int] = None
) -> None:
    """Broadcast general activity update to all clients."""
```

### Usage Pattern

```python
async def execute_task(self, task):
    # Update status
    self.update_task_status(task_id, TaskStatus.IN_PROGRESS.value)

    # Broadcast status change
    if self.ws_manager:
        try:
            await broadcast_task_status(
                self.ws_manager,
                self.project_id,
                task_id,
                TaskStatus.IN_PROGRESS.value,
                agent_id="backend-worker"
            )
        except Exception as e:
            logger.debug(f"Broadcast failed: {e}")
            # Continue execution - broadcasts are non-critical
```

---

## Error Handling Contract

### Exceptions

1. **asyncio.CancelledError**: Task cancellation
   - **Handler**: Catch, log, update status, re-raise
   - **Example**:
     ```python
     except asyncio.CancelledError:
         logger.info(f"Task {task_id} cancelled")
         self.update_task_status(task_id, TaskStatus.CANCELLED.value)
         raise
     ```

2. **anthropic.APIError**: LLM API failures
   - **Handler**: Catch, log, return failed status
   - **Example**:
     ```python
     except anthropic.APIError as e:
         logger.error(f"Anthropic API error: {e}")
         return {"status": "failed", "error": str(e)}
     ```

3. **asyncio.TimeoutError**: Operation timeout
   - **Handler**: Catch, log, return failed status
   - **Example**:
     ```python
     except asyncio.TimeoutError:
         logger.error(f"Task {task_id} timed out")
         return {"status": "failed", "error": "Timeout"}
     ```

4. **Exception**: General errors
   - **Handler**: Catch all, log, return failed status
   - **Example**:
     ```python
     except Exception as e:
         logger.error(f"Task {task_id} failed: {e}")
         return {"status": "failed", "error": str(e)}
     ```

### Broadcast Error Handling

Broadcasts should **never** block task execution:

```python
if self.ws_manager:
    try:
        await broadcast_task_status(...)
    except Exception as e:
        logger.warning(f"Broadcast failed (non-critical): {e}")
        # Continue execution
```

---

## Type Annotations

### Imports

```python
from typing import Dict, Any, Optional, List
from pathlib import Path
import asyncio
from anthropic import AsyncAnthropic
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.ui.connection_manager import ConnectionManager
```

### Type Hints

```python
class BackendWorkerAgent:
    project_id: int
    db: Database
    codebase_index: CodebaseIndex
    provider: str
    api_key: Optional[str]
    project_root: Path
    ws_manager: Optional[ConnectionManager]

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]: ...
    async def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]: ...
    def fetch_next_task(self) -> Optional[Dict[str, Any]]: ...
    def build_context(self, task: Dict[str, Any]) -> Dict[str, Any]: ...
    def apply_file_changes(self, files: List[Dict[str, Any]]) -> List[str]: ...
```

---

## Compatibility Matrix

| Method | v1.x (Sync) | v2.0 (Async) | Breaking? | Migration |
|--------|-------------|--------------|-----------|-----------|
| `__init__` | ✅ | ✅ | No | None |
| `execute_task` | Sync | Async | ⚠️ Yes | Add `await` |
| `generate_code` | Sync | Async | ⚠️ Yes | Add `await` |
| `fetch_next_task` | Sync | Sync | No | None |
| `build_context` | Sync | Sync | No | None |
| `apply_file_changes` | Sync | Sync | No | None |
| `update_task_status` | Sync | Sync | No | None |
| `_broadcast_async` | Sync | ❌ Removed | ⚠️ Yes | Use direct await |
| `_run_and_record_tests` | Sync | Async | Internal | N/A |
| `_self_correction_loop` | Sync | Async | Internal | N/A |
| `_attempt_self_correction` | Sync | Async | Internal | N/A |

---

## Testing Contract

### Test Requirements

1. **Async Test Decorator**: All tests for async methods must use `@pytest.mark.asyncio`
2. **Async Mocks**: Use `AsyncMock` for mocking async methods
3. **Await Assertions**: Use `await` when calling async methods in tests

### Example Test

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_execute_task_success():
    # Setup
    agent = BackendWorkerAgent(
        project_id=1,
        db=mock_db,
        codebase_index=mock_index,
        api_key="test-key"
    )

    # Mock AsyncAnthropic
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = AsyncMock(
        content=[MagicMock(text='{"files": [], "explanation": "Done"}')]
    )

    # Execute
    result = await agent.execute_task(test_task)

    # Assert
    assert result["status"] == "completed"
```

---

## Performance Contract

### Timeouts

| Operation | Timeout | Rationale |
|-----------|---------|-----------|
| LLM API call | 300s (5 min) | Allows for large code generation |
| Task execution | No timeout | Controlled by self-correction loop |
| Broadcast | 5s | Fast, shouldn't block |
| Database query | 1s | Should be very fast |

### Concurrency

- **Max Concurrent Tasks**: 10 (configurable via AgentPoolManager)
- **Concurrent Execution**: Managed by LeadAgent via `asyncio.gather()`
- **Resource Limits**: Controlled by semaphore in AgentPoolManager

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-10-25 | Initial sync implementation |
| 2.0.0 | 2025-11-07 | Async/await refactoring (Sprint 5) |

---

## Migration Guide

See `quickstart.md` for detailed migration guide.

---

**API Contract Complete**: 2025-11-07
**Next**: quickstart.md (implementation guide)
