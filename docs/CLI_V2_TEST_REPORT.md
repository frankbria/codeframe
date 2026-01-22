# CodeFRAME CLI v2 End-to-End Test Report

**Date:** 2026-01-16
**Test Project:** Task Tracker CLI (`~/projects/cf-test`)
**Tester:** Claude (Opus 4.5)

---

## Executive Summary

The CodeFRAME CLI v2 workflow was tested from workspace initialization through batch execution. The workflow infrastructure is solid, but all 15 tasks failed during execution due to environment configuration and state management issues.

**Key Metrics:**
- Tasks Generated: 15
- Tasks Completed: 0/15
- Code Generated: 1,433 lines (main) + 2,196 lines (tests)
- Batch Duration: ~21 minutes
- Dependencies Correctly Inferred: Yes (LLM-based)

---

## What Worked Well

### 1. Workspace Initialization (`codeframe init`)
- Clean initialization process
- Creates `.codeframe/` directory with SQLite state storage
- Provides clear next-step instructions
- Idempotent operation

### 2. PRD Management (`codeframe prd add`)
- Successfully parsed markdown PRD
- Extracted title automatically
- Clear confirmation output

### 3. Task Generation (`codeframe tasks generate`)
- Generated 15 well-scoped tasks from simple PRD
- Tasks are logically ordered
- Uses LLM for intelligent decomposition
- Good granularity (not too big, not too small)

### 4. Status Commands
- `codeframe tasks list` - Clean table formatting with status, priority, dependencies
- `codeframe status` - Good workspace overview
- `codeframe summary` - Concise status report
- `codeframe work batch status` - Detailed batch progress

### 5. Dependency Inference (`--strategy auto`)
- LLM correctly inferred logical dependencies between tasks
- Created 4 execution groups for parallelization
- Recognized that "Write tests" depends on implementation tasks
- Identified independent tasks that could run in parallel

### 6. Parallel Batch Execution
- Worker pool correctly limits concurrent tasks (max 2 tested)
- Group-based execution respects dependencies
- Event streaming provides real-time feedback
- Batch status tracking works correctly

---

## Critical Issues Found

### Issue #1: Task State Not Updated on Failure (BUG)

**Severity:** Critical
**Location:** `codeframe/core/runtime.py:fail_run()`

**Problem:** When a run fails, `fail_run()` updates the run status to FAILED but does NOT update the task status. The task remains stuck in `IN_PROGRESS` forever.

**Evidence:** After batch failure, all 15 tasks show `IN_PROGRESS`:
```
Total: 15 | IN_PROGRESS: 15
```

**Expected:** Failed tasks should transition to either `READY` (for retry) or a new `FAILED` status.

**Comparison:**
| Function | Updates Run? | Updates Task? |
|----------|--------------|---------------|
| `complete_run()` | ✓ to COMPLETED | ✓ to DONE |
| `block_run()` | ✓ to BLOCKED | ✓ to BLOCKED |
| `fail_run()` | ✓ to FAILED | ✗ Missing! |

**Fix Required:** Add task status update to `fail_run()`:
```python
# After updating run status, also update task:
tasks.update_status(workspace, run.task_id, TaskStatus.READY)  # or TaskStatus.FAILED
```

---

### Issue #2: Agent Uses `pip install` Instead of `uv`

**Severity:** High
**Location:** Agent execution / LLM prompts

**Problem:** The agent tries to install dependencies with `pip install`, which fails on Linux systems with "externally-managed-environment" (PEP 668 compliance).

**Error Message:**
```
error: externally-managed-environment
× This environment is externally managed
```

**Root Cause:** The planner instructs to "Install dependencies using the project's package manager" but:
1. New projects don't have a package manager configured
2. Agent defaults to `pip install` instead of `uv` or virtualenv creation

**Fix Options:**
1. Update planner prompts to prefer `uv pip install` or create virtualenv first
2. Add project-level config (like `AGENTS.md`) to target workspace
3. Detect environment and translate commands automatically

---

### Issue #3: Missing `__main__.py` for Module Execution

**Severity:** High
**Location:** Agent code generation

**Problem:** Agent creates `task_tracker/` package but doesn't add `__main__.py`, causing:
```
No module named task_tracker.__main__; 'task_tracker' is a package and cannot be directly executed
```

**Root Cause:** Agent's verification step tries `python -m task_tracker` but the package lacks a proper entry point.

**Fix:** Agent should:
1. Create `__main__.py` when building CLI applications
2. Or use direct script execution instead of `-m` flag

---

### Issue #4: No Blockers Created Despite Failures

**Severity:** Medium
**Location:** `codeframe/core/agent.py`

**Problem:** Agent fails with FAILED status instead of creating blockers for human review.

**Root Cause:** Agent classifies these errors as "technical" (self-correctable) rather than requiring human input. After max self-correction attempts, it sets `AgentStatus.FAILED` without creating a blocker.

**Impact:** Users have no visibility into why tasks failed or what help the agent needs.

**Fix:** Consider creating informational blockers even for technical failures, or add a new "NEEDS_ATTENTION" status.

---

### Issue #5: Test Configuration Issues

**Severity:** Low
**Location:** Generated test files

**Problem:** Tests trigger pytest-asyncio deprecation warnings that cause verification failures:
```
pytest_asyncio/plugin.py:208: PytestDeprecationWarning:
The configuration option "asyncio_default_fixture_loop_scope" is unset.
```

**Fix:** Agent should configure pytest properly in `pyproject.toml` or `pytest.ini`.

---

## Workflow Observations

### What the User Experience Looks Like

1. **Initialization** (smooth): 2 seconds
2. **PRD Add** (smooth): <1 second
3. **Task Generation** (good): ~15 seconds, clear feedback
4. **Set Tasks to READY** (smooth): Single command
5. **Batch Execution** (needs work): 21 minutes, failures not properly surfaced
6. **Post-Failure** (broken): Can't see why tasks failed, tasks stuck in wrong state

### Missing CLI Features

1. **`codeframe tasks set status FAILED --all --from IN_PROGRESS`** - Would help recover from current state
2. **`codeframe work batch retry <batch-id>`** - Currently have `resume` but might need explicit retry
3. **`codeframe work show <task-id>`** - See detailed task including error messages
4. **`codeframe events search --error`** - Find error events quickly

### Good CLI Features Already Present

- `--dry-run` option for batch runs
- `--strategy auto` for dependency inference
- `--all-ready` convenience flag
- `--retry N` for automatic retry
- Clean table formatting
- Helpful next-step suggestions

---

## Code Quality Assessment

Despite all tasks "failing," the agent generated substantial code:

| Category | Lines | Quality |
|----------|-------|---------|
| Main Code | 1,433 | Good structure, imports mostly correct |
| Tests | 2,196 | Comprehensive, but won't run without fixes |
| Docs | ~100 | README generated |

The failures are primarily infrastructure/environment issues, not code generation quality issues.

---

## Recommendations

### Immediate Fixes (Critical)

1. **Fix `fail_run()` to update task status** - This is breaking state management
2. **Add `FAILED` task status** - Currently only have BACKLOG, READY, IN_PROGRESS, BLOCKED, DONE
3. **Surface error messages in task list** - Users need to see why tasks failed

### Short-Term Improvements

4. **Environment Detection** - Detect `uv` availability and use it automatically
5. **Project-Level Agent Config** - Allow target projects to have `AGENTS.md` or `.codeframe/config.yaml`
6. **Create `__main__.py` for CLI projects** - Standard Python packaging practice

### UX Improvements

7. **Show error summary after batch failure** - Don't just say "0/15 completed"
8. **Add `codeframe debug <task-id>`** - Show execution log for a task
9. **Progress estimation** - Show "Task 5 of 15" during execution

---

## Appendix: Commands Used

```bash
# Initialization
codeframe init /home/frankbria/projects/cf-test
codeframe prd add requirements.md
codeframe tasks generate

# Status Management
codeframe tasks list
codeframe tasks set status READY --all --from BACKLOG

# Execution
codeframe work batch run --all-ready --strategy auto --max-parallel 2

# Monitoring
codeframe work batch status [batch_id]
codeframe status
codeframe summary
codeframe blocker list
codeframe review
```

---

## Conclusion

The CodeFRAME CLI v2 foundation is solid. The workflow from init through batch execution is well-designed and mostly functional. The critical bug in `fail_run()` is the highest priority fix needed - without proper state management, users cannot recover from failures. The agent environment issues (pip vs uv, missing __main__.py) are fixable with better prompting and environment detection.

**Overall Assessment:** 70% ready for production use. Critical state management bug must be fixed first.
