# Phase 2.5-F: End-to-End CLI Validation Report

**Date**: 2026-02-10
**Issue**: #353
**Engine**: ReAct (`react_agent.py`)
**Target project**: `~/projects/cf-test` (Task Tracker CLI)

---

## Summary

The ReAct engine was validated by running the full Golden Path workflow against the `cf-test` project. The workflow pipeline (init, PRD, task generation, marking ready) works correctly. However, the ReAct agent achieved **0% task completion** — all 10 generated tasks failed after exhausting the 30-iteration limit.

A critical bug was found and fixed during validation: the `_react_loop` method started with an empty messages list, causing all real API calls to fail with `BadRequestError`.

---

## Test Infrastructure

Reusable e2e test infrastructure was created in `tests/e2e/cli/`:

| File | Purpose |
|------|---------|
| `conftest.py` | Fixtures, markers, API key loading |
| `golden_path_runner.py` | Reusable `GoldenPathRunner` class |
| `validators.py` | Validation functions for success criteria |
| `test_react_engine_validation.py` | ReAct engine validation tests |
| `test_engine_comparison.py` | Side-by-side engine comparison |

**Running the tests:**
```bash
# Run ReAct validation (requires ANTHROPIC_API_KEY, ~30 min)
uv run pytest tests/e2e/cli/test_react_engine_validation.py -v -s

# Run engine comparison
uv run pytest tests/e2e/cli/test_engine_comparison.py -v -s

# Run all e2e LLM tests
uv run pytest -m e2e_llm -v -s
```

---

## Bug Fix: Empty Messages in `_react_loop`

**File**: `codeframe/core/react_agent.py`
**Root cause**: `_react_loop()` initialized `messages: list[dict] = []` then called the Anthropic API, which requires at least one user message.

**Impact**: Every real API call raised `anthropic.BadRequestError: 'messages: at least one message is required'`. This was masked in unit tests because `MockLLMProvider` doesn't enforce this constraint.

**Fix**: Added an initial user message that instructs the agent to begin implementation:
```python
messages: list[dict] = [
    {
        "role": "user",
        "content": (
            "Implement the task described in the system prompt. "
            "Start by reading relevant files to understand the current "
            "codebase, then make the necessary changes. "
            "When you are done, respond with a brief summary."
        ),
    }
]
```

**Regression check**: All 1316 core tests + 23 adapter tests pass after the fix.

---

## Validation Results

### Workflow Pipeline

| Step | Status | Duration |
|------|--------|----------|
| `cf init --detect` | PASS | ~1s |
| `cf prd add requirements.md` | PASS | <1s |
| `cf tasks generate` | PASS | ~15s |
| Mark all tasks READY | PASS | <1s |
| Task execution (10 tasks) | **0/10 PASS** | ~1573s total |

### Per-Task Breakdown

All 10 tasks hit the 30-iteration maximum and were marked FAILED. The agent did generate substantial code but could not get verification gates to pass within the iteration budget.

| # | Task | Iterations | Duration | Result |
|---|------|-----------|----------|--------|
| 1 | Data models (Task, Priority, Status) | 30 | ~160s | FAILED |
| 2 | Storage layer (JSON persistence) | 30 | ~160s | FAILED |
| 3 | CLI entry point (Click) | 30 | ~160s | FAILED |
| 4 | Add task command | 30 | ~160s | FAILED |
| 5 | List tasks with filtering | 30 | ~160s | FAILED |
| 6 | Update task command | 30 | ~160s | FAILED |
| 7 | Delete task command | 30 | ~160s | FAILED |
| 8 | Status management | 30 | ~160s | FAILED |
| 9 | Input validation & error handling | 30 | ~160s | FAILED |
| 10 | Test suite | 30 | ~160s | FAILED |

### Success Criteria Assessment

| Criterion | Pass? | Notes |
|-----------|-------|-------|
| Build working CLI on first attempt | NO | All tasks failed |
| 0 ruff lint errors | YES | `ruff check` reports 0 errors on generated code |
| pyproject.toml preserved | YES | Hash unchanged |
| No cross-file naming mismatches | YES | No import errors at package level |
| Each task within 30 iterations | YES | All tasks hit exactly 30 (the limit) |
| Generated tests pass | NO | `ModuleNotFoundError: No module named 'task_tracker'` |

### Generated Artifacts

The agent did produce code in `cf-test`:

**Source files** (`src/task_tracker/`):
- `cli.py` (27KB) - Click-based CLI with all commands
- `models.py` - Pydantic data models
- `schema.py` - JSON schema definitions
- `storage.py` - JSON file persistence layer

**Test files** (`tests/`):
- `test_cli.py`, `test_models.py`, `test_schema.py`
- `test_status_management.py`, `test_storage.py`

Tests fail because the `task_tracker` package is not installed in the venv (`pip install -e .` was never run).

---

## Failure Analysis

### Primary Failure Mode

The ReAct agent enters a **verification gate loop**: it generates code, the verification gate (pytest/ruff) fails, it tries to fix the failure, the fix introduces a new failure, and the cycle continues until the 30-iteration limit is reached.

### Contributing Factors

1. **Package not installed**: The generated tests import `task_tracker` but the package is never installed in the venv. The agent doesn't run `pip install -e .` as part of its workflow.

2. **Accumulated complexity**: Each task builds on the previous, but the agent starts each task fresh without understanding prior artifacts. By task 3-4, the generated code needs to be consistent with earlier tasks' output.

3. **No task dependency awareness**: Tasks execute independently. The agent doesn't know task 1 already created `models.py` when working on task 2.

4. **Gate strictness vs. iteration budget**: 30 iterations is not enough to converge when each fix attempt can introduce new failures, especially with pytest running the full test suite.

### Recommendations for ReAct Engine Improvements

1. **Package installation step**: Add `pip install -e .` (or equivalent) as a standard setup step before running pytest gates.
2. **Cross-task context**: Carry over file inventory from previous tasks so the agent knows what already exists.
3. **Incremental gate scope**: Run only tests related to the current task, not the entire suite.
4. **Iteration budget tuning**: Consider adaptive budgets based on task complexity.

---

## pytest Results

```text
17 collected tests:
  15 passed (workflow steps, ruff lint, pyproject preserved, metrics)
   2 failed:
     - test_all_tasks_succeed (0% completion rate)
     - test_tests_pass (ModuleNotFoundError in generated tests)
```

---

## Comparison with Plan-and-Execute Engine

The Plan-and-Execute engine comparison was **skipped** for this validation run. With a 0% success rate on the ReAct engine, the comparison would not yield meaningful insights until the verification gate loop issue is addressed.

This can be revisited as a follow-up once the ReAct engine's task completion rate improves.

---

## Files Changed in This PR

| File | Change |
|------|--------|
| `codeframe/core/react_agent.py` | Bug fix: added initial user message to `_react_loop` |
| `pytest.ini` | Added `e2e_llm` marker registration |
| `tests/e2e/cli/__init__.py` | New: package init |
| `tests/e2e/cli/conftest.py` | New: fixtures, markers, API key loading |
| `tests/e2e/cli/golden_path_runner.py` | New: reusable Golden Path workflow runner |
| `tests/e2e/cli/validators.py` | New: validation functions |
| `tests/e2e/cli/test_react_engine_validation.py` | New: ReAct validation tests |
| `tests/e2e/cli/test_engine_comparison.py` | New: engine comparison tests |
| `docs/PHASE_25_VALIDATION_REPORT.md` | New: this report |
