# ReactAgent Deep Analysis

**Date:** 2026-02-16
**Based on:** Golden path CLI test run on `~/projects/cf-test/` (Task Tracker CLI spec)
**Engine:** `--engine react` with `--strategy auto`

---

## 1. Test Run Summary

| Metric | Value |
|--------|-------|
| Tasks generated | 15 |
| Completed (DONE) | 10 (67%) |
| Blocked | 5 (33%) |
| Failed (after retry) | 0 |
| Duration | ~25 min |
| Dependency groups | 6 (LLM-inferred) |
| Parallel workers | 4 |

**All 6 PRD requirements were implemented and functional.** The CLI passes 60 tests and all commands work correctly (add, list, complete, delete, priority, search).

---

## 2. Architecture Overview

### Core Files

| File | Lines | Purpose |
|------|-------|---------|
| `core/react_agent.py` | ~1370 | ReAct loop, verification, compaction |
| `core/tools.py` | ~940 | 7 tools: read, list, search, edit, create, run_tests, run_command |
| `core/editor.py` | ~560 | SearchReplaceEditor for edit_file |
| `core/blocker_detection.py` | ~220 | Pattern-based blocker classification |
| `core/conductor.py` | ~600+ | Batch orchestration + SupervisorResolver |
| `core/fix_tracker.py` | ~200 | Fix attempt dedup + escalation |
| `core/quick_fixes.py` | ~150 | Pattern-based fixes without LLM |

### Execution Flow

```
run(task_id)
  │
  ├── ContextLoader.load() → TaskContext
  │     (PRD, file tree, loaded files, tech stack, preferences)
  │
  ├── _calculate_adaptive_budget() → iteration cap
  │     score 1→15, 2→22, 3→30, 4→37, 5→45 (default config)
  │
  ├── _build_system_prompt() → 3-layer prompt
  │     L1: Base rules (hardcoded)
  │     L2: Preferences, tech stack, file tree, source files
  │     L3: Task title/desc, PRD, answered blockers
  │
  ├── _react_loop() → iterate until text-only or max_iterations
  │     ├── LLM call with tools
  │     ├── Execute tools (with inline lint)
  │     ├── Loop detection (3x identical signatures)
  │     └── Conversation compaction (3-tier)
  │
  └── _run_final_verification() → gates + mini ReAct fix loop
        ├── Quick fix (no LLM)
        ├── Escalation check
        └── Mini ReAct loop (5 LLM turns per retry, up to 5 retries)
```

---

## 3. What Worked Well

### 3.1 LLM Dependency Inference
The `--strategy auto` correctly identified a 6-group DAG:
1. Project setup
2. Models + Storage (parallel)
3. All 6 commands (parallel, 4 workers)
4. Cross-cutting (color, validation, help, entry point — parallel)
5. Testing
6. Documentation

This is a strong result — the dependencies were logically correct and enabled meaningful parallelism.

### 3.2 Code Quality
The generated code for the Task Tracker CLI was clean and well-structured:
- Proper `pyproject.toml` with Click + Colorama
- Clean dataclass model with validation
- JSON storage with comprehensive error handling
- All CLI commands with colored output, `--help`, and proper error messages
- 60 tests across 3 files covering edge cases (unicode, special chars, empty storage)

### 3.3 Tool Design
The 7-tool set is well-scoped:
- **read_file** with auto-truncation (head 200 + tail 50 for large files)
- **edit_file** with search/replace (forces the LLM to be precise)
- **create_file** that fails if file exists (prevents accidental overwrites)
- **run_tests** with focused failure output (first failing test only)
- **run_command** with dangerous-command blocking and venv auto-detection

### 3.4 Inline Lint Feedback
After every `create_file` or `edit_file`, the agent runs:
1. `gates.run_autofix_on_file()` — auto-fix lint issues
2. `gates.run_lint_on_file()` — report remaining issues

This prevents lint errors from accumulating and gives the LLM immediate feedback.

### 3.5 Supervisor Auto-Resolution
The `SupervisorResolver` in `conductor.py` successfully:
- Detected tactical blockers (e.g., "which approach should I use")
- Auto-resolved them with cached/generated decisions
- Retried the task after resolution
- Task 14 (testing) was auto-resolved and succeeded on retry

### 3.6 Loop Detection
3-iteration identical tool-call signature detection prevents infinite loops. This worked in the test — no tasks got stuck in loops.

### 3.7 Conversation Compaction
3-tier compaction prevents context overflow:
- **Tier 1:** Replace verbose tool results with summaries
- **Tier 2:** Remove redundant read_file calls and passing test results
- **Tier 3:** Summarize old messages into a single `[Summary]` message

---

## 4. Issues Observed

### 4.1 Verification Gate Failures on "Already Done" Tasks (HIGH)

**5 tasks blocked** because verification gates kept failing after the features were already implemented by earlier tasks. The blocked tasks were:
- Add colored terminal output (already in cli.py from the command tasks)
- Error handling and validation (already in cli.py and models.py)
- `--help` documentation (Click provides this automatically)
- Create main CLI entry point (already in cli.py from task 1)
- Create user documentation (downstream dependency on blocked tasks)

**Root cause:** When parallel tasks create/modify the same files, later tasks in Group 4 try to add code that's already there. The edit_file search/replace fails because the code pattern has changed, and after 3 verification retries, it escalates to a blocker.

**Impact:** 33% of tasks blocked unnecessarily. The project was fully functional despite these "failures."

### 4.2 Over-Granular Task Decomposition (MEDIUM)

The LLM generated 15 tasks from a simple 20-line spec. Several tasks had overlapping scope:
- "Add colored terminal output" overlaps with all command implementation tasks (they already use colorama)
- "Create main CLI entry point" overlaps with "Set up project structure" (both create cli.py)
- "Add --help documentation" is a no-op with Click (it's automatic)
- "Implement error handling" overlaps with every command task

**Result:** Tasks 10-13 are essentially verification/enhancement passes over work already completed by tasks 1-9.

### 4.3 Test Data Leakage (LOW)

The "Test all features" task ran the CLI to create test tasks, but the data persisted in `~/.task-tracker/tasks.json` across runs. When we ran the CLI manually, IDs started at 16 instead of 1.

**Root cause:** The agent tests by running the CLI directly (via `run_command`) rather than through pytest fixtures with isolated storage.

### 4.4 Ruff Not in Target Project Dependencies (LOW)

The verification gates try to run `ruff` on the target project, but ruff wasn't added to the project's `pyproject.toml` dev dependencies. This causes lint gates to fail with "command not found" errors.

**Current behavior:** The agent's `_run_lint_on_file()` emits a `GATES_COMPLETED` event with `status=ERROR` for linter infrastructure failures, which is correctly **not** surfaced to the LLM. But during final verification, `gates.run()` may still fail if it expects ruff to be available.

### 4.5 Blocker Text Quality Could Be Better (LOW)

All 5 blocked tasks had identical blocker text: "Verification keeps failing and automated fixes are not working." The blocker should include more specific context:
- What specific edits failed
- What the gate output was
- What the agent tried to fix

---

## 5. Future Optimization Opportunities

### 5.1 Task Deduplication / No-Op Detection (HIGH PRIORITY)

**Problem:** Tasks that describe features already implemented by earlier tasks waste iterations and create false blockers.

**Approaches:**
1. **Pre-flight check:** Before executing a task, have the agent scan the workspace for evidence the feature already exists. If found, mark as DONE immediately.
2. **Workspace diff awareness:** After each task completes, record what files changed. Pass this to subsequent tasks so they know what's already been built.
3. **Coarser task generation:** Instruct the LLM to generate fewer, more cohesive tasks. A 20-line spec shouldn't produce 15 tasks — 5-7 would be more appropriate.
4. **Merge pass:** After generating tasks but before execution, have the LLM merge tasks with overlapping scope.

**Suggested implementation:** Option 1 (pre-flight check) is lowest effort and highest impact. Add a `_check_if_already_done()` method that reads the workspace state and decides whether the task is already satisfied.

### 5.2 Smarter Task Generation Prompt (MEDIUM PRIORITY)

**Problem:** The task generation prompt doesn't account for implicit features that frameworks provide (e.g., Click auto-generates `--help`).

**Approach:** Include framework-awareness in the task generation prompt:
```
When generating tasks, do NOT create separate tasks for:
- --help flags (most CLI frameworks provide these automatically)
- Error handling (implement within each feature task)
- "Main entry point" (create during project setup)
```

### 5.3 Parallel Conflict Prevention (MEDIUM PRIORITY)

**Problem:** Parallel tasks that modify the same files can conflict, causing search/replace failures.

**Approaches:**
1. **File-level locking:** Track which files each task is likely to modify and don't parallelize tasks that touch the same files.
2. **Merge-on-conflict:** When an edit_file fails because the search text changed, re-read the file and try again with the new content.
3. **Sequential fallback:** If a parallel task fails on edit_file, re-queue it as serial.

**Suggested implementation:** Option 2 (merge-on-conflict) — the `SearchReplaceEditor` could retry once after re-reading the file content.

### 5.4 Gate Configuration Per-Project (MEDIUM PRIORITY)

**Problem:** Verification gates assume ruff is available, but the target project may not have it.

**Approach:** The `_detect_available_gates()` function should check what linters are actually installed in the target project's environment, not the host environment. For the cf-test case, ruff wasn't in the venv, so lint gates should have been skipped (they were for inline lint, but not for final verification).

**Suggested implementation:** Make `gates.run()` respect the target workspace's tool availability. If ruff isn't available, skip lint gates rather than failing.

### 5.5 Adaptive Verification Retry Budget (LOW PRIORITY)

**Problem:** All tasks get the same verification retry budget (5 retries). Simple tasks that fail verification after 3 retries are unlikely to succeed on retries 4-5.

**Approach:** Reduce the retry budget when:
- The same error appears 2+ times consecutively
- The fix attempts are cycling through the same strategies
- The task complexity score is low (simple tasks shouldn't need many retries)

### 5.6 Better Blocker Context (LOW PRIORITY)

**Problem:** Escalation blockers have generic text ("Verification keeps failing").

**Approach:** Include in the blocker:
- The specific gate output (last 300 chars)
- The last 3 fix attempts (what was tried)
- The specific files that failed
- A suggested resolution path

### 5.7 Workspace-Aware Test Execution (LOW PRIORITY)

**Problem:** The agent runs CLI commands that leave state behind (test data leakage).

**Approach:** When the task is "test all features":
1. Use pytest fixtures with `tmp_path` isolation
2. Set storage path via environment variable during tests
3. Clean up after run_command test invocations

### 5.8 Context Compaction Improvements (LOW PRIORITY)

The current 3-tier compaction is functional but could be improved:
- **Tier 1** uses a simple first-line summary. Could use structured extraction (file path, operation type, result status).
- **Tier 2** only removes redundant reads and passing tests. Could also remove successful creates/edits that aren't referenced later.
- **Tier 3** summarizes old messages but loses architectural decisions. Could preserve a structured "decisions log" format.

### 5.9 Tool Result Compression (LOW PRIORITY)

**Problem:** `list_files` and `search_codebase` results can be very verbose for large projects.

**Approach:**
- `list_files`: Return a tree-style summary for large directories instead of flat file lists.
- `search_codebase`: Group results by file and show match count per file, with details only for the first N files.

### 5.10 Intent Preview for Complex Tasks (LOW PRIORITY)

**Current behavior:** Tasks with `complexity_score >= 4` get a "Before writing code, outline your plan" instruction in the system prompt.

**Enhancement:** For tasks with complexity >= 3, require the agent to output a structured plan (files to modify, approach) in its first response before executing any tools. This prevents the agent from diving into code before understanding the full scope.

---

## 6. Performance Profile

### Token Usage (Estimated)
- System prompt: ~2-4K tokens per task (varies with context)
- Average iterations per task: ~10-15 for implementation, ~5-8 for simple tasks
- Verification retries: 1-3 iterations of 5 turns each for failed tasks
- Estimated cost: ~$0.20-0.50 per task at claude-sonnet-4 rates

### Timing
- Task generation: ~15 seconds
- Dependency inference: ~15 seconds
- Individual task execution: 1-3 minutes each
- Verification + retries: 30-90 seconds per task
- Total batch (15 tasks, 4 workers): ~25 minutes

---

## 7. Comparison: Plan Engine vs React Engine

| Aspect | Plan Engine | React Engine |
|--------|------------|--------------|
| Approach | Generate full plan → execute steps | Iterate: reason → act → observe |
| Adaptability | Low (follows plan rigidly) | High (adjusts based on tool results) |
| Token efficiency | Lower (plan + execution) | Higher (no separate planning step) |
| Error recovery | Self-correction loop (3 attempts) | Inline lint + loop detection + mini ReAct fix |
| Parallelism | Same | Same (conductor handles this) |
| Test run result | Not tested this session | 10/15 DONE, 0 FAILED |

---

## 8. Key Takeaways

1. **The React agent works.** It successfully built a functional CLI project from a simple spec, with proper project structure, tests, and documentation scaffolding.

2. **The biggest win is inline lint feedback.** Running lint after every file write catches errors before they compound, reducing the need for expensive verification retries.

3. **The biggest pain point is over-decomposition.** The task generator creates too many tasks for simple specs, and later tasks describe features that earlier tasks already implemented. This is the #1 optimization target.

4. **Parallel execution works but needs conflict awareness.** When multiple tasks modify the same files simultaneously, edit_file can fail. File-level coordination would prevent this.

5. **The supervisor auto-resolution is valuable.** It correctly identified and resolved tactical blockers without human intervention. The "Test all features" task succeeded on retry thanks to this.

6. **The compaction system prevents context overflow** but could be more intelligent about what to preserve.
