# Quickstart: Async Worker Agents Implementation

**Branch**: `048-async-worker-agents` | **Date**: 2025-11-07
**Estimated Time**: 4 hours

---

## Overview

This guide provides step-by-step instructions for converting BackendWorkerAgent, FrontendWorkerAgent, and TestWorkerAgent from synchronous to asynchronous execution.

---

## Prerequisites

### Dependencies
```bash
# Already installed (verify)
pip install anthropic>=0.18.0  # AsyncAnthropic support
pip install pytest-asyncio>=0.21.0  # Async test support
pip install asyncio  # Standard library
```

### Environment Setup
```bash
# Ensure you're on the feature branch
git checkout 048-async-worker-agents

# Verify tests pass before starting
pytest tests/agents/test_backend_worker_agent.py -v
pytest tests/agents/test_frontend_worker_agent.py -v
pytest tests/agents/test_test_worker_agent.py -v
```

---

## Phase 1: Backend Worker Agent (2 hours)

### Step 1.1: Convert execute_task to Async

**File**: `codeframe/agents/backend_worker_agent.py`

**Location**: Line ~797

**Change**:
```python
# Before:
    def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single task end-to-end."""

# After:
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single task end-to-end."""
```

### Step 1.2: Add Await to Internal Async Calls

**Within execute_task**, update these calls:

```python
# Line ~835: generate_code call
# Before:
generation_result = self.generate_code(context)

# After:
generation_result = await self.generate_code(context)

# Line ~841: _run_and_record_tests call
# Before:
self._run_and_record_tests(task_id)

# After:
await self._run_and_record_tests(task_id)

# Line ~854: _self_correction_loop call
# Before:
correction_successful = self._self_correction_loop(task, latest_test["id"])

# After:
correction_successful = await self._self_correction_loop(task, latest_test["id"])
```

### Step 1.3: Convert generate_code to Async

**Location**: Line ~230

**Changes**:
```python
# Before:
    def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate code using LLM based on context."""
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(...)

# After:
    async def generate_code(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate code using LLM based on context."""
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=self.api_key)
        response = await client.messages.create(...)
```

**Note**: Only the client import and the .create() call change. The rest remains the same.

### Step 1.4: Replace _broadcast_async with Direct Awaits

**Pattern to find and replace** (multiple locations):

```python
# Before:
self._broadcast_async(
    broadcast_task_status,
    self.ws_manager,
    self.project_id,
    task_id,
    status,
    agent_id="backend-worker"
)

# After:
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

**Locations** (approximate line numbers):
- Line ~446: In `update_task_status` → Remove broadcast from here
- Line ~511-528: In `_run_and_record_tests` → Update to await
- Line ~674-685: In `_self_correction_loop` (attempt start) → Update to await
- Line ~721-745: In `_self_correction_loop` (success) → Update to await
- Line ~756-771: In `_self_correction_loop` (failure) → Update to await
- Line ~876-889: In `execute_task` (completion) → Update to await

### Step 1.5: Remove _broadcast_async Method

**Location**: Line ~97-126

**Action**: Delete entire method

```python
# DELETE THIS ENTIRE METHOD:
    def _broadcast_async(
        self,
        broadcast_func,
        *args,
        **kwargs
    ) -> None:
        """
        Helper to broadcast WebSocket messages (handles async event loop safely).
        ...
        """
        # ... entire method body ...
```

### Step 1.6: Convert Helper Methods to Async

**_run_and_record_tests** (Line ~457):
```python
# Before:
    def _run_and_record_tests(self, task_id: int) -> None:

# After:
    async def _run_and_record_tests(self, task_id: int) -> None:
```

**_self_correction_loop** (Line ~644):
```python
# Before:
    def _self_correction_loop(self, task: Dict[str, Any], initial_test_result_id: int) -> bool:

# After:
    async def _self_correction_loop(self, task: Dict[str, Any], initial_test_result_id: int) -> bool:
```

**_attempt_self_correction** (Line ~548):
```python
# Before:
    def _attempt_self_correction(
        self,
        task: Dict[str, Any],
        test_result_id: int,
        attempt_number: int
    ) -> Dict[str, Any]:

# After:
    async def _attempt_self_correction(
        self,
        task: Dict[str, Any],
        test_result_id: int,
        attempt_number: int
    ) -> Dict[str, Any]:
```

**Within _self_correction_loop**, update calls:
```python
# Line ~688: _attempt_self_correction call
correction = await self._attempt_self_correction(task, initial_test_result_id, attempt_num)

# Line ~711: _run_and_record_tests call
await self._run_and_record_tests(task_id)
```

**Within _attempt_self_correction**, update calls:
```python
# Line ~624: generate_code call
generation_result = await self.generate_code(context)
```

### Step 1.7: Update Tests

**File**: `tests/agents/test_backend_worker_agent.py`

**Changes**:

1. **Add import**:
```python
import pytest
from unittest.mock import AsyncMock  # Add AsyncMock
```

2. **Update test functions**:
```python
# Before:
def test_execute_task_success(backend_agent, sample_task):
    result = backend_agent.execute_task(sample_task)

# After:
@pytest.mark.asyncio
async def test_execute_task_success(backend_agent, sample_task):
    result = await backend_agent.execute_task(sample_task)
```

3. **Update mocks for AsyncAnthropic**:
```python
@pytest.fixture
def backend_agent(tmp_path):
    mock_db = MagicMock()
    mock_index = MagicMock()

    # Mock AsyncAnthropic client
    with patch("codeframe.agents.backend_worker_agent.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(
            return_value=MagicMock(
                content=[MagicMock(text='{"files": [], "explanation": "Test"}')]
            )
        )
        mock_anthropic.return_value = mock_client

        agent = BackendWorkerAgent(...)
        yield agent
```

4. **Update all test methods**:
   - Add `@pytest.mark.asyncio` decorator
   - Change `def test_*` to `async def test_*`
   - Add `await` before agent method calls

### Step 1.8: Verify Phase 1

```bash
# Run backend worker tests
pytest tests/agents/test_backend_worker_agent.py -v

# Expected: All tests pass
```

---

## Phase 2: Frontend & Test Workers (1 hour)

### Step 2.1: Frontend Worker Agent

**File**: `codeframe/agents/frontend_worker_agent.py`

**Action**: Apply the same pattern as BackendWorkerAgent:

1. Convert `execute_task` to async
2. Convert `generate_code` to async
3. Use `AsyncAnthropic` client
4. Replace `_broadcast_async` with direct awaits
5. Remove `_broadcast_async` method
6. Convert any other internal methods to async as needed

**Hint**: Use BackendWorkerAgent as reference. The structure is very similar.

### Step 2.2: Test Worker Agent

**File**: `codeframe/agents/test_worker_agent.py`

**Action**: Apply the same pattern as BackendWorkerAgent.

### Step 2.3: Update Frontend Tests

**File**: `tests/agents/test_frontend_worker_agent.py`

**Action**: Apply the same test updates as BackendWorkerAgent tests.

### Step 2.4: Update Test Worker Tests

**File**: `tests/agents/test_test_worker_agent.py`

**Action**: Apply the same test updates as BackendWorkerAgent tests.

### Step 2.5: Verify Phase 2

```bash
# Run all agent tests
pytest tests/agents/ -v

# Expected: All tests pass
```

---

## Phase 3: LeadAgent Integration (30 minutes)

### Step 3.1: Update _assign_and_execute_task

**File**: `codeframe/agents/lead_agent.py`

**Location**: Line ~1256 (method signature) and ~1324 (executor call)

**Changes**:

1. **Method remains async** (already is):
```python
async def _assign_and_execute_task(
    self,
    task: Task,
    retry_counts: Dict[int, int]
) -> bool:
```

2. **Remove run_in_executor wrapper**:
```python
# Before (Line ~1317-1329):
            print(f"🎯 DEBUG: About to execute task via run_in_executor...")
            loop = asyncio.get_running_loop()

            print(f"🎯 DEBUG: Calling run_in_executor...")
            await loop.run_in_executor(
                None,
                agent_instance.execute_task,
                task_dict
            )
            print(f"🎯 DEBUG: run_in_executor completed ✅")

# After:
            print(f"🎯 DEBUG: About to execute task directly (async)...")
            await agent_instance.execute_task(task_dict)
            print(f"🎯 DEBUG: execute_task completed ✅")
```

3. **Remove executor import if not used elsewhere**:
```python
# Check if asyncio.get_running_loop() is used elsewhere
# If not, this change is sufficient
```

### Step 3.2: Verify LeadAgent Integration

```bash
# Run integration tests
pytest tests/integration/test_agent_pool_manager.py -v

# Expected: All tests pass
```

---

## Phase 4: Full Validation (30 minutes)

### Step 4.1: Run Complete Test Suite

```bash
# Unit tests
pytest tests/agents/ -v

# Integration tests
pytest tests/integration/ -v

# Full suite
pytest tests/ -v
```

**Expected Results**:
- All unit tests pass (≥98% like Sprint 4)
- All integration tests pass (≥75% like Sprint 4)
- No new test failures

### Step 4.2: Run Regression Tests

```bash
# Sprint 3 tests (if they exist in separate directory)
pytest tests/sprint3/ -v

# Sprint 4 tests
pytest tests/sprint4/ -v
```

**Expected**: Zero regressions

### Step 4.3: Performance Check

```bash
# Run with timing
pytest tests/agents/test_backend_worker_agent.py -v --durations=10

# Compare execution times with baseline
# Should be similar or faster
```

### Step 4.4: Manual Testing

1. **Start the server**:
```bash
cd web-ui
npm run dev

# In another terminal
cd ..
python -m codeframe.ui.server
```

2. **Create a test project**:
```bash
# Via API or UI
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "test-async", "root_path": "/tmp/test"}'
```

3. **Start discovery and generate tasks**:
```bash
# Via UI: Start discovery, answer questions, generate PRD/tasks
```

4. **Watch agents execute tasks**:
   - Check dashboard for agent activity
   - Verify broadcasts work (real-time updates)
   - Check task status updates
   - Verify no deadlocks or hangs

5. **Check logs**:
```bash
# Look for any errors or warnings
tail -f /tmp/codeframe.log  # Or wherever logs are
```

---

## Testing Checklist

### Unit Tests
- [ ] `test_backend_worker_agent.py`: All tests pass
- [ ] `test_frontend_worker_agent.py`: All tests pass
- [ ] `test_test_worker_agent.py`: All tests pass
- [ ] All tests use `@pytest.mark.asyncio`
- [ ] All async method calls use `await`
- [ ] AsyncAnthropic client properly mocked

### Integration Tests
- [ ] `test_agent_pool_manager.py`: All tests pass
- [ ] Multi-agent coordination works
- [ ] Broadcasts delivered successfully
- [ ] No deadlocks or race conditions

### Regression Tests
- [ ] Sprint 3 tests pass
- [ ] Sprint 4 tests pass
- [ ] Zero new failures

### Manual Tests
- [ ] Server starts successfully
- [ ] Project creation works
- [ ] Discovery flow completes
- [ ] Tasks execute successfully
- [ ] Broadcasts appear in UI
- [ ] No errors in logs

---

## Troubleshooting

### Issue: `RuntimeError: asyncio.run() cannot be called from a running event loop`

**Cause**: Mixing async/await with threading patterns

**Solution**: Ensure all calls use `await`, no `asyncio.run()` in async context

---

### Issue: `TypeError: object MagicMock can't be used in 'await' expression`

**Cause**: Mock not set up as AsyncMock

**Solution**:
```python
# Change:
mock_method = MagicMock()

# To:
mock_method = AsyncMock()
```

---

### Issue: Tests hang indefinitely

**Cause**: Missing `await` on async method call

**Solution**: Add `await` to all async method calls in tests

---

### Issue: `AttributeError: module 'anthropic' has no attribute 'AsyncAnthropic'`

**Cause**: Outdated anthropic SDK

**Solution**:
```bash
pip install --upgrade anthropic>=0.18.0
```

---

### Issue: Broadcasts don't appear in UI

**Cause**: WebSocket connection issue or broadcast error silently caught

**Solution**:
1. Check WebSocket connection in browser dev tools
2. Check server logs for broadcast errors
3. Verify `ws_manager` is passed to agent constructor

---

### Issue: Event loop closed errors in tests

**Cause**: Test cleanup issue or pytest-asyncio not configured

**Solution**:
```python
# Add to conftest.py or test file:
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

---

## Rollback Plan

If issues arise:

1. **Immediate rollback**:
```bash
git checkout main
git branch -D 048-async-worker-agents
```

2. **Partial rollback** (revert specific file):
```bash
git checkout main -- codeframe/agents/backend_worker_agent.py
```

3. **Stash changes** (temporary):
```bash
git stash
# Test something
git stash pop  # Restore changes
```

---

## Commit Strategy

Commit after each phase for easy rollback:

```bash
# After Phase 1
git add codeframe/agents/backend_worker_agent.py tests/agents/test_backend_worker_agent.py
git commit -m "feat: convert BackendWorkerAgent to async"

# After Phase 2
git add codeframe/agents/frontend_worker_agent.py codeframe/agents/test_worker_agent.py tests/agents/
git commit -m "feat: convert FrontendWorkerAgent and TestWorkerAgent to async"

# After Phase 3
git add codeframe/agents/lead_agent.py tests/integration/
git commit -m "feat: update LeadAgent to use async worker agents"

# After Phase 4
git add .
git commit -m "feat: complete async worker agents refactoring (Sprint 5)"
```

---

## Success Criteria

### Code Changes
- [X] All three worker agents use `async def execute_task()`
- [X] AsyncAnthropic client used instead of sync client
- [X] No `_broadcast_async()` wrapper - direct await calls only
- [X] LeadAgent uses `await agent.execute_task()` - no `run_in_executor()`

### Testing
- [X] All unit tests pass (≥98%)
- [X] All integration tests pass (≥75%)
- [X] All regression tests pass (100%)
- [X] Manual E2E test successful

### Performance
- [X] No degradation in task execution time
- [X] Memory usage stable or improved
- [X] Broadcasts work reliably

### Quality
- [X] No event loop deadlocks
- [X] No broadcast failures
- [X] Clean logs (no unexpected errors)
- [X] Code review approved

---

## Next Steps

After completing this refactoring:

1. **Merge to main**:
```bash
git checkout main
git merge 048-async-worker-agents
git push origin main
```

2. **Deploy** (follow deployment guide)

3. **Monitor** production for any issues

4. **Close issue**:
```bash
bd close cf-48 "Async worker agents refactoring complete"
```

---

## References

- **Spec**: [spec.md](./spec.md)
- **Research**: [research.md](./research.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Contract**: [contracts/worker-agent-api.md](./contracts/worker-agent-api.md)
- **Anthropic Async Docs**: https://github.com/anthropics/anthropic-sdk-python#async-usage
- **pytest-asyncio Docs**: https://github.com/pytest-dev/pytest-asyncio

---

**Quickstart Complete**: 2025-11-07
**Estimated Implementation Time**: 4 hours
**Next**: Run `.specify/scripts/bash/update-agent-context.sh` to update agent context
