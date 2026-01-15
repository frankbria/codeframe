# CodeFRAME v2 — Golden Path Contract (CLI-first)

This document is the contract for CodeFRAME v2 development.

**Rule 0 (the only rule that matters):**
> If a change does not directly support the Golden Path flow below, do not implement it.

This applies to both humans and agentic coding assistants.

---

## Goals

### What “done” looks like (MVP definition)
CodeFRAME can run a complete end-to-end workflow **from the CLI** on a small repo:

1) Initialize a workspace for a target repo
2) Add a PRD
3) Generate tasks
4) Execute one task via agents
5) Handle blockers (human-in-loop)
6) Produce a patch/commit and run gates (tests/lint)
7) Summarize results and checkpoint the state

**No UI is required.**
**A FastAPI server is not required for the Golden Path to work.**

---

## Non-Goals (explicitly forbidden until Golden Path works)

Do not build or refactor:
- Web UI / dashboard features
- Settings pages, preferences, themes
- Multi-provider/model switching UI or complex provider management
- Advanced metrics dashboards or timeseries endpoints
- Auth / sessions for remote users
- Electron desktop app
- Plugin marketplace / extensibility frameworks
- “Perfect” project structure, monorepo tooling, or build system redesign
- Large migrations or renames that aren’t required by Golden Path

These may be revisited **only after** Golden Path is working and stable.

---

## Golden Path CLI Flow (the only flow that matters)

### 0) Preconditions
- A target repo exists (any small test repo is fine).
- CodeFRAME runs locally and can store durable state (SQLite or filesystem).
- The CLI can be run from anywhere.

### 1) Initialize a workspace
Command:
- `codeframe init <path-to-repo>`

Required behavior:
- Registers the repo as a workspace.
- Creates/updates durable state storage.
- Prints a short workspace summary (repo path, workspace id, state location).

Artifacts:
- Local state created (DB/file), e.g. `.codeframe/` and/or `codeframe.db`.

### 2) Add a PRD
Command:
- `codeframe prd add <file.md>` (or `codeframe prd set <file.md>`)

Required behavior:
- Stores PRD text in state.
- Parses minimal metadata if available (title, optional tags).
- Confirms PRD stored.

### 3) Generate tasks from PRD
Command:
- `codeframe tasks generate`

Required behavior:
- Produces a task list in durable state.
- Tasks have at minimum:
  - `id`, `title`, `description`, `status`
- Status values must be from the state machine below.

### 4) Start work on a task (agents run)
Command:
- `codeframe work start <task-id>`

Required behavior:
- Transitions task status to `IN_PROGRESS`.
- Launches agent execution for that task (synchronously or via a worker loop).
- Writes events to an event log (stdout + durable log).
- Uses a working directory strategy (can be simple at MVP):
  - either worktree/branch OR plain git branch OR patch staging
- Must not require any web UI to observe progress.

### 5) Observe status and events (human-in-loop visibility)
Commands:
- `codeframe status`
- `codeframe events tail` (optional, but strongly recommended)
- `codeframe work status <task-id>` (optional)

Required behavior:
- Shows current tasks grouped by status.
- Shows most recent events for active task.
- Makes blockers visible.

### 6) Blockers (human-in-loop)
Commands:
- `codeframe blockers`
- `codeframe blocker answer <blocker-id> "<text>"`
- `codeframe blocker resolve <blocker-id>` (optional)

Required behavior:
- Agents can emit blockers into state.
- Human can answer.
- Agent run continues after answer OR can be resumed with:
  - `codeframe work resume <task-id>`

### 7) Gates / verification
Command:
- `codeframe review` OR `codeframe gates run`

Required behavior:
- Runs basic gates (minimal viable set):
  - `pytest` (if present)
  - lint (optional if already in repo)
- Records results in state and event log.

### 8) Produce an output artifact (patch or commit)
Command:
- `codeframe patch export` OR `codeframe commit create -m "<message>"`

Required behavior:
- Produces either:
  - a patch file (preferred early for safety), OR
  - a git commit on a branch
- Records artifact path/commit hash in state.

### 9) Checkpoint + summary
Commands:
- `codeframe checkpoint create "<name>"`
- `codeframe summary`

Required behavior:
- Creates a checkpoint snapshot of state.
- Produces a short summary:
  - PRD title
  - tasks and statuses
  - completed work and artifacts
  - open blockers

---

## State Machine (authoritative)

Statuses:
- `BACKLOG`
- `READY`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`
- `MERGED` (optional for later)

Allowed transitions (minimal):
- BACKLOG -> READY
- READY -> IN_PROGRESS
- IN_PROGRESS -> BLOCKED
- BLOCKED -> IN_PROGRESS
- IN_PROGRESS -> DONE
- DONE -> READY (reopen)
- DONE -> MERGED (later)

The CLI is the authority for transitions.
UIs (web/electron) are views over this state machine, not the source of truth.

---

## Implementation Principles

### Core-first (no FastAPI in the core)
- Domain logic must live in a reusable core module/package.
- Core must not import FastAPI, websockets, or HTTP request objects.
- FastAPI server (if used) must be a thin adapter over core.

### CLI-first (server optional)
- Golden Path commands must work without any running backend server.
- If a server exists, it may be started separately (`codeframe serve`) and must wrap core.

### Salvage safely
- Legacy code can be read and copied from.
- Core must not take dependencies on legacy UI-driven modules.
- Prefer copying useful functions into core and simplifying interfaces.

### Keep it runnable
- Every commit should keep `codeframe --help` working.
- The Golden Path commands should remain executable even if stubs at first.

---

## Acceptance Checklist (must pass)

**Status: ✅ Golden Path Complete (2025-01-14)**

- [x] `codeframe init` creates durable state for a repo
- [x] `codeframe prd add` stores PRD
- [x] `codeframe tasks generate` creates tasks in state machine
- [x] `codeframe work start <id>` runs an agent workflow and logs events
- [x] `codeframe blockers` + `codeframe blocker answer` works
- [x] `codeframe review` runs gates and records results
- [x] `codeframe patch export` or `codeframe commit create` produces an artifact
- [x] `codeframe checkpoint create` snapshots state
- [x] No UI is required at any point

All Golden Path requirements are met. Next phase: Batch execution (see `BATCH_EXECUTION_PLAN.md`).
