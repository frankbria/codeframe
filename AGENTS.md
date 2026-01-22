# CodeFRAME Development Guidelines (v2 Reset)

Last updated: 2026-01-14

This repo is in an **in-place v2 refactor** (“strangler rewrite”). The goal is to deliver a **headless, CLI-first Golden Path** and treat all UI/server layers as optional adapters.

If you are an agent working in this repo: **do not improvise architecture**. Follow the documents listed below.

---

## 🚦Primary Contract (MUST FOLLOW)

1) **Golden Path**: `docs/GOLDEN_PATH.md`  
   The only workflow we build until it works end-to-end.

2) **Refactor Plan**: `docs/REFACTOR_PLAN_FOR_AGENT.md`  
   Step-by-step refactor instructions.

3) **Command Tree + Module Mapping**: `docs/CLI_WIREFRAME.md`  
   The authoritative map from CLI commands → core modules/functions.

**Rule 0:** If a change does not directly support Golden Path, do not implement it.

---

## Current Reality (v1) vs Target Reality (v2)

### v1 Reality (legacy)
- FastAPI server + WebSockets + React/Next.js dashboard is currently the “center of gravity”.
- Many docs/specs/sprints describe this v1 workflow, UI, auth, and websocket behavior.

### v2 Target (what we’re building now)
- **Core-first**: domain logic lives in a reusable core module.
- **CLI-first**: Golden Path must work **without any running FastAPI server**.
- **Server/UI optional**: FastAPI and any UI are thin adapters over core.
- **Legacy quarantine**: UI and UI-driven server code is retained for reference only.

---

## Repository Structure (v2 additions)

This repo currently has:
- `codeframe/` (Python package)
- `web-ui/` (frontend)

During the refactor we will introduce (within `codeframe/`):
- `codeframe/core/` — headless domain + orchestration (NO FastAPI imports)
- `codeframe/cli/` — Typer CLI entry + subcommands (calls core directly)
- `codeframe/adapters/` — optional adapters (LLM providers, git, fs, persistence)
- `codeframe/server/` — optional FastAPI wrapper over core (thin adapter)

Legacy quarantine:
- `web-ui/` will be moved to `legacy/web-ui/` (or equivalent) when the refactor begins.
- Any UI-shaped orchestration/server logic will be moved under `legacy/`.
- Existing docs directory will be renamed `legacydocs/`

**Important:** We are not doing a big repo reshuffle. Keep moves incremental and purposeful.

---

## Architecture Rules (non-negotiable)

### 1) Core must be headless
`codeframe/core/**` must NOT import:
- FastAPI
- WebSocket frameworks
- HTTP request/response objects
- UI modules

Core is allowed to:
- read/write durable state (SQLite/filesystem)
- run orchestration/worker loops
- emit events to an append-only event log
- call adapters via interfaces (LLM, git, fs)

### 2) CLI must not require a server
Golden Path commands must work from the CLI with **no server running**.

FastAPI is optional and must be started explicitly (e.g., `codeframe serve`) and must wrap core.

### 3) Legacy can be read, not depended on
Legacy code is reference material.
- Copy/simplify logic into core when useful.
- Do NOT import legacy UI/server modules into core.
- Do NOT “fix the UI” during Golden Path work.

### 4) Keep commits runnable
At all times:
- `codeframe --help` works
- Golden Path command stubs can run
- Avoid breaking the repo with large renames/moves

---

## Documentation Navigation (what is authoritative)

### Authoritative (v2)
- `GOLDEN_PATH.md`
- `REFACTOR_PLAN_FOR_AGENT.md`
- `CLI_WIREFRAME.md`

### Legacy (v1 reference only)
These may describe the old server/UI-driven architecture and are NOT the current contract:
- `SPRINTS.md`, `sprints/`
- `specs/`
- `CODEFRAME_SPEC.md`
- v1 feature docs in `legacydocs/` such as context/session/auth/UI state management

You may consult legacy docs to salvage ideas, but do not build toward them unless they align with Golden Path.

---

## Commands (current + expected)

### Python (preferred)
Use `uv` for Python tasks where available:

```bash
uv run pytest
uv run ruff check .

## CLI (v2)
The v2 CLI is Typer-based and will expose Golden Path commands such as:
```bash

codeframe init <repo>
codeframe prd add <file.md>
codeframe tasks generate
codeframe work start <task-id>
codeframe blocker list
codeframe blocker answer <id> "..."
codeframe review
codeframe patch export
codeframe checkpoint create "name"
codeframe summary
```

Note: `codeframe serve` may exist, but Golden Path must not depend on it.

## Frontend (legacy)
Frontend commands remain for legacy UI reference only:
```bash
cd web-ui && npm test
cd web-ui && npm run build
```
Do not expand frontend scope during Golden Path work.

---

## What NOT to do (common agent failure modes)
- Don't add new HTTP endpoints to support the CLI.
- Don't require `codeframe serve` for CLI workflows.
- Don't implement UI concepts (tabs, panels, progress bars) inside core.
- Don't redesign auth, websockets, or UI state management.
- Don't add multi-providers/model switching features before Golden Path works.
- Don't "clean up the repo" as a goal. Only refactor to enable Golden Path.

---

## Practical Working Mode for Agents
When implementing anything, do this loop:
1. Read `docs/GOLDEN_PATH.md` and confirm the change is required.
2. Find the command in `docs/CLI_WIREFRAME.md`.
3. Implement core functionality in `codeframe/core/`.
4. Call it from Typer command in `codeframe/cli/`.
5. Emit events + persist state.
6. Keep it runnable. Commit.

If you are unsure which direction to take, default to:
- simpler state
- fewer dependencies
- smaller surface area
- core-first, CLI-first

---

## Legacy sections removed on purpose
This file previously contained extensive v1 details (auth, websocket, UI template, sprint history).
Those are still in git hsitory and legacy docs, but they are not the current contract.

The current contract is Golden Path + Refactor Plan + Command Tree mapping (CLI_WIREFRAME.md)
