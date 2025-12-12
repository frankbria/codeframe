# Test Fixes Required for Router Refactoring

**Total Tests to Fix:** 19 (15 import-related, 4 test runner issues)

---

## Fix 1: tests/test_review_api.py (9 errors)

### Issue
Tests try to access `server.review_cache` which moved to `codeframe.ui.shared.review_cache`

### Current Code (Line 49)
```python
# Clear review cache before each test
server.review_cache.clear()
```

### Fixed Code
```python
# Import at top of file
from codeframe.ui.shared import review_cache

# In fixture:
# Clear review cache before each test
review_cache.clear()
```

### Tests Affected
- `test_post_review_endpoint_exists`
- `test_post_review_endpoint_validates_request`
- `test_post_review_endpoint_runs_quality_checks`
- `test_post_review_endpoint_creates_blocker_on_failure`
- `test_get_review_status_endpoint_exists`
- `test_get_review_status_no_review_yet`
- `test_get_review_stats_endpoint_exists`
- `test_get_review_stats_aggregates_correctly`
- `test_get_review_stats_no_reviews_yet`

---

## Fix 2: tests/agents/test_agent_lifecycle.py (2 failures)

### Issue
Tests try to access `server.start_agent` which moved to `codeframe.ui.shared.start_agent`

### Search for
```python
server.start_agent
```

### Replace with
```python
# Import at top of file
from codeframe.ui.shared import start_agent

# Use directly:
start_agent(...)
```

### Tests Affected
- `test_start_agent_endpoint_returns_202_accepted`
- `test_start_agent_endpoint_handles_already_running`

---

## Fix 3: tests/api/test_chat_api.py (4 failures)

### Issue
Tests try to access `server.running_agents` which moved to `codeframe.ui.shared.running_agents`

### Search for
```python
server.running_agents
```

### Replace with
```python
# Import at top of file
from codeframe.ui.shared import running_agents

# Use directly:
running_agents[...]
running_agents.clear()
```

### Tests Affected
- `test_send_message_success`
- `test_send_message_agent_not_started`
- `test_chat_broadcasts_message`
- `test_chat_continues_when_broadcast_fails`

---

## Fix 4: tests/testing/test_test_runner.py (4 failures)

### Issue
Tests expect 'passed'/'failed' status but getting 'error' status

### Tests Affected
- `test_run_tests_with_real_pytest_passing`
- `test_run_tests_with_real_pytest_failing`
- `test_run_tests_with_real_pytest_errors`
- `test_run_tests_with_specific_test_paths`

### Action Required
1. Review `codeframe/testing/test_runner.py` implementation
2. Check pytest subprocess execution logic
3. Verify status parsing from pytest output
4. May be unrelated to router refactoring (needs investigation)

---

## Verification Commands

### Run Fixed Tests
```bash
# After fixing test_review_api.py
uv run pytest tests/test_review_api.py -v

# After fixing test_agent_lifecycle.py
uv run pytest tests/agents/test_agent_lifecycle.py -v

# After fixing test_chat_api.py
uv run pytest tests/api/test_chat_api.py -v

# After investigating test_test_runner.py
uv run pytest tests/testing/test_test_runner.py::TestTestRunnerRealPytestExecution -v
```

### Run Full Test Suite
```bash
uv run pytest tests/ --ignore=tests/debug/ -v
```

### Expected Result
- All 1,843+ tests should pass (100% pass rate)
- Zero errors
- Coverage should remain at 78%+ (88% after router test additions)

---

## Additional Fixes

### Minor: Duplicate Operation ID Warning

**File:** `codeframe/ui/routers/session.py`

**Issue:** Duplicate operation ID `get_session_state_api_projects__project_id__session_get`

**Fix:**
```python
@router.get(
    "/api/projects/{project_id}/session",
    operation_id="get_project_session_state",  # Add unique ID
    tags=["session"]
)
async def get_session_state(...):
    ...
```

---

## Estimated Fix Time

| Task | Time |
|------|------|
| Fix test_review_api.py | 10 min |
| Fix test_agent_lifecycle.py | 5 min |
| Fix test_chat_api.py | 10 min |
| Fix duplicate operation ID | 5 min |
| Investigate test_test_runner.py | 1-2 hours |
| **Total (excluding investigation)** | **30 min** |

---

## Success Criteria

After fixes:
- ✅ All 1,852 tests passing (100% pass rate)
- ✅ Zero errors
- ✅ No duplicate operation ID warnings
- ✅ Coverage maintained at 78%+
- ✅ All 54 OpenAPI endpoints documented

---

**Created:** 2025-12-11
**Status:** Ready to implement
**Priority:** High (blocking Phase 10 completion)
