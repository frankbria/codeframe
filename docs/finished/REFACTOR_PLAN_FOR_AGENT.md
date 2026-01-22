# CodeFRAME v2 — Refactor Plan (for agentic coding inside repo)

This document tells an agent (or human) exactly how to refactor CodeFRAME in-place
without “starting from scratch,” and without letting legacy UI or server concerns
drive the new architecture.

---

## Constraints (must respect)

1) **Same repo, no backward compatibility required.**
   Users/stars are not a constraint. Internal velocity is.

2) **Agent must be able to read legacy code.**
   Do not delete legacy immediately. Quarantine it.

3) **Golden Path is the only priority.**
   See `docs/GOLDEN_PATH.md`. If it’s not in the Golden Path, it does not get built.

4) **Core must not require FastAPI or a running server.**
   `codeframe ...` commands should work headlessly.

---

## High-level strategy: “Strangler rewrite in-place”

- Keep the repository.
- Create a new “spine” inside the existing structure:
  - new core module (headless)
  - new CLI command surface (Typer)
  - legacy UI/server becomes an adapter that can be reduced later

---

## Step 0 — Create a refactor branch

Create a branch for v2 work:
- `rewrite-cli-core`

Do not do this work on `main`.

---

## Step 1 — Quarantine the legacy UI (and UI-driven orchestration)

Goal: stop thinking of the web UI as “the product” while keeping it available for reference.

Actions:
1) Move the existing web UI into a clearly labeled legacy folder, preserving git history:
   - Example (adjust to repo reality):
     - `web-ui/` -> `legacy/web-ui/`
2) If there is server code primarily serving websocket/dashboard UI concerns,
   place it under:
   - `legacy/server-ui/` (or similar)

3) Add a `legacy/README.md`:
   - “Reference only. No new features. Do not depend on legacy from core.”

Important:
- Do not spend time fixing legacy UI bugs.
- Keep it runnable only if it is cheap.

---

## Step 2 — Establish the new core module (headless, reusable)

Goal: create a core module that contains state machine, orchestration, and persistence interfaces.

Add a new Python package under the existing `codeframe/` Python code directory.

Example structure (adjust to actual repo layout):
- `codeframe/core/`
  - `state/` (task state machine, events, models)
  - `runtime/` (orchestration, worker loop)
  - `persistence/` (SQLite/filesystem implementations)
  - `providers/` (interfaces only; no vendor-specific code here)

Hard rules:
- `codeframe/core/**` must not import:
  - FastAPI
  - websockets
  - HTTP request/response objects
- The core may expose:
  - `run_task(task_id, workspace_id, ...)`
  - `create_tasks_from_prd(...)`
  - `emit_event(...)`
  - `record_blocker(...)`

Persistence:
- Use a minimal durable store (SQLite or filesystem).
- If the repo already uses SQLite (e.g., `codeframe.db` exists), reuse the storage concept,
  but avoid coupling to API endpoints.

---

## Step 3 — Build the v2 CLI command tree (Typer)

Goal: implement the Golden Path commands using Typer.

Principle:
- Keep existing CLI commands only if they are already cleanly headless and match the Golden Path.
- Otherwise, create a new set of commands (recommended).

Implementation approach:
1) Create a new CLI entry module, e.g.:
   - `codeframe/cli/app.py` (Typer app)
2) Implement the Golden Path surface first:
   - `codeframe init`
   - `codeframe prd add`
   - `codeframe tasks generate`
   - `codeframe work start`
   - `codeframe status`
   - `codeframe blockers`
   - `codeframe blocker answer`
   - `codeframe review` (or `gates run`)
   - `codeframe patch export` OR `codeframe commit create`
   - `codeframe checkpoint create`
   - `codeframe summary`

3) Each CLI command should call core functions:
   - No direct calls to FastAPI routes.
   - No dependence on a running server.

Output:
- Use simple, readable console output.
- Optional: add Rich later. Not required for Golden Path.

---

## Step 4 — Decouple “run” from “serve”

Goal: make `codeframe run/work start` work without any running backend server.

Actions:
1) Ensure the orchestrator loop can be invoked as a plain function from core:
   - `codeframe.core.runtime.run(...)`

2) Ensure the CLI can run:
   - agent execution
   - event logging
   - blocker creation/answer/resume
   without starting FastAPI.

3) Keep `codeframe serve` as an optional adapter:
   - `codeframe serve` starts FastAPI
   - FastAPI wraps the same core functions
   - FastAPI should not own the domain logic

If current code expects websockets/events server-side:
- Move event emission into core (append-only event log).
- FastAPI can “tail” that log and broadcast if needed.
- CLI can also tail the same log.

---

## Step 5 — Salvage useful backend pieces (selectively)

Goal: reuse the 70% “good backend infrastructure” without inheriting UI-first design.

Rules:
- Prefer copying logic into core over importing legacy modules into core.
- If a module is UI-shaped (built around dashboard needs), quarantine it in legacy.
- Identify and keep pieces that are truly headless:
  - agent runner
  - task decomposition logic
  - checkpointing
  - persistence layer primitives
  - git/worktree utilities (as adapters)

Process:
1) Identify candidate modules in existing `codeframe/` Python package.
2) For each candidate, classify:
   - **KEEP**: move into `codeframe/core/` or `codeframe/adapters/`
   - **QUARANTINE**: move into `legacy/` (UI/server driven)
   - **DELETE**: only after Golden Path is stable

---

## Step 6 — Minimal tests for Golden Path

Goal: prevent regressions and keep agent work honest.

Add:
- One “smoke test” that:
  - creates a temp repo
  - runs `codeframe init`
  - stores a tiny PRD
  - generates tasks
  - starts work on one task (can be mocked initially)
  - confirms state transitions + events are recorded

Do not build a full test suite yet.

---

## Step 7 — Only after Golden Path works: rebuild UIs as adapters

When (and only when) Golden Path passes, you may:
- rebuild a web UI that consumes the core via FastAPI
- build an Electron UI
- add Kanban visualization

Rule:
- UI must never be the source of truth.
- UI is a view over the core state machine and event log.

---

## Repo-structure adaptation notes (important)

Current repo does not have `apps/` today. That is fine.

Use the existing top-level structure:
- keep `codeframe/` as the Python package root
- move `web-ui/` into `legacy/` (or similar)
- introduce new subpackages under `codeframe/`:
  - `codeframe/core/`
  - `codeframe/cli/`
  - `codeframe/adapters/` (optional)
  - `codeframe/server/` (FastAPI wrapper, optional)

Avoid large sweeping renames that break everything.
Prefer incremental moves and keeping imports stable.

---

## Definition of done for this refactor phase

- `docs/GOLDEN_PATH.md` exists and is followed
- `codeframe --help` works and shows Golden Path commands
- `codeframe init`, `prd add`, `tasks generate`, `work start`, `blockers`, `review`,
  `patch export/commit create`, `checkpoint create`, `summary` all work headlessly
- No dependency on running FastAPI for Golden Path
- Legacy UI is quarantined and not being actively “fixed”

If these are not true, do not add new features.
