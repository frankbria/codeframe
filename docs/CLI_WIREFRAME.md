# CodeFRAME v2 — Command Tree + Module Mapping (Cheat Sheet)

This document prevents “architecture freestyling” by providing a single authoritative map:

- CLI commands (Typer)
- The core functions they call
- The state they read/write
- The events they emit
- The adapters they may use

**Rule:** Implement commands exactly as mapped here unless `docs/GOLDEN_PATH.md` changes.

---

## Target module layout (within existing repo structure)

Repository currently uses a top-level `codeframe/` Python package and `web-ui/` at top level.

Add these subpackages under `codeframe/`:

- `codeframe/cli/`
  - `app.py` (Typer root)
  - `commands/` (subcommands grouped by domain)
- `codeframe/core/`
  - `models.py` (Pydantic/dataclasses for domain objects)
  - `state_machine.py` (authoritative transitions)
  - `events.py` (event log interface + event types)
  - `workspace.py` (workspace registration + config)
  - `config.py` (environment configuration: package manager, test framework, lint tools)
  - `prd.py` (PRD store + parsing)
  - `tasks.py` (task generation + CRUD)
  - `blockers.py` (blocker store + answering)
  - `runtime.py` (single-task orchestrator/worker loop)
  - `conductor.py` (batch orchestration, multi-task execution)
  - `dependency_analyzer.py` (Phase 2: LLM-based dependency inference)
  - `checkpoints.py` (snapshot + restore)
  - `gates.py` (review/test runners)
- `codeframe/adapters/` (optional but recommended)
  - `llm/` (provider-specific clients)
  - `git/` (branch/worktree/patch utilities)
  - `fs/` (file operations)
  - `persistence/` (SQLite/filesystem implementations)
- `codeframe/server/` (FastAPI wrapper; optional during Golden Path)
  - `app.py` (FastAPI app)
  - `routes/` (thin wrappers over core)

Legacy quarantine:
- Move `web-ui/` -> `legacy/web-ui/` (or `legacy/` equivalent)

---

## Shared concepts (authoritative)

### State store (durable)
- SQLite or filesystem-backed store.
- Recommended location: `.codeframe/` in workspace repo OR repo root `codeframe.db`.
- Must support: workspaces, PRDs, tasks, blockers, checkpoints, event log pointers.

### Event log (append-only)
- Core emits events for all meaningful actions.
- CLI prints selected events to stdout and can tail the log.
- Server/UI may subscribe later; server is not required for event recording.

### State machine (task status)
Statuses:
- `BACKLOG`, `READY`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `MERGED` (optional later)

Transitions enforced in `codeframe/core/state_machine.py`.

---

## Command Tree (Typer) → Core mapping

Notation:
- CLI entrypoint: `codeframe/cli/app.py`
- Core functions are suggested names; adjust if repo already has similar functions.

Each command:
- Calls core functions
- Writes durable state
- Emits events

---

## Root: `codeframe`

### `codeframe init <repo_path>`
**Purpose:** Create/register a workspace.

**CLI module:**
- `codeframe/cli/commands/workspace.py`

**Core calls:**
- `codeframe.core.workspace.create_or_load(repo_path) -> Workspace`
- `codeframe.core.events.emit(workspace_id, "WORKSPACE_INIT", payload)`

**State writes:**
- Workspace record (id, path, created_at, config)

**Notes:**
- Must not start server.
- Must succeed even if repo already initialized (idempotent).

---

### `codeframe status`
**Purpose:** Show current workspace summary + task counts + latest activity.

**CLI module:**
- `codeframe/cli/commands/status.py`

**Core calls:**
- `codeframe.core.workspace.get_current() -> Workspace`
- `codeframe.core.tasks.list_by_status(workspace_id) -> dict[Status, list[Task]]`
- `codeframe.core.events.list_recent(workspace_id, limit=20) -> list[Event]`

**State reads only.**
**Emits:** optional `STATUS_VIEWED` event (not required).

---

## Configuration: `codeframe config ...`

### `codeframe config init [--detect] [--force]`
**Purpose:** Initialize project environment configuration.

**CLI module:**
- `codeframe/cli/app.py` (config_app subgroup)

**Core calls:**
- `codeframe.core.config.load_environment_config(workspace_path) -> EnvironmentConfig | None`
- `codeframe.core.config.save_environment_config(workspace_path, config) -> None`
- Auto-detection reads: pyproject.toml, package.json, lock files

**Options:**
- `--detect`: Auto-detect settings from project files (non-interactive)
- `--force`: Overwrite existing config file
- `--workspace/-w`: Workspace path (defaults to cwd)

**State writes:**
- `.codeframe/config.yaml`

---

### `codeframe config show`
**Purpose:** Display current project configuration.

**Core calls:**
- `codeframe.core.config.load_environment_config(workspace_path) -> EnvironmentConfig | None`
- `codeframe.core.config.get_default_environment_config() -> EnvironmentConfig` (fallback)

**State reads only.**

---

### `codeframe config set <key> <value>`
**Purpose:** Set individual configuration values.

**Core calls:**
- `codeframe.core.config.load_environment_config(workspace_path) -> EnvironmentConfig | None`
- `codeframe.core.config.save_environment_config(workspace_path, config) -> None`
- `config.validate() -> list[str]` (validation errors)

**Valid keys:**
- `package_manager`: uv, pip, poetry, npm, pnpm, yarn
- `python_version`: e.g., 3.11
- `test_framework`: pytest, jest, vitest, mocha
- `lint_tools`: comma-separated, e.g., "ruff,mypy"
- `test_command`: custom test command override
- `lint_command`: custom lint command override

**State writes:**
- `.codeframe/config.yaml`

---

## PRD: `codeframe prd ...`

### `codeframe prd add <file.md>`
**Purpose:** Store PRD text + metadata.

**CLI module:**
- `codeframe/cli/commands/prd.py`

**Core calls:**
- `codeframe.core.prd.load_file(path) -> str`
- `codeframe.core.prd.store(workspace_id, text, metadata) -> PrdRecord`
- `codeframe.core.events.emit(workspace_id, "PRD_ADDED", payload)`

**State writes:**
- PRD record (id, title, text, created_at)

---

### `codeframe prd show`
**Purpose:** Print PRD summary/title and location.

**Core calls:**
- `codeframe.core.prd.get_latest(workspace_id) -> PrdRecord`

---

## Tasks: `codeframe tasks ...`

### `codeframe tasks generate`
**Purpose:** Generate tasks from PRD.

**CLI module:**
- `codeframe/cli/commands/tasks.py`

**Core calls:**
- `codeframe.core.prd.get_latest(workspace_id) -> PrdRecord`
- `codeframe.core.tasks.generate_from_prd(workspace_id, prd_id) -> list[Task]`
- `codeframe.core.events.emit(workspace_id, "TASKS_GENERATED", payload)`

**State writes:**
- Task records (id, title, description, status=BACKLOG/READY)

**Adapter usage:**
- LLM provider adapter may be used inside `generate_from_prd` (allowed).
- But keep provider code out of core; core uses an interface like `LLMClient`.

---

### `codeframe tasks list [--status READY]`
**Purpose:** List tasks.

**Core calls:**
- `codeframe.core.tasks.list(workspace_id, status=None) -> list[Task]`

---

### `codeframe tasks set status <task_id> <status>`
**Purpose:** Manually transition state.

**Core calls:**
- `codeframe.core.state_machine.transition(task, new_status) -> Task`
- `codeframe.core.tasks.update_status(workspace_id, task_id, new_status)`
- `codeframe.core.events.emit(workspace_id, "TASK_STATUS_CHANGED", payload)`

**Future state:**
- Allow other task attributes to be set, like `provider`, etc.
- `codeframe task set <attribute> <task_id> <attribute_value>`

### `codeframe tasks get status <task_id>`
**Purpose:** Get current state.

**Core calls:**
-`codeframe.core.tasks.get_status(workspace_id, task_id)`

**Future state:**
- Allow other task attributes to be retrieved

---

## Work: `codeframe work ...`

### `codeframe work start <task_id>`
**Purpose:** Begin execution of a task.

**CLI module:**
- `codeframe/cli/commands/work.py`

**Core calls:**
- `workspace = codeframe.core.workspace.get_current()`
- `task = codeframe.core.tasks.get(workspace_id, task_id)`
- `codeframe.core.tasks.update_status(..., IN_PROGRESS)`
- `run_id = codeframe.core.runtime.start_task_run(workspace_id, task_id) -> RunRecord`
- `codeframe.core.events.emit(workspace_id, "RUN_STARTED", payload)`

**Runtime behavior (core):**
- Orchestrator executes agent plan for the task.
- Emits step events:
  - `AGENT_STEP_STARTED`, `AGENT_STEP_COMPLETED`
  - `PATCH_UPDATED` / `FILES_MODIFIED`
  - `BLOCKER_CREATED` when stuck

**Adapter usage (runtime):**
- LLM adapter
- git adapter (branch/worktree/patch)
- fs adapter

**Important constraint:**
- Must work without FastAPI server running.

---

### `codeframe work resume <task_id>`
**Purpose:** Continue after blocker resolution or pause.

**Core calls:**
- `codeframe.core.runtime.resume_task_run(workspace_id, task_id)`

---

### `codeframe work stop <task_id>`
**Purpose:** Stop execution (graceful).

**Core calls:**
- `codeframe.core.runtime.stop_task_run(workspace_id, task_id)`

---

### `codeframe work batch run <task_ids...>` (Phase 1)
**Purpose:** Execute multiple tasks in sequence (or parallel in Phase 2).

**CLI module:**
- `codeframe/cli/commands/work.py` (batch subcommand group)

**Core calls:**
- `batch = codeframe.core.conductor.start_batch(workspace_id, task_ids, strategy, max_parallel)`
- `codeframe.core.events.emit(workspace_id, "BATCH_STARTED", payload)`
- For each task: spawns subprocess `cf work start <task_id> --execute`
- `codeframe.core.events.emit(workspace_id, "BATCH_COMPLETED", payload)`

**State writes:**
- BatchRun record (id, task_ids, status, strategy, results)

**CLI options:**
- `--all-ready`: Process all READY tasks instead of specifying IDs
- `--strategy serial|parallel`: Execution strategy (default: serial)
- `--max-parallel N`: Max concurrent tasks when parallel (default: 4)
- `--dry-run`: Show execution plan without running
- `--on-failure continue|stop`: Behavior on task failure (default: continue)
- `--retry N, -r N`: Max retry attempts for failed tasks (default: 0, no retries)

**Important constraint:**
- Must work without FastAPI server running.
- Phase 1: Serial execution only (parallel flag accepted but runs serial)
- Phase 2: True parallel execution with dependency analysis

---

### `codeframe work batch status [batch_id]`
**Purpose:** Show batch execution status.

**Core calls:**
- `codeframe.core.conductor.list_batches(workspace_id)` (if no batch_id)
- `codeframe.core.conductor.get_batch(workspace_id, batch_id)` (if batch_id provided)

**Output:**
- Batch ID, status, strategy
- Task progress (completed/total)
- Per-task status and duration

---

### `codeframe work batch cancel <batch_id>`
**Purpose:** Cancel a running batch.

**Core calls:**
- `codeframe.core.conductor.cancel_batch(workspace_id, batch_id)`
- `codeframe.core.events.emit(workspace_id, "BATCH_CANCELLED", payload)`

**Behavior:**
- Sends SIGTERM to running subprocesses
- Marks batch as CANCELLED
- Does not affect already-completed tasks

---

### `codeframe work batch resume <batch_id>` (Phase 2)
**Purpose:** Re-run failed/blocked tasks from a previous batch.

**Core calls:**
- `codeframe.core.conductor.resume_batch(workspace_id, batch_id, force)`
- `codeframe.core.events.emit(workspace_id, "BATCH_STARTED", payload)` with `is_resume=True`

**CLI options:**
- `--force, -f`: Re-run all tasks including completed ones

**Behavior:**
- Loads existing BatchRun record
- Identifies tasks with FAILED or BLOCKED status
- Re-executes only those tasks (or all with --force)
- Merges new results into existing batch
- Updates batch status based on final results

**Example:**
```bash
cf work batch resume abc123           # Re-run failed/blocked only
cf work batch resume abc123 --force   # Re-run all tasks
```

---

### `codeframe events tail`
**Purpose:** Tail event log in terminal.

**Core calls:**
- `codeframe.core.events.tail(workspace_id, since=<cursor>) -> iterator[Event]`

---

## Blockers: `codeframe blocker ...`

### `codeframe blocker list`
**Purpose:** List open blockers.

**CLI module:**
- `codeframe/cli/commands/blockers.py`

**Core calls:**
- `codeframe.core.blockers.list_open(workspace_id) -> list[Blocker]`

---

### `codeframe blocker answer <blocker_id> "<text>"`
**Purpose:** Answer a blocker and unblock work.

**Core calls:**
- `codeframe.core.blockers.answer(workspace_id, blocker_id, text)`
- `codeframe.core.events.emit(workspace_id, "BLOCKER_ANSWERED", payload)`
- Optional: `codeframe.core.runtime.notify_blocker_answered(...)`

---

### `codeframe blocker resolve <blocker_id>`
**Purpose:** Mark blocker resolved (optional if answer implies resolved).

**Core calls:**
- `codeframe.core.blockers.resolve(workspace_id, blocker_id)`
- `emit(..., "BLOCKER_RESOLVED")`

---

## Review / Gates: `codeframe review` or `codeframe gates run`

### `codeframe review`
**Purpose:** Run verification gates.

**CLI module:**
- `codeframe/cli/commands/gates.py`

**Core calls:**
- `result = codeframe.core.gates.run(workspace_id, repo_path) -> GateResult`
- `emit(..., "GATES_COMPLETED", payload)`

**Adapters:**
- process runner / shell adapter

**MVP gates:**
- run `pytest` if present
- record pass/fail + logs

---

## Artifacts: `codeframe patch ...` / `codeframe commit ...`

### `codeframe patch export [--out <file.patch>]`
**Purpose:** Export changes safely.

**CLI module:**
- `codeframe/cli/commands/artifacts.py`

**Core calls:**
- `patch_path = codeframe.core.runtime.export_patch(workspace_id, repo_path, out_path=None)`
- `emit(..., "PATCH_EXPORTED", payload)`

**Adapters:**
- git adapter or filesystem diff tool

---

### `codeframe commit create -m "<message>"`
**Purpose:** Create a commit for completed work.

**Core calls:**
- `commit_hash = codeframe.core.runtime.create_commit(workspace_id, repo_path, message)`
- `emit(..., "COMMIT_CREATED", payload)`

**Notes:**
- This can be postponed in favor of patch export early.

---

## Checkpoints: `codeframe checkpoint ...`

### `codeframe checkpoint create "<name>"`
**Purpose:** Snapshot durable state + optionally repo ref.

**CLI module:**
- `codeframe/cli/commands/checkpoints.py`

**Core calls:**
- `checkpoint = codeframe.core.checkpoints.create(workspace_id, name)`
- `emit(..., "CHECKPOINT_CREATED", payload)`

---

### `codeframe checkpoint list`
**Purpose:** List checkpoints.

**Core calls:**
- `codeframe.core.checkpoints.list(workspace_id) -> list[Checkpoint]`

---

### `codeframe checkpoint restore "<name|id>"`
**Purpose:** Restore state snapshot.

**Core calls:**
- `codeframe.core.checkpoints.restore(workspace_id, checkpoint_id)`

---

## Summary: `codeframe summary`

### `codeframe summary`
**Purpose:** Print a short status report of the workspace.

**CLI module:**
- `codeframe/cli/commands/summary.py`

**Core calls:**
- `prd = prd.get_latest(...)`
- `tasks = tasks.list(...)`
- `blockers = blockers.list_open(...)`
- `artifacts = runtime.list_artifacts(...)`
- `emit(..., "SUMMARY_VIEWED", payload)` (optional)

Output includes:
- PRD title
- Tasks by status
- Open blockers
- Latest artifact(s)
- Latest checkpoint

---

## Server (optional adapter): `codeframe serve`

### `codeframe serve`
**Purpose:** Start FastAPI server as a wrapper over core.

**CLI module:**
- `codeframe/cli/commands/server.py`

**Server module:**
- `codeframe/server/app.py`

**Hard rules:**
- FastAPI routes must call core functions.
- No domain logic lives in routes.
- Golden Path must work without running `serve`.

---

## “Keep vs Start Over” guidance (for existing CLI)

### Keep
- Any existing Typer CLI scaffolding that:
  - already runs headlessly
  - maps to Golden Path commands cleanly
  - does not import FastAPI routes or UI modules

### Start over (recommended if unclear)
- Create a new `codeframe/cli/app.py` Typer root.
- Add the Golden Path commands as above.
- Leave old CLI commands in legacy or deprecate later.

---

## Implementation order (do not reorder)

### Phase 0: Golden Path (COMPLETE)
1) `init` + durable state
2) `prd add`
3) `tasks generate`
4) `status`
5) `work start` (stubbed run loop ok initially, but must emit events)
6) blockers list/answer
7) review/gates
8) patch export (preferred before commit)
9) checkpoint + summary

### Phase 1: Batch Execution (COMPLETE)
10) `work batch run` - serial execution of multiple tasks
11) `work batch status` - batch status monitoring
12) `work batch cancel` - batch cancellation

### Phase 2: Parallel Execution & Retry (COMPLETE)
13) `work batch resume <batch-id>` - re-run failed/blocked tasks ✓ DONE
14) `depends_on` field on Task model ✓ DONE
15) Dependency graph analysis ✓ DONE
16) True parallel execution with worker pool ✓ DONE
17) `--strategy auto` with LLM-based dependency inference ✓ DONE
18) `work batch run --retry N` - automatic retry of failed tasks ✓ DONE

### Phase 3: Observability (IN PROGRESS)
19) `work batch follow` - live streaming to terminal ✓ DONE
20) WebSocket adapter for batch events (deferred - infrastructure exists)
21) Progress estimation and ETA ✓ DONE

Only after these are stable:
- server adapter improvements
- UI rebuilding
- multi-provider switching

---

## Quick “don’t do this” list (common failure modes)

- Don’t build new HTTP endpoints to support the CLI.
- Don’t require `codeframe serve` to be running for CLI commands.
- Don’t implement UI concepts (tabs, panels, progress bars) in core.
- Don’t refactor the entire repo layout “because it’s cleaner.”
- Don’t add multi-model selection logic before Golden Path works.
- Don’t import legacy UI/server modules into core.

---

## Acceptance criteria (must match Golden Path)

If any of these are false, stop and fix before adding features:
- Golden Path commands work without FastAPI running.
- Core contains domain logic; server is thin.
- Legacy UI is quarantined and not depended upon by core.
- Events are written durably and viewable from CLI.
