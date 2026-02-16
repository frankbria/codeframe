# Agent V3: Unified Architectural Plan

**Date**: 2026-02-07
**Status**: ✅ Implemented — Default engine since 2026-02-15 (#355)
**Sources**: AGENT_ARCHITECTURE_RESEARCH.md, AGENT_FRAMEWORK_DEEP_DIVE.md, AGENT_ARCHITECTURE_CRITIQUE.md, REACT_AGENT_ARCHITECTURE.md

---

## Executive Summary

This plan redesigns CodeFRAME's agent execution from Plan-and-Execute to a **Hybrid ReAct architecture** — a tool-use loop where the LLM decides what to do at each step, with a lightweight intent preview for complex/greenfield tasks. The redesign preserves all existing functionality behind a feature flag and addresses the specific failure modes discovered during testing.

### What We're Solving

| Failure Mode | Root Cause | Fix |
|---|---|---|
| Config file overwrites (pyproject.toml) | Whole-file generation ignores existing content | Search-replace editing with fuzzy matching |
| Cross-file naming inconsistency | Each file generated in isolation, plan doesn't see actual output | ReAct loop — agent reads files it just created before creating the next |
| 92 ruff errors in generated code | No incremental verification | Lint gate after every file edit/create |
| Ineffective self-correction (empty error context) | Bug in error propagation after re-verification | ReAct loop eliminates the separate self-correction phase; errors are visible in tool results |
| Shell operator rejection (`cd X && command`) | Executor rejects `&&` in shell commands | Agent uses `run_command` tool with `cwd` parameter instead |

### Design Principles (Agreed by All Agents)

1. **Search-replace editing for existing files, whole-file only for new files** — ~98% accuracy vs ~70-80% for whole-file regeneration
2. **Read before write** — always see actual file state before editing
3. **Lint after every file change** — catch errors immediately, not after 92 accumulate
4. **Model is the planner** — the LLM decides what to do next based on observed reality
5. **Fewer tools = higher accuracy** — 7 focused tools, not a large surface area
6. **Backward compatible** — `--engine plan` available as fallback (ReAct is now default)

---

## Architecture

### High-Level Design

```
cf work start <task-id> --execute [--engine react]
    │
    ├── runtime.start_task_run()
    │   └── Select engine: "react" (default) or "plan" (legacy)
    │
    └── runtime.execute_agent(engine="react")
            │
            ├── Load initial context (task, PRD, file tree, preferences)
            ├── Build layered system prompt (base + project + task)
            │
            ├── [Intent Preview Phase] (for HIGH complexity or greenfield tasks)
            │   └── Agent outlines approach: files to create, module boundaries, key interfaces
            │   └── NOT a rigid plan — a lightweight sketch the agent can deviate from
            │
            └── [ReAct Loop] (max 30 iterations):
                ├── LLM call with 7 tools available
                ├── If tool_calls: execute tools → auto-lint → append results → continue
                ├── If text only: agent is done → run final verification
                ├── If blocker detected: create blocker → exit BLOCKED
                └── Token budget check → compact if approaching limit
```

### Module Map

| Module | Status | Notes |
|---|---|---|
| **New: `core/react_agent.py`** | Create | ReAct loop agent, parallel to existing Agent |
| **New: `core/tools.py`** | Create | Tool definitions, schemas, dispatch |
| **New: `core/editor.py`** | Create | Search-replace editor with fuzzy matching |
| `core/agent.py` | Keep | Existing Plan-and-Execute, unchanged |
| `core/executor.py` | Keep | Used by tools.py for run_command |
| `core/planner.py` | Keep | Optional, used for intent preview only |
| `core/context.py` | Minor | Add file tree summary, line-range reads |
| `core/gates.py` | Keep | Used for final verification and per-edit lint |
| `core/runtime.py` | Minor | Engine selection param |
| `core/fix_tracker.py` | Reuse | Escalation detection in ReAct loop |
| `core/quick_fixes.py` | Reuse | Pattern-based auto-fixes still valuable |
| `core/blockers.py` | Keep | Blocker creation unchanged |
| `core/events.py` | Keep | Event emission unchanged |
| `core/streaming.py` | Keep | SSE streaming unchanged |
| `adapters/llm/base.py` | Keep | Already has Tool/ToolCall/ToolResult types |
| `cli/app.py` | Minor | Add `--engine react` flag |

---

## Tool Set (7 Tools)

Intentionally minimal. Research shows fewer tools = higher accuracy (Vercel: 80% reduction → 3.5x speedup).

### 1. `read_file`
Read file contents with optional line range. **Always read before editing.**

```
Input: { path: string, start_line?: int, end_line?: int }
Output: File content with line numbers. Large files (>500 lines) auto-truncated with summary.
Maps to: context.py file loading
```

### 2. `edit_file`
Targeted search-replace edits on existing files.

```
Input: { path: string, edits: [{ search: string, replace: string }] }
Output: Unified diff on success. On failure: actual file content near expected location.
Maps to: NEW editor.py with fuzzy matching fallback chain
```

**Matching fallback chain**: exact → whitespace-normalized → indentation-agnostic → fuzzy (Levenshtein > 0.85) → fail with context

**Error feedback** (critical for self-correction):
```
EDIT FAILED: No match found for search block in models.py.
The file contains these similar lines near the expected location:
  Line 42: def add_task(self, title: str, priority: int = 0):
  Line 43:     """Add a new task."""
Please retry with the actual content from the file.
```

### 3. `create_file`
Create a genuinely new file. Fails if file already exists (suggests edit_file instead).

```
Input: { path: string, content: string }
Output: Success or error. Auto-creates parent directories.
```

### 4. `search_codebase`
Regex search across the codebase. Deterministic, fast, precise.

```
Input: { pattern: string, file_glob?: string, max_results?: int (default 20) }
Output: Matching lines with file paths and line numbers.
```

### 5. `list_files`
Directory listing with glob filtering.

```
Input: { path?: string, pattern?: string, max_depth?: int (default 3) }
Output: File listing with sizes. Respects ignore patterns.
```

### 6. `run_command`
Execute a shell command in the workspace. Sandboxed.

```
Input: { command: string, timeout?: int (default 60, max 300) }
Output: stdout + stderr + exit code. Output truncated to 4000 chars.
Safety: dangerous command regex, shlex.split(), timeout, cwd locked to workspace.
```

### 7. `run_tests`
Run the project's test suite with focused output.

```
Input: { test_path?: string, verbose?: bool }
Output: Summary (passed/failed/errors). On failure: first failing test + traceback only.
Maps to: gates.py _run_pytest() / _run_npm_test()
```

**Why `run_tests` separate from `run_command`**: Focused output keeps context clean. Full test suite output can be 10K+ characters; `run_tests` shows only the first failure.

---

## The Hybrid Approach: Intent Preview + ReAct

### Why Not Pure ReAct (Skeptic's Key Insight)

The research's ReAct recommendation is based on interactive agents (Claude Code has a human in the loop) and bug-fixing benchmarks (SWE-bench). CodeFRAME runs **autonomously on greenfield projects**. A pure ReAct loop without any structure can:

- Make contradictory architectural decisions across iterations
- Wander exploring without making progress
- Run up token costs on dead ends

### Why Not Pure Plan-and-Execute (Known Failures)

The current approach generates a rigid plan, then executes it blindly. Plans become stale immediately — step 5 doesn't know what step 3 actually produced. This is the root cause of cross-file inconsistency.

### The Hybrid: Best of Both

```
Task Received
    │
    ├── Complexity Assessment (LOW / MEDIUM / HIGH)
    │   └── Uses existing planner.py Complexity enum
    │
    ├── [LOW complexity] → Direct ReAct loop (no preview)
    │   Example: "Add a --verbose flag to the list command"
    │
    ├── [MEDIUM complexity] → Brief intent preview → ReAct loop
    │   Example: "Add a delete command with confirmation"
    │
    └── [HIGH complexity / greenfield] → Detailed intent preview → ReAct loop
        Example: "Build a CLI task tracker with CRUD operations"
```

### Intent Preview (Not a Rigid Plan)

The intent preview is the agent's first "think" step. It outlines:
- Files to create and their purposes
- Module boundaries and key interfaces
- Execution strategy (what order to build things)

This is embedded in the conversation as the agent's first response. It's **not** a PlanStep list — it's natural language reasoning that guides subsequent tool calls. The agent can and should deviate when reality differs from the sketch.

Implementation: System prompt includes "Before making changes, briefly outline your approach." No code changes needed — just prompt engineering.

---

## System Prompt Design

### Layered Structure

```
┌─────────────────────────────────────┐
│ Layer 1: BASE                       │  ← Always present, ~2K tokens
│ - Agent identity and role           │
│ - Available tools (auto-generated)  │
│ - Core constraints and rules        │
│ - Termination conditions            │
│ - Decision-making autonomy          │
├─────────────────────────────────────┤
│ Layer 2: PROJECT                    │  ← Per-workspace, ~2-5K tokens
│ - AGENTS.md / CLAUDE.md content     │
│ - Tech stack description            │
│ - Repository structure summary      │
├─────────────────────────────────────┤
│ Layer 3: TASK                       │  ← Per-task, ~2-5K tokens
│ - Task title and description        │
│ - PRD content (truncated to 5K)     │
│ - Previous blocker answers          │
└─────────────────────────────────────┘
Total initial context: ~10-15K tokens
```

### Base Prompt (Layer 1) — Key Rules

```
You are CodeFRAME, an autonomous software engineering agent.

## Rules

- ALWAYS read a file before editing it. Never assume file contents.
- Make small, targeted edits. Do not rewrite entire files.
- For NEW files: use create_file. For EXISTING files: use edit_file with search/replace.
- Never edit_file on a file you haven't read in this session.
- Run tests after implementing each major feature, not after every line change.
- Keep solutions simple. Do not add features beyond what was asked.
- Do not change configuration files (pyproject.toml, package.json, etc.) unless
  the task explicitly requires it. If you must edit them, read first and make
  minimal, targeted changes.

## Code Quality

- No trailing whitespace
- Use 'raise X from Y' not bare 'raise X' after catching exceptions
- Follow the project's existing code style (read existing files first)
- All imports at the top of file, organized: stdlib → third-party → local

## When You're Done

Respond with a brief summary. Do not call any more tools.

## When You're Stuck

If you encounter a genuine blocker (conflicting requirements, missing credentials,
unclear business logic), explain clearly. Do NOT stop for trivial decisions.
```

---

## Verification Strategy

### Per-Edit Lint Gate

After every `edit_file` or `create_file` tool call, automatically run `ruff check` on the modified file. Results are appended to the tool response:

```python
# In react_agent.py tool execution
if tool_call.name in ("edit_file", "create_file") and not result.is_error:
    lint = self._run_ruff_on_file(tool_call.input["path"])
    if lint.errors:
        result.content += f"\n\nLINT ERRORS (must fix before continuing):\n{lint.format_errors()}"
```

The agent sees lint errors immediately and fixes them in the next iteration. No separate verification phase. No accumulating 92 errors.

### Test Execution

- Agent-initiated: agent calls `run_tests` when it thinks a feature is complete
- Final verification: all gates run when agent signals completion
- System prompt: "Run tests after implementing each major feature"

### Self-Correction in ReAct

The ReAct loop IS the self-correction loop. When an edit fails or tests fail, the agent sees the error in the tool result and adapts. No separate self-correction phase.

Escalation (reusing existing modules):
- `fix_tracker.py`: Same error 3+ times → blocker
- `fix_tracker.py`: Same file 3+ attempts → blocker
- Hard cap: 30 iterations → FAILED

### Final Verification

When the agent stops calling tools (text-only response), run all gates:
- ruff check (full project)
- pytest (if tests exist)

If final verification fails, give the agent 5 more iterations to fix issues (entering a bounded self-correction phase within the ReAct loop itself).

---

## Progress Reporting

### Phase-Based Events (Addressing Skeptic's UX Concern)

The ReAct loop emits phase-based events for `cf work follow` and SSE streaming:

| Phase | Trigger | Event |
|---|---|---|
| EXPLORING | Agent calls read_file or list_files | "Exploring codebase..." |
| PLANNING | Agent produces intent preview | "Planning approach..." |
| CREATING | Agent calls create_file | "Creating {filename}..." |
| EDITING | Agent calls edit_file | "Editing {filename}..." |
| TESTING | Agent calls run_tests | "Running tests..." |
| FIXING | Agent fixing lint/test errors | "Fixing {error_type}..." |
| VERIFYING | Final gate check | "Running final verification..." |

Implementation: Tool execution handler emits events via existing `events.py` before/after each tool call. Compatible with existing `streaming.py` SSE infrastructure.

---

## Context Management

### Initial Context (in system prompt)
- Task metadata, PRD, file tree summary, preferences, tech stack
- ~10-15K tokens total
- Files are NOT pre-loaded — agent retrieves on demand via tools

### During Execution (just-in-time)
- Agent reads files as needed via `read_file`
- No pre-loading of potentially relevant files
- Agent follows imports/references to discover related files

### Compaction (at 85% context window)
Priority order:
1. **Tool result clearing**: Replace verbose outputs with summaries
2. **Intermediate step removal**: Remove tool calls that didn't lead to useful results
3. **Conversation summary**: Oldest N messages → summary paragraph

Preserve: architectural decisions, unresolved errors, file paths created/modified, last 5 tool call/result pairs

---

## Cost and Latency (Addressing Skeptic's Concern)

### Estimated Costs

| Engine | Typical Task (5 files) | Token Usage | Cost (Sonnet) |
|---|---|---|---|
| Plan-and-Execute (current) | ~6 LLM calls | ~20-30K tokens | ~$0.10-0.20 |
| ReAct (new) | ~15-25 iterations | ~60-100K tokens | ~$0.30-0.50 |

ReAct is ~3x more expensive per task. **However**: the current engine FAILS on simple tasks (infinite cost per successful completion). A working engine at 3x cost beats a broken engine at 1x cost.

### Optimization Strategies (Phase F+)

1. **Model selection per iteration**: Use Haiku for read_file/list_files tool calls (simple routing, no complex reasoning needed). Only use Sonnet for edit/create decisions.
2. **Caching**: Cache file reads within a session. If the agent reads a file, then reads it again 5 iterations later without modifying it, serve from cache.
3. **Early termination**: If all required files are created and tests pass, stop even if the agent wants to "polish."
4. **Batch context sharing**: For batch execution, share the initial context (file tree, tech stack) across tasks to avoid redundant exploration.

---

## Migration Plan

### Phase A: Search-Replace Editor (Low Risk, Standalone)

**Create**: `codeframe/core/editor.py` + `tests/core/test_editor.py`

- `SearchReplaceEditor` with 4-level matching fallback chain
- Detailed error context on match failure
- Diff generation for success feedback
- **Can ship independently** — no existing code changes

### Phase B: Tool Definitions (Low Risk, Standalone)

**Create**: `codeframe/core/tools.py` + `tests/core/test_tools.py`

- 7 tool schemas as `Tool` objects (using existing `adapters/llm/base.py` types)
- `execute_tool()` dispatcher connecting to existing modules
- **Depends on**: Phase A (editor.py for edit_file)

### Phase C: ReAct Agent (Core Change, Feature-Flagged)

**Create**: `codeframe/core/react_agent.py` + `tests/core/test_react_agent.py`
**Modify**: `core/runtime.py` (engine selection), `cli/app.py` (--engine flag)

- `ReactAgent` class with the ReAct loop
- System prompt builder (3 layers)
- Tool call/result conversation management
- Phase-based event emission
- Integration with existing AgentState, events, fix_tracker
- **Default engine remains "plan"** — `--engine react` opts in

### Phase D: Incremental Verification (Refinement)

**Modify**: `core/react_agent.py`, `core/tools.py`

- Auto-lint after edit_file/create_file
- Lint errors appended to tool results
- **Only affects ReAct path**

### Phase E: Context Compaction (Refinement)

**Modify**: `core/react_agent.py`

- Token budget tracking
- 3-tier compaction strategy
- **Only affects ReAct path**

### Phase F: Validation and Default Switch

- Run both engines on test tasks (cf-test project)
- Compare success rates, cost, latency
- When ReAct matches or exceeds Plan-and-Execute: switch default
- Keep `--engine plan` available as fallback

```
Timeline:
Phase A ──── [standalone, start now]
Phase B ──── [depends on A]
Phase C ──── [depends on B, the big one]
Phase D,E ── [depends on C, can parallelize]
Phase F ──── [depends on C-E validated]
```

---

## What We Explicitly Decided NOT to Do

1. **No multi-agent for single tasks** — Research overwhelmingly shows single agent beats multi-agent for coding. Keep batch conductor for parallel independent tasks.

2. **No rigid planning** — No ImplementationPlan with ordered PlanSteps. The intent preview is a soft sketch, not a contract.

3. **No model-as-judge verification** — Rules-based verification (linters, tests) is more reliable and cheaper than LLM-based evaluation.

4. **No full rewrite of existing code** — The new engine lives alongside the old one. Existing tests, batch execution, blocker detection, event streaming all preserved.

5. **No immediate Resume support for ReAct** — On failure, restart the task from the beginning (ReAct can re-explore quickly). Resume support can be added later via conversation serialization.

---

## Success Criteria

The ReAct engine is ready for default when it can:

1. **Build the cf-test task tracker** from requirements.md → working CLI with tests, on first attempt, with 0 lint errors
2. **Preserve existing config files** — pyproject.toml is never overwritten during brownfield tasks
3. **Maintain cross-file consistency** — No naming mismatches between files created by the same agent
4. **Self-correct effectively** — Lint errors are caught per-edit and fixed in the next iteration, not accumulated
5. **Complete within 30 iterations** — Typical 5-file tasks finish in 15-25 iterations
6. **Cost within 5x of Plan-and-Execute** — Acceptable premium for dramatically higher success rate

---

## Research Documents

| Document | Author | Focus |
|---|---|---|
| `docs/AGENT_ARCHITECTURE_RESEARCH.md` | patterns-researcher | SWE-bench data, orchestration frameworks, proven patterns |
| `docs/AGENT_FRAMEWORK_DEEP_DIVE.md` | frameworks-researcher | Per-framework analysis of 9 major tools |
| `docs/AGENT_ARCHITECTURE_CRITIQUE.md` | skeptic-debater | Risk analysis, cost concerns, greenfield problem |
| `docs/REACT_AGENT_ARCHITECTURE.md` | architect-synthesizer | Detailed implementation plan with code examples |
| `docs/AGENT_V3_UNIFIED_PLAN.md` | synthesis (this doc) | Final unified plan incorporating all perspectives |

---

## Key Debate Resolutions

| Topic | Architect Position | Skeptic Position | Resolution |
|---|---|---|---|
| ReAct vs Plan-and-Execute | Full ReAct | Targeted evolution, fix execution not model | **Hybrid**: ReAct with intent preview for complex tasks |
| SWE-bench applicability | Directly applicable | Overfits to bug-fixing | **Acknowledged**: Section 8 of architect plan addresses greenfield. Skeptic's concern valid but mitigated |
| Cost/latency | Not addressed | 3-6x more expensive | **Accepted**: Working at 3x > broken at 1x. Optimize later with model selection |
| Progress reporting | Agent decides | Users need predictability | **Phase-based events**: EXPLORING → CREATING → TESTING → FIXING |
| Resume support | Not addressed | Hard with ReAct | **Deferred**: Restart on failure for now. Add later via conversation serialization |
| Migration risk | Phased A-F | Run old/new in parallel | **Agreed**: Both say the same thing. Default stays "plan" until validated |
| Discard planner entirely | Yes | No, greenfield needs structure | **Keep planner optional**: Used for intent preview, not rigid plans |
