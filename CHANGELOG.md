# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **BREAKING**: Converted worker agents to async/await pattern (cf-48)
  - `BackendWorkerAgent.execute_task()` is now async
  - `FrontendWorkerAgent.execute_task()` is now async
  - `TestWorkerAgent.execute_task()` is now async
  - All internal agent methods now use async/await
  - Replaced `Anthropic` client with `AsyncAnthropic`
  - Removed `_broadcast_async()` threading wrapper from all worker agents
  - `LeadAgent` now calls worker agents directly with `await` (removed `run_in_executor()`)

### Fixed
- Resolved event loop deadlocks in worker agent broadcasts
- Eliminated threading overhead in agent task execution
- Improved WebSocket broadcast reliability with direct async calls

### Technical Details
- **Files Modified**:
  - `codeframe/agents/backend_worker_agent.py`: Full async conversion
  - `codeframe/agents/frontend_worker_agent.py`: Full async conversion
  - `codeframe/agents/test_worker_agent.py`: Full async conversion
  - `codeframe/agents/lead_agent.py`: Removed threading wrapper
- **Net Changes**: -115 lines (simpler, cleaner code)
- **Broadcast Pattern**: Direct `await broadcast_*()` calls instead of `run_coroutine_threadsafe()`
- **Migration Impact**: Existing tests require async updates (`@pytest.mark.asyncio` and `await` calls)

### Migration Guide for Test Updates
Tests that call worker agent methods need to be updated:
```python
# Before (synchronous)
def test_execute_task(agent):
    result = agent.execute_task(task)

# After (asynchronous)
@pytest.mark.asyncio
async def test_execute_task(agent):
    result = await agent.execute_task(task)
```

See: `specs/048-async-worker-agents/quickstart.md` for detailed migration instructions.
