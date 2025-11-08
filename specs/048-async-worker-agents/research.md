# Research: Async Worker Agents Refactoring

**Branch**: `048-async-worker-agents` | **Date**: 2025-11-07
**Phase**: Phase 0 (Research & Design Decisions)

---

## Executive Summary

This document consolidates research findings for converting synchronous worker agents to asynchronous execution in CodeFRAME. The refactoring addresses event loop deadlocks, improves performance, and follows Python async best practices.

---

## 1. Python Async/Await Best Practices

### Decision: Use `async def` for All I/O-Bound Methods

**Rationale**:
- Worker agents perform I/O-bound operations (LLM API calls, database queries, file I/O)
- Async/await provides true concurrency for I/O without threading overhead
- Python's asyncio is the standard for concurrent I/O operations

**Pattern**:
```python
# Before (sync)
def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
    result = self.generate_code(context)
    return result

# After (async)
async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
    result = await self.generate_code(context)
    return result
```

**Alternatives Considered**:
- **Threading** (`run_in_executor`): Rejected - causes deadlocks, higher overhead
- **Multiprocessing**: Rejected - too heavyweight, IPC complexity
- **Sync with callbacks**: Rejected - callback hell, harder to maintain

---

## 2. Anthropic AsyncAnthropic Client

### Decision: Use `AsyncAnthropic` for All LLM Calls

**Rationale**:
- Anthropic SDK provides native async support via `AsyncAnthropic`
- API is nearly identical to sync client (minimal code changes)
- Properly integrates with Python asyncio event loop
- Official SDK pattern for async usage

**Implementation**:
```python
# Before
import anthropic
client = anthropic.Anthropic(api_key=self.api_key)
response = client.messages.create(...)

# After
from anthropic import AsyncAnthropic
client = AsyncAnthropic(api_key=self.api_key)
response = await client.messages.create(...)
```

**Key Changes**:
1. Import `AsyncAnthropic` instead of `Anthropic`
2. Instantiate with same parameters
3. Add `await` to all `.messages.create()` calls
4. Mark containing methods as `async def`

**Documentation**: https://github.com/anthropics/anthropic-sdk-python#async-usage

**Alternatives Considered**:
- **Keep sync client with threads**: Rejected - root cause of deadlocks
- **Custom async wrapper**: Rejected - reinventing the wheel, SDK provides it

---

## 3. Event Loop and WebSocket Broadcasts

### Decision: Direct `await` for Broadcasts, Remove `_broadcast_async()` Wrapper

**Rationale**:
- Current `_broadcast_async()` wrapper tries to get event loop from thread context → deadlock
- With async methods, we're already in event loop context
- Direct `await broadcast_*()` is simpler and more reliable
- Follows standard asyncio patterns

**Pattern**:
```python
# Before (problematic)
def _broadcast_async(self, broadcast_func, *args, **kwargs):
    try:
        loop = asyncio.get_running_loop()  # Fails in thread
        asyncio.run_coroutine_threadsafe(...)
    except RuntimeError:
        pass

# After (correct)
async def execute_task(self, task):
    if self.ws_manager:
        from codeframe.ui.websocket_broadcasts import broadcast_task_status
        await broadcast_task_status(
            self.ws_manager,
            self.project_id,
            task_id,
            status
        )
```

**Benefits**:
- No event loop context issues
- Simpler code (remove wrapper method)
- Proper async error handling
- No silent failures

**Alternatives Considered**:
- **Keep wrapper with better detection**: Rejected - adding complexity when simple solution exists
- **Queue-based broadcasts**: Rejected - overkill for this use case

---

## 4. Test Migration Strategy

### Decision: Use `pytest-asyncio` with `@pytest.mark.asyncio`

**Rationale**:
- Standard pytest plugin for testing async code
- Minimal changes to existing tests
- Provides async fixture support
- Already used in FastAPI testing

**Pattern**:
```python
# Before
def test_execute_task():
    agent = BackendWorkerAgent(...)
    result = agent.execute_task(task)
    assert result["status"] == "completed"

# After
@pytest.mark.asyncio
async def test_execute_task():
    agent = BackendWorkerAgent(...)
    result = await agent.execute_task(task)
    assert result["status"] == "completed"
```

**Mock Updates**:
```python
# Async mock for Anthropic client
mock_client = AsyncMock()
mock_client.messages.create.return_value = AsyncMock(
    content=[AsyncMock(text='{"files": []}')]
)
```

**Fixtures**:
- Use `@pytest.fixture` with `scope="function"` for async fixtures
- Use `@pytest_asyncio.fixture` for explicitly async fixtures
- Ensure cleanup with `async with` or `try/finally`

**Alternatives Considered**:
- **asynctest library**: Rejected - pytest-asyncio is more current
- **Manual event loop management**: Rejected - pytest-asyncio handles it

---

## 5. Backward Compatibility Strategy

### Decision: Phase-Based Migration with Comprehensive Testing

**Rationale**:
- Large refactoring with high risk of breaking existing functionality
- Incremental approach allows validation at each step
- Full test coverage ensures no regressions

**Migration Phases**:

**Phase 1: Backend Worker Agent**
1. Convert `execute_task()` to async
2. Convert `generate_code()` to async
3. Replace `_broadcast_async()` with direct awaits
4. Update helper methods (`_run_and_record_tests`, `_self_correction_loop`)
5. Switch to `AsyncAnthropic`
6. Update tests
7. Verify: Run backend worker tests

**Phase 2: Frontend & Test Workers**
8. Apply same pattern to `FrontendWorkerAgent`
9. Apply same pattern to `TestWorkerAgent`
10. Update their tests
11. Verify: Run all agent tests

**Phase 3: LeadAgent Integration**
12. Remove `run_in_executor()` from `_assign_and_execute_task()`
13. Change to `await agent.execute_task(task_dict)`
14. Update any other thread-related code
15. Verify: Run integration tests

**Phase 4: Full Validation**
16. Run complete test suite (unit + integration)
17. Verify Sprint 3 tests still pass
18. Verify Sprint 4 tests still pass
19. Manual testing with real project

**Rollback Plan**:
- Git branch allows easy rollback
- Each phase can be reverted independently
- Tests provide safety net

**Alternatives Considered**:
- **Big-bang migration**: Rejected - too risky
- **Parallel implementation**: Rejected - code duplication

---

## 6. Performance Considerations

### Decision: Maintain Current Performance Baseline

**Rationale**:
- Async eliminates threading overhead (should improve performance)
- Task execution time dominated by LLM API calls (not affected)
- Real performance gain is in concurrent task execution

**Measurements to Track**:
1. **Task Execution Time**: Should remain ≤ current baseline
2. **Agent Creation Time**: Should remain < 100ms
3. **Broadcast Latency**: Should decrease (no thread context switching)
4. **Memory Usage**: Should decrease (no thread stacks)

**Benchmarking Strategy**:
```python
import time

start = time.perf_counter()
await agent.execute_task(task)
duration = time.perf_counter() - start

# Compare against current baseline: ~3-5s for typical task
```

**Acceptance Criteria**:
- No regression in average task execution time
- Concurrent execution shows improvement (measured in integration tests)
- No increase in memory usage

**Alternatives Considered**:
- **Defer performance testing**: Rejected - need baseline comparison
- **Focus only on correctness**: Rejected - performance is key requirement

---

## 7. Error Handling and Cancellation

### Decision: Implement Proper Async Exception Handling

**Rationale**:
- Async code requires different error handling patterns
- Need to handle task cancellation gracefully
- WebSocket disconnections should not crash agents

**Pattern**:
```python
async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # Task execution
        context = self.build_context(task)
        result = await self.generate_code(context)
        return result
    except asyncio.CancelledError:
        # Handle task cancellation
        logger.info(f"Task {task['id']} cancelled")
        raise  # Re-raise to propagate cancellation
    except Exception as e:
        # Handle other errors
        logger.error(f"Task {task['id']} failed: {e}")
        return {"status": "failed", "error": str(e)}
```

**Broadcast Error Handling**:
```python
try:
    await broadcast_task_status(...)
except Exception as e:
    logger.warning(f"Broadcast failed (non-critical): {e}")
    # Continue execution - broadcasts are non-critical
```

**Timeout Handling**:
```python
try:
    async with asyncio.timeout(300):  # 5 minute timeout
        result = await agent.execute_task(task)
except asyncio.TimeoutError:
    logger.error(f"Task {task_id} timed out")
    # Update task status to failed
```

**Alternatives Considered**:
- **No explicit cancellation handling**: Rejected - can leak resources
- **Synchronous error handling**: Rejected - doesn't work with async

---

## 8. Database Access Patterns

### Decision: Keep Synchronous Database Access

**Rationale**:
- SQLite connections are not thread-safe but we're in async context
- Database operations are fast (< 10ms typically)
- Converting to async DB would require major refactoring
- Current synchronous approach works in async functions

**Pattern** (unchanged):
```python
async def execute_task(self, task):
    # Sync DB access is OK in async function (it's fast)
    cursor = self.db.conn.cursor()
    cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", ...)
    self.db.conn.commit()
```

**Future Consideration**:
- If database operations become bottleneck, consider `aiosqlite`
- Not needed for Sprint 5 scope

**Alternatives Considered**:
- **aiosqlite**: Rejected for now - unnecessary complexity, not a bottleneck
- **Database pool**: Rejected - SQLite doesn't benefit from pooling

---

## 9. File I/O Patterns

### Decision: Keep Synchronous File I/O

**Rationale**:
- File operations in this context are fast (local filesystem)
- `aiofiles` would add dependency with minimal benefit
- File writes are infrequent (only during code generation)
- Synchronous file I/O acceptable in async functions when fast

**Pattern** (unchanged):
```python
async def apply_file_changes(self, files):
    for file_spec in files:
        path = file_spec["path"]
        content = file_spec["content"]

        # Sync file I/O is OK - it's fast
        target_path.write_text(content, encoding="utf-8")
```

**Future Consideration**:
- If file operations become slow (network filesystem), consider `aiofiles`
- Not relevant for current use case

**Alternatives Considered**:
- **aiofiles**: Rejected - premature optimization
- **run_in_executor for file I/O**: Rejected - overkill for local files

---

## 10. Testing Strategy

### Decision: Comprehensive Multi-Layer Testing

**Test Layers**:

1. **Unit Tests** (per agent):
   - Test async methods directly
   - Mock AsyncAnthropic client
   - Mock WebSocket manager
   - Verify error handling
   - **Target**: 100% existing tests pass

2. **Integration Tests**:
   - Test LeadAgent → Worker interaction
   - Test concurrent task execution
   - Test broadcast delivery
   - **Target**: All Sprint 4 integration tests pass

3. **Regression Tests**:
   - Run full Sprint 3 test suite
   - Run full Sprint 4 test suite
   - **Target**: Zero regressions

**Test Execution**:
```bash
# Unit tests
pytest tests/agents/test_backend_worker_agent.py -v

# Integration tests
pytest tests/integration/test_agent_pool_manager.py -v

# Full suite
pytest tests/ -v

# With coverage
pytest tests/ --cov=codeframe.agents --cov-report=html
```

**Success Criteria**:
- ✅ All unit tests pass (≥98% like Sprint 4)
- ✅ All integration tests pass (≥75% like Sprint 4)
- ✅ All regression tests pass (100% like Sprint 4)
- ✅ No new test failures introduced

**Alternatives Considered**:
- **Minimal testing**: Rejected - high risk refactoring needs validation
- **Manual testing only**: Rejected - not repeatable or reliable

---

## Implementation Checklist

### Phase 0: Research ✅
- [X] Research async/await best practices
- [X] Review AsyncAnthropic documentation
- [X] Design broadcast pattern
- [X] Plan test migration strategy
- [X] Document decisions

### Phase 1: Backend Worker (Next)
- [ ] Convert `execute_task()` to async
- [ ] Convert `generate_code()` to async
- [ ] Switch to `AsyncAnthropic`
- [ ] Replace `_broadcast_async()` with direct awaits
- [ ] Update helper methods
- [ ] Update unit tests
- [ ] Verify tests pass

### Phase 2: Frontend & Test Workers
- [ ] Apply pattern to `FrontendWorkerAgent`
- [ ] Apply pattern to `TestWorkerAgent`
- [ ] Update tests
- [ ] Verify tests pass

### Phase 3: LeadAgent Integration
- [ ] Remove `run_in_executor()`
- [ ] Update to `await agent.execute_task()`
- [ ] Test integration
- [ ] Verify integration tests pass

### Phase 4: Validation
- [ ] Run full test suite
- [ ] Check performance metrics
- [ ] Verify broadcasts work
- [ ] Manual E2E testing

---

## Risk Mitigation

### Risk 1: Breaking Existing Functionality
**Mitigation**: Comprehensive test suite, incremental approach, easy rollback

### Risk 2: Performance Regression
**Mitigation**: Baseline measurements, benchmarking at each phase

### Risk 3: Async Bugs (race conditions, deadlocks)
**Mitigation**: Follow established patterns, thorough testing, code review

### Risk 4: Test Migration Issues
**Mitigation**: pytest-asyncio best practices, incremental test updates

---

## References

1. **Anthropic SDK Async Usage**: https://github.com/anthropics/anthropic-sdk-python#async-usage
2. **Python asyncio Docs**: https://docs.python.org/3/library/asyncio.html
3. **pytest-asyncio**: https://github.com/pytest-dev/pytest-asyncio
4. **Sprint 4 Status**: `claudedocs/SPRINT_4_FINAL_STATUS.md`
5. **Issue cf-48**: Beads issue tracker

---

**Research Complete**: 2025-11-07
**Next Phase**: Phase 1 (data-model.md, contracts/, quickstart.md)
