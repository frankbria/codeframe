# Sprint 4 Code Review Troubleshooting Plan

**PR**: feat(sprint-4): Multi-Agent Coordination Backend Implementation
**Status**: 109 passing unit tests, integration tests hanging
**Review Source**: CodeRabbit AI automated review
**Date**: 2025-10-25

---

## Executive Summary

The PR has **comprehensive unit test coverage (109 passing tests)** but faces **13 actionable issues** and **43 nitpick items** from automated review. The primary blocker is the **integration test hanging issue** which prevents verification of the multi-agent orchestration system end-to-end.

### Issue Severity Breakdown

| Category | Count | Priority | Risk Level |
|----------|-------|----------|------------|
| **Critical Blockers** | 1 | 🔴 P0 | High |
| **Functionality Issues** | 6 | 🟡 P1 | Medium |
| **Code Quality** | 6 | 🟢 P2 | Low |
| **Nitpicks** | 43 | ⚪ P3 | Minimal |

---

## 🔴 CRITICAL BLOCKER (P0)

### Issue 1: Integration Tests Hanging Indefinitely

**Files**: `tests/test_multi_agent_integration.py`, `codeframe/agents/lead_agent.py:1079-1149`
**Impact**: Cannot verify multi-agent coordination works end-to-end
**Root Cause Hypothesis**: Infinite loop in `start_multi_agent_execution()` coordination loop

#### Symptoms
```python
# All 11 integration tests hang at asyncio.run() or asyncio.wait()
tests/test_multi_agent_integration.py ...... 11 tests (all hang)
```

#### Suspected Root Causes

1. **Infinite Loop in Coordination**
   - `_all_tasks_complete()` logic may not detect completion correctly
   - Task assignment loop may not exit when all tasks done
   - Dependency resolution may create deadlock scenarios

2. **Async Event Loop Issues**
   - Nested event loops (mixing `asyncio.run()` in sync tests)
   - Tasks not being properly awaited or cancelled
   - Background broadcast tasks preventing shutdown

3. **Mock Configuration**
   - Mocks may not simulate completion states correctly
   - Agent execution mocks may not trigger proper callbacks

#### Troubleshooting Steps

**Step 1: Add Comprehensive Instrumentation**
```python
# codeframe/agents/lead_agent.py:1079-1149
async def start_multi_agent_execution(self):
    logger.info("🚀 Multi-agent execution started")
    iteration_count = 0
    max_iterations = 1000  # Safety watchdog

    while not self._all_tasks_complete():
        iteration_count += 1
        if iteration_count > max_iterations:
            logger.error(f"❌ WATCHDOG: Hit max iterations {max_iterations}")
            break

        logger.debug(f"🔄 Coordination loop iteration {iteration_count}")
        logger.debug(f"📊 Ready tasks: {len(ready_tasks)}")
        logger.debug(f"🏃 Running tasks: {len(running_tasks)}")
        logger.debug(f"✅ Completed: {completed_count}/{total_count}")

        # ... existing logic with more logging ...
```

**Step 2: Fix `_all_tasks_complete()` Logic**
```python
# codeframe/agents/lead_agent.py:1234-1248
def _all_tasks_complete(self) -> bool:
    """Check if all tasks are complete with detailed logging."""
    tasks = self.db.get_project_tasks(self.project_id)

    incomplete = [t for t in tasks if t.status not in ("completed", "failed")]
    blocked = [t for t in tasks if t.status == "blocked"]

    logger.debug(f"Task status: {len(incomplete)} incomplete, {len(blocked)} blocked")

    # Deadlock detection: if all remaining tasks are blocked, we're deadlocked
    if incomplete and all(t.status == "blocked" for t in incomplete):
        logger.error(f"❌ DEADLOCK: All {len(incomplete)} remaining tasks are blocked")
        return True  # Force exit to prevent infinite loop

    return len(incomplete) == 0
```

**Step 3: Add Timeout and Graceful Shutdown**
```python
# codeframe/agents/lead_agent.py
async def start_multi_agent_execution(self, timeout: int = 300):
    """Execute with timeout to prevent infinite hangs."""
    try:
        async with asyncio.timeout(timeout):
            await self._execute_coordination_loop()
    except asyncio.TimeoutError:
        logger.error(f"❌ Execution timed out after {timeout}s")
        # Cleanup: cancel running tasks, retire agents
        await self._emergency_shutdown()
        raise
```

**Step 4: Fix Test Async Usage**
```python
# tests/test_multi_agent_integration.py
@pytest.mark.asyncio
async def test_circular_dependency_detection(self, lead_agent, db, project_id):
    """Test proper async invocation, not nested asyncio.run()."""
    # ... setup tasks with circular dependencies ...

    with pytest.raises(ValueError, match="Circular dependencies detected"):
        await lead_agent.start_multi_agent_execution()  # Not asyncio.run()
```

**Step 5: Reduce Integration Test Scope**
```python
# Create minimal integration test that can succeed quickly
@pytest.mark.asyncio
async def test_single_task_execution_minimal(self, lead_agent, db, project_id):
    """Simplest possible integration test - 1 task, 1 agent."""
    task = db.create_task(
        project_id=project_id,
        title="Simple test",
        task_type="backend",
        depends_on=[]
    )

    # Mock agent execution to complete immediately
    with patch.object(BackendWorkerAgent, "execute_task", return_value=...):
        result = await asyncio.wait_for(
            lead_agent.start_multi_agent_execution(),
            timeout=5.0  # Fail fast
        )

    assert result["completed"] == 1
```

#### Action Items

- [ ] Add watchdog counter (max 1000 iterations) with emergency exit
- [ ] Add detailed logging at every loop decision point
- [ ] Fix `_all_tasks_complete()` to detect deadlocks
- [ ] Add `asyncio.timeout()` wrapper with cleanup
- [ ] Convert integration tests to `@pytest.mark.asyncio` (no `asyncio.run()`)
- [ ] Create minimal passing integration test first
- [ ] Add instrumentation to track: ready_tasks count, running_tasks count, completed count, blocked count per iteration

#### Success Criteria

1. ✅ At least 1 integration test passes within 5 seconds
2. ✅ Watchdog never triggers in successful execution
3. ✅ Deadlock detection logs appear when circular deps exist
4. ✅ All integration tests pass or explicitly fail (no hangs)

---

## 🟡 FUNCTIONALITY ISSUES (P1)

### Issue 2: Agent Pool Status Mismatch (UI vs Backend)

**Files**: `codeframe/agents/agent_pool_manager.py:24-31`, `web-ui/src/types/index.ts:131-136`
**Impact**: Frontend displays wrong agent status; confuses users

#### Problem
```python
# Backend uses: "idle", "busy", "blocked"
agent_info["status"] = "busy"

# Frontend expects: "idle", "working", "blocked", "offline"
type AgentStatus = "idle" | "working" | "blocked" | "offline";
```

#### Solution
```python
# codeframe/agents/agent_pool_manager.py
def _status_for_ui(self, internal_status: str) -> str:
    """Map internal status to UI-compatible status."""
    mapping = {
        "idle": "idle",
        "busy": "working",  # Map busy → working
        "blocked": "blocked"
    }
    return mapping.get(internal_status, "offline")

def get_agent_status(self) -> Dict[str, Dict[str, Any]]:
    # ... existing code ...
    status[agent_id] = {
        "status": self._status_for_ui(agent_info["status"]),  # Convert
        # ... other fields ...
    }
```

#### Action Items
- [ ] Add `_status_for_ui()` mapping function
- [ ] Update `get_agent_status()` to use mapping
- [ ] Update WebSocket broadcasts to use consistent status
- [ ] Add UI status enum validation test

---

### Issue 3: Dependency Validation Accepts Invalid Task IDs

**Files**: `codeframe/agents/dependency_resolver.py:208-235`
**Impact**: Cycle detection may fail if unknown task IDs are used

#### Problem
```python
def validate_dependency(self, task_id: int, depends_on_id: int) -> bool:
    # Currently adds dependency even if depends_on_id not in all_tasks
    self.dependencies[task_id].add(depends_on_id)  # ❌ No validation
```

#### Solution
```python
def validate_dependency(self, task_id: int, depends_on_id: int) -> bool:
    """Validate dependency between two tasks."""
    # Guard against unknown task IDs
    if task_id not in self.all_tasks:
        logger.warning(f"Unknown task_id in validation: {task_id}")
        return False
    if depends_on_id not in self.all_tasks:
        logger.warning(f"Unknown depends_on_id in validation: {depends_on_id}")
        return False

    # Temporarily add dependency for cycle check
    self.dependencies[task_id].add(depends_on_id)
    # ... rest of validation ...
```

#### Action Items
- [ ] Add task ID existence checks
- [ ] Add unit test for validation with unknown IDs
- [ ] Update error logging

---

### Issue 4: WebSocket Broadcasts Use Truthiness Instead of `is not None`

**Files**: `codeframe/ui/websocket_broadcasts.py:105-111, 234-239, 493-495, 63-65`
**Impact**: Agent ID 0 or empty strings may be skipped incorrectly

#### Problem
```python
if current_task_id:  # ❌ Skips ID 0
    message["current_task"] = {...}

if agent_id:  # ❌ Skips agent_id=0
    message["agent_id"] = agent_id
```

#### Solution
```python
if current_task_id is not None:  # ✅ Correct
    message["current_task"] = {...}

if agent_id is not None:  # ✅ Correct
    message["agent_id"] = agent_id
```

#### Action Items
- [ ] Replace all truthiness checks with `is not None`
- [ ] Add unit test with `agent_id=0` and `task_id=0`
- [ ] Audit codebase for similar pattern

---

### Issue 5: Subprocess Pytest Execution Missing `cwd` and Explicit Executable

**Files**: `codeframe/agents/test_worker_agent.py:418-424`
**Impact**: Tests may fail due to PATH issues or wrong Python interpreter

#### Problem
```python
result = subprocess.run(
    ["pytest", str(test_file), "-v", "--tb=short"],  # ❌ Relies on PATH
    capture_output=True,
    text=True,
    timeout=60
)
```

#### Solution
```python
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
    capture_output=True,
    text=True,
    timeout=60,
    cwd=str(self.project_root)  # Explicit working directory
)
```

#### Action Items
- [ ] Use `sys.executable` instead of `"pytest"`
- [ ] Add `cwd` parameter
- [ ] Test in virtual environment to verify
- [ ] Apply same fix to `_correct_failing_tests()`

---

### Issue 6: Agent Pool Returns Mutable References in `get_agent_status()`

**Files**: `codeframe/agents/agent_pool_manager.py:262-273`
**Impact**: Callers can accidentally mutate internal pool state

#### Problem
```python
status[agent_id] = {
    "blocked_by": agent_info.get("blocked_by")  # ❌ Returns list reference
}
# Caller could do: status[agent_id]["blocked_by"].append(999)
```

#### Solution
```python
status[agent_id] = {
    "blocked_by": list(agent_info["blocked_by"]) if agent_info.get("blocked_by") else None
}
```

#### Action Items
- [ ] Return deep copies of `blocked_by`
- [ ] Add unit test that mutates returned status
- [ ] Consider using `copy.deepcopy()` for entire status dict

---

### Issue 7: `blocked_by` Not Cleared When Agent Becomes Idle

**Files**: `codeframe/agents/agent_pool_manager.py:195-200`
**Impact**: Agents may show stale "blocked" reasons in UI

#### Problem
```python
def mark_agent_idle(self, agent_id: str, task_id: int) -> None:
    self.agent_pool[agent_id]["status"] = "idle"
    self.agent_pool[agent_id]["current_task"] = None
    # ❌ blocked_by not cleared
```

#### Solution
```python
def mark_agent_idle(self, agent_id: str, task_id: int) -> None:
    self.agent_pool[agent_id]["status"] = "idle"
    self.agent_pool[agent_id]["current_task"] = None
    self.agent_pool[agent_id]["blocked_by"] = None  # ✅ Clear blocked state
```

#### Action Items
- [ ] Clear `blocked_by` when marking idle
- [ ] Add test: block agent → mark idle → verify blocked_by is None
- [ ] Verify UI updates correctly

---

## 🟢 CODE QUALITY IMPROVEMENTS (P2)

### Issue 8: Broad Exception Handling Without Stack Traces

**Files**: Multiple (`frontend_worker_agent.py:199-215`, `test_worker_agent.py:197-207`, etc.)
**Impact**: Debugging is harder without full stack traces

#### Solution Pattern
```python
# Before
except Exception as e:
    logger.error(f"Task failed: {e}")

# After
except Exception:
    logger.exception("Task failed")  # Includes full traceback
```

#### Action Items
- [ ] Replace all `logger.error(f"... {e}")` with `logger.exception()`
- [ ] Add specific exception types where possible
- [ ] Create automated linter rule to catch pattern

---

### Issue 9: Unused Parameters and Variables

**Files**: Multiple test files and agent implementations
**Impact**: Code smell, potential bugs

#### Examples
```python
# Unused loop variable
for i, word in enumerate(words):  # 'i' never used
    process(word)

# Unused fixture
@pytest.fixture
def frontend_agent(temp_web_ui_dir, monkeypatch):  # 'monkeypatch' unused
```

#### Action Items
- [ ] Prefix unused params with `_` (e.g., `_monkeypatch`)
- [ ] Remove truly unused code
- [ ] Enable Ruff ARG001 check in CI

---

### Issue 10: Hard Dependencies on `anthropic.types` in Tests

**Files**: `tests/test_frontend_worker_agent.py:8-10`, `tests/test_test_worker_agent.py:5-12`
**Impact**: Tests fail if Anthropic SDK not installed; tight coupling

#### Solution
```python
# Before
from anthropic.types import Message, TextBlock
mock_message = Mock(spec=Message)

# After
mock_message = Mock()  # Duck typing, no import needed
mock_message.content = [Mock(text="...")]
```

#### Action Items
- [ ] Remove `anthropic.types` imports from test files
- [ ] Use plain `Mock()` without `spec=`
- [ ] Verify tests pass without anthropic package installed

---

### Issue 11: Lazy Import of Anthropic in Production Code

**Files**: `codeframe/agents/test_worker_agent.py:15-16`
**Impact**: ImportError if package missing

#### Solution
```python
# Before (top-level import)
from anthropic import Anthropic

# After (lazy import)
def __init__(self, ...):
    self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if self.api_key:
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
        except ImportError:
            logger.warning("anthropic package not installed, using template fallback")
            self.client = None
    else:
        self.client = None
```

#### Action Items
- [ ] Move Anthropic import inside method/conditional
- [ ] Add graceful fallback to template generation
- [ ] Document optional dependency in README

---

### Issue 12: Missing Language Tags in Markdown Code Blocks

**Files**: `specs/004-multi-agent-coordination/SPRINT4-COMPLETION-STATUS.md:88-101`
**Impact**: Linter warnings, poor rendering

#### Solution
````markdown
```text
tests/test_frontend_worker_agent.py .......... 28 passed
```
````

#### Action Items
- [ ] Add language tags to all fenced code blocks
- [ ] Run markdownlint and fix all MD040 violations
- [ ] Add pre-commit hook for markdown linting

---

### Issue 13: Absolute Filesystem Paths in Documentation

**Files**: `specs/004-multi-agent-coordination/PROGRESS.md:122-130`, `SPRINT4-COMPLETION-STATUS.md:75-80`
**Impact**: Breaks for other developers, leaks local environment

#### Examples
```markdown
❌ **File**: `/home/frankbria/projects/codeframe/tests/test_multi_agent_integration.py`
✅ **File**: `tests/test_multi_agent_integration.py`
```

#### Action Items
- [ ] Replace all absolute paths with repo-relative paths
- [ ] Add linter rule to catch absolute paths
- [ ] Audit all documentation files

---

## ⚪ NITPICKS (P3) - 43 Items

**Not blocking merge**, but should be addressed in cleanup pass:

- Type narrowing in TypeScript (use enums instead of strings)
- Test timeout optimization (mock TimeoutExpired instead of waiting 60s)
- Consistent checkbox syntax in markdown
- Minor code formatting and style issues
- Variable naming improvements
- Documentation typos

**Recommendation**: Create separate "cleanup" PR after merge to address all nitpicks in batch.

---

## Implementation Plan

### Phase 1: Critical Blocker Resolution (P0) - 🔴 MUST DO BEFORE MERGE

**Goal**: Fix integration test hanging issue
**Timeline**: 2-4 hours
**Owner**: Lead developer

**Tasks**:
1. Add watchdog counter and logging to `start_multi_agent_execution()`
2. Fix `_all_tasks_complete()` deadlock detection
3. Add `asyncio.timeout()` wrapper
4. Convert integration tests to proper async
5. Create minimal passing integration test
6. Verify all tests pass or fail explicitly (no hangs)

**Success Criteria**: At least 1 integration test passes cleanly

---

### Phase 2: Functionality Fixes (P1) - 🟡 SHOULD DO BEFORE MERGE

**Goal**: Fix bugs that affect runtime behavior
**Timeline**: 1-2 hours
**Owner**: Developer team

**Priority Order**:
1. Fix agent status mismatch (UI impact)
2. Fix WebSocket truthiness checks (correctness)
3. Fix subprocess pytest invocation (reliability)
4. Fix dependency validation (correctness)
5. Fix agent pool mutations (defensive programming)
6. Clear blocked_by on idle (UI consistency)

**Success Criteria**: All unit tests still pass, manual testing shows correct behavior

---

### Phase 3: Code Quality (P2) - 🟢 CAN DO AFTER MERGE

**Goal**: Improve maintainability and debugging
**Timeline**: 1 hour
**Owner**: Any developer

**Tasks**:
- Use `logger.exception()` everywhere
- Remove unused code
- Fix test dependencies
- Lazy import Anthropic
- Fix markdown linting
- Remove absolute paths

**Success Criteria**: Linters pass, code review feedback addressed

---

### Phase 4: Nitpick Cleanup (P3) - ⚪ OPTIONAL POST-MERGE

**Goal**: Polish code to perfection
**Timeline**: 30 minutes
**Owner**: Junior developer (good learning task)

**Tasks**: Create separate "cleanup" PR with all 43 nitpick fixes

---

## Testing Strategy

### Pre-Merge Testing Checklist

- [ ] Run full unit test suite: `pytest tests/ -v`
- [ ] Verify 109+ tests pass (including new fixes)
- [ ] Run integration tests with timeout: `pytest tests/test_multi_agent_integration.py --timeout=10`
- [ ] Verify at least 1 integration test passes
- [ ] Manual test: Create project → Add tasks with dependencies → Execute
- [ ] Verify UI shows correct agent status
- [ ] Check WebSocket messages in browser devtools
- [ ] Run linters: `ruff check .`
- [ ] Run type checker: `mypy codeframe/`

### Post-Fix Regression Testing

After each fix:
1. Run affected unit tests
2. Run full test suite
3. Check for new failures
4. Update tests if needed

---

## Risk Assessment

### Risks of Merging Now (Without P0 Fix)

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Multi-agent coordination silently fails in production | 🔴 High | 🟡 Medium | ❌ **BLOCKER** - Must fix P0 first |
| Infinite loops in production environment | 🔴 High | 🟡 Medium | ❌ **BLOCKER** - Add watchdog |
| Cannot debug production issues | 🔴 High | 🟢 Low | Add comprehensive logging |

### Risks of Merging After P0 + P1 Fixes

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Minor UI glitches | 🟡 Medium | 🟢 Low | ✅ Fixed by P1 items |
| Debugging takes longer | 🟢 Low | 🟡 Medium | ✅ Fixed by P2 items |
| Code style complaints | ⚪ Minimal | 🟡 Medium | Address in follow-up PR |

**Recommendation**: Merge after completing P0 + P1. Do P2 + P3 in follow-up PR.

---

## Timeline Estimate

| Phase | Tasks | Est. Time | Can Parallelize? |
|-------|-------|-----------|------------------|
| P0: Integration Test Fix | 6 tasks | 2-4 hours | No (complex debugging) |
| P1: Functionality Fixes | 6 fixes | 1-2 hours | Yes (independent fixes) |
| P2: Code Quality | 6 improvements | 1 hour | Yes |
| P3: Nitpick Cleanup | 43 items | 30 min | Yes |
| **Total (P0+P1 only)** | **12 critical items** | **3-6 hours** | Partial |
| **Total (All phases)** | **61 total items** | **4.5-7.5 hours** | Partial |

**Recommended Approach**: Complete P0 + P1 (3-6 hours), then merge. Schedule P2 + P3 for next sprint.

---

## Success Metrics

### Definition of Done for Merge

✅ **Must Have** (P0 + P1):
- [ ] At least 1 integration test passes without hanging
- [ ] All integration tests either pass or fail (no hangs > 10s)
- [ ] All 109+ unit tests pass
- [ ] Agent status mapping correct (UI displays "working" not "busy")
- [ ] WebSocket broadcasts use `is not None` checks
- [ ] Subprocess pytest uses `sys.executable` and `cwd`
- [ ] Dependency validation rejects unknown task IDs
- [ ] Agent pool returns copies (no mutable references)
- [ ] `blocked_by` cleared when marking idle

🎯 **Nice to Have** (P2):
- [ ] All exceptions use `logger.exception()`
- [ ] No unused code/parameters
- [ ] Anthropic imports are lazy
- [ ] Markdown lint passes
- [ ] No absolute paths in docs

⚪ **Optional** (P3):
- [ ] All 43 nitpicks addressed (can defer to follow-up PR)

### Quality Gates

| Gate | Threshold | Current | Status |
|------|-----------|---------|--------|
| Unit Test Pass Rate | 100% | 100% (109/109) | ✅ PASS |
| Integration Test Pass Rate | ≥50% | 0% (0/11) | ❌ FAIL |
| Integration Test Hang Rate | 0% | 100% (11/11) | ❌ FAIL |
| Code Coverage | ≥80% | Unknown | ⚠️ MEASURE |
| Linter Errors | 0 critical | Unknown | ⚠️ MEASURE |
| Type Errors | 0 | Unknown | ⚠️ MEASURE |

**Current Status**: **NOT READY FOR MERGE** until integration test hanging is fixed.

---

## Communication Plan

### Stakeholder Updates

**To Team**:
- Share this troubleshooting plan immediately
- Daily standups: Report progress on P0 fix
- Demo: Show passing integration test when fixed

**To Management**:
- Expected delay: 3-6 hours for critical fixes
- Confidence level: High (unit tests prove components work)
- Risk if we merge now: High (untested orchestration in production)

### Documentation Updates

After fixes:
- [ ] Update PR description with fix summary
- [ ] Update `claudedocs/sprint4-integration-test-issue.md` with resolution
- [ ] Add "Lessons Learned" section to sprint retrospective
- [ ] Update SPRINT4-COMPLETION-STATUS.md with final metrics

---

## Appendix: Quick Reference

### Files Requiring Changes

**P0 (Critical)**:
- `codeframe/agents/lead_agent.py:1079-1149` (add watchdog, logging, timeout)
- `codeframe/agents/lead_agent.py:1234-1248` (fix `_all_tasks_complete()`)
- `tests/test_multi_agent_integration.py` (convert to proper async)

**P1 (Important)**:
- `codeframe/agents/agent_pool_manager.py:24-31, 195-200, 262-273` (status mapping, clear blocked_by, return copies)
- `codeframe/agents/dependency_resolver.py:208-235` (validate task IDs)
- `codeframe/ui/websocket_broadcasts.py:105-111, 234-239, 493-495, 63-65` (use `is not None`)
- `codeframe/agents/test_worker_agent.py:418-424` (fix subprocess invocation)

### Commands for Testing

```bash
# Run unit tests only
pytest tests/ -v --ignore=tests/test_multi_agent_integration.py

# Run integration tests with timeout
pytest tests/test_multi_agent_integration.py -v --timeout=10

# Run with coverage
pytest --cov=codeframe --cov-report=html tests/

# Run linters
ruff check codeframe/ tests/
mypy codeframe/

# Run markdown linter
markdownlint specs/ claudedocs/
```

### Developer Onboarding

New developers fixing issues should:
1. Read this entire troubleshooting plan first
2. Start with P0 issues (highest impact)
3. Run tests after each change
4. Ask for help if stuck > 30 minutes
5. Document any new findings in this plan

---

## Notes for PR Author

**Dear frankbria**,

Your Sprint 4 implementation is **architecturally sound** with **excellent unit test coverage (109 tests)**. The code review found mostly **minor quality issues** and **one critical blocker** (integration test hanging).

**Recommended Actions**:
1. **Fix P0 first** (integration test hanging) - this is the merge blocker
2. **Then fix P1** (6 functionality issues) - low risk, high value
3. **Merge the PR** - you've earned it with 109 passing tests!
4. **Schedule P2 + P3** for next sprint - they're polish items

**Confidence Level**: High. The hanging issue is likely a simple async loop bug that will be obvious once you add the instrumentation suggested above.

**Estimated Time to Merge-Ready**: 3-6 hours of focused debugging.

Good luck! 🚀

---

**Document Version**: 1.0
**Last Updated**: 2025-10-25
**Next Review**: After P0 fix is complete
