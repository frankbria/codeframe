# Feature Specification: Async Worker Agents

**Issue**: cf-48
**Priority**: P1
**Type**: Refactoring (Architecture)
**Sprint**: 5
**Labels**: architecture, async, refactoring, sprint-5

---

## Overview

Convert BackendWorkerAgent, FrontendWorkerAgent, and TestWorkerAgent from synchronous to asynchronous execution pattern to resolve event loop deadlocks and improve the architecture.

## Problem Statement

### Current Architecture Issues

The current implementation uses synchronous `execute_task()` methods wrapped in `run_in_executor()`, which causes problems:

1. **Event Loop Deadlocks**: Worker agents trying to broadcast via `_broadcast_async()` create deadlocks when called from thread pool executors
2. **Threading Overhead**: Unnecessary thread creation and context switching
3. **Incorrect Async Semantics**: Using `run_in_executor()` to wrap sync code instead of proper async/await
4. **Broadcast Failures**: WebSocket broadcasts fail or behave unpredictably from threaded context

### Root Cause

From Sprint 4 troubleshooting (see `claudedocs/SPRINT_4_FINAL_STATUS.md`):
- Worker agents use sync `execute_task()` methods
- LeadAgent wraps these in `loop.run_in_executor()`
- When agents try to broadcast, they attempt to get event loop from thread context
- This creates deadlocks or broadcast failures

## Goals

### Primary Goals

1. **Convert to Async Pattern**: Refactor all three worker agents to use `async def execute_task()`
2. **Remove Threading**: Eliminate `run_in_executor()` wrapper in LeadAgent
3. **Fix Broadcasts**: Use direct `await broadcast_task_status()` instead of `_broadcast_async()` wrapper
4. **Maintain Compatibility**: Ensure all existing tests and integrations continue to work

### Secondary Goals

5. **Improve Performance**: Reduce threading overhead
6. **Better Error Handling**: Proper async exception handling and cancellation
7. **True Concurrency**: Enable proper concurrent execution without threads

## Requirements

### Functional Requirements

1. **Worker Agent Conversion**:
   - Convert `BackendWorkerAgent.execute_task()` to async
   - Convert `FrontendWorkerAgent.execute_task()` (if exists)
   - Convert `TestWorkerAgent.execute_task()` (if exists)
   - Use `AsyncAnthropic` client instead of sync `Anthropic` client

2. **LeadAgent Updates**:
   - Remove `run_in_executor()` wrapper from `_assign_and_execute_task()`
   - Call worker agent methods with `await` instead
   - Remove threading logic

3. **Broadcast Changes**:
   - Replace `_broadcast_async()` helper method with direct `await` calls
   - Update all broadcast call sites to use async pattern
   - Remove event loop detection logic

4. **Testing**:
   - Update existing tests to use async patterns
   - Add tests for concurrent execution
   - Verify broadcasts work correctly

### Non-Functional Requirements

1. **Backward Compatibility**: All existing Sprint 3 and Sprint 4 tests must pass
2. **Performance**: No degradation in task execution time
3. **Reliability**: Broadcasts must work reliably
4. **Code Quality**: Maintain current test coverage levels

## Design

### Architecture Changes

```
Before:
LeadAgent._assign_and_execute_task()
  └─> run_in_executor(agent.execute_task)  [SYNC in thread]
      └─> agent._broadcast_async()  [Attempts to get event loop - DEADLOCK]

After:
LeadAgent._assign_and_execute_task()
  └─> await agent.execute_task()  [ASYNC]
      └─> await broadcast_task_status()  [Direct async call - WORKS]
```

### Files to Modify

1. **codeframe/agents/backend_worker_agent.py**:
   - Change `execute_task()` to `async def execute_task()`
   - Change `generate_code()` to `async def generate_code()`
   - Use `AsyncAnthropic` client
   - Replace `_broadcast_async()` with direct `await` calls
   - Update all internal methods that need to be async

2. **codeframe/agents/frontend_worker_agent.py**:
   - Same pattern as BackendWorkerAgent
   - Convert to async execution

3. **codeframe/agents/test_worker_agent.py**:
   - Same pattern as BackendWorkerAgent
   - Convert to async execution

4. **codeframe/agents/lead_agent.py**:
   - Remove `run_in_executor()` call in `_assign_and_execute_task()`
   - Change to `await agent.execute_task(task_dict)`
   - Remove thread pool executor imports if no longer needed

5. **tests/agents/test_backend_worker_agent.py**:
   - Convert tests to async using `@pytest.mark.asyncio`
   - Update test fixtures and mocks

6. **tests/agents/test_frontend_worker_agent.py**:
   - Same test updates as backend

7. **tests/agents/test_test_worker_agent.py**:
   - Same test updates as backend

### Implementation Steps

#### Phase 1: Backend Worker Agent (2 hours)
1. Convert `execute_task()` to async
2. Convert `generate_code()` to async
3. Switch to `AsyncAnthropic` client
4. Replace `_broadcast_async()` with direct awaits
5. Update helper methods as needed
6. Update tests

#### Phase 2: Frontend & Test Workers (1 hour)
7. Apply same pattern to FrontendWorkerAgent
8. Apply same pattern to TestWorkerAgent
9. Update their tests

#### Phase 3: LeadAgent Integration (30 min)
10. Remove `run_in_executor()` wrapper
11. Update to `await agent.execute_task()`
12. Test integration

#### Phase 4: Testing & Verification (30 min)
13. Run full test suite
14. Verify broadcasts work
15. Check for regressions

## Dependencies

- **Depends on**: Sprint 4 completion (cf-38, cf-37)
- **Blocks**: None
- **Related**: Sprint 4 P0 fixes (event loop deadlock resolution)

## Acceptance Criteria

1. ✅ All three worker agents use `async def execute_task()`
2. ✅ AsyncAnthropic client used instead of sync client
3. ✅ No `_broadcast_async()` wrapper - direct await calls only
4. ✅ LeadAgent uses `await agent.execute_task()` - no `run_in_executor()`
5. ✅ All broadcasts work reliably
6. ✅ All existing tests pass (Sprint 3 + Sprint 4)
7. ✅ Test coverage maintained at current levels
8. ✅ No performance regression
9. ✅ No event loop deadlocks

## Success Metrics

- **Test Pass Rate**: 100% (all existing tests pass)
- **Broadcast Success Rate**: 100% (no failed broadcasts)
- **Event Loop Deadlocks**: 0 occurrences
- **Performance**: Task execution time ≤ current baseline

## References

- **Sprint 4 Final Status**: `claudedocs/SPRINT_4_FINAL_STATUS.md`
- **Issue cf-48**: Beads issue tracker
- **Anthropic Async Client**: https://github.com/anthropics/anthropic-sdk-python#async-usage

## Estimated Effort

**Total**: 4 hours
- Phase 1 (Backend): 2 hours
- Phase 2 (Frontend/Test): 1 hour
- Phase 3 (LeadAgent): 30 min
- Phase 4 (Testing): 30 min

## Risk Assessment

**Risk Level**: Low-Medium

**Risks**:
1. **Breaking Changes**: Converting sync to async could break calling code
   - Mitigation: Comprehensive test coverage, careful review

2. **Async Complexity**: New async patterns may introduce bugs
   - Mitigation: Follow established async best practices

3. **Anthropic Client Changes**: AsyncAnthropic API may differ
   - Mitigation: Review Anthropic docs, test thoroughly

**Confidence**: High - This is a well-understood architectural improvement with clear benefits
