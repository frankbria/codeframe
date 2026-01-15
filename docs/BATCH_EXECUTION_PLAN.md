# Batch Execution Implementation Plan

**Status**: Phase 2 Complete
**Created**: 2025-01-15
**Last Updated**: 2026-01-15

This document outlines the implementation plan for multi-task batch execution in CodeFRAME v2.

---

## Overview

Enable users to submit multiple tasks to the coding agent at once. A conductor orchestrates execution, managing parallelization based on task dependencies.

### Goals
1. Process multiple tasks in a single command
2. Support serial execution (Phase 1) and parallel execution (Phase 2)
3. Provide visibility into batch progress via CLI
4. Prepare for websocket streaming (Phase 3)

### Non-Goals (for now)
- Server-based batch management
- Real-time websocket dashboard
- Distributed execution across machines

---

## Architecture

### Component Hierarchy

```
cf work batch run <task-ids...>
    │
    └── conductor.start_batch()          # Batch orchestrator
            │
            ├── Create BatchRun record
            ├── Build execution plan
            │
            └── For each task (serial in Phase 1):
                │
                └── subprocess: cf work start <id> --execute
                        │
                        └── runtime.execute_agent()  # Existing
                                │
                                └── agent.run()      # Existing
```

### Key Design Decisions

1. **Subprocess-based execution**: Each task runs as a separate `cf work start` process
   - Complete isolation (one crash doesn't kill siblings)
   - Natural fit with existing CLI architecture
   - Each agent has its own LLM context window

2. **No server required**: Conductor is a long-running CLI process
   - State stored in SQLite
   - Child processes write to same database
   - Conductor polls for completion

3. **Serial by default**: Phase 1 executes tasks sequentially
   - Safe and predictable
   - Can force parallel with `--strategy parallel`
   - Phase 2 adds intelligent dependency analysis

---

## Data Model

### BatchRun

```python
class BatchStatus(str, Enum):
    PENDING = "PENDING"       # Created but not started
    RUNNING = "RUNNING"       # Tasks being processed
    COMPLETED = "COMPLETED"   # All tasks finished successfully
    PARTIAL = "PARTIAL"       # Some tasks completed, some failed
    FAILED = "FAILED"         # Critical failure
    CANCELLED = "CANCELLED"   # User cancelled

@dataclass
class BatchRun:
    id: str                           # UUID
    workspace_id: str
    task_ids: list[str]               # Ordered list of tasks
    status: BatchStatus
    strategy: str                     # "serial", "parallel", "auto"
    max_parallel: int                 # Max concurrent tasks
    started_at: datetime
    completed_at: Optional[datetime]
    results: dict[str, str]           # task_id -> RunStatus value
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS batch_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    task_ids TEXT NOT NULL,           -- JSON array
    status TEXT NOT NULL,
    strategy TEXT NOT NULL,
    max_parallel INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    results TEXT,                     -- JSON dict
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

---

## CLI Commands

### Phase 1 Commands (Implemented)

```bash
# Start batch (blocks until complete)
cf work batch run <task-ids...>
cf work batch run --all-ready
cf work batch run t1 t2 t3 --strategy serial    # Explicit serial (default)
cf work batch run t1 t2 t3 --strategy parallel  # Force parallel (runs serial in Phase 1)
cf work batch run --dry-run                     # Preview execution plan

# Monitor batch
cf work batch status                        # List active/recent batches
cf work batch status <batch-id>             # Show specific batch
cf work batch cancel <batch-id>             # Cancel running batch
```

### Phase 2 Commands (Future)

```bash
# Analyze dependencies before execution
cf work batch --analyze                     # Show dependency graph
cf work batch --strategy auto               # Use agent to infer dependencies

# Live streaming
cf work batch follow <batch-id>             # Stream events to terminal
```

---

## Event Types

Add to `events.py`:

```python
class EventType:
    # ... existing events ...

    # Batch events
    BATCH_STARTED = "BATCH_STARTED"
    BATCH_TASK_QUEUED = "BATCH_TASK_QUEUED"
    BATCH_TASK_STARTED = "BATCH_TASK_STARTED"
    BATCH_TASK_COMPLETED = "BATCH_TASK_COMPLETED"
    BATCH_TASK_FAILED = "BATCH_TASK_FAILED"
    BATCH_TASK_BLOCKED = "BATCH_TASK_BLOCKED"
    BATCH_COMPLETED = "BATCH_COMPLETED"
    BATCH_PARTIAL = "BATCH_PARTIAL"
    BATCH_FAILED = "BATCH_FAILED"
    BATCH_CANCELLED = "BATCH_CANCELLED"
```

---

## Implementation Phases

### Phase 1: Core Batch Infrastructure

**Goal**: Serial execution of multiple tasks via CLI

#### Tasks

1. **Add BatchRun model and schema** (`core/conductor.py`)
   - BatchStatus enum
   - BatchRun dataclass
   - SQLite table creation in workspace init

2. **Implement conductor core** (`core/conductor.py`)
   - `start_batch(workspace, task_ids, strategy, max_parallel)` → BatchRun
   - `get_batch(workspace, batch_id)` → BatchRun
   - `list_batches(workspace)` → list[BatchRun]
   - `cancel_batch(workspace, batch_id)` → BatchRun

3. **Implement serial execution loop**
   - Spawn subprocess for each task
   - Wait for completion
   - Update BatchRun results
   - Handle failures (continue vs stop)

4. **Add CLI commands** (`cli/app.py`)
   - `cf work batch run` - start batch
   - `cf work batch status` - show status
   - `cf work batch cancel` - cancel batch

5. **Add batch events** (`core/events.py`)
   - Emit events at batch lifecycle points

6. **Tests** (`tests/core/test_conductor.py`)
   - Unit tests for conductor logic
   - Integration test with mock subprocess

#### Acceptance Criteria
- [x] `cf work batch run t1 t2 t3` executes tasks sequentially
- [x] `cf work batch status` shows progress
- [x] `cf work batch cancel <id>` stops execution
- [x] Events emitted for batch lifecycle
- [x] Batch state persisted to SQLite

### Phase 2: Parallelization & Dependency Analysis

**Goal**: Intelligent parallel execution based on task dependencies

#### Tasks

1. **Add depends_on to Task model** (`core/tasks.py`)
   - New field: `depends_on: list[str]`
   - Migration for existing tasks

2. **Implement dependency graph** (`core/conductor.py`)
   - Build DAG from task dependencies
   - Topological sort for execution order
   - Group independent tasks for parallel execution

3. **Add agent-based dependency analyzer** (`core/dependency_analyzer.py`)
   - Use LLM to analyze task descriptions
   - Infer dependencies from:
     - File paths mentioned
     - "After X" / "Once Y is done" language
     - PRD structure (sections imply order)
   - Generate `depends_on` suggestions

4. **Implement parallel execution**
   - Worker pool with `max_parallel` limit
   - Process group management
   - Graceful shutdown on Ctrl+C

5. **Add `--strategy auto`**
   - Run dependency analyzer
   - Show inferred graph
   - Execute with parallelization

6. **Add `--analyze` flag**
   - Show dependency graph without executing
   - Let user review before committing

#### Acceptance Criteria
- [x] Tasks with `depends_on=[]` run in parallel
- [x] Tasks with dependencies wait for predecessors
- [x] `--strategy auto` infers and uses dependencies
- [ ] `--analyze` shows graph preview (moved to Phase 3)
- [x] Max parallel limit respected

### Phase 3: Observability & Streaming

**Goal**: Real-time visibility into batch execution

#### Tasks

1. **Add `cf work batch follow`**
   - Stream events to terminal
   - Progress bar / spinner
   - ETA estimation

2. **Create websocket adapter** (`server/batch_ws.py`)
   - `/ws/batch/{batch_id}` endpoint
   - Subscribe to batch events
   - Push to connected clients

3. **Add batch dashboard endpoint** (optional)
   - REST endpoint for batch status
   - Aggregate statistics

4. **Progress estimation**
   - Track historical task durations
   - Estimate remaining time

#### Acceptance Criteria
- [ ] `cf work batch follow <id>` shows live updates
- [ ] Websocket pushes events to subscribers
- [ ] Progress includes ETA

---

## File Structure

```
codeframe/
├── core/
│   ├── conductor.py           # NEW: Batch orchestration
│   ├── dependency_analyzer.py # NEW (Phase 2): LLM-based analysis
│   ├── runtime.py             # Existing (unchanged)
│   ├── agent.py               # Existing (unchanged)
│   ├── tasks.py               # Modified: add depends_on field
│   └── events.py              # Modified: add batch events
├── cli/
│   └── app.py                 # Modified: add batch subcommands
├── server/
│   └── batch_ws.py            # NEW (Phase 3): WebSocket adapter
└── tests/
    └── core/
        ├── test_conductor.py  # NEW
        └── test_dependency_analyzer.py  # NEW (Phase 2)
```

---

## Execution Strategy Details

### Serial Execution (Phase 1 Default)

```python
def _execute_serial(self, workspace, batch_run):
    for task_id in batch_run.task_ids:
        # Spawn subprocess
        proc = subprocess.Popen(
            ['cf', 'work', 'start', task_id, '--execute'],
            cwd=workspace.repo_path,
        )

        # Wait for completion
        proc.wait()

        # Check result from database
        run = runtime.get_active_run(workspace, task_id)
        batch_run.results[task_id] = run.status.value

        # Emit event
        self._emit_task_completed(batch_run, task_id, run.status)
```

### Parallel Execution (Phase 2)

```python
def _execute_parallel(self, workspace, batch_run, execution_groups):
    for group in execution_groups:
        # Start all tasks in group
        processes = {}
        for task_id in group:
            proc = subprocess.Popen(
                ['cf', 'work', 'start', task_id, '--execute'],
                cwd=workspace.repo_path,
            )
            processes[task_id] = proc

        # Wait for all in group
        for task_id, proc in processes.items():
            proc.wait()
            # ... update results ...

        # Continue to next group
```

### Agent-Based Dependency Analysis (Phase 2)

```python
def analyze_dependencies(workspace, task_ids) -> dict[str, list[str]]:
    """Use LLM to infer task dependencies.

    Returns:
        Dict mapping task_id -> list of task_ids it depends on
    """
    tasks = [tasks.get(workspace, tid) for tid in task_ids]

    prompt = f"""Analyze these tasks and identify dependencies.

Tasks:
{format_tasks(tasks)}

For each task, list which other tasks (by ID) must complete first.
Return as JSON: {{"task_id": ["dependency_id", ...], ...}}
Tasks with no dependencies should have an empty list.
"""

    response = llm.generate(prompt, purpose=Purpose.PLANNING)
    return parse_dependency_json(response)
```

---

## Error Handling

### Task Failure Strategies

| Strategy | Behavior |
|----------|----------|
| `--on-failure continue` | Continue with remaining tasks (default) |
| `--on-failure stop` | Stop batch on first failure |
| `--on-failure skip-dependents` | Skip tasks that depend on failed task |

### Blocker Handling

When a task becomes BLOCKED:
1. Emit `BATCH_TASK_BLOCKED` event
2. Continue with other tasks (if parallel)
3. At end, batch status = PARTIAL if any blocked

User can:
- Answer blockers: `cf blocker answer <id> "answer"`
- Resume: `cf work batch resume <batch-id>` (re-runs blocked tasks)

---

## CLI Output Design

### Batch Start

```
$ cf work batch run t1 t2 t3

Starting batch 7a3b...
Strategy: serial
Tasks: 3

[1/3] Starting task t1: Add user authentication
      ⟳ Running...
      ✓ Completed (2m 34s)

[2/3] Starting task t2: Add login form
      ⟳ Running...
      ✓ Completed (1m 12s)

[3/3] Starting task t3: Add logout button
      ⟳ Running...
      ✗ Failed: Verification gate failed

Batch completed: 2 succeeded, 1 failed
Duration: 4m 18s
```

### Batch Status

```
$ cf work batch status 7a3b

Batch 7a3b...
Status: PARTIAL
Strategy: serial
Started: 2025-01-15 10:30:00
Duration: 4m 18s

Tasks:
  ✓ t1  Add user authentication     DONE      2m 34s
  ✓ t2  Add login form              DONE      1m 12s
  ✗ t3  Add logout button           FAILED    0m 32s

Summary: 2/3 completed (67%)
```

---

## Future Enhancements: Retry & Self-Correction

### Current State (Phase 1)
- Individual agents have self-correction: when verification fails, the agent
  can re-attempt with a stronger model (Opus) via the `CORRECTION` purpose
- Batch conductor does NOT retry failed tasks automatically
- Failed tasks are recorded in `batch.results` with status `FAILED`

### Planned: Batch-Level Retry (Phase 2+)

#### Option A: Simple Retry Flag ✓ IMPLEMENTED
```bash
cf work batch run t1 t2 t3 --retry 2    # Retry failed tasks up to 2 times
cf work batch run --all-ready --retry 1  # One retry attempt
```

Implementation (DONE):
- After all tasks complete in initial run, re-run FAILED tasks up to N times
- Retries stop early if all tasks succeed before exhausting max_retries
- BLOCKED tasks are NOT retried (they need human intervention)
- Final batch status based on all results after retries complete

#### Option B: Batch Resume Command ✓ IMPLEMENTED
```bash
cf work batch resume <batch-id>         # Re-run only failed/blocked tasks
cf work batch resume <batch-id> --force # Re-run even completed tasks
```

Implementation (DONE):
- Load existing BatchRun via `resume_batch()`
- Filter to tasks with FAILED or BLOCKED status
- Execute only those tasks (or all with --force)
- Merge results into existing batch record
- Update batch status based on final results

#### Option C: Self-Correction Escalation
When a task fails repeatedly:
1. First attempt: Normal execution
2. Retry 1: Use `CORRECTION` purpose (stronger model)
3. Retry 2: Add previous error context to prompt
4. Final: Mark as BLOCKED with human review required

### Decision Points
- [x] Which retry approach to implement first? → **Batch Resume (Option B)** ✓
- [x] Should we also implement --retry N flag? → **Yes (Option A)** ✓
- [ ] Should retries use exponential backoff?
- [ ] Should we track retry history for analytics?
- [ ] Should blocked tasks prevent retries of dependent tasks?

---

## Open Questions

1. **Retry logic**: Should failed tasks auto-retry? How many times?
   - Recommendation: No auto-retry in Phase 1. Add `--retry N` in Phase 2.
   - See "Future Enhancements" section above for detailed options.

2. **Resource limits**: Should we limit total LLM tokens across batch?
   - Recommendation: Defer. Let each task manage its own budget.

3. **Batch resume**: If batch is interrupted (Ctrl+C), resume from where it left off?
   - Recommendation: Yes, track which tasks completed and skip them on resume.

4. **Self-correction integration**: How should batch leverage agent self-correction?
   - Current: Agent already self-corrects within a single run
   - Future: Batch could escalate failed tasks to stronger models

---

## References

- [GOLDEN_PATH.md](./GOLDEN_PATH.md) - CLI-first workflow contract
- [CLI_WIREFRAME.md](./CLI_WIREFRAME.md) - Command structure
- [finished/AGENT_IMPLEMENTATION_TASKS.md](./finished/AGENT_IMPLEMENTATION_TASKS.md) - Agent architecture
