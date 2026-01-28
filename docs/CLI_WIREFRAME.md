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
  - `prd.py` (PRD store + AI-driven generation)
  - `tasks.py` (task generation + CRUD with dependencies)
  - `blockers.py` (blocker store + AI-powered resolution)
  - `runtime.py` (single-task orchestrator/worker loop)
  - `conductor.py` (batch orchestration, multi-task execution)
  - `dependency_analyzer.py` (LLM-based dependency inference)
  - `checkpoints.py` (snapshot + restore with git refs)
  - `gates.py` (enhanced review/test runners)
  - `git_integration.py` (Git workflow and PR management)
- `codeframe/adapters/` (optional but recommended)
  - `llm/` (provider-specific clients)
  - `git/` (branch/worktree/patch utilities + PR operations)
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

### `codeframe prd generate` (Enhanced - Primary)
**Purpose:** AI-driven interactive PRD generation.

**CLI module:**
- `codeframe/cli/commands/prd.py`

**Core calls:**
- `codeframe.core.prd.start_discovery_session(workspace_id) -> DiscoverySession`
- `codeframe.core.prd.ask_followup_questions(session, context) -> DiscoverySession`
- `codeframe.core.prd.generate_prd(session) -> PrdRecord`
- `codeframe.core.prd.refine_prd(prd_id, feedback) -> PrdRecord`
- `codeframe.core.events.emit(workspace_id, "PRD_GENERATED", payload)`

**State writes:**
- Discovery session records
- Comprehensive PRD record with technical specs
- Version history and change tracking

**Adapter usage:**
- LLM adapter for interactive discovery and content generation
- Analysis adapter for technical requirement extraction

---

### `codeframe prd add <file.md>` (Legacy Support)
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

### `codeframe prd refine <prd-id>`
**Purpose:** Iterative PRD improvement based on feedback.

**CLI module:**
- `codeframe/cli/commands/prd.py`

**Core calls:**
- `codeframe.core.prd.get(workspace_id, prd_id) -> PrdRecord`
- `codeframe.core.prd.suggest_improvements(prd) -> list[Suggestion]`
- `codeframe.core.prd.apply_feedback(prd_id, feedback) -> PrdRecord`
- `codeframe.core.events.emit(workspace_id, "PRD_REFINED", payload)`

**State writes:**
- Updated PRD record
- Suggestion and feedback history

---

### `codeframe prd show [prd-id]`
**Purpose:** Print PRD content. Without ID shows latest; with ID shows specific PRD.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.get_latest(workspace_id) -> PrdRecord` (if no ID)
- `codeframe.core.prd.get_by_id(workspace_id, prd_id) -> PrdRecord` (if ID provided)

**CLI options:**
- `--full`: Show complete content (default truncates long PRDs)
- `--workspace/-w`: Workspace path (defaults to cwd)

---

### `codeframe prd list`
**Purpose:** List all PRDs in the workspace.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.list_all(workspace_id) -> list[PrdRecord]`

**Output:**
- Table showing: ID (truncated), Title, Version, Created date

---

### `codeframe prd delete <prd-id>`
**Purpose:** Delete a PRD from the workspace.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.get_by_id(workspace_id, prd_id) -> PrdRecord`
- `codeframe.core.prd.delete(workspace_id, prd_id, check_dependencies) -> bool`
- `codeframe.core.events.emit(workspace_id, "PRD_DELETED", payload)`

**CLI options:**
- `--force, -f`: Skip confirmation prompt
- `--workspace/-w`: Workspace path (defaults to cwd)

**State writes:**
- Removes PRD record from database

**Validation:**
- Checks for dependent tasks (raises `PrdHasDependentTasksError` if found with `check_dependencies=True`)

---

### `codeframe prd export <prd-id> <file-path>`
**Purpose:** Export a PRD to a file.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.export_to_file(workspace_id, prd_id, file_path, force) -> bool`

**CLI options:**
- `--latest`: Export the latest PRD instead of requiring ID
- `--force, -f`: Overwrite existing file
- `--workspace/-w`: Workspace path (defaults to cwd)

**State reads only** (exports content to file)

---

### `codeframe prd versions <prd-id>`
**Purpose:** Show version history for a PRD.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.get_versions(workspace_id, prd_id) -> list[PrdRecord]`

**Output:**
- Table showing: Version number, ID (truncated), Change summary, Created date
- Versions sorted by version number descending (newest first)

---

### `codeframe prd diff <prd-id> <version1> <version2>`
**Purpose:** Show diff between two versions of a PRD.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.diff_versions(workspace_id, prd_id, v1, v2) -> str`

**Output:**
- Unified diff format showing additions (+) and removals (-)

---

### `codeframe prd update <prd-id>`
**Purpose:** Create a new version of an existing PRD.

**CLI module:**
- `codeframe/cli/app.py` (prd subcommand group)

**Core calls:**
- `codeframe.core.prd.load_file(file_path) -> str`
- `codeframe.core.prd.create_new_version(workspace_id, prd_id, content, change_summary) -> PrdRecord`
- `codeframe.core.events.emit(workspace_id, "PRD_UPDATED", payload)`

**CLI options:**
- `--file, -f`: Path to file with new content (required)
- `--message, -m`: Change summary message (required)
- `--workspace/-w`: Workspace path (defaults to cwd)

**State writes:**
- New PRD record with incremented version
- Links to parent via `parent_id`
- Shares `chain_id` with all versions in the chain

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

## Git Integration & PR Management: `codeframe git ...` / `codeframe pr ...`

### `codeframe work start <task_id> --create-branch`
**Purpose:** Begin task execution with automatic branch creation.

**CLI module:**
- `codeframe/cli/commands/work.py`

**Core calls:**
- `branch_name = codeframe.core.git.create_feature_branch(workspace_id, task_id)`
- `run = codeframe.core.runtime.start_task_run(workspace_id, task_id, branch=branch_name)`
- `emit(..., "TASK_STARTED_WITH_BRANCH", payload)`

**Adapter usage:**
- git adapter for branch management

---

### `codeframe pr create [--title <title>] [--branch <branch>] [--base <base>]`
**Purpose:** Create pull request with optional auto-generated description from commits.

**CLI module:**
- `codeframe/cli/pr_commands.py`

**Core calls:**
- `GitHubIntegration.create_pull_request(branch, title, body, base)`

**Options:**
- `--title/-t`: PR title (required)
- `--branch/-b`: Source branch (defaults to current)
- `--base`: Target branch (defaults to main)
- `--body`: PR description body
- `--auto-description/--no-auto-description`: Auto-generate from commits

**Adapter usage:**
- `codeframe.git.github_integration.GitHubIntegration`

**Examples:**
```bash
codeframe pr create --title "Add new feature"
codeframe pr create --branch feature/auth --title "Auth system" --base develop
codeframe pr create --title "Quick fix" --no-auto-description
```

---

### `codeframe pr list [--status open|closed|all] [--format table|json]`
**Purpose:** List pull requests with optional filtering.

**CLI module:**
- `codeframe/cli/pr_commands.py`

**Core calls:**
- `GitHubIntegration.list_pull_requests(state)`

**Examples:**
```bash
codeframe pr list
codeframe pr list --status closed
codeframe pr list --format json
```

---

### `codeframe pr get <pr-number> [--format text|json]`
**Purpose:** Get detailed information about a specific PR.

**CLI module:**
- `codeframe/cli/pr_commands.py`

**Core calls:**
- `GitHubIntegration.get_pull_request(pr_number)`

**Examples:**
```bash
codeframe pr get 42
codeframe pr get 42 --format json
```

---

### `codeframe pr merge <pr-number> [--strategy squash|merge|rebase]`
**Purpose:** Merge pull request with specified strategy.

**CLI module:**
- `codeframe/cli/pr_commands.py`

**Core calls:**
- `GitHubIntegration.get_pull_request(pr_number)` (validate state)
- `GitHubIntegration.merge_pull_request(pr_number, method)`

**Examples:**
```bash
codeframe pr merge 42
codeframe pr merge 42 --strategy rebase
```

---

### `codeframe pr close <pr-number>`
**Purpose:** Close a pull request without merging.

**CLI module:**
- `codeframe/cli/pr_commands.py`

**Core calls:**
- `GitHubIntegration.close_pull_request(pr_number)`

**Examples:**
```bash
codeframe pr close 42
```

---

### `codeframe pr status`
**Purpose:** Show PR status for current branch.

**CLI module:**
- `codeframe/cli/pr_commands.py`

**Core calls:**
- `get_current_branch()` (git helper)
- `GitHubIntegration.list_pull_requests(state="open")`
- Filters to find PR matching current branch

**Examples:**
```bash
codeframe pr status
```

---

### `codeframe git status` (Enhanced)
**Purpose:** Show git status summary with CodeFRAME context.

**CLI module:**
- `codeframe/cli/commands/git.py`

**Core calls:**
- `status = codeframe.core.git.get_enhanced_status(workspace_id)`

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

## Implementation order (reordered for Enhanced MVP)

### Enhanced MVP Priority Order

### Phase 0: Enhanced PRD & Discovery (NEW HIGH PRIORITY)
1) `prd generate` - AI-driven interactive PRD generation with follow-up questions
2) `prd refine` - iterative PRD improvement based on user feedback
3) Enhanced `init` with auto-discovery and environment configuration
4) PRD versioning and change tracking

### Phase 1: Enhanced Task Generation (NEW HIGH PRIORITY)
5) Enhanced `tasks generate` with dependency analysis and effort estimation
6) Task template system for common implementation patterns
7) Critical path identification and workstream grouping
8) `tasks analyze` - dependency graph visualization and analysis

### Phase 2: Git Integration & PR Workflow (NEW HIGH PRIORITY)
9) `codeframe git_integration` module implementation
10) Enhanced `work start --create-branch` with automatic branch management
11) `pr create` with AI-generated comprehensive descriptions
12) `pr merge` with automated verification and merge strategies
13) Git adapter for branch/worktree/patch operations

### Phase 3: Enhanced Quality Gates (UPGRADED)
14) Enhanced `gates.run` with comprehensive test suite
15) AI-assisted code review and best practices checking
16) Quality metrics tracking and trend analysis
17) Technical debt accumulation monitoring
18) Security and performance regression detection

### Phase 4: Advanced Blocker Resolution (ENHANCED)
19) Enhanced blocker system with AI-powered suggestions
20) Contextual blocker display with rich background information
21) Learning system for blocker pattern recognition
22) Similar past blocker solutions and recommendations

### Phase 5: Advanced Checkpointing (ENHANCED)
23) Rich checkpoint snapshots with complete workspace state
24) Cross-environment checkpoint portability
25) Seamless workflow resumption from any checkpoint
26) Executive reporting with progress and risk metrics

### Legacy Phase Completion (MAINTAINED)
**Basic Golden Path (already complete):**
- Basic `init` + durable state ✓ DONE
- Basic `prd add` ✓ DONE (superseded by `prd generate`)
- Basic `tasks generate` ✓ DONE (enhanced above)
- Basic `work start` ✓ DONE (enhanced with git integration)
- Basic blockers ✓ DONE (enhanced above)
- Basic review/gates ✓ DONE (enhanced above)
- Basic patch/commit ✓ DONE (enhanced with PR workflow)
- Basic checkpoint + summary ✓ DONE (enhanced above)

**Batch Execution (already complete):**
- `work batch run` ✓ DONE (enhanced with git integration)
- `work batch status` ✓ DONE
- `work batch cancel` ✓ DONE
- Parallel execution & retry ✓ DONE
- Observability ✓ DONE

Only after Enhanced MVP phases are complete:
- Production readiness features
- Advanced multi-provider support
- Performance optimization at scale
- Enterprise security and compliance features
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
